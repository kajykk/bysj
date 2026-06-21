from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.database import AsyncSessionLocal
from app.core.deps import require_permission
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.response import ok
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.review import (
    CrisisEventFilter,
    ReviewEscalateRequest,
    ReviewResolveRequest,
    ReviewTaskFilter,
)
from app.services.review_service import CrisisEventService, ReviewService

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("/stats", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def get_review_stats(
    current_user: Annotated[User, Depends(require_permission("review.view"))],
) -> dict:
    """获取复核统计"""
    async with AsyncSessionLocal() as db:
        service = ReviewService(db)
        stats = await service.get_review_stats()
        return ok(stats.model_dump())


@router.get("/crisis-events", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def list_crisis_events(
    current_user: Annotated[User, Depends(require_permission("crisis_event.view"))],
    status: str | None = Query(None, description="筛选状态"),
    start_date: str | None = Query(None, description="开始日期"),
    end_date: str | None = Query(None, description="结束日期"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
) -> dict:
    """查询危机事件列表（管理员权限）"""
    async with AsyncSessionLocal() as db:
        service = CrisisEventService(db)
        filter_data = CrisisEventFilter(
            status=status,
            page=page,
            page_size=page_size,
        )
        result = await service.get_crisis_events(filter_data)
        return ok(result)


@router.get("", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def list_reviews(
    current_user: Annotated[User, Depends(require_permission("review.view"))],
    status: str | None = Query(None, description="筛选状态"),
    priority: str | None = Query(None, description="筛选优先级"),
    assigned_to: int | None = Query(None, description="筛选分配给的咨询师"),
    user_id: int | None = Query(None, description="筛选用户"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
) -> dict:
    """查询复核任务列表"""
    async with AsyncSessionLocal() as db:
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


@router.get("/{review_id}", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def get_review(
    review_id: int,
    current_user: Annotated[User, Depends(require_permission("review.view"))],
) -> dict:
    """查看复核详情"""
    async with AsyncSessionLocal() as db:
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
async def assign_review(
    review_id: int,
    current_user: Annotated[User, Depends(require_permission("review.handle"))],
) -> dict:
    """分配复核任务"""
    async with AsyncSessionLocal() as db:
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
async def resolve_review(
    review_id: int,
    payload: ReviewResolveRequest,
    current_user: Annotated[User, Depends(require_permission("review.handle"))],
) -> dict:
    """处理复核任务"""
    async with AsyncSessionLocal() as db:
        service = ReviewService(db)
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
async def escalate_review(
    review_id: int,
    payload: ReviewEscalateRequest,
    current_user: Annotated[User, Depends(require_permission("review.handle"))],
) -> dict:
    """升级复核任务"""
    async with AsyncSessionLocal() as db:
        service = ReviewService(db)
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
