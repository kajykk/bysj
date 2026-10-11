from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring import (
    CanaryRecord,
    CanaryStatus,
    DriftAlert,
    MonitoringEventType,
    MonitoringLog,
)
from app.services.canary_manager import canary_manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# P0-漂移：窗口内最小样本量（可达性阈值）
#
# 旧判据 max_drift_alerts_per_hour 默认 10，但唯一告警生产者
# drift_monitoring_service 按 (feature_name, drift_type, model_version, 未解决) 去重，
# 而 MODALITY_COLUMNS 只有 4 个模态 → 1 小时窗口内同版本告警最多 4 条 < 10，
# 漂移维度自动回滚永远不可达（fail-open）。
#
# 新定义：有效阈值 = min(配置的 max_drift_alerts_per_hour, DRIFT_MIN_ALERTS_IN_WINDOW)，
# DRIFT_MIN_ALERTS_IN_WINDOW 默认 2，可用 thresholds["min_drift_alerts_in_window"] 覆盖。
# 可达性论证：去重键加入 model_version 后，一次漂移检测（每小时 1 次）对某个金丝雀版本
# 最多产生 4 条（每个模态 1 条）；因此「窗口内 > 2 条」等价于「4 个模态中至少 3 个同时漂移」，
# 该事件在真实分布突变时可自然产生，不会像旧阈值一样成为不可达分支。
DRIFT_MIN_ALERTS_IN_WINDOW = 2

# ---------------------------------------------------------------------------
# P0-兜底：跨进程锁 + 心跳（beat 与进程内 fallback monitor 共用）
#
# 复用仓内既有设施：app.core.cache.get_redis_client（共享 Redis 连接池）
# 与 app.monitoring.dedup_lock 的 SET NX EX 锁语义。
# 心跳 key 带 TTL，进程被 kill -9 后 key 自动过期 → 下一次读取判定为「超时/缺失」→ 兜底接管，
# 因此进程重启后心跳能被正确判定为超时，而不需要任何进程内状态。
CANARY_CHECK_LOCK_KEY = "canary:rollback:check:lock"
CANARY_CHECK_HEARTBEAT_KEY = "canary:rollback:check:heartbeat"
# 锁 TTL：> 单次检查耗时上限，防止持锁进程崩溃后长时间阻塞；心跳 TTL 见 canary_fallback_monitor。
CANARY_CHECK_LOCK_TTL_SECONDS = 120


async def _redis_client_or_none() -> Any | None:
    """获取共享 Redis 客户端；不可用时返回 None（调用方必须自行记录/计数）。"""
    try:
        from app.core.cache import get_redis_client

        return await get_redis_client()
    except Exception as exc:
        logger.error("[canary_rollback] 获取 redis 客户端失败: %s", exc, exc_info=True)
        return None


def _bump_lock_counter(outcome: str) -> None:
    """锁/心跳相关可观测计数（Redis 不可用等失败路径不允许静默）。"""
    try:
        from app.core.metrics import canary_rollback_check_lock_total

        canary_rollback_check_lock_total.labels(outcome=outcome).inc()
    except Exception:  # pragma: no cover - 指标模块异常不得影响主流程
        logger.debug("canary_rollback 锁计数更新失败", exc_info=True)


async def try_acquire_check_lock(ttl_seconds: int = CANARY_CHECK_LOCK_TTL_SECONDS) -> bool:
    """尝试获取 check_all_canaries 的跨进程互斥锁。

    Returns:
        True=获得锁，应执行检查；False=其他进程正在执行（跳过本次）；
        Redis 不可用时返回 True（降级执行），并记录 unavailable 计数 + warning 日志。
    """
    client = await _redis_client_or_none()
    if client is None:
        _bump_lock_counter("unavailable")
        logger.warning(
            "[canary_rollback] Redis 不可用, 无法获取跨进程锁 (降级执行检查, beat/fallback 可能重复触发)"
        )
        return True
    try:
        acquired = await client.set(
            CANARY_CHECK_LOCK_KEY, str(time.time()), nx=True, ex=ttl_seconds
        )
    except Exception as exc:
        _bump_lock_counter("unavailable")
        logger.error(
            "[canary_rollback] 获取跨进程锁异常 (降级执行检查): %s", exc, exc_info=True
        )
        return True
    if acquired:
        _bump_lock_counter("acquired")
    else:
        _bump_lock_counter("skipped")
        logger.info("[canary_rollback] 另一进程正在执行 check_all_canaries, 本次跳过")
    return bool(acquired)


