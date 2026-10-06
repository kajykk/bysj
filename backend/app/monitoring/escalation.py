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
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.metrics import alert_detail_parse_failed_total
from app.models.admin import OperationLog
from app.monitoring.notifier import AlertPayload, CompositeNotifier

logger = logging.getLogger(__name__)


# 升级阈值 (分钟)
ESCALATION_THRESHOLDS = {
    "P1_to_P0": timedelta(minutes=10),
    "P0_repeat": timedelta(minutes=30),
    "P0_final": timedelta(hours=1),
}


def _observe_escalation_latency(
    start: float, result: str, *, cycle: bool = False
) -> None:
    """上报 escalation 耗时指标 (AUDIT-2026-10-05 OPEN-1)。

    **绝不抛异常** —— 指标链路故障不得阻断告警升级 (P1 关键路径)。
    """
    elapsed = time.perf_counter() - start
    try:
        from app.core import metrics as m

        if cycle:
            m.escalation_cycle_duration_seconds.observe(elapsed)
        else:
            m.escalation_notify_duration_seconds.observe(elapsed, result=result)
    except Exception as exc:  # noqa: BLE001
        # 仅 debug: 指标上报失败本身不影响业务, 但需留痕便于排查
        logger.debug(
            "escalation 耗时指标上报失败 (cycle=%s result=%s): %s",
            cycle,
            result,
            exc,
            exc_info=True,
        )


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
        # AUDIT-2026-10-06 (P1-6): 原实现静默置 `{}` —— 两个后果都很难从下游反推：
        #   1) acknowledged 丢失 → 已确认的告警被误判为未确认，持续升级到 P0；
        #   2) escalation_level 归零 → 同一告警被重复升级。
        # 改为：计数 + 结构化日志（含 alert_id 便于修复数据）。
        try:
            # 注意：app.core.metrics 是自研 Counter（无 labels() 链式 API），
            # 必须写成 inc(amount, **labels)。
            alert_detail_parse_failed_total.inc(1, stage="escalation")
        except Exception:  # noqa: BLE001 - 计数失败绝不能影响升级决策
            logger.debug("告警 detail 解析失败计数上报失败", exc_info=True)
        logger.warning(
            "[escalation] OperationLog.detail 解析失败, 按空 detail 处理 "
            "(alert_id=%s) — 可能导致已确认告警被重复升级",
            alert.id,
            exc_info=True,
        )
        detail = {}

    # 已确认 -> 不升级
    if detail.get("acknowledged"):
        return EscalationDecision(alert_id=alert.id, should_escalate=False, reason="acknowledged")

    # 已升级次数
    escalation_level = detail.get("escalation_level", 0)
    severity = detail.get("severity", "P2")
    age = now - alert.created_at

    # P1 10 分钟未确认 -> 升级到 P0
    #
    # SEC-FIX-2026-10-05（状态机卡死）:
    #   原实现只在返回的 detail 里写 escalation_level=1，却**从不更新 severity**。
    #   而 compute_escalation 的 severity 取自 detail["severity"]（第 81 行），
    #   于是升级后 severity 仍是 "P1"：
    #     - 第 85 行因 `escalation_level < 1` 不成立被跳过；
    #     - 第 95/105 行的 `severity == "P0"` 判定**永假**。
    #   结果：P1 告警在 10 分钟升级为 level=1 后永久停滞，
    #   docstring 承诺的「30 分钟未确认 P0 → 再次通知」与
    #   「1 小时 → 记录 OperationLog 合规追踪」**永不发生** —— 已升级的告警
    #   从此静默，无人再被提醒。这是 P1 告警的默认路径，不是边界情况。
    #   （原生 severity=P0 的告警不走本分支，能正常走完 2→3 级。）
    if severity == "P1" and age >= ESCALATION_THRESHOLDS["P1_to_P0"] and escalation_level < 1:
        return EscalationDecision(
            alert_id=alert.id,
            should_escalate=True,
            new_severity="P0",
            reason=f"P1 unconfirmed for {int(age.total_seconds() // 60)}min, escalating to P0",
            # severity 必须一并提升为 "P0"，否则下一轮判定全部落空。
            detail={
                **detail,
                "severity": "P0",
                "escalation_level": 1,
                "escalated_at": now.isoformat(),
            },
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

    AUDIT-2026-10-05 (OPEN-1): 埋点采集事务持有时长。
    本函数**循环结束后才commit**, 而循环内每条决策都 await notifier.send(...)
    —— 外部 HTTP 耗时全部计入事务时长, 事务久则行锁久。审查报告的
    "最坏 2.5h 持事务"是估算而非实测, 故此处只加埋点不改事务边界:
    先拿到真实 P95, 再决定"仅加监控"还是"按批切分事务"。
    改动约束: alert.detail 更新与 alert_escalated 日志写入必须同事务。
    """
    cycle_start = time.perf_counter()
    notifier = CompositeNotifier()
    executed: list[EscalationDecision] = []
    for d in decisions:
        if not d.should_escalate or d.detail is None:
            continue
        # 更新 OperationLog
        row = (await db.execute(select(OperationLog).where(OperationLog.id == d.alert_id))).scalar_one_or_none()
        if row is None:
            continue
        # SEC-FIX-2026-10-05: 落库时以 new_severity 为准提升 severity。
        # compute_escalation 现在会在 P1→P0 分支一并写入 severity，但
        # 其他分支（P0 的 2→3 级）new_severity 也是 "P0"，不改变原值，
        # 因此这里做一次统一兜底，保证 detail["severity"] 与决策一致。
        # 缺了这一步就会复现原缺陷：detail 里 escalation_level 升了但
        # severity 没升，下一轮 severity=="P0" 判定永假 → 永久停滞。
        detail_to_persist = d.detail
        if d.new_severity and detail_to_persist.get("severity") != d.new_severity:
            detail_to_persist = {**detail_to_persist, "severity": d.new_severity}
        row.detail = json.dumps(detail_to_persist, ensure_ascii=False)
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
            notify_start = time.perf_counter()
            result = "success"
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
                result = "failure"
                logger.error("Escalation notify failed: %s", exc)
            finally:
                # 指标不可用不应影响主流程(与项目既有降级惯例一致)
                _observe_escalation_latency(notify_start, result)
        executed.append(d)
    if executed:
        await db.commit()
    _observe_escalation_latency(cycle_start, "success", cycle=True)
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
