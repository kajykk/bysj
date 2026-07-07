from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_permission
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.rate_limit import limiter
from app.core.response import ok
from app.models.user import User
from app.schemas.canary import (
    CanaryCreateRequest,
    CanaryDeploymentResponse,
    CanaryListResponse,
    CanaryRollbackRequest,
    CanaryTrafficUpdateRequest,
)
from app.schemas.common import ApiResponse
from app.services.canary_manager import canary_manager

router = APIRouter(prefix="/canary", tags=["canary"])


@router.post(
    "/deployments", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
@limiter.limit("10/minute")
async def create_canary(
    request: Request,
    payload: CanaryCreateRequest,
    current_user: Annotated[User, Depends(require_permission("admin.predict.audit"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Create a new canary deployment."""
    try:
        canary = await canary_manager.start_canary(
            db_session=db,
            version=payload.version,
            traffic_percent=payload.traffic_percent,
            triggered_by=current_user.id,
            thresholds=payload.thresholds,
        )
        return ok(
            CanaryDeploymentResponse(
                id=canary.id,
                version=canary.version,
                traffic_percent=canary.traffic_percent,
                status=canary.status,
                started_at=canary.started_at.isoformat() if canary.started_at else None,
                created_at=canary.created_at.isoformat() if canary.created_at else None,
            ).model_dump()
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/deployments", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
@limiter.limit("30/minute")
async def list_canaries(
    request: Request,
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    status: Annotated[str | None, Query(description="Filter by status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """List canary deployments with optional filtering."""
    from sqlalchemy import func, select

    from app.models.monitoring import CanaryRecord

    stmt = select(CanaryRecord)
    if status:
        stmt = stmt.where(CanaryRecord.status == status)

    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # Get paginated results
    stmt = stmt.order_by(CanaryRecord.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    canaries = result.scalars().all()

    data = [
        {
            "id": c.id,
            "version": c.version,
            "traffic_percent": c.traffic_percent,
            "status": c.status,
            "auto_rollback_thresholds": c.auto_rollback_thresholds,
            "triggered_by": c.triggered_by,
            "started_at": c.started_at.isoformat() if c.started_at else None,
            "ended_at": c.ended_at.isoformat() if c.ended_at else None,
            "rollback_reason": c.rollback_reason,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in canaries
    ]

    return ok(
        CanaryListResponse(
            total=total, limit=limit, offset=offset, items=data
        ).model_dump()
    )


@router.get(
    "/deployments/{deployment_id}",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("30/minute")
async def get_canary(
    request: Request,
    deployment_id: Annotated[int, Path()],
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Get a specific canary deployment."""
    from sqlalchemy import select

    from app.models.monitoring import CanaryRecord

    result = await db.execute(
        select(CanaryRecord).where(CanaryRecord.id == deployment_id)
    )
    canary = result.scalar_one_or_none()

    if not canary:
        raise HTTPException(status_code=404, detail="Canary deployment not found")

    return ok(
        {
            "id": canary.id,
            "version": canary.version,
            "traffic_percent": canary.traffic_percent,
            "status": canary.status,
            "auto_rollback_thresholds": canary.auto_rollback_thresholds,
            "triggered_by": canary.triggered_by,
            "started_at": canary.started_at.isoformat() if canary.started_at else None,
            "ended_at": canary.ended_at.isoformat() if canary.ended_at else None,
            "rollback_reason": canary.rollback_reason,
            "created_at": canary.created_at.isoformat() if canary.created_at else None,
        }
    )


@router.patch(
    "/deployments/{deployment_id}/traffic",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("10/minute")
async def update_canary_traffic(
    request: Request,
    deployment_id: Annotated[int, Path()],
    payload: CanaryTrafficUpdateRequest,
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Update canary traffic percentage."""
    try:
        canary = await canary_manager.update_traffic_percent(
            db, deployment_id, payload.traffic_percent
        )
        return ok(
            {
                "id": canary.id,
                "version": canary.version,
                "traffic_percent": canary.traffic_percent,
                "status": canary.status,
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/deployments/{deployment_id}/pause",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("10/minute")
async def pause_canary(
    request: Request,
    deployment_id: Annotated[int, Path()],
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Pause a running canary deployment."""
    try:
        canary = await canary_manager.pause_canary(db, deployment_id)
        return ok(
            {
                "id": canary.id,
                "version": canary.version,
                "status": canary.status,
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/deployments/{deployment_id}/resume",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("10/minute")
async def resume_canary(
    request: Request,
    deployment_id: Annotated[int, Path()],
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Resume a paused canary deployment."""
    try:
        canary = await canary_manager.resume_canary(db, deployment_id)
        return ok(
            {
                "id": canary.id,
                "version": canary.version,
                "status": canary.status,
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/deployments/{deployment_id}/rollback",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("10/minute")
async def rollback_canary(
    request: Request,
    deployment_id: Annotated[int, Path()],
    payload: CanaryRollbackRequest,
    current_user: Annotated[User, Depends(require_permission("admin.predict.audit"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Rollback a canary deployment."""
    try:
        canary = await canary_manager.rollback_canary(
            db,
            deployment_id,
            f"{payload.reason} (by user {current_user.id})",
        )
        return ok(
            {
                "id": canary.id,
                "version": canary.version,
                "status": canary.status,
                "rollback_reason": canary.rollback_reason,
                "ended_at": canary.ended_at.isoformat() if canary.ended_at else None,
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/deployments/{deployment_id}/complete",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("10/minute")
async def complete_canary(
    request: Request,
    deployment_id: Annotated[int, Path()],
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Complete a successful canary deployment."""
    try:
        canary = await canary_manager.complete_canary(db, deployment_id)
        return ok(
            {
                "id": canary.id,
                "version": canary.version,
                "status": canary.status,
                "ended_at": canary.ended_at.isoformat() if canary.ended_at else None,
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/traffic-percentages", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
@limiter.limit("30/minute")
async def get_traffic_percentages(
    request: Request,
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    """Get available traffic percentage options."""
    return ok({"percentages": canary_manager.get_traffic_percentages()})