async def publish_check_heartbeat(source: str, checked: int, ttl_seconds: int = 120) -> bool:
    """成功执行 check_all_canaries 后写入心跳（跨进程可见，带 TTL）。

    失败只记录日志 + 计数，不抛出：心跳写失败不应让回滚结果丢失。
    """
    client = await _redis_client_or_none()
    if client is None:
        _bump_lock_counter("unavailable")
        logger.warning("[canary_rollback] Redis 不可用, 心跳未写入 (source=%s)", source)
        return False
    payload = {
        "source": source,
        "checked": checked,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    import json

    try:
        await client.set(CANARY_CHECK_HEARTBEAT_KEY, json.dumps(payload), ex=ttl_seconds)
    except Exception as exc:
        _bump_lock_counter("unavailable")
        logger.error(
            "[canary_rollback] 写入心跳失败 (source=%s): %s", source, exc, exc_info=True
        )
        return False
    logger.debug(
        "[canary_rollback] 心跳已更新 source=%s checked=%d ttl=%ds",
        source,
        checked,
        ttl_seconds,
    )
    return True


async def get_check_heartbeat_age() -> float | None:
    """读取心跳年龄（秒）。

    Returns:
        None=无心跳或 Redis 不可读（调用方必须按「未知」处理，不得静默跳过检查）。
    """
    import json

    client = await _redis_client_or_none()
    if client is None:
        _bump_lock_counter("unavailable")
        return None
    try:
        raw = await client.get(CANARY_CHECK_HEARTBEAT_KEY)
    except Exception as exc:
        _bump_lock_counter("unavailable")
        logger.error("[canary_rollback] 读取心跳失败: %s", exc, exc_info=True)
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        at = datetime.fromisoformat(payload["at"])
    except (TypeError, ValueError, KeyError) as exc:
        # 心跳内容损坏: 视为无心跳（兜底必须接管）, 但显式记录, 不静默
        _bump_lock_counter("unavailable")
        logger.error("[canary_rollback] 心跳内容解析失败, 视为无心跳: %s", exc)
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - at).total_seconds()
    try:
        from app.core.metrics import canary_rollback_heartbeat_age_seconds

        canary_rollback_heartbeat_age_seconds.set(age)
    except Exception:  # pragma: no cover
        logger.debug("心跳年龄 gauge 更新失败", exc_info=True)
    return age


@dataclass
class RollbackCheckResult:
    """Result of auto-rollback check."""

    should_rollback: bool
    reason: str
    metrics: dict[str, Any]
    canary_id: int | None = None


