from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.response import ok
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.warning import WarningSettingsUpdateRequest
from app.services.warning_service import WarningService

router = APIRouter(prefix="/user", tags=["user-warning"])


@router.get("/warnings", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def list_warnings(
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    is_read: bool | None = Query(default=None),
    risk_level: int | None = Query(default=None, ge=0, le=4),
) -> dict:
    service = WarningService(db)
    # M6 修复：将 risk_level 下推到 service，在 SQL 层过滤，避免 total 被错误覆盖
    data = await service.list_warnings(
        current_user.id, page, page_size, is_read, risk_level=risk_level
    )
    for item in data.get("items", []):
        item.setdefault("physiological_score", None)
        item.setdefault("fusion_detail", None)
    return ok(data)


@router.put("/warnings/{warning_id}/read", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def mark_warning_read(
    warning_id: int,
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = WarningService(db)
    success = await service.mark_read(current_user.id, warning_id)
    if not success:
        raise HTTPException(status_code=404, detail="预警不存在")
    return ok({"message": "已标记为已读"})


@router.put("/warnings/read-all", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def mark_all_warning_read(
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = WarningService(db)
    count = await service.mark_all_read(current_user.id)
    return ok({"message": "全部标记为已读", "count": count})


@router.get("/warning-settings", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def get_warning_setting(
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = WarningService(db)
    setting = await service.get_setting(current_user.id)
    return ok(
        {
            "notify_channels": setting.notify_channels,
            "threshold_level": setting.threshold_level,
            "quiet_hours_start": setting.quiet_hours_start.isoformat() if setting.quiet_hours_start else None,
            "quiet_hours_end": setting.quiet_hours_end.isoformat() if setting.quiet_hours_end else None,
        }
    )


@router.put("/warning-settings", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def update_warning_setting(
    payload: WarningSettingsUpdateRequest,
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = WarningService(db)
    data = payload.model_dump()
    await service.update_setting(current_user.id, data)
    return ok({"message": "设置已更新"})
