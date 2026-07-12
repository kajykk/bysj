"""Phase 5 租户级数据导出 API.

支持租户级别的数据导出，用于数据迁移、备份和合规审计：
- GET  /tenants/{id}/export  导出租户数据概要（JSON）

导出内容包含租户信息、用户统计、评估统计、审计日志摘要等。
不含敏感字段（密码哈希、PII 等），仅提供聚合统计和脱敏摘要。
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
from app.models.user import User
from app.api.v1.tenant_admin import _get_tenant_or_404, _serialize_tenant

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tenants", tags=["tenants-export"])


@router.get(
    "/{tenant_id}/export",
    response_model=None,
    responses=COMMON_ERROR_RESPONSES,
    summary="导出租户数据（管理员）",
)
@limiter.limit("5/minute")
async def export_tenant_data(
    request: Request,
    tenant_id: int,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    format: str = Query(default="summary", description="导出格式: summary"),
) -> dict[str, Any]:
    """导出租户数据概要.

    目前仅支持 ``summary`` 格式，返回聚合统计和脱敏摘要。
    后续可扩展 ``full`` 格式，导出完整数据集（需额外权限审批）。
    """
    if format != "summary":
        raise HTTPException(
            status_code=400,
            detail=f"不支持的导出格式: {format}，目前仅支持 summary",
        )

    tenant = await _get_tenant_or_404(db, tenant_id)

    # 在 flush/commit 前序列化租户信息
    tenant_info = _serialize_tenant(tenant)

    # 用户统计
    user_count = (
        await db.execute(
            select(func.count()).select_from(User).where(User.tenant_id == tenant_id)
        )
    ).scalar_one()

    # 按角色统计用户数
    role_counts_raw = (
        await db.execute(
            select(User.role, func.count())
            .where(User.tenant_id == tenant_id)
            .group_by(User.role)
        )
    ).all()
    role_counts = {role: count for role, count in role_counts_raw}

    # 审计日志统计（最近 30 天）
    from datetime import timedelta

    from app.api.v1.tenant_admin import _naive_utc_now

    thirty_days_ago = _naive_utc_now() - timedelta(days=30)
    audit_log_count_30d = (
        await db.execute(
            select(func.count())
            .select_from(OperationLog)
            .where(
                OperationLog.tenant_id == tenant_id,
                OperationLog.created_at >= thirty_days_ago,
            )
        )
    ).scalar_one()

    # 审计日志按 action_type 统计（最近 30 天）
    action_type_counts_raw = (
        await db.execute(
            select(OperationLog.action_type, func.count())
            .where(
                OperationLog.tenant_id == tenant_id,
                OperationLog.created_at >= thirty_days_ago,
            )
            .group_by(OperationLog.action_type)
        )
    ).all()
    action_type_counts = {
        action_type: count for action_type, count in action_type_counts_raw
    }

    # 记录导出操作
    db.add(
        OperationLog(
            operator_id=current_user.id,
            operator_role="admin",
            action_type="tenant.export",
            target_type="tenant",
            target_id=tenant_id,
            detail=f"format={format}",
            tenant_id=current_user.tenant_id,
        )
    )
    await db.commit()

    logger.info(
        "Tenant %s data exported by admin %s (format=%s)",
        tenant_id, current_user.id, format,
    )

    return ok({
        "tenant": tenant_info,
        "user_stats": {
            "total": user_count,
            "by_role": role_counts,
        },
        "audit_log_stats_30d": {
            "total": audit_log_count_30d,
            "by_action_type": action_type_counts,
        },
        "exported_by": current_user.id,
        "export_format": format,
    })