class AutoRollbackService:
    """Monitors canary deployments and triggers auto-rollback when thresholds are exceeded.

    Thresholds:
    - max_fallback_rate: 5% (default)
    - max_drift_alerts_per_hour: 10 (default), 实际生效值会被 min_drift_alerts_in_window
      (默认 2) 夹紧, 以保证在 4 模态下该判据可达
    - max_avg_latency_ms: 500 (default)
    """

    def __init__(self) -> None:
        pass

    async def check_canary_health(
        self,
        db_session: AsyncSession,
        canary_id: int,
    ) -> RollbackCheckResult:
        """Check canary health metrics against thresholds.

        Args:
            db_session: Database session.
            canary_id: Canary record ID.

        Returns:
            RollbackCheckResult with decision and metrics.
        """
        result = await db_session.execute(
            select(CanaryRecord).where(CanaryRecord.id == canary_id)
        )
        canary = result.scalar_one_or_none()

        if not canary:
            return RollbackCheckResult(
                should_rollback=False,
                reason="canary_not_found",
                metrics={},
                canary_id=canary_id,
            )

        if canary.status != CanaryStatus.RUNNING:
            return RollbackCheckResult(
                should_rollback=False,
                reason=f"canary_status_{canary.status}",
                metrics={},
                canary_id=canary_id,
            )

        thresholds = canary.auto_rollback_thresholds or {}
        metrics: dict[str, Any] = {}

        # Calculate fallback rate (last hour)
        # M-14 修复：MonitoringLog.created_at 为 naive DateTime 列，比较时需用 naive UTC
        one_hour_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            hours=1
        )
        fallback_stmt = select(func.count()).where(
            MonitoringLog.event_type == MonitoringEventType.FALLBACK,
            MonitoringLog.created_at >= one_hour_ago,
            MonitoringLog.model_version == canary.version,
        )
        fallback_result = await db_session.execute(fallback_stmt)
        fallback_count = fallback_result.scalar() or 0

        inference_stmt = select(func.count()).where(
            MonitoringLog.event_type == MonitoringEventType.INFERENCE,
            MonitoringLog.created_at >= one_hour_ago,
            MonitoringLog.model_version == canary.version,
        )
        inference_result = await db_session.execute(inference_stmt)
        inference_count = inference_result.scalar() or 0

        total = inference_count + fallback_count
        fallback_rate = fallback_count / max(1, total)
        metrics["fallback_count"] = fallback_count
        metrics["inference_count"] = inference_count
        metrics["fallback_rate"] = fallback_rate

        max_fallback_rate = thresholds.get("max_fallback_rate", 0.05)
        if fallback_rate > max_fallback_rate:
            return RollbackCheckResult(
                should_rollback=True,
                reason=f"fallback_rate {fallback_rate:.2%} exceeds threshold {max_fallback_rate:.2%}",
                metrics=metrics,
                canary_id=canary_id,
            )

        # P0-漂移 fail-open 修复：判据由「窗口内未解决告警数」改为「窗口内新建告警数」
        # （created_at 落在窗口内即计数），并与实际可产生的告警量级（≤ 模态数）相称。
        # 旧判据 resolved_at IS NULL + 阈值 10 在 4 模态下不可达（永远 < 10）。
        # model_version 过滤保留：PSI > 2.0 的疑似版本失配告警按既有设计 model_version=None，
        # 因此天然不匹配任何 canary 版本，不参与自动回滚（该语义不变）。
        drift_stmt = select(func.count()).where(
            DriftAlert.created_at >= one_hour_ago,
            DriftAlert.model_version == canary.version,
        )
        drift_result = await db_session.execute(drift_stmt)
        drift_count = drift_result.scalar() or 0
        metrics["drift_alerts_per_hour"] = drift_count

        max_drift = int(thresholds.get("max_drift_alerts_per_hour", 10))
        min_samples = int(thresholds.get("min_drift_alerts_in_window", DRIFT_MIN_ALERTS_IN_WINDOW))
        # 有效阈值 = min(配置上限, 最小可达样本量); 后者保证该判据在 4 模态下真实可达。
        effective_max_drift = max(1, min(max_drift, min_samples))
        metrics["max_drift_alerts_per_hour"] = effective_max_drift
        if drift_count > effective_max_drift:
            logger.warning(
                "Canary %d 漂移告警超阈值: %d > %d (窗口=1h, model_version=%s)",
                canary_id,
                drift_count,
                effective_max_drift,
                canary.version,
            )
            return RollbackCheckResult(
                should_rollback=True,
                reason=(
                    f"drift_alerts_per_hour {drift_count} exceeds threshold "
                    f"{effective_max_drift}"
                ),
                metrics=metrics,
                canary_id=canary_id,
            )

        # Calculate average latency (last hour)
        latency_stmt = select(func.avg(MonitoringLog.latency_ms)).where(
            MonitoringLog.latency_ms.isnot(None),
            MonitoringLog.created_at >= one_hour_ago,
            MonitoringLog.model_version == canary.version,
        )
        latency_result = await db_session.execute(latency_stmt)
        avg_latency = latency_result.scalar() or 0.0
        metrics["avg_latency_ms"] = round(avg_latency, 2)

        max_latency = thresholds.get("max_avg_latency_ms", 500.0)
        if avg_latency > max_latency:
            return RollbackCheckResult(
                should_rollback=True,
                reason=f"avg_latency_ms {avg_latency:.0f} exceeds threshold {max_latency}",
                metrics=metrics,
                canary_id=canary_id,
            )

        return RollbackCheckResult(
            should_rollback=False,
            reason="within_thresholds",
            metrics=metrics,
            canary_id=canary_id,
        )

    async def execute_rollback(
        self,
        db_session: AsyncSession,
        canary_id: int,
        reason: str,
        triggered_by: str = "auto",
    ) -> bool:
        """Execute rollback for a canary deployment.

        Args:
            db_session: Database session.
            canary_id: Canary record ID.
            reason: Rollback reason.
            triggered_by: Who triggered the rollback ("auto" or user_id).

        Returns:
            True if rollback was successful.

        C-Svc-1 修复：原实现在 begin_nested() savepoint 内调用 commit()，
        会提交最外层事务而非仅释放 savepoint，破坏 check_all_canaries 中
        每个 canary 的事务隔离；同时失败时调用 rollback() 也会回滚整个
        外层事务，影响其他 canary 的处理。改为：
        - 使用 flush() 仅将更改刷入 DB，事务提交交给 savepoint 释放或外层调用方
        - 不在此处捕获异常，让异常向上传播以触发 savepoint 自动回滚
        """
        await canary_manager.rollback_canary(db_session, canary_id, reason)

        # Record rollback event
        log = MonitoringLog(
            event_type=MonitoringEventType.CANARY_SWITCH,
            response_summary={
                "canary_id": canary_id,
                "action": "rollback",
                "reason": reason,
                "triggered_by": triggered_by,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        db_session.add(log)
        await db_session.flush()

        logger.warning("Canary %d auto-rollback executed: %s", canary_id, reason)
        return True

    async def check_all_canaries(
        self, db_session: AsyncSession, *, source: str = "unknown"
    ) -> list[RollbackCheckResult]:
        """Check all running canaries and return results.

        P0 修复：入口加跨进程互斥锁 + 成功心跳。Celery beat 与进程内 fallback monitor
        走的是同一个方法，之前 half_open 下两者可同时执行，第二次回滚抛 ValueError 仅被记录。
        锁使用仓内既有的 Redis SET NX EX 设施（见 try_acquire_check_lock）。

        Args:
            db_session: Database session.
            source: 调用来源标识（celery / fallback），写入心跳便于排障。

        Returns:
            List of RollbackCheckResult for each running canary.
        """
        if not await try_acquire_check_lock():
            # 另一进程正在执行：这不是失败，但必须可观测，不能静默 return。
            logger.info(
                "check_all_canaries skipped (source=%s): 跨进程锁被占用",
                source,
            )
            return []

        result = await db_session.execute(
            select(CanaryRecord).where(CanaryRecord.status == CanaryStatus.RUNNING)
        )
        canaries = result.scalars().all()

        results: list[RollbackCheckResult] = []
        for canary in canaries:
            # M-22 修复：每个 canary 的检查和回滚使用 savepoint 隔离
            # 避免单个 canary 失败回滚整个事务，影响后续 canary 的查询
            try:
                async with db_session.begin_nested():
                    check_result = await self.check_canary_health(db_session, canary.id)

                if check_result.should_rollback:
                    # H-AUDIT-01: execute_rollback 仅 flush 不 commit (C-Svc-1),
                    # 事务提交由调用方 (scheduler / fallback monitor) 负责.
                    # 用独立 savepoint 隔离单只金丝雀回滚失败.
                    try:
                        async with db_session.begin_nested():
                            await self.execute_rollback(
                                db_session,
                                canary.id,
                                check_result.reason,
                                triggered_by="auto",
                            )
                    except Exception:
                        logger.exception(
                            "Rollback savepoint failed for canary %d", canary.id
                        )
            except Exception:
                logger.exception("Check/rollback failed for canary %d", canary.id)
                check_result = RollbackCheckResult(
                    should_rollback=False,
                    reason="check_error",
                    metrics={},
                    canary_id=canary.id,
                )
            results.append(check_result)

        # 心跳在「本轮检查跑完」时发布，使兜底 monitor 能据此判断 beat 是否存活；
        # 进程崩溃不会写心跳 → key 到期 → 兜底接管。
        await publish_check_heartbeat(source=source, checked=len(results))
        return results


# Global service instance
auto_rollback_service = AutoRollbackService()
