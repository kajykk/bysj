from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_permission
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.rate_limit import limiter
from app.core.response import ok
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.review import (
    CrisisCloseRequest,
    CrisisEscalateRequest,
    CrisisEventFilter,
    CrisisHandleRequest,
    ReviewEscalateRequest,
    ReviewResolveRequest,
    ReviewTaskFilter,
)
from app.services.review_service import CrisisEventService, ReviewService

router = APIRouter(prefix="/reviews", tags=["reviews"])


def _parse_date_param(value: str | None) -> datetime | None:
    """M-API-2 修复：将日期字符串解析为 naive UTC datetime，用于 DB 比较.

    支持 ISO 8601 格式（含 'Z' 后缀）。aware datetime 转为 naive UTC。
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"无效的日期格式: {value}") from exc
    # 统一为 naive UTC 用于与 naive DB 列比较
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


@router.get("/stats", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("60/minute")
async def get_review_stats(
    request: Request,
    current_user: Annotated[User, Depends(require_permission("review.view"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """获取复核统计"""
    service = ReviewService(db)
    stats = await service.get_review_stats()
    return ok(stats.model_dump())


@router.get(
    "/crisis-events", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
@limiter.limit("60/minute")
async def list_crisis_events(
    request: Request,
    current_user: Annotated[User, Depends(require_permission("crisis_event.view"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    status: str | None = Query(None, description="筛选状态"),
    start_date: str | None = Query(None, description="开始日期"),
    end_date: str | None = Query(None, description="结束日期"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
) -> dict:
    """查询危机事件列表（管理员权限）"""
    service = CrisisEventService(db)
    # M-API-2 修复：将 start_date/end_date 传入 filter 并应用到查询，
    # 原实现接收参数但完全忽略，导致时间范围过滤无效
    filter_data = CrisisEventFilter(
        status=status,
        start_date=_parse_date_param(start_date),
        end_date=_parse_date_param(end_date),
        page=page,
        page_size=page_size,
    )
    result = await service.get_crisis_events(filter_data)
    return ok(result)


# ISS-072 修复：危机事件状态流转端点（处理 / 升级 / 关闭）


@router.post(
    "/crisis-events/{event_id}/handle",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("30/minute")
async def handle_crisis_event(
    event_id: int,
    payload: CrisisHandleRequest,
    request: Request,
    current_user: Annotated[User, Depends(require_permission("crisis_event.handle"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """ISS-072: 处理危机事件 (detected|reviewed|escalated → reviewed)"""
    service = CrisisEventService(db)
    try:
        event = await service.handle_crisis_event(
            event_id=event_id,
            handled_by=current_user.id,
            action=payload.action,
            note=payload.note,
        )
        return ok(service._to_response(event))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/crisis-events/{event_id}/escalate",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("30/minute")
async def escalate_crisis_event(
    event_id: int,
    payload: CrisisEscalateRequest,
    request: Request,
    current_user: Annotated[User, Depends(require_permission("crisis_event.handle"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """ISS-072: 升级危机事件 (detected|reviewed → escalated)"""
    service = CrisisEventService(db)
    try:
        event = await service.escalate_crisis_event(
            event_id=event_id,
            handled_by=current_user.id,
            reason=payload.reason,
        )
        return ok(service._to_response(event))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/crisis-events/{event_id}/close",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("30/minute")
async def close_crisis_event(
    event_id: int,
    payload: CrisisCloseRequest,
    request: Request,
    current_user: Annotated[User, Depends(require_permission("crisis_event.handle"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """ISS-072: 关闭危机事件 (detected|reviewed|escalated → resolved)"""
    service = CrisisEventService(db)
    try:
        event = await service.close_crisis_event(
            event_id=event_id,
            handled_by=current_user.id,
            note=payload.note,
        )
        return ok(service._to_response(event))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("60/minute")
async def list_reviews(
    request: Request,
    current_user: Annotated[User, Depends(require_permission("review.view"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    status: str | None = Query(None, description="筛选状态"),
    priority: str | None = Query(None, description="筛选优先级"),
    assigned_to: int | None = Query(None, description="筛选分配给的咨询师"),
    user_id: int | None = Query(None, description="筛选用户"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
) -> dict:
    """查询复核任务列表"""
    service = ReviewService(db)

    # 权限控制：咨询师只能查看分配给自己的
    if current_user.role == "counselor":
        assigned_to = current_user.id

    filter_data = ReviewTaskFilter(
        status=status,
        priority=priority,
        assigned_to=assigned_to,
        user_id=user_id,
        page=page,
        page_size=page_size,
    )

    result = await service.get_reviews(filter_data)
    return ok(result.model_dump())


@router.get(
    "/{review_id}", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
@limiter.limit("60/minute")
async def get_review(
    review_id: int,
    request: Request,
    current_user: Annotated[User, Depends(require_permission("review.view"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """查看复核详情"""
    service = ReviewService(db)
    task = await service.get_review_by_id(review_id)
    if not task:
        raise HTTPException(status_code=404, detail="复核任务不存在")

    # 权限控制：咨询师只能查看分配给自己的
    if current_user.role == "counselor" and task.assigned_to != current_user.id:
        raise HTTPException(status_code=403, detail="无权查看此复核任务")

    return ok(service.to_response(task).model_dump())


@router.post(
    "/{review_id}/assign",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("30/minute")
async def assign_review(
    review_id: int,
    request: Request,
    current_user: Annotated[User, Depends(require_permission("review.handle"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """分配复核任务"""
    service = ReviewService(db)
    try:
        task = await service.assign_review(review_id, current_user.id)
        return ok(service.to_response(task).model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{review_id}/resolve",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("30/minute")
async def resolve_review(
    review_id: int,
    payload: ReviewResolveRequest,
    request: Request,
    current_user: Annotated[User, Depends(require_permission("review.handle"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """处理复核任务"""
    service = ReviewService(db)
    # C-API-5 修复：咨询师水平越权防护 - resolve 必须校验 owner。
    # 原实现仅校验 review.handle 权限，任何咨询师都能 resolve 任意任务（含未分配给自己的）。
    task = await service.get_review_by_id(review_id)
    if not task:
        raise HTTPException(status_code=404, detail="复核任务不存在")
    if current_user.role == "counselor" and task.assigned_to != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作此复核任务")
    try:
        task = await service.resolve_review(
            review_id,
            current_user.id,
            payload.resolution_note,
            is_admin=current_user.role == "admin",
        )
        return ok(service.to_response(task).model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{review_id}/escalate",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("30/minute")
async def escalate_review(
    review_id: int,
    payload: ReviewEscalateRequest,
    request: Request,
    current_user: Annotated[User, Depends(require_permission("review.handle"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """升级复核任务"""
    service = ReviewService(db)
    # C-API-5 修复：咨询师水平越权防护 - escalate 必须校验 owner。
    # 原实现仅校验 review.handle 权限，任何咨询师都能 escalate 任意任务（含未分配给自己的）。
    task = await service.get_review_by_id(review_id)
    if not task:
        raise HTTPException(status_code=404, detail="复核任务不存在")
    if current_user.role == "counselor" and task.assigned_to != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作此复核任务")
    try:
        task = await service.escalate_review(
            review_id,
            current_user.id,
            payload.reason,
            is_admin=current_user.role == "admin",
        )
        return ok(service.to_response(task).model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
