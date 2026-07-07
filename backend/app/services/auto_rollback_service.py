from __future__ import annotations

import logging
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
    - max_drift_alerts_per_hour: 10 (default)
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

        # Calculate drift alerts per hour
        drift_stmt = select(func.count()).where(
            DriftAlert.created_at >= one_hour_ago,
            DriftAlert.model_version == canary.version,
            DriftAlert.resolved_at.is_(None),
        )
        drift_result = await db_session.execute(drift_stmt)
        drift_count = drift_result.scalar() or 0
        metrics["drift_alerts_per_hour"] = drift_count

        max_drift = thresholds.get("max_drift_alerts_per_hour", 10)
        if drift_count > max_drift:
            return RollbackCheckResult(
                should_rollback=True,
                reason=f"drift_alerts_per_hour {drift_count} exceeds threshold {max_drift}",
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
        self, db_session: AsyncSession
    ) -> list[RollbackCheckResult]:
        """Check all running canaries and return results.

        Args:
            db_session: Database session.

        Returns:
            List of RollbackCheckResult for each running canary.
        """
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
                    # execute_rollback 内部会 commit，使用独立 savepoint 隔离
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

        return results


# Global service instance
auto_rollback_service = AutoRollbackService()
