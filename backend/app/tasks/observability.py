"""v1.36: 可观测性相关 Celery 任务.

任务:
- flush_lock_stats_task: 每分钟将 dedup_lock 内存统计 flush 到 OperationLog
  用于监控多实例去重锁的健康度 (acquired/skipped/fallback/errors).
"""

from __future__ import annotations

import logging

from app.core.celery_app import celery_app
from app.core.celery_async import get_celery_loop as _get_loop
from app.core.celery_async import run_async as _run_async
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


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
            "[observability] flush_lock_stats failed: %s",
            exc,
            exc_info=True,
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
            # M-ML-4 修复：flush_lock_stats 返回 False 时不应 commit（避免写入空/无效统计），
            # 改为 rollback 丢弃本次未生效的变更
            if success:
                await db.commit()
            else:
                await db.rollback()
                logger.warning(
                    "[observability] flush_lock_stats returned False, transaction rolled back"
                )
            return success
        except Exception as exc:
            await db.rollback()
            logger.error(
                "[observability] flush_lock_stats transaction failed: %s",
                exc,
            )
            return False
