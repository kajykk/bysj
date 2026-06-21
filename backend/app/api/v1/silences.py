"""v1.34: 告警静默规则 API.

端点:
- POST   /api/v1/alerts/silences           - 创建静默规则 (admin)
- GET    /api/v1/alerts/silences           - 列出所有规则 (admin)
- GET    /api/v1/alerts/silences/active    - 列出当前生效的规则 (admin)
- DELETE /api/v1/alerts/silences/{id}      - 取消静默 (admin)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.response import ok
from app.models.admin import AlertSilence
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts/silences", tags=["alerts"])

# P1-SEC-021 修复：静默规则输入限制，防止滥用和资源耗尽
_SILENCE_MAX_MATCHER_ENTRIES = 20
_SILENCE_MAX_KEY_LEN = 64
_SILENCE_MAX_VAL_LEN = 256
_SILENCE_MAX_COMMENT_LEN = 1000
_SILENCE_MAX_DURATION_DAYS = 90  # 单次静默最长 90 天，防止长期静默掩盖告警


# ===== Request/Response Models =====


class SilenceCreate(BaseModel):
    """v1.34: 创建静默规则请求."""

    name: str = Field(..., min_length=1, max_length=200)
    matcher: dict[str, str] = Field(
        default_factory=dict,
        max_length=_SILENCE_MAX_MATCHER_ENTRIES,
        description="告警标签匹配器，最多 20 个键值对",
    )
    starts_at: datetime
    ends_at: datetime
    comment: str | None = Field(default=None, max_length=_SILENCE_MAX_COMMENT_LEN)

    @model_validator(mode="after")
    def _validate_silence_fields(self) -> "SilenceCreate":
        """P1-SEC-021 修复：校验 matcher 键值长度、时间范围与持续期."""
        for key, value in self.matcher.items():
            if len(key) > _SILENCE_MAX_KEY_LEN:
                raise ValueError(
                    f"matcher key 长度不能超过 {_SILENCE_MAX_KEY_LEN} 字符"
                )
            if len(value) > _SILENCE_MAX_VAL_LEN:
                raise ValueError(
                    f"matcher value 长度不能超过 {_SILENCE_MAX_VAL_LEN} 字符"
                )
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        # 限制静默最长持续期，防止管理员误操作导致长期静默掩盖告警
        max_ends_at = self.starts_at + timedelta(days=_SILENCE_MAX_DURATION_DAYS)
        if self.ends_at > max_ends_at:
            raise ValueError(
                f"静默持续期不能超过 {_SILENCE_MAX_DURATION_DAYS} 天"
            )
        return self


class SilenceItem(BaseModel):
    """v1.34: 静默规则响应."""

    id: int
    name: str
    matcher: dict[str, str]
    starts_at: str
    ends_at: str
    created_by: int | None = None
    created_at: str | None = None
    comment: str | None = None
    is_active: bool


def _serialize_silence(s: AlertSilence) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "matcher": s.matcher or {},
        "starts_at": s.starts_at.isoformat() if s.starts_at else None,
        "ends_at": s.ends_at.isoformat() if s.ends_at else None,
        "created_by": s.created_by,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "comment": s.comment,
        "is_active": bool(s.is_active),
    }


# ===== Endpoints =====


@router.post("", response_model=dict)
async def create_silence(
    payload: SilenceCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> dict:
    """v1.34: 创建静默规则 (v1.35: 同步到 AlertManager)."""
    # P1-SEC-021 修复：时间范围与持续期校验已迁移至 SilenceCreate 模型 validator
    silence = AlertSilence(
        name=payload.name,
        matcher=payload.matcher,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        created_by=current_user.id,
        comment=payload.comment,
        is_active=True,
    )
    db.add(silence)
    await db.commit()
    await db.refresh(silence)

    # v1.35: 同步到 AlertManager
    try:
        from app.monitoring.am_sync import local_to_am_format, push_silence
        am_payload = local_to_am_format(
            silence_id=silence.id,
            name=silence.name,
            matcher=silence.matcher or {},
            starts_at=silence.starts_at,
            ends_at=silence.ends_at,
            comment=silence.comment,
        )
        am_result = await push_silence(am_payload, db=db)
        if am_result:
            silence_id_am = am_result.get("silenceID", "")
            # 记录 AM ID 到 detail (via comment 追加或后续字段)
            logger.info(
                "[silence] synced to AM (local_id=%d, am_id=%s)",
                silence.id, silence_id_am,
            )
        else:
            logger.warning(
                "[silence] AM sync skipped/failed (local_id=%d)",
                silence.id,
            )
    except Exception as exc:
        logger.error("[silence] AM sync exception: %s", exc)

    logger.info(
        "[silence] created by user=%d name=%s matcher=%s window=%s..%s",
        current_user.id, silence.name, silence.matcher, silence.starts_at, silence.ends_at,
    )
    return ok(_serialize_silence(silence))


@router.get("", response_model=dict)
async def list_silences(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_role("admin"))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    is_active: bool | None = Query(default=None),
) -> dict:
    """v1.34: 列出静默规则 (admin)."""
    offset = (page - 1) * page_size
    stmt = select(AlertSilence)
    count_stmt = select(func.count()).select_from(AlertSilence)
    if is_active is not None:
        stmt = stmt.where(AlertSilence.is_active.is_(is_active))
        count_stmt = count_stmt.where(AlertSilence.is_active.is_(is_active))
    stmt = stmt.order_by(desc(AlertSilence.starts_at)).offset(offset).limit(page_size)
    rows = (await db.execute(stmt)).scalars().all()
    total = (await db.execute(count_stmt)).scalar_one()
    return ok(
        {
            "items": [_serialize_silence(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/active", response_model=dict)
async def list_active_silences(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_role("admin"))],
) -> dict:
    """v1.34: 列出当前生效的静默规则."""
    now = datetime.now(timezone.utc)
    stmt = select(AlertSilence).where(
        and_(
            AlertSilence.is_active.is_(True),
            AlertSilence.starts_at <= now,
            AlertSilence.ends_at >= now,
        )
    ).order_by(desc(AlertSilence.starts_at))
    rows = (await db.execute(stmt)).scalars().all()
    return ok({"items": [_serialize_silence(r) for r in rows], "total": len(rows)})


@router.delete("/{silence_id}", response_model=dict)
async def delete_silence(
    silence_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> dict:
    """v1.34: 取消静默 (软删除, 保留审计)."""
    row = (await db.execute(select(AlertSilence).where(AlertSilence.id == silence_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="silence not found")
    row.is_active = False
    # 记录到 OperationLog
    from app.models.admin import OperationLog
    op_log = OperationLog(
        operator_id=current_user.id,
        operator_role="admin",
        action_type="delete_silence",
        target_type="alert_silence",
        target_id=silence_id,
        detail=json.dumps({"name": row.name, "matcher": row.matcher}, ensure_ascii=False),
    )
    db.add(op_log)
    await db.commit()
    logger.info("[silence] deleted by user=%d id=%d", current_user.id, silence_id)
    return ok({"id": silence_id, "is_active": False})
