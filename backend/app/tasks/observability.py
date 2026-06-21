"""v1.36: 可观测性相关 Celery 任务.

任务:
- flush_lock_stats_task: 每分钟将 dedup_lock 内存统计 flush 到 OperationLog
  用于监控多实例去重锁的健康度 (acquired/skipped/fallback/errors).
"""
from __future__ import annotations

import asyncio
import logging

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

_event_loop: asyncio.AbstractEventLoop | None = None


def _get_loop() -> asyncio.AbstractEventLoop:
    """v1.36: 复用事件循环 (celery worker 进程级)."""
    global _event_loop
    if _event_loop is None or _event_loop.is_closed():
        _event_loop = asyncio.new_event_loop()
    return _event_loop


def _run_async(coro):
    loop = _get_loop()
    return loop.run_until_complete(coro)


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    time_limit=60,
    soft_time_limit=50,
    name="app.tasks.observability.flush_lock_stats_task",
)
def flush_lock_stats_task(self):
    """v1.36: 每分钟 flush dedup_lock 统计到 OperationLog.

    失败不会重置内存计数 (下次重试), 由 dedup_lock.flush_lock_stats 保证.
    """
    logger.info("[observability] flush_lock_stats_task started")
    try:
        success = _run_async(_flush_lock_stats_impl())
        logger.info(
            "[observability] flush_lock_stats_task completed: %s",
            "ok" if success else "failed",
        )
        return {"success": success}
    except Exception as exc:
        logger.error(
            "[observability] flush_lock_stats failed: %s", exc, exc_info=True,
        )
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("[observability] flush_lock_stats max retries exceeded")
            return {"error": str(exc)}


async def _flush_lock_stats_impl() -> bool:
    """v1.36: flush 锁统计到 OperationLog."""
    from app.monitoring.dedup_lock import flush_lock_stats

    async with AsyncSessionLocal() as db:
        try:
            success = await flush_lock_stats(db)
            await db.commit()
            return success
        except Exception as exc:
            await db.rollback()
            logger.error(
                "[observability] flush_lock_stats transaction failed: %s", exc,
            )
            return False
