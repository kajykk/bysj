"""v1.33: 告警升级策略.

升级规则:
- 10 分钟未确认 P1 → 升级到 P0
- 30 分钟未确认 P0 → 强制标记为 P0-1h (再次发送)
- 1 小时未确认 → 记录到 OperationLog (合规追踪)
- 已被确认的告警停止升级

设计原则:
- 幂等: 同一 alert_id 同一时间点只升级一次
- 状态存储: 在 OperationLog.detail 中追加 escalation_level 字段
- 调度: 由 Celery beat 调用 (在 production) 或人工触发 (in tests)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.admin import OperationLog
from app.monitoring.notifier import AlertPayload, CompositeNotifier

logger = logging.getLogger(__name__)


# 升级阈值 (分钟)
ESCALATION_THRESHOLDS = {
    "P1_to_P0": timedelta(minutes=10),
    "P0_repeat": timedelta(minutes=30),
    "P0_final": timedelta(hours=1),
}


@dataclass
class EscalationDecision:
    """v1.33: 升级决策."""

    alert_id: int
    should_escalate: bool
    new_severity: str | None = None
    reason: str = ""
    detail: dict[str, Any] | None = None


def compute_escalation(alert: OperationLog, now: datetime) -> EscalationDecision:
    """v1.33: 计算单个告警是否需要升级.

    Args:
        alert: OperationLog 行 (action_type='alert_fired')
        now: 当前时间

    Returns:
        EscalationDecision
    """
    if alert.action_type != "alert_fired":
        return EscalationDecision(alert_id=alert.id, should_escalate=False, reason="not firing")

    if alert.created_at is None:
        return EscalationDecision(alert_id=alert.id, should_escalate=False, reason="no created_at")

    # 解析 detail
    detail: dict = {}
    try:
        if alert.detail:
            detail = json.loads(alert.detail)
    except Exception:
        detail = {}

    # 已确认 -> 不升级
    if detail.get("acknowledged"):
        return EscalationDecision(alert_id=alert.id, should_escalate=False, reason="acknowledged")

    # 已升级次数
    escalation_level = detail.get("escalation_level", 0)
    severity = detail.get("severity", "P2")
    age = now - alert.created_at

    # P1 10 分钟未确认 -> 升级到 P0
    if severity == "P1" and age >= ESCALATION_THRESHOLDS["P1_to_P0"] and escalation_level < 1:
        return EscalationDecision(
            alert_id=alert.id,
            should_escalate=True,
            new_severity="P0",
            reason=f"P1 unconfirmed for {int(age.total_seconds() // 60)}min, escalating to P0",
            detail={**detail, "escalation_level": 1, "escalated_at": now.isoformat()},
        )

    # P0 30 分钟 -> 再次发送
    if severity == "P0" and age >= ESCALATION_THRESHOLDS["P0_repeat"] and escalation_level < 2:
        return EscalationDecision(
            alert_id=alert.id,
            should_escalate=True,
            new_severity="P0",
            reason=f"P0 unconfirmed for {int(age.total_seconds() // 60)}min, repeat notification",
            detail={**detail, "escalation_level": 2, "re_escalated_at": now.isoformat()},
        )

    # P0 1 小时 -> 标记 P0-1h
    if severity == "P0" and age >= ESCALATION_THRESHOLDS["P0_final"] and escalation_level < 3:
        return EscalationDecision(
            alert_id=alert.id,
            should_escalate=True,
            new_severity="P0",
            reason=f"P0 unconfirmed for {int(age.total_seconds() // 3600)}h, marking as P0-1h",
            detail={**detail, "escalation_level": 3, "final_escalated_at": now.isoformat()},
        )

    return EscalationDecision(alert_id=alert.id, should_escalate=False, reason="no escalation needed")


async def run_escalation_check(db: AsyncSession) -> list[EscalationDecision]:
    """v1.33: 扫描所有未确认 firing 告警, 执行升级.

    Returns:
        所有升级决策 (包括未升级的)
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stmt = select(OperationLog).where(
        and_(
            OperationLog.action_type == "alert_fired",
            OperationLog.target_type == "alert",
        )
    ).order_by(desc(OperationLog.created_at)).limit(500)
    rows = (await db.execute(stmt)).scalars().all()

    decisions: list[EscalationDecision] = []
    for row in rows:
        decision = compute_escalation(row, now)
        decisions.append(decision)
    return decisions


async def apply_escalation(
    db: AsyncSession, decisions: list[EscalationDecision]
) -> list[EscalationDecision]:
    """v1.33: 应用升级决策 (更新 detail + 触发 notifier).

    Returns:
        实际执行的升级 (should_escalate=True)
    """
    notifier = CompositeNotifier()
    executed: list[EscalationDecision] = []
    for d in decisions:
        if not d.should_escalate or d.detail is None:
            continue
        # 更新 OperationLog
        row = (await db.execute(select(OperationLog).where(OperationLog.id == d.alert_id))).scalar_one_or_none()
        if row is None:
            continue
        row.detail = json.dumps(d.detail, ensure_ascii=False)
        # 记录升级事件
        escalation_log = OperationLog(
            operator_id=None,
            operator_role="system",
            action_type="alert_escalated",
            target_type="alert",
            target_id=d.alert_id,
            detail=json.dumps(
                {
                    "alert_id": d.alert_id,
                    "new_severity": d.new_severity,
                    "reason": d.reason,
                    "escalation_level": d.detail.get("escalation_level"),
                },
                ensure_ascii=False,
            ),
        )
        db.add(escalation_log)

        # 触发通知
        if d.new_severity:
            try:
                payload = AlertPayload(
                    rule=d.detail.get("rule", "UnknownAlert"),
                    severity=d.new_severity,
                    status="firing",
                    message=f"[ESCALATED] {d.reason}",
                    labels=d.detail.get("labels", {}),
                    annotations={**d.detail.get("annotations", {}), "escalation_reason": d.reason},
                    fingerprint=d.detail.get("fingerprint"),
                )
                await notifier.send(payload, db=db)
            except Exception as exc:
                logger.error("Escalation notify failed: %s", exc)
        executed.append(d)
    if executed:
        await db.commit()
    return executed


async def escalate_pending_alerts() -> list[EscalationDecision]:
    """v1.33: 主入口: 扫描 + 升级.

    Returns:
        执行的升级列表
    """
    async for db in get_db():
        decisions = await run_escalation_check(db)
        return await apply_escalation(db, decisions)
    return []
