"""Phase 5 租户品牌配置 API.

提供租户级别的品牌定制能力，支持多租户场景下每个租户独立展示：
- GET  /tenants/{id}/branding  获取品牌配置
- PUT  /tenants/{id}/branding  更新品牌配置

品牌配置存储在 Tenant.config["branding"] 子键中，与功能开关等其他配置隔离。
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.tenant_admin import _get_tenant_or_404
from app.core.contracts import DEFAULT_TENANT_ID
from app.core.database import get_db
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.rate_limit import limiter
from app.core.response import ok
from app.core.tenant_context import require_role_tenant_scoped
from app.models.admin import OperationLog
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tenants", tags=["tenants-branding"])


def _assert_tenant_owned_by(tenant_id: int, current_user: User) -> None:
    """SEC-FIX (租户越权) AUDIT-2026-10-01 (P0-1)：路径 tenant_id 必须归属操作者租户。

    沿用 ``tenant_export.py:58-71`` 的既有模式。必要性：
    ``require_role_tenant_scoped`` 只校验"请求头租户 == 用户租户"，**与路径参数脱钩** ——
    因此租户 A 的管理员只要不带 ``X-Tenant-ID`` 头，仍可 ``PUT /tenants/{B}/branding``
    改写 B 的品牌配置（含 10000 字符的 ``custom_css``，构成跨租户存储型 XSS 投放面）。
    默认租户管理员保留平台级放行（与 tenant_admin 的全局管理语义一致）。
    """
    user_tenant = current_user.tenant_id or DEFAULT_TENANT_ID
    if tenant_id != user_tenant and user_tenant != DEFAULT_TENANT_ID:
        logger.warning(
            "Tenant branding blocked (IDOR): admin_tenant=%s, target_tenant=%s, admin_id=%s",
            user_tenant,
            tenant_id,
            current_user.id,
        )
        raise HTTPException(status_code=403, detail="只能管理本租户的品牌配置")

# 品牌配置允许的字段及校验规则
BRANDING_FIELDS = {
    "display_name", "logo_url", "primary_color",
    "secondary_color", "favicon_url", "custom_css",
}


# =========================================================================
# 请求模型
# =========================================================================


class BrandingConfig(BaseModel):
    """租户品牌配置."""

    display_name: str | None = Field(default=None, max_length=100, description="展示名称")
    logo_url: str | None = Field(default=None, max_length=500, description="Logo URL")
    primary_color: str | None = Field(
        default=None,
        pattern=r"^#[0-9a-fA-F]{6}$",
        description="主色调（十六进制，如 #1a73e8）",
    )
    secondary_color: str | None = Field(
        default=None,
        pattern=r"^#[0-9a-fA-F]{6}$",
        description="辅助色调",
    )
    favicon_url: str | None = Field(default=None, max_length=500, description="Favicon URL")
    custom_css: str | None = Field(default=None, max_length=10000, description="自定义 CSS")


class UpdateBrandingRequest(BaseModel):
    """更新品牌配置请求."""

    branding: BrandingConfig


# =========================================================================
# 端点
# =========================================================================


@router.get(
    "/{tenant_id}/branding",
    response_model=None,
    responses=COMMON_ERROR_RESPONSES,
    summary="获取租户品牌配置（管理员）",
)
@limiter.limit("30/minute")
async def get_tenant_branding(
    request: Request,
    tenant_id: int,
    current_user: Annotated[User, Depends(require_role_tenant_scoped("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """获取指定租户的品牌配置."""
    _assert_tenant_owned_by(tenant_id, current_user)
    tenant = await _get_tenant_or_404(db, tenant_id)
    config = tenant.config or {}
    branding = config.get("branding", {})
    return ok({
        "tenant_id": tenant_id,
        "tenant_code": tenant.code,
        "branding": branding,
    })


@router.put(
    "/{tenant_id}/branding",
    response_model=None,
    responses=COMMON_ERROR_RESPONSES,
    summary="更新租户品牌配置（管理员）",
)
@limiter.limit("10/minute")
async def update_tenant_branding(
    request: Request,
    tenant_id: int,
    payload: UpdateBrandingRequest,
    current_user: Annotated[User, Depends(require_role_tenant_scoped("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """更新租户品牌配置.

    品牌配置存储在 ``tenant.config["branding"]`` 中，与其他配置隔离。
    仅更新提供的字段，未提供的字段保持不变。
    """
    _assert_tenant_owned_by(tenant_id, current_user)
    tenant = await _get_tenant_or_404(db, tenant_id)

    # 合并品牌配置
    config = dict(tenant.config) if tenant.config else {}
    existing_branding = config.get("branding", {})
    new_branding = payload.branding.model_dump(exclude_none=True)

    # 合并：新值覆盖旧值
    merged_branding = {**existing_branding, **new_branding}
    config["branding"] = merged_branding
    tenant.config = config

    # 在 flush 前序列化，避免 async lazy load
    result = {
        "tenant_id": tenant_id,
        "branding": merged_branding,
    }

    await db.flush()
    db.add(
        OperationLog(
            operator_id=current_user.id,
            operator_role="admin",
            action_type="tenant.branding.update",
            target_type="tenant",
            target_id=tenant_id,
            detail=f"fields={list(new_branding.keys())}",
            tenant_id=current_user.tenant_id,
        )
    )
    await db.commit()

    logger.info("Tenant %s branding updated by admin %s", tenant_id, current_user.id)
    return ok(result)
