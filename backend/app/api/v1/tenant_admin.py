"""Phase 5 租户管理 API.

按 ADR-001 决策实施租户管理：
- POST   /tenants              创建租户
- GET    /tenants              列出租户
- GET    /tenants/{id}         获取租户详情
- PUT    /tenants/{id}         更新租户配置
- POST   /tenants/{id}/suspend  暂停租户
- POST   /tenants/{id}/activate 激活租户

仅管理员可访问。所有操作记录到 OperationLog 审计日志。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
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
router = APIRouter(prefix="/tenants", tags=["tenants"])


# =========================================================================
# 请求模型
# =========================================================================


class CreateTenantRequest(BaseModel):
    """创建租户请求."""

    name: str = Field(..., min_length=2, max_length=100, description="租户名称")
    code: str = Field(
        ...,
        min_length=2,
        max_length=50,
        pattern=r"^[a-z0-9_]+$",
        description="租户编码（小写字母/数字/下划线）",
    )
    config: dict[str, Any] | None = Field(default=None, description="租户配置")


class UpdateTenantRequest(BaseModel):
    """更新租户请求."""

    name: str | None = Field(default=None, min_length=2, max_length=100)
    config: dict[str, Any] | None = None


class SuspendTenantRequest(BaseModel):
    """暂停租户请求."""

    reason: str = Field(..., min_length=1, max_length=500, description="暂停原因")


class ActivateTenantRequest(BaseModel):
    """激活租户请求."""

    reason: str = Field(..., min_length=1, max_length=500, description="激活原因")


# =========================================================================
# 响应序列化
# =========================================================================


def _serialize_tenant(t: Tenant) -> dict[str, Any]:
    """序列化租户对象为字典."""
    return {
        "id": t.id,
        "name": t.name,
        "code": t.code,
        "status": t.status,
        "config": t.config,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def _naive_utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# =========================================================================
# 端点
# =========================================================================


@router.post(
    "",
    response_model=None,
    responses=COMMON_ERROR_RESPONSES,
    summary="创建租户（管理员）",
)
@limiter.limit("10/minute")
async def create_tenant(
    request: Request,
    payload: CreateTenantRequest,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """创建新租户.

    租户 code 全局唯一，用于请求头/子域名解析。
    """
    # 检查 code 唯一性
    existing = (
        await db.execute(select(Tenant).where(Tenant.code == payload.code))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"租户编码已存在: {payload.code}")

    tenant = Tenant(
        name=payload.name,
        code=payload.code,
        status="active",
        config=payload.config,
    )
    db.add(tenant)
    await db.flush()

    db.add(
        OperationLog(
            operator_id=current_user.id,
            operator_role="admin",
            action_type="tenant.create",
            target_type="tenant",
            target_id=tenant.id,
            detail=f"name={payload.name}; code={payload.code}",
            tenant_id=current_user.tenant_id,
        )
    )
    await db.commit()

    logger.info("Tenant %s created by admin %s", tenant.code, current_user.id)
    return ok(_serialize_tenant(tenant))


@router.get(
    "",
    response_model=None,
    responses=COMMON_ERROR_RESPONSES,
    summary="列出租户（管理员）",
)
@limiter.limit("30/minute")
async def list_tenants(
    request: Request,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
) -> dict[str, Any]:
    """列出所有租户（分页）."""
    stmt = select(Tenant)
    if status_filter:
        stmt = stmt.where(Tenant.status == status_filter)

    # 总数
    count_stmt = select(func.count()).select_from(Tenant)
    if status_filter:
        count_stmt = count_stmt.where(Tenant.status == status_filter)
    total = (await db.execute(count_stmt)).scalar_one()

    # 分页
    stmt = stmt.order_by(Tenant.id.asc()).offset((page - 1) * page_size).limit(page_size)
    tenants = (await db.execute(stmt)).scalars().all()

    return ok({
        "items": [_serialize_tenant(t) for t in tenants],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.get(
    "/{tenant_id}",
    response_model=None,
    responses=COMMON_ERROR_RESPONSES,
    summary="获取租户详情（管理员）",
)
@limiter.limit("30/minute")
async def get_tenant(
    request: Request,
    tenant_id: int,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """获取指定租户详情."""
    tenant = await _get_tenant_or_404(db, tenant_id)
    return ok(_serialize_tenant(tenant))


@router.put(
    "/{tenant_id}",
    response_model=None,
    responses=COMMON_ERROR_RESPONSES,
    summary="更新租户配置（管理员）",
)
@limiter.limit("10/minute")
async def update_tenant(
    request: Request,
    tenant_id: int,
    payload: UpdateTenantRequest,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """更新租户名称或配置."""
    tenant = await _get_tenant_or_404(db, tenant_id)

    changes: list[str] = []
    if payload.name is not None and payload.name != tenant.name:
        tenant.name = payload.name
        changes.append(f"name={payload.name}")
    if payload.config is not None:
        tenant.config = payload.config
        changes.append("config updated")

    if not changes:
        raise HTTPException(status_code=400, detail="未提供任何更新字段")

    # 在 flush 前序列化，避免 flush 后 onupdate=func.now() 导致 updated_at 属性
    # 被 expire，访问时触发 async lazy load (MissingGreenlet)
    result = _serialize_tenant(tenant)

    await db.flush()
    db.add(
        OperationLog(
            operator_id=current_user.id,
            operator_role="admin",
            action_type="tenant.update",
            target_type="tenant",
            target_id=tenant_id,
            detail="; ".join(changes),
            tenant_id=current_user.tenant_id,
        )
    )
    await db.commit()

    logger.info("Tenant %s updated by admin %s", tenant_id, current_user.id)
    return ok(result)


@router.post(
    "/{tenant_id}/suspend",
    response_model=None,
    responses=COMMON_ERROR_RESPONSES,
    summary="暂停租户（管理员）",
)
@limiter.limit("10/minute")
async def suspend_tenant(
    request: Request,
    tenant_id: int,
    payload: SuspendTenantRequest,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """暂停租户.

    暂停后该租户所有请求将被拒绝（get_current_tenant 抛 403）。
    """
    tenant = await _get_tenant_or_404(db, tenant_id)

    if tenant.status == "suspended":
        raise HTTPException(status_code=409, detail="租户已处于暂停状态")

    previous_status = tenant.status
    tenant.status = "suspended"
    await db.flush()

    db.add(
        OperationLog(
            operator_id=current_user.id,
            operator_role="admin",
            action_type="tenant.suspend",
            target_type="tenant",
            target_id=tenant_id,
            detail=f"reason={payload.reason}; previous_status={previous_status}",
            tenant_id=current_user.tenant_id,
        )
    )
    await db.commit()

    logger.warning(
        "Tenant %s suspended by admin %s: %s",
        tenant_id, current_user.id, payload.reason,
    )
    return ok({
        "tenant_id": tenant_id,
        "status": "suspended",
        "suspended_by": current_user.id,
        "suspended_at": _naive_utc_now().isoformat(),
        "reason": payload.reason,
    })


@router.post(
    "/{tenant_id}/activate",
    response_model=None,
    responses=COMMON_ERROR_RESPONSES,
    summary="激活租户（管理员）",
)
@limiter.limit("10/minute")
async def activate_tenant(
    request: Request,
    tenant_id: int,
    payload: ActivateTenantRequest,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """激活已暂停的租户."""
    tenant = await _get_tenant_or_404(db, tenant_id)

    if tenant.status == "active":
        raise HTTPException(status_code=409, detail="租户已处于活跃状态")

    previous_status = tenant.status
    tenant.status = "active"
    await db.flush()

    db.add(
        OperationLog(
            operator_id=current_user.id,
            operator_role="admin",
            action_type="tenant.activate",
            target_type="tenant",
            target_id=tenant_id,
            detail=f"reason={payload.reason}; previous_status={previous_status}",
            tenant_id=current_user.tenant_id,
        )
    )
    await db.commit()

    logger.info(
        "Tenant %s activated by admin %s: %s",
        tenant_id, current_user.id, payload.reason,
    )
    return ok({
        "tenant_id": tenant_id,
        "status": "active",
        "activated_by": current_user.id,
        "activated_at": _naive_utc_now().isoformat(),
        "reason": payload.reason,
    })


@router.get(
    "/{tenant_id}/stats",
    response_model=None,
    responses=COMMON_ERROR_RESPONSES,
    summary="租户统计（管理员）",
)
@limiter.limit("30/minute")
async def get_tenant_stats(
    request: Request,
    tenant_id: int,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """获取租户统计信息（用户数、审计日志数等）."""
    await _get_tenant_or_404(db, tenant_id)

    # 用户数
    user_count = (
        await db.execute(
            select(func.count()).select_from(User).where(User.tenant_id == tenant_id)
        )
    ).scalar_one()

    # 审计日志数（最近 30 天）
    from datetime import timedelta

    thirty_days_ago = _naive_utc_now() - timedelta(days=30)
    audit_log_count = (
        await db.execute(
            select(func.count())
            .select_from(OperationLog)
            .where(
                OperationLog.tenant_id == tenant_id,
                OperationLog.created_at >= thirty_days_ago,
            )
        )
    ).scalar_one()

    return ok({
        "tenant_id": tenant_id,
        "user_count": user_count,
        "audit_log_count_30d": audit_log_count,
    })


# =========================================================================
# 辅助函数
# =========================================================================


async def _get_tenant_or_404(db: AsyncSession, tenant_id: int) -> Tenant:
    """获取租户或抛 404."""
    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="租户不存在")
    return tenant
