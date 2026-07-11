"""v1.34: 告警静默匹配逻辑.

匹配规则:
- starts_at <= now <= ends_at 才生效
- is_active=True
- matcher 是 dict, 任何键值对都需在 alert.labels 中匹配 (AND 逻辑)
- 空 matcher {} 匹配所有告警 (全静默)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import and_, select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AlertSilence
from app.monitoring.notifier import AlertPayload

logger = logging.getLogger(__name__)


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _matcher_matches(matcher: dict, labels: dict) -> bool:
    """检查 matcher 是否匹配 alert labels.

    所有 matcher 键值对都必须在 labels 中存在且相等 (AND).
    空 matcher 匹配所有.
    """
    if not matcher:
        return True
    for key, value in matcher.items():
        if labels.get(key) != value:
            return False
    return True


async def is_silenced(
    alert: AlertPayload,
    db: "AsyncSession",
) -> tuple[bool, AlertSilence | None]:
    """v1.34: 检查告警是否被静默.

    Args:
        alert: 内部 AlertPayload
        db: 数据库会话

    Returns:
        (is_silenced, matching_silence) - matching_silence 是首个匹配的静默规则
    """
    now = _utcnow_naive()
    stmt = select(AlertSilence).where(
        and_(
            AlertSilence.is_active.is_(True),
            AlertSilence.starts_at <= now,
            AlertSilence.ends_at >= now,
        )
    )
    rows = (await db.execute(stmt)).scalars().all()

    labels = {**alert.labels}
    for silence in rows:
        if _matcher_matches(silence.matcher, labels):
            logger.info(
                "[silence] alert matched (fingerprint=%s, silence_id=%d, name=%s)",
                alert.fingerprint, silence.id, silence.name,
            )
            return True, silence
    return False, None
