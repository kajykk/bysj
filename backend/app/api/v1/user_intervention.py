from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.database import get_db
from app.core.deps import require_role
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.response import ok
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.intervention import (
    TaskCompleteRequest,
    TaskFeedbackRequest,
    TaskStatusUpdateRequest,
)
from app.services.intervention_service import InterventionService

router = APIRouter(prefix="/user/intervention", tags=["user-intervention"])


async def _log_intervention_op(
    db: AsyncSession,
    user: User,
    action_type: str,
    task_id: int,
    detail: dict | None = None,
    *,
    # P2-33 第六批：审计上下文由调用方（API 端点）穿入；request 缺失时
    # helper 记 no_request，ip 为 None（用户自助操作，ip 有助于追溯共享设备）。
    request: Request | None = None,
) -> None:
    """M-API-17 修复：为干预任务状态变更记录 OperationLog 审计日志.

    P2-33 第六批：改走统一审计 helper（detail 统一 JSON 对象、tenant 落列）。
    本端点的操作者即资源 owner（require_role("user") + 服务层校验归属），
    tenant_id 取操作者自己的租户。
    """
    await record_audit(
        db,
        actor_id=user.id,
        actor_role=user.role,
        action=action_type,
        target_type="intervention_task",
        target_id=task_id,
        detail=detail or {},
        request=request,
        tenant_id=user.tenant_id,
    )


@router.get("/active", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def get_active_intervention(
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = InterventionService(db)
    data = await service.get_active(current_user.id, create_missing=False)
    if "plan" in data:
        data["plan"].setdefault("dominant_modality", None)
    for task in data.get("tasks", []):
        task.setdefault("modality_based_actions", [])
    return ok(data)


@router.get("/history", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def get_intervention_history(
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> dict:
    service = InterventionService(db)
    data = await service.get_history(current_user.id, page, page_size)
    for item in data.get("items", []):
        item.setdefault("dominant_modality", None)
    return ok(data)


@router.get("/stats", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def get_intervention_stats(
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """干预计划统计（SQL 层聚合）。

    P1-15 / F-03：替代前端 ``page_size:200`` 拉全量到浏览器 filter 的做法 ——
    数据超 200 条时分子截断、分母不截断，统计结果是错的。口径与
    ``get_history`` 一致（见 InterventionService.get_stats 文档）。
    """
    service = InterventionService(db)
    return ok(await service.get_stats(current_user.id))


@router.put(
    "/tasks/{task_id}/complete",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
async def complete_task(
    task_id: int,
    payload: TaskCompleteRequest,
    request: Request,
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = InterventionService(db)
    success, reason = await service.complete_task(
        current_user.id,
        task_id,
        payload.scheduled_date,
        # P2-33 第六批：审计上下文（ip / 租户落列）
        request=request,
        tenant_id=current_user.tenant_id,
    )
    if not success and reason is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not success:
        raise HTTPException(status_code=409, detail=reason)
    # M-API-17 修复：记录状态变更审计日志
    await _log_intervention_op(
        db, current_user, "intervention_task_complete", task_id, request=request
    )
    await db.commit()
    return ok({"message": "任务已完成"})


@router.put(
    "/tasks/{task_id}/feedback",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
async def feedback_task(
    task_id: int,
    payload: TaskFeedbackRequest,
    request: Request,
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = InterventionService(db)
    success, reason = await service.feedback_task(
        user_id=current_user.id,
        task_id=task_id,
        scheduled_date=payload.scheduled_date,
        feedback_score=payload.feedback_score,
        feedback_note=payload.feedback_note,
        # P2-33 第六批：审计上下文（ip / 租户落列）
        request=request,
        tenant_id=current_user.tenant_id,
    )
    if not success and reason is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not success:
        raise HTTPException(status_code=409, detail=reason)
    # M-API-17 修复：记录状态变更审计日志
    await _log_intervention_op(
        db,
        current_user,
        "intervention_task_feedback",
        task_id,
        {"feedback_score": payload.feedback_score},
        request=request,
    )
    await db.commit()
    return ok({"message": "反馈已提交"})


@router.put(
    "/tasks/{task_id}/missed",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
async def mark_task_missed(
    task_id: int,
    payload: TaskStatusUpdateRequest,
    request: Request,
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = InterventionService(db)
    success, reason = await service.mark_task_missed(
        current_user.id, task_id, payload.scheduled_date, payload.note
    )
    if not success and reason is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not success:
        raise HTTPException(status_code=409, detail=reason)
    # L-API-11 修复：补全 mark_task_missed 缺失的 OperationLog 审计日志
    await _log_intervention_op(
        db, current_user, "intervention_task_missed", task_id, request=request
    )
    await db.commit()
    return ok({"message": "任务已标记为未完成"})


@router.put(
    "/tasks/{task_id}/skip",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
async def skip_task(
    task_id: int,
    payload: TaskStatusUpdateRequest,
    request: Request,
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = InterventionService(db)
    success, reason = await service.skip_task(
        current_user.id, task_id, payload.scheduled_date, payload.note
    )
    if not success and reason is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not success:
        raise HTTPException(status_code=409, detail=reason)
    # M-API-17 修复：记录状态变更审计日志
    await _log_intervention_op(
        db, current_user, "intervention_task_skip", task_id, request=request
    )
    await db.commit()
    return ok({"message": "任务已跳过"})


@router.put(
    "/tasks/{task_id}/postpone",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
async def postpone_task(
    task_id: int,
    payload: TaskStatusUpdateRequest,
    request: Request,
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    if payload.postpone_to is None:
        raise HTTPException(status_code=400, detail="postpone_to不能为空")

    service = InterventionService(db)
    success, reason = await service.postpone_task(
        current_user.id,
        task_id,
        payload.scheduled_date,
        payload.postpone_to,
        payload.note,
    )
    if not success and reason is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not success:
        raise HTTPException(status_code=409, detail=reason)
    # M-API-17 修复：记录状态变更审计日志
    await _log_intervention_op(
        db,
        current_user,
        "intervention_task_postpone",
        task_id,
        {"postpone_to": str(payload.postpone_to)},
        request=request,
    )
    await db.commit()
    return ok({"message": "任务已延期"})
