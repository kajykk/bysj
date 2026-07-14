import json
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.rate_limit import get_real_client_ip, limiter
from app.core.request_id import get_or_create_request_id
from app.core.response import ok
from app.models.admin import OperationLog
from app.models.user import User
from app.schemas.admin import (
    ConfigUpsertRequest,
    ModelRegistryRequest,
    ModelUpdateRequest,
    TemplateUpsertRequest,
    ThresholdUpsertRequest,
)
from app.schemas.common import ApiResponse
from app.services.admin_service import AdminService
from app.services.crisis_export_service import CrisisExportService

router = APIRouter(prefix="/admin", tags=["admin"])


def _sanitize_filename(name: str) -> str:
    """M-API-14 修复：移除 filename 中的特殊字符，防止 Content-Disposition 头注入.

    仅保留字母、数字、下划线、连字符和点号，避免 CRLF 注入或路径穿越。
    """
    import re

    return re.sub(r"[^A-Za-z0-9_\-.]", "_", name)


@router.get("/dashboard", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("60/minute")
async def admin_dashboard(
    request: Request,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    data = await service.get_stats()
    return ok(data)


@router.get("/stats", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("60/minute")
async def get_admin_stats(
    request: Request,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    data = await service.get_stats()
    return ok(data)


@router.get("/templates", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("60/minute")
async def list_templates(
    request: Request,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    service = AdminService(db)
    data = await service.list_templates(page, page_size)
    return ok(data)


@router.post("/templates", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("10/minute")
async def upsert_template(
    request: Request,
    payload: TemplateUpsertRequest,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    try:
        # ISS-076: 传入 operator_id 和 operator_role 以写入 OperationLog 审计日志
        template_id = await service.upsert_template(
            payload.model_dump(),
            admin_id=current_user.id,
            operator_role=current_user.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ok({"template_id": template_id})


@router.delete(
    "/templates/{template_id}",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("10/minute")
async def delete_template(
    request: Request,
    template_id: int,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """ISS-075: 删除干预模板."""
    service = AdminService(db)
    try:
        await service.delete_template(template_id, current_user.id, current_user.role)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ok({"message": "模板已删除"})


@router.get("/thresholds", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("60/minute")
async def list_thresholds(
    request: Request,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    data = await service.list_thresholds()
    return ok({"items": data})


@router.post(
    "/thresholds", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
@limiter.limit("10/minute")
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
        ip_address=get_real_client_ip(request),
        request_id=request_id,
    )
    return ok({"threshold_id": threshold_id})


@router.get(
    "/model-feedbacks", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
@limiter.limit("60/minute")
async def list_feedbacks(
    request: Request,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    service = AdminService(db)
    data = await service.list_feedbacks(page, page_size)
    return ok(data)


@router.get("/configs", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("60/minute")
async def list_configs(
    request: Request,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    data = await service.list_configs()
    return ok({"items": data})


@router.post("/configs", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("10/minute")
async def upsert_config(
    request: Request,
    payload: ConfigUpsertRequest,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    config_id = await service.upsert_config(current_user.id, payload.model_dump())
    return ok({"config_id": config_id})


@router.get("/settings", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("60/minute")
async def get_admin_settings(
    request: Request,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    thresholds = await service.list_thresholds()
    configs = await service.list_configs()
    return ok({"thresholds": thresholds, "configs": configs})


@router.get(
    "/operation-logs", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
@limiter.limit("60/minute")
async def list_operation_logs(
    request: Request,
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
    data = await service.list_operation_logs(
        page, page_size, action_type, operator_role, start_time, end_time
    )
    return ok(data)


@router.get(
    "/operation-logs/export",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("10/minute")
async def export_operation_logs(
    request: Request,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    action_type: str | None = Query(default=None),
    operator_role: str | None = Query(default=None, pattern="^(user|counselor|admin)$"),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
) -> dict:
    """ISS-080: 导出全部筛选条件下的操作日志（不分页），供前端生成 CSV."""
    service = AdminService(db)
    items = await service.export_operation_logs(
        action_type, operator_role, start_time, end_time
    )
    return ok({"items": items, "total": len(items)})


@router.get("/audit-logs", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("60/minute")
async def list_audit_logs(
    request: Request,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    # M-API-3 修复：统一 page_size 上限为 100，与其他端点一致（原为 200）
    page_size: int = Query(default=50, ge=1, le=100),
    action_types: list[str] | None = Query(
        default=None, description="按 action_type 过滤（可多个）"
    ),
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
@limiter.limit("60/minute")
async def list_models(
    request: Request,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    service = AdminService(db)
    data = await service.list_models(page, page_size)
    return ok(data)


@router.post("/models", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("10/minute")
async def register_model(
    request: Request,
    payload: ModelRegistryRequest,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    model_id = await service.register_model(payload.model_dump())
    return ok({"model_id": model_id})


@router.put(
    "/models/{model_id_int}",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("10/minute")
async def update_model(
    request: Request,
    model_id_int: int,
    payload: ModelUpdateRequest,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    await service.update_model(model_id_int, payload.model_dump(exclude_unset=True))
    # L-API-6 修复：记录 OperationLog 审计日志，与其他模型操作（register/activate）保持一致
    db.add(
        OperationLog(
            operator_id=current_user.id,
            operator_role=current_user.role,
            action_type="update_model",
            target_type="model",
            target_id=model_id_int,
            detail=json.dumps(
                payload.model_dump(exclude_unset=True), ensure_ascii=False
            ),
        )
    )
    await db.commit()
    return ok({"message": "模型更新成功"})


@router.post(
    "/models/{model_id_int}/activate",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("10/minute")
async def activate_model(
    request: Request,
    model_id_int: int,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    await service.activate_model(model_id_int)
    return ok({"message": "模型已激活"})


@router.post(
    "/archive-logs", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
@limiter.limit("10/minute")
async def archive_logs(
    request: Request,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = Query(default=90, ge=30, le=365),
) -> dict:
    service = AdminService(db)
    count = await service.archive_old_logs(days=days)
    return ok(
        {"archived_count": count, "message": f"已归档{count}条超过{days}天的操作日志"}
    )


@router.get("/crisis-events/export", response_class=PlainTextResponse)
@limiter.limit("60/minute")
async def export_crisis_events(
    request: Request,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    start_date: date = Query(..., description="开始日期 (YYYY-MM-DD)"),
    end_date: date = Query(..., description="结束日期 (YYYY-MM-DD)"),
) -> PlainTextResponse:
    """导出危机事件 CSV（管理员权限）。"""
    if start_date > end_date:
        raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期")

    # M-15 修复：限制导出日期范围，防止一次性导出过大数据集导致性能问题
    from datetime import timedelta

    max_range = timedelta(days=90)
    if (end_date - start_date) > max_range:
        raise HTTPException(
            status_code=422,
            detail="导出日期范围不能超过 90 天",
        )

    service = CrisisExportService(db)
    csv_content, filename = await service.export_crisis_events(start_date, end_date)

    # M-API-14 修复：对 filename 做注入防护（CSV 单元格已由 CrisisExportService._sanitize_csv_cell 防护）
    safe_filename = _sanitize_filename(filename)

    # SEC-P1-003 修复：记录危机事件 CSV 导出审计日志
    db.add(
        OperationLog(
            operator_id=current_user.id,
            operator_role=current_user.role,
            action_type="admin.crisis.export",
            target_type="crisis_event",
            target_id=None,
            detail=json.dumps(
                {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "filename": safe_filename,
                    "content_size": len(csv_content),
                },
                ensure_ascii=False,
            ),
            ip_address=get_real_client_ip(request),
        )
    )
    await db.commit()

    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
    )
