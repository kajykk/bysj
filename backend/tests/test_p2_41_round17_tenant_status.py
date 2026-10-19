"""ROUND_17 T1：租户缺行的 fail-open 必须可观测，且不可回退成静默。

改前：``is_tenant_suspended`` 对「tenants 表无该行」只写一条 warning，
返回 False；调用方与运维都拿不到任何计数 —— 异常部署与「租户正常」同形。

T1 保留 fail-open 决策（不因缺行拒绝服务），但要求：
1. 返回 False（决策不变）；
2. ``silent_degradation_total{location="core.tenant_status.missing_tenant",
   tenant_id="<id>"}`` +1；
3. 已存在的 active / suspended 租户**不**计入该降级（避免把正常路径算成故障）。

变异见证：删掉 ``record_silent_degradation`` 调用后，
``test_missing_tenant_counts_with_tenant_label`` 必须红。
"""

from __future__ import annotations

from app.core.metrics import silent_degradation_total
from app.core.tenant_status import is_tenant_suspended
from app.models.tenant import Tenant

MISSING_LOCATION = "core.tenant_status.missing_tenant"


def _degradation_count(tenant_id: int) -> float:
    total = 0.0
    for labels, value in silent_degradation_total.collect():
        if (
            labels.get("location") == MISSING_LOCATION
            and labels.get("tenant_id") == str(tenant_id)
        ):
            total += value
    return total


async def test_missing_tenant_counts_with_tenant_label(db_session):
    """缺租户行 ⇒ 返回 False（fail-open）且带 tenant_id 标签计数 +1。"""
    missing_id = 987_654
    before = _degradation_count(missing_id)

    result = await is_tenant_suspended(db_session, missing_id)

    assert result is False, "fail-open 决策被改动：缺行不再视为未暂停"
    assert _degradation_count(missing_id) == before + 1, (
        "缺租户行未计入 silent_degradation_total —— 异常部署将再次与正常态同形"
    )


async def test_existing_active_tenant_is_not_degraded(db_session):
    tenant_id = 987_655
    db_session.add(
        Tenant(id=tenant_id, name="R17 active", code="r17-active", status="active")
    )
    await db_session.flush()
    before = _degradation_count(tenant_id)

    assert await is_tenant_suspended(db_session, tenant_id) is False
    assert _degradation_count(tenant_id) == before, (
        "active 租户被误记为缺行降级"
    )


async def test_existing_suspended_tenant_not_degraded(db_session):
    tenant_id = 987_656
    db_session.add(
        Tenant(
            id=tenant_id, name="R17 suspended", code="r17-suspended", status="suspended"
        )
    )
    await db_session.flush()
    before = _degradation_count(tenant_id)

    assert await is_tenant_suspended(db_session, tenant_id) is True
    assert _degradation_count(tenant_id) == before, (
        "suspended 是正常判定路径，不应计入缺行降级"
    )


async def test_none_tenant_id_returns_false_without_degradation(db_session):
    """tenant_id=None 由调用方兜底（默认租户），不是"缺行"，不计降级。"""
    before = sum(
        v
        for labels, v in silent_degradation_total.collect()
        if labels.get("location") == MISSING_LOCATION and labels.get("tenant_id") == ""
    )

    assert await is_tenant_suspended(db_session, None) is False

    after = sum(
        v
        for labels, v in silent_degradation_total.collect()
        if labels.get("location") == MISSING_LOCATION and labels.get("tenant_id") == ""
    )
    assert after == before
