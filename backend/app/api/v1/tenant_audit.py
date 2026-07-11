"""Phase 5 租户级审计查询 API.

按 ADR-001 决策实施审计隔离：
- GET /tenant-audit/logs          查询当前租户审计日志
- GET /tenant-audit/logs/{tenant_id}  管理员查询指定租户审计日志

审计日志按 tenant_id 隔离。普通管理员只能查看本租户审计日志。
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.rate_limit import limiter
from app.core.response import ok
from app.models.admin import OperationLog
from app.models.tenant import Tenant
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tenant-audit", tags=["tenant-audit"])


@router.get(
    "/logs",
    response_model=None,
    responses=COMMON_ERROR_RESPONSES,
    summary="查询当前租户审计日志（管理员）",
)
@limiter.limit("30/minute")
async def list_tenant_audit_logs(
    request: Request,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    action_type: str | None = Query(default=None, description="按动作类型过滤"),
) -> dict[str, Any]:
    """查询当前管理员所属租户的审计日志.

    自动按 current_user.tenant_id 过滤，确保租户隔离。
    """
    tenant_id = current_user.tenant_id

    stmt = select(OperationLog).where(OperationLog.tenant_id == tenant_id)
    count_stmt = (
        select(func.count())
        .select_from(OperationLog)
        .where(OperationLog.tenant_id == tenant_id)
    )

    if action_type:
        stmt = stmt.where(OperationLog.action_type == action_type)
        count_stmt = count_stmt.where(OperationLog.action_type == action_type)

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.order_by(OperationLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    logs = (await db.execute(stmt)).scalars().all()

    items = [
        {
            "id": log.id,
            "operator_id": log.operator_id,
            "operator_role": log.operator_role,
            "action_type": log.action_type,
            "target_type": log.target_type,
            "target_id": log.target_id,
            "detail": log.detail,
            "ip_address": log.ip_address,
            "tenant_id": log.tenant_id,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]

    return ok({
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "tenant_id": tenant_id,
    })


@router.get(
    "/logs/{tenant_id}",
    response_model=None,
    responses=COMMON_ERROR_RESPONSES,
    summary="查询指定租户审计日志（管理员）",
)
@limiter.limit("30/minute")
async def list_tenant_audit_logs_by_id(
    request: Request,
    tenant_id: int,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    action_type: str | None = Query(default=None, description="按动作类型过滤"),
) -> dict[str, Any]:
    """查询指定租户的审计日志.

    管理员可查询任意租户的审计日志（跨租户审计权限）。
    """
    # 验证租户存在
    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="租户不存在")

    stmt = select(OperationLog).where(OperationLog.tenant_id == tenant_id)
    count_stmt = (
        select(func.count())
        .select_from(OperationLog)
        .where(OperationLog.tenant_id == tenant_id)
    )

    if action_type:
        stmt = stmt.where(OperationLog.action_type == action_type)
        count_stmt = count_stmt.where(OperationLog.action_type == action_type)

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.order_by(OperationLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    logs = (await db.execute(stmt)).scalars().all()

    items = [
        {
            "id": log.id,
            "operator_id": log.operator_id,
            "operator_role": log.operator_role,
            "action_type": log.action_type,
            "target_type": log.target_type,
            "target_id": log.target_id,
            "detail": log.detail,
            "ip_address": log.ip_address,
            "tenant_id": log.tenant_id,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]

    return ok({
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "tenant_id": tenant_id,
        "tenant_name": tenant.name,
        "tenant_code": tenant.code,
    })
