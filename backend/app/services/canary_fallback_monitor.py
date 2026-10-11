"""STAB-P1-009: 金丝雀自动回滚备用监控 (Celery 不可用时的 fallback).

原问题:
    canary_auto_rollback_check 由 Celery beat 每 30s 触发, 当 Celery broker/worker
    不可用时 (circuit OPEN), 自动回滚检查停止, 金丝雀异常无法被自动回滚,
    可能导致故障扩大.

P0 修复 (静默失效窗口):
    原实现只在 celery_breaker.get_state_snapshot()['state'] != 'closed' 时才接管,
    而 breaker 只反映 broker 发布/探测失败、默认恒为 closed。worker 挂掉 / beat 停摆时
    → 兜底跳过 + beat 不执行 → 超阈值金丝雀永不自动回滚, 且除 debug 日志外无任何信号。
    现改为**心跳/租约接管**: 以「距上次成功执行 check_all_canaries 的时间」为准,
    超过 N 倍轮询间隔 (默认 3 倍) 即接管, 不再依赖 breaker 状态;
    breaker 仅作为附加信号保留 (非 closed 时直接接管, 覆盖 broker 故障场景)。
    心跳写入与跨进程互斥锁统一放在 auto_rollback_service.check_all_canaries,
    beat 与兜底共用同一把锁, 因此 half_open 下不会再并发执行两次回滚。
    心跳保存在 Redis (带 TTL), 进程被强杀后 key 到期即被判定为「超时」,
    进程重启同样能正确接管。

设计原则:
    - 心跳缺失/超时 → 立即接管 (fail-safe), 不静默跳过
    - 锁不可获取 / Redis 不可用: 记录 error/warning + 计数, 不静默 return
    - 不阻塞 lifespan: 后台任务, 失败仅记录日志
    - 测试环境跳过启动 (避免后台任务干扰测试)
    - 应用关闭时正确取消任务
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

from app.core.database import AsyncSessionLocal

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

# 默认 30s 检查间隔 (与 Celery beat 配置一致)
CANARY_FALLBACK_INTERVAL_SECONDS = 30.0

# 接管判定: 距上次成功执行 check_all_canaries 超过 N 倍轮询间隔即认为 beat 已停摆。
# N=3 → 90s 容忍 (2 次连续 beat 缺失后接管), 且心跳 key TTL 同样按此设置。
CANARY_FALLBACK_TAKEOVER_MULTIPLIER = 3
CANARY_FALLBACK_TAKEOVER_SECONDS = (
    CANARY_FALLBACK_INTERVAL_SECONDS * CANARY_FALLBACK_TAKEOVER_MULTIPLIER
)

# 全局任务句柄 (单例, 由 start/stop 管理)
_canary_fallback_task: asyncio.Task | None = None


def _is_test_environment() -> bool:
    """检测是否在测试环境中运行 (避免后台任务干扰测试)."""
    return os.environ.get("PYTEST_CURRENT_TEST") is not None


def _bump_takeover_counter(reason: str) -> None:
    """接管判定计数 (静默失效必须有可观测计数)。"""
    try:
        from app.core.metrics import canary_rollback_takeover_total

        canary_rollback_takeover_total.labels(reason=reason).inc()
    except Exception:  # pragma: no cover - 指标异常不得影响主流程
        logger.debug("canary_rollback_takeover_total 更新失败", exc_info=True)


async def _canary_fallback_loop() -> None:
    """金丝雀回滚备用监控循环.

    每 CANARY_FALLBACK_INTERVAL_SECONDS 秒按心跳/租约判断是否接管,
    需要接管时执行 auto_rollback_service.check_all_canaries().
    """
    from app.services.auto_rollback_service import auto_rollback_service

    while True:
        try:
            # breaker 只反映 broker 发布/探测失败, 不能作为接管依据 (P0 修复),
            # 仅在非 closed 时作为附加信号直接接管; 主判据是下方心跳.
            from app.core.celery_breaker import celery_breaker

            try:
                snapshot = celery_breaker.get_state_snapshot()
                celery_state = snapshot.get("state", "closed")
            except Exception as exc:
                # 原实现直接跳过检查 (worker 挂掉时的静默失效窗口), 现记录后继续走心跳判定
                logger.error(
                    "canary_fallback: celery_breaker snapshot 失败, 改用心跳判定: %s",
                    exc,
                    exc_info=True,
                )
                celery_state = "unknown"

            if celery_state not in ("closed", "unknown"):
                _bump_takeover_counter(f"celery_{celery_state}")
                logger.warning(
                    "canary_fallback: celery_breaker=%s, executing fallback rollback check",
                    celery_state,
                )
                take_over, reason = True, f"celery_{celery_state}"
            else:
                # 心跳判定: 距上次成功执行 check_all_canaries 超过 N×轮询间隔即接管
                from app.services.auto_rollback_service import get_check_heartbeat_age

                age = await get_check_heartbeat_age()
                if age is None:
                    # 无心跳 / Redis 不可读 / key 已过期 (进程重启或 beat 停摆)
                    _bump_takeover_counter("heartbeat_missing")
                    logger.warning(
                        "canary_fallback: 无心跳或心跳不可读, 判定 beat 未在执行, 接管 rollback check"
                    )
                    take_over, reason = True, "heartbeat_missing"
                elif age > CANARY_FALLBACK_TAKEOVER_SECONDS:
                    _bump_takeover_counter("heartbeat_stale")
                    logger.warning(
                        "canary_fallback: 心跳已超时 (age=%.1fs > %.1fs), 接管 rollback check",
                        age,
                        CANARY_FALLBACK_TAKEOVER_SECONDS,
                    )
                    take_over, reason = True, "heartbeat_stale"
                else:
                    _bump_takeover_counter("heartbeat_fresh")
                    logger.debug(
                        "canary_fallback: celery_breaker=closed, heartbeat fresh "
                        "(age=%.1fs <= %.1fs), skip (celery beat handles)",
                        age,
                        CANARY_FALLBACK_TAKEOVER_SECONDS,
                    )
                    take_over, reason = False, "heartbeat_fresh"

            if take_over:
                try:
                    async with AsyncSessionLocal() as db_session:
                        results = await auto_rollback_service.check_all_canaries(
                            db_session, source=f"fallback:{reason}"
                        )
                        # H-AUDIT-01 修复: execute_rollback 仅 flush (C-Svc-1),
                        # 必须 commit 否则回滚状态随 session 关闭丢失
                        await db_session.commit()
                    rollback_count = sum(1 for r in results if r.should_rollback)
                    if rollback_count > 0:
                        logger.warning(
                            "canary_fallback: %d canary(ies) triggered rollback (total checked=%d)",
                            rollback_count,
                            len(results),
                        )
                    else:
                        logger.debug(
                            "canary_fallback: no rollback needed (total checked=%d)",
                            len(results),
                        )
                except Exception as exc:
                    logger.error(
                        "canary_fallback: rollback check failed: %s",
                        exc,
                        exc_info=True,
                    )
        except asyncio.CancelledError:
            # 应用关闭, 退出循环
            logger.info("canary_fallback: loop cancelled, exiting")
            raise
        except Exception as exc:
            # 未预期异常: 记录但不退出循环 (保持监控持续运行)
            logger.error(
                "canary_fallback: unexpected error in loop: %s",
                exc,
                exc_info=True,
            )

        await asyncio.sleep(CANARY_FALLBACK_INTERVAL_SECONDS)


async def start_canary_fallback_monitor(app: "FastAPI") -> None:
    """启动金丝雀回滚备用监控后台任务.

    在 lifespan 启动阶段调用. 当 Celery 不可用时, 后台任务接管
    canary_auto_rollback_check 的工作, 确保金丝雀异常仍能被自动回滚.

    任务句柄存储在 app.state.canary_fallback_task, 在应用关闭时由
    stop_canary_fallback_monitor() 取消.

    测试环境 (PYTEST_CURRENT_TEST 已设置) 跳过启动, 避免后台任务干扰测试.
    """
    global _canary_fallback_task
    if _is_test_environment():
        logger.info("canary_fallback: skipped in test environment")
        return
    if _canary_fallback_task is not None and not _canary_fallback_task.done():
        logger.warning("canary_fallback: already running, skip duplicate start")
        return
    _canary_fallback_task = asyncio.create_task(_canary_fallback_loop())
    app.state.canary_fallback_task = _canary_fallback_task
    logger.info(
        "canary_fallback: monitor started (interval=%.1fs)",
        CANARY_FALLBACK_INTERVAL_SECONDS,
    )


async def stop_canary_fallback_monitor() -> None:
    """停止金丝雀回滚备用监控后台任务.

    在 lifespan 关闭阶段调用. 取消后台任务并等待其退出.
    """
    global _canary_fallback_task
    if _canary_fallback_task is None:
        return
    _canary_fallback_task.cancel()
    try:
        await _canary_fallback_task
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.warning("canary_fallback: error during stop: %s", exc, exc_info=True)
    _canary_fallback_task = None
    logger.info("canary_fallback: monitor stopped")


def is_canary_fallback_running() -> bool:
    """检查备用监控任务是否正在运行 (供测试或 /health 使用)."""
    return _canary_fallback_task is not None and not _canary_fallback_task.done()
