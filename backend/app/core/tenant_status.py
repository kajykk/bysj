"""租户运行状态校验 SSOT（REV-2026-10-20 S7）。

背景：``tenant_admin.suspend`` 把 ``Tenant.status`` 写成 ``suspended``，
但全仓没有任何读取点 —— 唯一实现校验的 ``tenant_context.get_current_tenant``
在 ``app/api`` 下 ``Depends`` 命中 0 次。结果是"封禁开关"是假回执：
管理员暂停租户后，该租户用户仍可登录、旧 token 继续有效、全部业务接口照常读写。

本模块提供认证入口共用的最小校验：只回答"该租户是否被暂停"，
错误形态（HTTP 403 / ValueError / WS close code）由各入口自行决定。

关于"租户行不存在"：``tenants`` 是部署时的根表（seed 保证存在），
缺失只可能出现在测试库或异常部署。此处按**未暂停**处理，避免误伤；
已存在的 suspended 行则一律拒绝。

显式降级（ROUND_17 T1）：
- 缺租户行是一条**必然失真**的判定 —— 调用方拿到 False 会以为"租户正常"，
  实际是"无法判断"。保留 fail-open 决策（不因缺行而全站拒绝服务），但绝不
  允许它静默通过：每次命中都记
  ``silent_degradation_total{location="core.tenant_status.missing_tenant",tenant_id=...}``
  并写 warning 日志。运维可在 /metrics 按租户定位异常部署，而不是等事故复盘。
- 有租户行但状态为 suspended 时返回 True，调用方按各自入口语义拒绝
  （HTTP 403 / ValueError / WS 4003），该路径不计降级。
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.contracts import TENANT_STATUS_SUSPENDED
from app.core.degradation import record_silent_degradation
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
        # ROUND_17 T1：fail-open 但可观测（带 tenant_id 维度）
        record_silent_degradation(
            "core.tenant_status.missing_tenant", tenant_id=tenant_id
        )
        logger.warning(
            "tenant.status_check.missing_tenant tenant_id=%s "
            "(treating as not suspended; tenants is a seed-guaranteed root table)",
            tenant_id,
        )
        return False
    return tenant.status == TENANT_STATUS_SUSPENDED
