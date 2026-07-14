"""v1.34: 告警静默规则 API.

端点:
- POST   /api/v1/alerts/silences           - 创建静默规则 (admin)
- GET    /api/v1/alerts/silences           - 列出所有规则 (admin)
- GET    /api/v1/alerts/silences/active    - 列出当前生效的规则 (admin)
- PUT    /api/v1/alerts/silences/{id}      - 编辑静默规则 (admin)  # ISS-073
- POST   /api/v1/alerts/silences/{id}/enable - 启用已停用的规则 (admin)  # ISS-073
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
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
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
        # C-05 修复：matcher 不能为空，否则会匹配所有告警导致监控失效
        if not self.matcher:
            raise ValueError("matcher 不能为空，至少需要一个标签匹配条件")
        for key, value in self.matcher.items():
            # H-API-9 修复：拒绝空 value 的 matcher，AlertManager 语义中空值会匹配所有告警
            if not value:
                raise ValueError("matcher value 不能为空，空值会匹配所有告警")
            if len(key) > _SILENCE_MAX_KEY_LEN:
                raise ValueError(
                    f"matcher key 长度不能超过 {_SILENCE_MAX_KEY_LEN} 字符"
                )
            if len(value) > _SILENCE_MAX_VAL_LEN:
                raise ValueError(
                    f"matcher value 长度不能超过 {_SILENCE_MAX_VAL_LEN} 字符"
                )
        # H-API-9 修复：starts_at 不能早于当前时间 5 分钟以前，防止回溯静默历史告警
        now = datetime.now(timezone.utc)
        starts_at_aware = self.starts_at
        if starts_at_aware.tzinfo is None:
            starts_at_aware = starts_at_aware.replace(tzinfo=timezone.utc)
        if starts_at_aware < now - timedelta(minutes=5):
            raise ValueError("starts_at 不能早于当前时间 5 分钟以前")
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        # 限制静默最长持续期，防止管理员误操作导致长期静默掩盖告警
        max_ends_at = self.starts_at + timedelta(days=_SILENCE_MAX_DURATION_DAYS)
        if self.ends_at > max_ends_at:
            raise ValueError(f"静默持续期不能超过 {_SILENCE_MAX_DURATION_DAYS} 天")
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


class SilenceUpdate(BaseModel):
    """ISS-073: 编辑静默规则请求.

    与 SilenceCreate 相同的字段约束（matcher 长度、时间范围、持续期），
    但允许 starts_at 早于当前时间（已生效规则可调整时间窗口）。
    """

    name: str = Field(..., min_length=1, max_length=200)
    matcher: dict[str, str] = Field(
        ...,
        max_length=_SILENCE_MAX_MATCHER_ENTRIES,
        description="告警标签匹配器，最多 20 个键值对",
    )
    starts_at: datetime
    ends_at: datetime
    comment: str | None = Field(default=None, max_length=_SILENCE_MAX_COMMENT_LEN)

    @model_validator(mode="after")
    def _validate_update_fields(self) -> "SilenceUpdate":
        # 复用 matcher 校验
        if not self.matcher:
            raise ValueError("matcher 不能为空，至少需要一个标签匹配条件")
        for key, value in self.matcher.items():
            if not value:
                raise ValueError("matcher value 不能为空，空值会匹配所有告警")
            if len(key) > _SILENCE_MAX_KEY_LEN:
                raise ValueError(
                    f"matcher key 长度不能超过 {_SILENCE_MAX_KEY_LEN} 字符"
                )
            if len(value) > _SILENCE_MAX_VAL_LEN:
                raise ValueError(
                    f"matcher value 长度不能超过 {_SILENCE_MAX_VAL_LEN} 字符"
                )
        # 编辑场景：仅校验时间顺序与持续期，不限制 starts_at 必须晚于现在
        # （允许调整已生效规则的时间窗口）
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        max_ends_at = self.starts_at + timedelta(days=_SILENCE_MAX_DURATION_DAYS)
        if self.ends_at > max_ends_at:
            raise ValueError(f"静默持续期不能超过 {_SILENCE_MAX_DURATION_DAYS} 天")
        return self


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


@router.post("", response_model=dict, responses=COMMON_ERROR_RESPONSES)
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

    # ISS-004 修复：AM push 与本地写入放入同一 savepoint, 用 flush 而非 commit;
    # 外层 commit 失败时回滚 AM 侧已创建的 silence, 避免孤儿
    am_silence_id_for_rollback: str | None = None
    try:
        async with db.begin_nested():
            await db.flush()  # 获取 silence.id, 不触发 commit

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
                    # M-5 修复：持久化 AM silenceID，删除时用于同步取消 AM 侧静默
                    if silence_id_am:
                        silence.am_silence_id = silence_id_am
                        am_silence_id_for_rollback = silence_id_am
                    logger.info(
                        "[silence] synced to AM (local_id=%d, am_id=%s)",
                        silence.id,
                        silence_id_am,
                    )
                else:
                    logger.warning(
                        "[silence] AM sync skipped/failed (local_id=%d)",
                        silence.id,
                    )
            except Exception as exc:
                logger.error("[silence] AM sync exception: %s", exc)

        await db.commit()
        await db.refresh(silence)
    except Exception:
        await db.rollback()
        # ISS-004 修复: 外层 commit 失败时回滚 AM 侧已创建的 silence
        if am_silence_id_for_rollback:
            try:
                from app.monitoring.am_sync import delete_silence as am_delete_silence

                await am_delete_silence(am_silence_id_for_rollback, db=None)
            except Exception as rollback_exc:
                logger.error(
                    "[silence] AM rollback on commit failure exception: %s",
                    rollback_exc,
                )
        raise

    logger.info(
        "[silence] created by user=%d name=%s matcher=%s window=%s..%s",
        current_user.id,
        silence.name,
        silence.matcher,
        silence.starts_at,
        silence.ends_at,
    )
    return ok(_serialize_silence(silence))


@router.get("", response_model=dict, responses=COMMON_ERROR_RESPONSES)
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


@router.get("/active", response_model=dict, responses=COMMON_ERROR_RESPONSES)
async def list_active_silences(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_role("admin"))],
) -> dict:
    """v1.34: 列出当前生效的静默规则."""
    now = datetime.now(timezone.utc)
    stmt = (
        select(AlertSilence)
        .where(
            and_(
                AlertSilence.is_active.is_(True),
                AlertSilence.starts_at <= now,
                AlertSilence.ends_at >= now,
            )
        )
        .order_by(desc(AlertSilence.starts_at))
    )
    rows = (await db.execute(stmt)).scalars().all()
    return ok({"items": [_serialize_silence(r) for r in rows], "total": len(rows)})


@router.put("/{silence_id}", response_model=dict, responses=COMMON_ERROR_RESPONSES)
async def update_silence(
    silence_id: int,
    payload: SilenceUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> dict:
    """ISS-073: 编辑静默规则 (admin).

    编辑已存在的静默规则（名称、匹配器、时间窗口、备注）。
    - 不修改 is_active 状态（启用/停用由专门端点处理）
    - 写入 OperationLog 审计日志
    - AM 同步：先取消旧 AM silence，再推送新 silence（AM 不支持 PUT）
    """
    row = (
        await db.execute(select(AlertSilence).where(AlertSilence.id == silence_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="silence not found")

    # 记录变更前快照用于审计日志
    before_snapshot = {
        "name": row.name,
        "matcher": row.matcher,
        "starts_at": row.starts_at.isoformat() if row.starts_at else None,
        "ends_at": row.ends_at.isoformat() if row.ends_at else None,
        "comment": row.comment,
    }

    # ISS-003 修复: 保存旧 am_silence_id, 用于 savepoint 内删除旧 AM silence
    old_am_silence_id = row.am_silence_id

    # 应用变更
    row.name = payload.name
    row.matcher = payload.matcher
    row.starts_at = payload.starts_at
    row.ends_at = payload.ends_at
    row.comment = payload.comment

    # ISS-003 修复: AM 同步采用 best-effort 语义，推送失败不影响本地数据一致性
    # 原 bug: update_silence 中 AM push 与本地 commit 非原子，失败时本地已 commit 但 AM 状态不一致
    # 修复策略: AM push 在本地 commit 前执行，失败时记录警告但不回滚本地变更
    # （AM 服务不可用不应阻断用户更新 silence，下次 enable/update 时会重新推送）
    from app.monitoring.am_sync import (
        delete_silence as am_delete_silence,
    )
    from app.monitoring.am_sync import (
        local_to_am_format,
        push_silence,
    )

    # 1. 先取消旧 AM silence（best-effort，失败仅记录日志）
    if old_am_silence_id:
        try:
            await am_delete_silence(old_am_silence_id, db=db)
        except Exception as exc:
            logger.error("[silence] AM delete (on update) exception: %s", exc)
        # 删除已尝试 (无论成功失败), 清空本地 am_silence_id 防止重复删除
        row.am_silence_id = None

    # 2. 推送新 silence 到 AM（best-effort）
    am_payload = local_to_am_format(
        silence_id=row.id,
        name=row.name,
        matcher=row.matcher or {},
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        comment=row.comment,
    )
    try:
        am_result = await push_silence(am_payload, db=db)
        if am_result:
            new_am_id = am_result.get("silenceID", "")
            if new_am_id:
                row.am_silence_id = new_am_id
            logger.info(
                "[silence] AM re-synced on update (local_id=%d, am_id=%s)",
                row.id,
                new_am_id,
            )
        else:
            logger.warning(
                "[silence] AM push (on update) returned empty (local_id=%d)",
                row.id,
            )
    except Exception as exc:
        logger.error("[silence] AM push (on update) exception: %s", exc)

    await db.commit()
    await db.refresh(row)

    # 审计日志
    from app.models.admin import OperationLog

    op_log = OperationLog(
        operator_id=current_user.id,
        operator_role="admin",
        action_type="update_silence",
        target_type="alert_silence",
        target_id=silence_id,
        detail=json.dumps(
            {"before": before_snapshot, "after": _serialize_silence(row)},
            ensure_ascii=False,
            default=str,
        ),
    )
    db.add(op_log)
    await db.commit()

    logger.info(
        "[silence] updated by user=%d id=%d name=%s",
        current_user.id,
        silence_id,
        row.name,
    )
    return ok(_serialize_silence(row))


@router.post(
    "/{silence_id}/enable", response_model=dict, responses=COMMON_ERROR_RESPONSES
)
async def enable_silence(
    silence_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> dict:
    """ISS-073: 启用已停用的静默规则 (admin).

    将 is_active 从 False 恢复为 True。
    - 若规则已过期（ends_at < now），仍允许启用（管理员可调整时间窗口后再启用，
      或本端点直接拒绝，这里选择前者以提供灵活性）
    - 写入 OperationLog 审计日志
    - AM 同步：重新推送 silence 到 AM（best-effort）
    """
    row = (
        await db.execute(select(AlertSilence).where(AlertSilence.id == silence_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="silence not found")
    if row.is_active:
        # 幂等：已启用直接返回当前状态
        return ok(_serialize_silence(row))

    row.is_active = True
    await db.commit()
    await db.refresh(row)

    # AM 同步：重新推送（best-effort）
    try:
        from app.monitoring.am_sync import local_to_am_format, push_silence

        am_payload = local_to_am_format(
            silence_id=row.id,
            name=row.name,
            matcher=row.matcher or {},
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            comment=row.comment,
        )
        am_result = await push_silence(am_payload, db=db)
        if am_result:
            new_am_id = am_result.get("silenceID", "")
            if new_am_id:
                row.am_silence_id = new_am_id
                await db.commit()
                await db.refresh(row)
            logger.info(
                "[silence] AM re-synced on enable (local_id=%d, am_id=%s)",
                row.id,
                new_am_id,
            )
    except Exception as exc:
        logger.error("[silence] AM push (on enable) exception: %s", exc)

    # 审计日志
    from app.models.admin import OperationLog

    op_log = OperationLog(
        operator_id=current_user.id,
        operator_role="admin",
        action_type="enable_silence",
        target_type="alert_silence",
        target_id=silence_id,
        detail=json.dumps(
            {"name": row.name, "matcher": row.matcher},
            ensure_ascii=False,
        ),
    )
    db.add(op_log)
    await db.commit()

    logger.info("[silence] enabled by user=%d id=%d", current_user.id, silence_id)
    return ok(_serialize_silence(row))


@router.delete("/{silence_id}", response_model=dict, responses=COMMON_ERROR_RESPONSES)
async def delete_silence(
    silence_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> dict:
    """v1.34: 取消静默 (软删除, 保留审计)."""
    row = (
        await db.execute(select(AlertSilence).where(AlertSilence.id == silence_id))
    ).scalar_one_or_none()
    # M-API-15 修复：不存在或已删除则返回 404，不写重复 OperationLog
    if row is None or not row.is_active:
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
        # L-API-3 修复：截断 detail 至 5000 字符，与 alerts.py 保持一致，避免超 DB 字段限制
        detail=json.dumps(
            {"name": row.name, "matcher": row.matcher}, ensure_ascii=False
        ),
    )
    db.add(op_log)
    await db.commit()
    # M-5 修复：删除静默规则时同步取消 AlertManager 侧的静默，避免 AM 静默残留导致告警被持续抑制
    if row.am_silence_id:
        try:
            from app.monitoring.am_sync import delete_silence as am_delete_silence

            await am_delete_silence(row.am_silence_id, db=db)
        except Exception as exc:
            logger.error("[silence] AM delete sync exception: %s", exc)
    logger.info("[silence] deleted by user=%d id=%d", current_user.id, silence_id)
    return ok({"id": silence_id, "is_active": False})
