import asyncio
import json
import logging
from datetime import date, datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.idempotency import (
    begin_idempotent_call,
    dismiss_idempotent_call,
    make_idempotency_key,
    settle_idempotent_call,
)
from app.core.openapi_responses import COMMON_ERROR_RESPONSES, CSV_EXPORT_RESPONSE
from app.core.rate_limit import get_real_client_ip, limiter
from app.core.request_id import get_or_create_request_id
from app.core.response import ok
from app.core.tenant_context import require_platform_admin
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def _sanitize_filename(name: str) -> str:
    """M-API-14 修复：移除 filename 中的特殊字符，防止 Content-Disposition 头注入.

    仅保留字母、数字、下划线、连字符和点号，避免 CRLF 注入或路径穿越。
    """
    import re

    return re.sub(r"[^A-Za-z0-9_\-.]", "_", name)


def _map_value_error(exc: ValueError) -> HTTPException:
    """ISS-093 修复：业务参数类 ValueError → 400，资源不存在才 404."""
    detail = str(exc)
    if "不存在" in detail or "not found" in detail:
        return HTTPException(status_code=404, detail=detail)
    return HTTPException(status_code=400, detail=detail)


async def _begin_idempotent(
    request: Request, actor_id: int
) -> tuple[str | None, dict | None]:
    """ISS-094: 读取 Idempotency-Key 头并开始幂等调用.

    返回 (idem_key, replay_data); 未带幂等头时返回 (None, None) 保持原行为;
    重复提交 (处理中) 直接抛 409。
    """
    header = request.headers.get("Idempotency-Key")
    if not header:
        return None, None
    key = make_idempotency_key(actor_id, header)
    proceed, replay = await begin_idempotent_call(key)
    if proceed:
        return key, None
    if replay is not None:
        return key, replay
    raise HTTPException(
        status_code=409, detail="重复提交：相同请求正在处理中，请稍后重试"
    )


