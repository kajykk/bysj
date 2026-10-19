"""租户运行状态校验 SSOT（REV-2026-10-20 S7）。

背景：``tenant_admin.suspend`` 把 ``Tenant.status`` 写成 ``suspended``，
但全仓没有任何读取点 —— 唯一实现校验的 ``tenant_context.get_current_tenant``
在 ``app/api`` 下 ``Depends`` 命中 0 次。结果是"封禁开关"是假回执：
管理员暂停租户后，该租户用户仍可登录、旧 token 继续有效、全部业务接口照常读写。

本模块提供认证入口共用的最小校验：只回答"该租户是否被暂停"，
错误形态（HTTP 403 / ValueError / WS close code）由各入口自行决定。

关于"租户行不存在"：``tenants`` 是部署时的根表（seed 保证存在），
缺失只可能出现在测试库或异常部署。此处按**未暂停**处理，避免误伤；
已存在的 suspended 行则一律拒绝。这个取舍写在 docstring 里，
不用沉默的 ``except`` 掩盖。
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.contracts import TENANT_STATUS_SUSPENDED
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)


async def is_tenant_suspended(db: AsyncSession, tenant_id: int | None) -> bool:
    """判断租户是否处于 suspended 状态。

    Args:
        db: 当前请求/连接使用的 AsyncSession
        tenant_id: 用户所属租户（None 视为默认租户，返回 False 由调用方兜底）

    Returns:
        True 仅当租户行存在且 status == 'suspended'。
    """
    if tenant_id is None:
        return False
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        logger.warning(
            "tenant.status_check.missing_tenant tenant_id=%s "
            "(treating as not suspended; tenants is a seed-guaranteed root table)",
            tenant_id,
        )
        return False
    return tenant.status == TENANT_STATUS_SUSPENDED
