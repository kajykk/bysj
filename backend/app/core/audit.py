"""P2-33: 统一审计 helper（SSOT）。

归属规则（固化）：
- 写操作同步落库：调用方 `await record_audit(...)` 内直接 `db.add + flush`，
  不经队列，审计行与业务写同事务可见。
- 读操作不落库：读路径审计改走异步队列（Celery `tasks.audit`），本 helper
  只服务写路径；读路径调用本 helper 直接抛 TypeError，防止误用。
- `ip_address` 一律从 `request` 取（`get_real_client_ip`）；`request` 存在时忽略
  调用方传入的 `ip_address`（禁止手填覆盖）。无 request 时（纯服务层内部写）才
  回退用调用方传入的 `ip_address`——第六批新增，用于迁移那些历史上由调用方
  显式传 ip 的审计点，避免"迁移后 ip 静默丢失"（审计质量倒退）。
  两者都无则记 None 并在 detail 注明。
- `tenant_id` 同时写入列与 detail：列做租户隔离查询，detail 保留可读归属；
  调用方必须显式传 tenant_id（可为 None 表示平台级操作，此时列记平台默认租户），漏传 TypeError。
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.contracts import DEFAULT_TENANT_ID
from app.core.rate_limit import get_real_client_ip
from app.models.admin import OperationLog

_MISSING: Any = object()


async def record_audit(
    db: AsyncSession,
    *,
    actor_id: int | None,
    actor_role: str,
    action: str,
    target_type: str,
    target_id: int | None,
    detail: dict[str, Any] | None = None,
    request: Request | None = None,
    tenant_id: int | None | Any = _MISSING,
    # 仅在 request 为 None 时生效的 ip 兜底（迁移历史"调用方显式传 ip"的审计点）
    ip_address: str | None = None,
) -> OperationLog:
    """写操作审计唯一入口（同步落库）。

    tenant_id 为必填关键字参数（显式传 None 表示平台级操作），漏传 TypeError。
    """
    if tenant_id is _MISSING:
        raise TypeError("record_audit() 缺少必填关键字参数 tenant_id（显式传 None 表示平台级）")
    payload = dict(detail or {})
    if tenant_id is not None:
        payload.setdefault("tenant_id", tenant_id)
    ip: str | None = None
    if request is not None:
        try:
            ip = get_real_client_ip(request)
        except Exception:
            ip = None
    else:
        # request 缺失时才回退到调用方传入的 ip（服务层内部写/历史调用方）。
        ip = ip_address
        payload.setdefault("no_request", True)
    log = OperationLog(
        operator_id=actor_id,
        operator_role=actor_role,
        action_type=action,
        target_type=target_type,
        target_id=target_id,
        # default=str：审计写**永不**因序列化失败拖垮业务流。原 scheduler 滞留提醒
        # 显式依赖该容忍（注释：「序列化失败会让本条以外的滞留预警全部丢失，
        # default=str 只会让异常值退化成其字符串形式，详情仍可人工复盘」）；
        # 迁到本 helper 后若无 default，MagicMock/枚举/模型对象等异常值会直接
        # TypeError 冒泡到调用方。detail 仍是 JSON 对象（调用侧闸门保证）。
        detail=json.dumps(payload, ensure_ascii=False, default=str),
        ip_address=ip,
        # P2-33 第四批修复：tenant_id 必须落列。修前只进 detail，列恒为模型默认，
        # detail 与列各说各话（tenant_admin 的 SEC-FIX 归属要求被静默丢弃）。
        # None = 平台级操作，记平台默认租户（与列默认值同值，None 调用方零行为变化）。
        tenant_id=tenant_id if tenant_id is not None else DEFAULT_TENANT_ID,
    )
    db.add(log)
    await db.flush()
    return log
