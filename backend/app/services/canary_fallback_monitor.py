"""STAB-P1-009: 金丝雀自动回滚备用监控 (Celery 不可用时的 fallback).

原问题:
    canary_auto_rollback_check 由 Celery beat 每 30s 触发, 当 Celery broker/worker
    不可用时 (circuit OPEN), 自动回滚检查停止, 金丝雀异常无法被自动回滚,
    可能导致故障扩大.

修复方案:
    在 FastAPI 进程内启动 asyncio.create_task 后台任务, 周期性 (默认 30s)
    检查 celery_breaker 状态:
    - state == "closed": Celery 可用, 跳过本次执行 (让 Celery beat 处理, 避免双重执行)
    - state != "closed" (open/half_open): Celery 不可用, 调用
      auto_rollback_service.check_all_canaries() 执行 fallback rollback check

设计原则:
    - 不与 Celery beat 双重执行: 通过 celery_breaker 状态判断, 仅在 Celery 不可用时执行
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

# 全局任务句柄 (单例, 由 start/stop 管理)
_canary_fallback_task: asyncio.Task | None = None


def _is_test_environment() -> bool:
    """检测是否在测试环境中运行 (避免后台任务干扰测试)."""
    return os.environ.get("PYTEST_CURRENT_TEST") is not None


async def _canary_fallback_loop() -> None:
    """金丝雀回滚备用监控循环.

    每 CANARY_FALLBACK_INTERVAL_SECONDS 秒检查 celery_breaker 状态,
    当 Celery 不可用时执行 auto_rollback_service.check_all_canaries().
    """
    from app.services.auto_rollback_service import auto_rollback_service

    while True:
        try:
            # 检查 celery_breaker 状态
            from app.core.celery_breaker import celery_breaker

            snapshot = celery_breaker.get_state_snapshot()
            celery_state = snapshot.get("state", "closed")

            if celery_state == "closed":
                # Celery 可用, 跳过 fallback (让 Celery beat 处理)
                logger.debug(
                    "canary_fallback: celery_breaker=closed, skip (celery beat handles)"
                )
            else:
                # Celery 不可用 (open/half_open), 执行 fallback rollback check
                logger.warning(
                    "canary_fallback: celery_breaker=%s, executing fallback rollback check",
                    celery_state,
                )
                try:
                    async with AsyncSessionLocal() as db_session:
                        results = await auto_rollback_service.check_all_canaries(
                            db_session
                        )
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
