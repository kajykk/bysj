"""v1.34: 告警去重 (fingerprint 抑制).

逻辑:
- 同 fingerprint 5 分钟内仅发送 1 次通知
- 持久化到 OperationLog 仍每次记录 (审计完整)
- 仅抑制通知通道 (CompositeNotifier)

设计:
- 通过查询 OperationLog 中 action_type='alert_fired' 的最近一条相同 fingerprint 记录
- 如果在 5 分钟内, 跳过通知
- 解决告警风暴 (同源高频触发)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import and_, desc, select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.monitoring.notifier import AlertPayload

logger = logging.getLogger(__name__)

# 默认去重窗口 (5 分钟)
DEFAULT_DEDUP_WINDOW = timedelta(minutes=5)


def _utcnow_naive() -> datetime:
    """v1.34: timezone-aware UTC 作为 naive datetime (匹配 DB 存储)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def should_send(
    alert: AlertPayload,
    db: "AsyncSession",
    window: timedelta = DEFAULT_DEDUP_WINDOW,
) -> bool:
    """v1.35: 检查告警是否应发送 (Redis 锁 + SQL 降级).

    流程:
    1. 尝试获取 Redis 锁 (跨实例去重)
    2. 锁获取失败 -> 跳过 (其他实例已发送)
    3. 锁获取成功 -> 检查 SQL 历史 (本地去重)
    4. SQL 检查在 5min 内有同 fingerprint -> 跳过 (本地重复)

    Args:
        alert: 内部 AlertPayload
        db: 数据库会话
        window: 去重窗口 (默认 5 分钟)

    Returns:
        True = 应发送, False = 应跳过 (去重)
    """
    from app.models.admin import OperationLog
    from app.monitoring.dedup_lock import try_acquire_lock

    # 无 fingerprint 不去重
    if not alert.fingerprint:
        return True

    # v1.35: 优先 Redis 锁 (跨实例)
    lock_acquired = await try_acquire_lock(alert.fingerprint, ttl_seconds=int(window.total_seconds()))
    if not lock_acquired:
        # 其他实例已获取锁 -> 跳过
        return False

    # 本地 SQL 检查 (降级或补充)
    now = _utcnow_naive()
    threshold = now - window

    stmt = (
        select(OperationLog)
        .where(
            and_(
                OperationLog.action_type == "alert_fired",
                OperationLog.target_type == "alert",
            )
        )
        .order_by(desc(OperationLog.created_at))
        .limit(50)
    )
    rows = (await db.execute(stmt)).scalars().all()

    for row in rows:
        if row.created_at is None or row.created_at < threshold:
            break
        try:
            detail = json.loads(row.detail or "{}")
        except Exception:
            continue
        if detail.get("fingerprint") == alert.fingerprint:
            logger.info(
                "[dedup] skip alert (fingerprint=%s, last_seen=%s, window=%s)",
                alert.fingerprint, row.created_at, window,
            )
            return False
    return True
