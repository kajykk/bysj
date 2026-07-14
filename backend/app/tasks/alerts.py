"""v1.34: 告警相关 Celery 任务.

任务:
- escalate_pending_alerts_task: 升级未确认告警 (复用 v1.33 escalation 逻辑)
- archive_old_alerts_task: 归档 90 天前告警到 AlertArchive
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, desc, select

from app.core.celery_app import celery_app
from app.core.celery_async import run_async as _run_async
from app.core.database import AsyncSessionLocal
from app.models.admin import OperationLog

logger = logging.getLogger(__name__)


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ===== 升级任务 =====


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    time_limit=120,
    soft_time_limit=90,
    name="app.tasks.alerts.escalate_pending_alerts_task",
)
def escalate_pending_alerts_task(self):
    """v1.34: 每分钟扫描未确认告警, 执行升级.

    复用 v1.33 escalation 模块的逻辑.
    """
    logger.info("[alerts] escalate_pending_alerts_task started")
    try:
        executed = _run_async(_escalate_impl())
        logger.info(
            "[alerts] escalate_pending_alerts_task completed: %d alerts escalated",
            len(executed) if executed else 0,
        )
        return {"escalated": len(executed) if executed else 0}
    except Exception as exc:
        logger.error("[alerts] escalate failed: %s", exc, exc_info=True)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("[alerts] escalate max retries exceeded")
            return {"error": str(exc)}


async def _escalate_impl() -> list[dict]:
    """v1.34: 升级实现 (复用 v1.33 escalation 模块)."""
    from app.monitoring.escalation import apply_escalation, run_escalation_check

    async with AsyncSessionLocal() as db:
        decisions = await run_escalation_check(db)
        executed = await apply_escalation(db, decisions)
        return [
            {
                "alert_id": d.alert_id,
                "new_severity": d.new_severity,
                "reason": d.reason,
            }
            for d in executed
        ]


# ===== 归档任务 =====


ARCHIVE_RETENTION_DAYS = 90


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    time_limit=600,
    soft_time_limit=540,
    name="app.tasks.alerts.archive_old_alerts_task",
)
def archive_old_alerts_task(self):
    """v1.34: 每日归档 90 天前告警.

    将 90 天前的 alert_fired/alert_resolved 记录移到 AlertArchive.
    AlertArchive 是只读归档表, 不参与告警通知.
    """
    logger.info("[alerts] archive_old_alerts_task started")
    try:
        count = _run_async(_archive_impl())
        logger.info(
            "[alerts] archive_old_alerts_task completed: %d alerts archived", count
        )
        return {"archived": count}
    except Exception as exc:
        logger.error("[alerts] archive failed: %s", exc, exc_info=True)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("[alerts] archive max retries exceeded")
            return {"error": str(exc)}


async def _archive_impl() -> int:
    """v1.35: 实际归档 90 天前 alert_fired/alert_resolved 到 AlertArchive.

    流程:
    1. 查询 90 天前 alert_fired/alert_resolved 记录 (limit 1000)
    2. 插入到 AlertArchive (保留 original_id 便于审计)
    3. 删除 OperationLog 原记录
    4. 事务原子性: 失败回滚

    P1-D-7 修复: 幂等性保护 - 插入前检查 original_id 是否已存在,
    避免重试时产生重复 AlertArchive 记录.

    Returns:
        归档条数
    """
    from app.models.admin import AlertArchive

    threshold = _utcnow_naive() - timedelta(days=ARCHIVE_RETENTION_DAYS)
    async with AsyncSessionLocal() as db:
        try:
            # 1. 查询候选
            stmt = (
                select(OperationLog)
                .where(
                    and_(
                        OperationLog.action_type.in_(["alert_fired", "alert_resolved"]),
                        OperationLog.created_at < threshold,
                    )
                )
                .order_by(desc(OperationLog.created_at))
                .limit(1000)
            )
            rows = (await db.execute(stmt)).scalars().all()

            if not rows:
                return 0

            # P1-D-7: 幂等性检查 - 查询已归档的 original_id 集合
            existing_ids_stmt = select(AlertArchive.original_id).where(
                AlertArchive.original_id.in_([r.id for r in rows])
            )
            existing_ids = set((await db.execute(existing_ids_stmt)).scalars().all())

            archived_count = 0
            skipped_count = 0
            for row in rows:
                # P1-D-7: 跳过已归档的记录 (重试场景)
                if row.id in existing_ids:
                    skipped_count += 1
                    # 仍需删除原记录 (可能上次插入成功但删除失败)
                    await db.delete(row)
                    continue

                # 解析 detail
                try:
                    detail = json.loads(row.detail or "{}")
                except Exception:
                    detail = {}

                # 2. 插入到 AlertArchive
                archive_row = AlertArchive(
                    original_id=row.id,
                    rule=detail.get("rule", "Unknown"),
                    severity=detail.get("severity", "P2"),
                    status="firing" if row.action_type == "alert_fired" else "resolved",
                    message=detail.get("message", ""),
                    labels=detail.get("labels", {}),
                    annotations=detail.get("annotations", {}),
                    fingerprint=detail.get("fingerprint"),
                    original_created_at=row.created_at or threshold,
                )
                db.add(archive_row)

                # 3. 删除原记录
                await db.delete(row)
                archived_count += 1

            # 4. 提交事务
            await db.commit()
            logger.info(
                "[alerts] archived %d alert logs older than %s (skipped %d duplicates)",
                archived_count,
                threshold,
                skipped_count,
            )
            return archived_count
        except Exception as exc:
            await db.rollback()
            logger.error("[alerts] archive transaction failed: %s", exc, exc_info=True)
            raise
