"""Phase 3 模型预测暂停开关 API.

提供管理员端点用于激活/解除模型预测暂停：
- POST /api/v1/model-kill-switch/activate  激活暂停
- POST /api/v1/model-kill-switch/deactivate  解除暂停
- GET  /api/v1/model-kill-switch/status  查询状态

所有操作记录到 OperationLog 审计日志。
仅管理员可访问。
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.kill_switch import (
    KillSwitchUnavailableError,
    get_kill_switch_status,
    set_model_paused,
)
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.rate_limit import limiter
from app.core.response import ok
from app.core.tenant_context import require_platform_admin
from app.models.admin import OperationLog
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/model-kill-switch", tags=["model-kill-switch"])


class KillSwitchActionRequest(BaseModel):
    """暂停开关操作请求."""

    reason: str = Field(
        ..., min_length=1, max_length=500, description="暂停/恢复原因（必填）"
    )


@router.post(
    "/activate",
    response_model=None,
    responses=COMMON_ERROR_RESPONSES,
    summary="激活模型预测暂停（管理员）",
)
@limiter.limit("10/minute")
async def activate_kill_switch(
    request: Request,
    payload: KillSwitchActionRequest,
    current_user: Annotated[User, Depends(require_platform_admin())],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """激活模型预测暂停.

    激活后所有预测端点（/predict/tabular、/predict/text、/predict/physiological）
    将返回 503。用于危机事件、安全事件或重大误判时立即停止模型输出。

    需提供暂停原因，操作记录到审计日志。
    """
    try:
        state = await set_model_paused(
            paused=True, admin_id=current_user.id, reason=payload.reason
        )
    except KillSwitchUnavailableError as exc:
        # AUDIT-2026-10-01 (P1-7)：绝不能返回「已暂停」——多实例部署下其他实例仍在预测。
        logger.error("Kill switch 激活失败（未生效）: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "暂停操作未生效：无法写入权威状态（Redis 不可用）。"
                "当前为 fail-closed 模式，各实例预测端点应已返回 503；请修复 Redis 后重试。"
            ),
        ) from exc

    # 写入审计日志
    db.add(
        OperationLog(
            operator_id=current_user.id,
            operator_role="admin",
            action_type="model.kill_switch.activate",
            target_type="kill_switch",
            target_id=None,
            detail=payload.reason,
        )
    )
    await db.commit()

    logger.warning(
        "Model kill switch ACTIVATED by admin %s: %s",
        current_user.id,
        payload.reason,
    )
    return ok(state)


@router.post(
    "/deactivate",
    response_model=None,
    responses=COMMON_ERROR_RESPONSES,
    summary="解除模型预测暂停（管理员）",
)
@limiter.limit("10/minute")
async def deactivate_kill_switch(
    request: Request,
    payload: KillSwitchActionRequest,
    current_user: Annotated[User, Depends(require_platform_admin())],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """解除模型预测暂停.

    恢复所有预测端点的正常服务。需提供恢复原因，操作记录到审计日志。
    """
    try:
        state = await set_model_paused(
            paused=False, admin_id=current_user.id, reason=payload.reason
        )
    except KillSwitchUnavailableError as exc:
        # 同上：无法确认已写入，就不能声称「已恢复」——否则界面显示恢复、
        # 其他实例仍在返回 503，运维会误判故障已排除。
        logger.error("Kill switch 解除失败（未生效）: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "恢复操作未生效：无法写入权威状态（Redis 不可用）。"
                "各实例预测端点仍可能返回 503；请修复 Redis 后重试。"
            ),
        ) from exc

    # 写入审计日志
    db.add(
        OperationLog(
            operator_id=current_user.id,
            operator_role="admin",
            action_type="model.kill_switch.deactivate",
            target_type="kill_switch",
            target_id=None,
            detail=payload.reason,
        )
    )
    await db.commit()

    logger.info(
        "Model kill switch DEACTIVATED by admin %s: %s",
        current_user.id,
        payload.reason,
    )
    return ok(state)


@router.get(
    "/status",
    response_model=None,
    responses=COMMON_ERROR_RESPONSES,
    summary="查询模型预测暂停状态（管理员）",
)
@limiter.limit("30/minute")
async def get_kill_switch_status_endpoint(
    request: Request,
    current_user: Annotated[User, Depends(require_platform_admin())],
) -> dict[str, Any]:
    """查询当前模型预测暂停状态."""
    state = await get_kill_switch_status()
    return ok(state)
