from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.request_id import get_or_create_request_id
from app.core.response import ok
from app.models.user import User
from app.schemas.admin import ConfigUpsertRequest, ModelRegistryRequest, ModelUpdateRequest, TemplateUpsertRequest, ThresholdUpsertRequest
from app.schemas.common import ApiResponse
from app.services.admin_service import AdminService
from app.services.crisis_export_service import CrisisExportService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/dashboard", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def admin_dashboard(
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    data = await service.get_stats()
    return ok(data)


@router.get("/stats", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def get_admin_stats(
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    data = await service.get_stats()
    return ok(data)


@router.get("/templates", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def list_templates(
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    service = AdminService(db)
    data = await service.list_templates(page, page_size)
    return ok(data)


@router.post("/templates", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def upsert_template(
    payload: TemplateUpsertRequest,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    try:
        template_id = await service.upsert_template(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ok({"template_id": template_id})


@router.get("/thresholds", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def list_thresholds(
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    data = await service.list_thresholds()
    return ok({"items": data})


@router.post("/thresholds", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def upsert_threshold(
    payload: ThresholdUpsertRequest,
    request: Request,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    request_id = get_or_create_request_id(request)
    threshold_id = await service.upsert_threshold(
        current_user.id,
        payload.model_dump(),
        ip_address=request.client.host if request.client else None,
        request_id=request_id,
    )
    return ok({"threshold_id": threshold_id})


@router.get("/model-feedbacks", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def list_feedbacks(
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    service = AdminService(db)
    data = await service.list_feedbacks(page, page_size)
    return ok(data)


@router.get("/configs", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def list_configs(
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    data = await service.list_configs()
    return ok({"items": data})


@router.post("/configs", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def upsert_config(
    payload: ConfigUpsertRequest,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    config_id = await service.upsert_config(current_user.id, payload.model_dump())
    return ok({"config_id": config_id})


@router.get("/settings", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def get_admin_settings(
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    thresholds = await service.list_thresholds()
    configs = await service.list_configs()
    return ok({"thresholds": thresholds, "configs": configs})


@router.get("/operation-logs", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def list_operation_logs(
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    action_type: str | None = Query(default=None),
    operator_role: str | None = Query(default=None, pattern="^(user|counselor|admin)$"),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
) -> dict:
    service = AdminService(db)
    data = await service.list_operation_logs(page, page_size, action_type, operator_role, start_time, end_time)
    return ok(data)


@router.get("/audit-logs", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def list_audit_logs(
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    action_types: list[str] | None = Query(default=None, description="按 action_type 过滤（可多个）"),
    operator_role: str | None = Query(default=None, pattern="^(user|counselor|admin)$"),
    target_type: str | None = Query(default=None, max_length=50),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
) -> dict:
    """v1.32: 合规审计日志查询.

    与 operation-logs 相比提供:
    - 多 action_type 过滤
    - target_type 过滤
    - 合规统计 (action_breakdown, retention_days)
    - 适合 GDPR / 等保 2.0 审计场景
    """
    service = AdminService(db)
    data = await service.list_audit_logs(
        page, page_size, action_types, operator_role, target_type, start_time, end_time
    )
    return ok(data)


@router.get("/models", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def list_models(
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    service = AdminService(db)
    data = await service.list_models(page, page_size)
    return ok(data)


@router.post("/models", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def register_model(
    payload: ModelRegistryRequest,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    model_id = await service.register_model(payload.model_dump())
    return ok({"model_id": model_id})


@router.put("/models/{model_id_int}", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def update_model(
    model_id_int: int,
    payload: ModelUpdateRequest,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    await service.update_model(model_id_int, payload.model_dump(exclude_unset=True))
    return ok({"message": "模型更新成功"})


@router.post("/models/{model_id_int}/activate", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def activate_model(
    model_id_int: int,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    await service.activate_model(model_id_int)
    return ok({"message": "模型已激活"})


@router.post("/archive-logs", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def archive_logs(
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = Query(default=90, ge=30, le=365),
) -> dict:
    service = AdminService(db)
    count = await service.archive_old_logs(days=days)
    return ok({"archived_count": count, "message": f"已归档{count}条超过{days}天的操作日志"})


@router.get("/crisis-events/export", response_class=PlainTextResponse)
async def export_crisis_events(
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    start_date: date = Query(..., description="开始日期 (YYYY-MM-DD)"),
    end_date: date = Query(..., description="结束日期 (YYYY-MM-DD)"),
) -> PlainTextResponse:
    """导出危机事件 CSV（管理员权限）。"""
    if start_date > end_date:
        raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期")

    service = CrisisExportService(db)
    csv_content, filename = await service.export_crisis_events(start_date, end_date)

    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