@router.get("/dashboard", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("60/minute")
async def admin_dashboard(
    request: Request,
    current_user: Annotated[User, Depends(require_platform_admin())],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    data = await service.get_stats()
    return ok(data)


@router.get("/stats", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("60/minute")
async def get_admin_stats(
    request: Request,
    current_user: Annotated[User, Depends(require_platform_admin())],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    data = await service.get_stats()
    return ok(data)


@router.get("/templates", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("60/minute")
async def list_templates(
    request: Request,
    current_user: Annotated[User, Depends(require_platform_admin())],
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
    current_user: Annotated[User, Depends(require_platform_admin())],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    idem_key, replay = await _begin_idempotent(request, current_user.id)
    if replay is not None:
        return ok(replay)
    try:
        # ISS-076: 传入 operator_id 和 operator_role 以写入 OperationLog 审计日志
        template_id = await service.upsert_template(
            payload.model_dump(),
            admin_id=current_user.id,
            operator_role=current_user.role,
        )
    except ValueError as exc:
        # ISS-093: 模板不存在 → 404, 业务参数问题 → 400
        if idem_key:
            await dismiss_idempotent_call(idem_key)
        raise _map_value_error(exc) from exc
    result = {"template_id": template_id}
    if idem_key:
        await settle_idempotent_call(idem_key, result)
    return ok(result)


@router.delete(
    "/templates/{template_id}",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("10/minute")
async def delete_template(
    request: Request,
    template_id: int,
    current_user: Annotated[User, Depends(require_platform_admin())],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """ISS-075: 删除干预模板."""
    service = AdminService(db)
    try:
        await service.delete_template(template_id, current_user.id, current_user.role)
    except ValueError as exc:
        raise _map_value_error(exc) from exc
    return ok({"message": "模板已删除"})


@router.get("/thresholds", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("60/minute")
async def list_thresholds(
    request: Request,
    current_user: Annotated[User, Depends(require_platform_admin())],
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
    current_user: Annotated[User, Depends(require_platform_admin())],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    idem_key, replay = await _begin_idempotent(request, current_user.id)
    if replay is not None:
        return ok(replay)
    request_id = get_or_create_request_id(request)
    threshold_id = await service.upsert_threshold(
        current_user.id,
        payload.model_dump(),
        ip_address=get_real_client_ip(request),
        request_id=request_id,
    )
    result = {"threshold_id": threshold_id}
    if idem_key:
        await settle_idempotent_call(idem_key, result)
    return ok(result)


@router.get(
    "/model-feedbacks", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
@limiter.limit("60/minute")
async def list_feedbacks(
    request: Request,
    current_user: Annotated[User, Depends(require_platform_admin())],
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
    current_user: Annotated[User, Depends(require_platform_admin())],
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
    current_user: Annotated[User, Depends(require_platform_admin())],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    idem_key, replay = await _begin_idempotent(request, current_user.id)
    if replay is not None:
        return ok(replay)
    try:
        config_id = await service.upsert_config(current_user.id, payload.model_dump())
    except ValueError as exc:
        # ISS-093: 不支持的配置键属业务参数错误 → 400 (原为未捕获 → 500)
        if idem_key:
            await dismiss_idempotent_call(idem_key)
        raise _map_value_error(exc) from exc
    result = {"config_id": config_id}
    if idem_key:
        await settle_idempotent_call(idem_key, result)
    return ok(result)


@router.get("/settings", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("60/minute")
async def get_admin_settings(
    request: Request,
    current_user: Annotated[User, Depends(require_platform_admin())],
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
    current_user: Annotated[User, Depends(require_platform_admin())],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    action_type: str | None = Query(default=None),
    operator_role: str | None = Query(default=None, pattern="^(user|counselor|admin)$"),
    # SEC-FIX (M4): 操作员用户名模糊筛选
    operator_name: str | None = Query(default=None, max_length=64),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
) -> dict:
    service = AdminService(db)
    data = await service.list_operation_logs(
        page, page_size, action_type, operator_role, operator_name, start_time, end_time
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
    current_user: Annotated[User, Depends(require_platform_admin())],
    db: Annotated[AsyncSession, Depends(get_db)],
    action_type: str | None = Query(default=None),
    operator_role: str | None = Query(default=None, pattern="^(user|counselor|admin)$"),
    operator_name: str | None = Query(default=None, max_length=64),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
) -> dict:
    """ISS-080: 导出全部筛选条件下的操作日志（不分页），供前端生成 CSV."""
    service = AdminService(db)
    items = await service.export_operation_logs(
        action_type, operator_role, operator_name, start_time, end_time
    )
    return ok({"items": items, "total": len(items)})


@router.get("/audit-logs", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("60/minute")
async def list_audit_logs(
    request: Request,
    current_user: Annotated[User, Depends(require_platform_admin())],
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
    current_user: Annotated[User, Depends(require_platform_admin())],
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
    current_user: Annotated[User, Depends(require_platform_admin())],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    try:
        model_id = await service.register_model(payload.model_dump())
    except ValueError as exc:
        # model_id 重复 → 409 (业务冲突), 避免未处理异常返回 500
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
    current_user: Annotated[User, Depends(require_platform_admin())],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    try:
        await service.update_model(model_id_int, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise _map_value_error(exc) from exc
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
    current_user: Annotated[User, Depends(require_platform_admin())],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = AdminService(db)
    try:
        await service.activate_model(model_id_int)
    except ValueError as exc:
        raise _map_value_error(exc) from exc
    return ok({"message": "模型已激活"})


@router.post(
    "/archive-logs", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
@limiter.limit("10/minute")
async def archive_logs(
    request: Request,
    current_user: Annotated[User, Depends(require_platform_admin())],
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = Query(default=90, ge=30, le=365),
) -> dict:
    service = AdminService(db)
    count = await service.archive_old_logs(days=days)
    return ok(
        {"archived_count": count, "message": f"已归档{count}条超过{days}天的操作日志"}
    )


@router.get(
    "/crisis-events/export",
    response_class=PlainTextResponse,
    responses={**COMMON_ERROR_RESPONSES, **CSV_EXPORT_RESPONSE},
)
@limiter.limit("60/minute")
async def export_crisis_events(
    request: Request,
    current_user: Annotated[User, Depends(require_platform_admin())],
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
    # M-API-14 修复：对 filename 做注入防护（CSV 单元格已由 CrisisExportService._sanitize_csv_cell 防护）
    safe_filename = _sanitize_filename(service.build_filename(start_date, end_date))

    # ISS-110 修复：CSV 改为 StreamingResponse + 逐行生成器, 避免全量字符串驻留内存
    async def _stream_csv():
        # SEC-P1-003 修复：记录危机事件 CSV 导出审计日志
        # SEC-FIX (P2): 流开始前先写入审计日志——客户端中途断开时生成器收到
        # GeneratorExit, 原"流式完成后写入"的分支永远不执行, 导出已部分发生
        # 却无任何审计记录。content_size 改为流结束后 UPDATE 回填。
        audit_log = OperationLog(
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
                    "content_size": 0,
                    "completed": False,
                },
                ensure_ascii=False,
            ),
            ip_address=get_real_client_ip(request),
        )
        db.add(audit_log)
        await db.commit()

        content_size = 0
        try:
            async for chunk in service.iter_export_crisis_csv(start_date, end_date):
                content_size += len(chunk)
                yield chunk
        finally:
            # 流结束/中断均尝试回填实际传输字节数与完成状态
            # (shield: 客户端断开触发任务取消时, 回填 commit 仍尽力完成)
            try:
                audit_log.detail = json.dumps(
                    {
                        "start_date": start_date.isoformat(),
                        "end_date": end_date.isoformat(),
                        "filename": safe_filename,
                        "content_size": content_size,
                        "completed": True,
                    },
                    ensure_ascii=False,
                )
                await asyncio.shield(db.commit())
            except Exception:  # noqa: BLE001
                logger.exception("回填危机事件导出审计日志失败 (log_id=%s)", audit_log.id)

    return StreamingResponse(
        _stream_csv(),
        media_type="text/csv; charset=utf-8-sig",
        headers={
            # ISS-092 修复: filename* 按 RFC 5987 (UTF-8 百分号编码) 提供非 ASCII 文件名,
            # ASCII fallback 保留在 filename= 中, 兼容不支持 filename* 的旧客户端
            "Content-Disposition": (
                f'attachment; filename="{safe_filename}"; '
                f"filename*=UTF-8''{quote(safe_filename)}"
            )
        },
    )
