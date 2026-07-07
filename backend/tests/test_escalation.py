"""v1.33: 告警升级策略测试"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.admin import OperationLog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
from app.monitoring.escalation import (
    ESCALATION_THRESHOLDS,
    EscalationDecision,
    apply_escalation,
    compute_escalation,
    escalate_pending_alerts,
    run_escalation_check,
)


def _make_alert(
    alert_id: int = 1,
    severity: str = "P1",
    age_minutes: int = 0,
    acknowledged: bool = False,
    escalation_level: int = 0,
) -> OperationLog:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    detail = {
        "rule": "HighErrorRate",
        "severity": severity,
        "fingerprint": "fp-1",
        "labels": {"alertname": "HighErrorRate"},
        "annotations": {"summary": "test"},
        "message": "test",
    }
    if acknowledged:
        detail["acknowledged"] = True
    if escalation_level:
        detail["escalation_level"] = escalation_level
    return OperationLog(
        id=alert_id,
        operator_id=None,
        operator_role="system",
        action_type="alert_fired",
        target_type="alert",
        target_id=None,
        detail=json.dumps(detail, ensure_ascii=False),
        created_at=now - timedelta(minutes=age_minutes),
    )


def test_compute_escalation_p1_after_10m() -> None:
    """v1.33: P1 告警 10 分钟后应升级到 P0."""
    alert = _make_alert(severity="P1", age_minutes=10)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    decision = compute_escalation(alert, now)
    assert decision.should_escalate is True
    assert decision.new_severity == "P0"
    assert "P1" in decision.reason


def test_compute_escalation_p1_before_10m() -> None:
    """v1.33: P1 告警不到 10 分钟不升级."""
    alert = _make_alert(severity="P1", age_minutes=5)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    decision = compute_escalation(alert, now)
    assert decision.should_escalate is False


def test_compute_escalation_p0_after_30m() -> None:
    """v1.33: P0 告警 30 分钟后应再次发送."""
    alert = _make_alert(severity="P0", age_minutes=30)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    decision = compute_escalation(alert, now)
    assert decision.should_escalate is True
    assert decision.new_severity == "P0"


def test_compute_escalation_p0_after_1h() -> None:
    """v1.33: P0 告警 1 小时后应标记 P0-1h."""
    alert = _make_alert(severity="P0", age_minutes=60, escalation_level=2)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    decision = compute_escalation(alert, now)
    assert decision.should_escalate is True
    assert decision.detail["escalation_level"] == 3


def test_compute_escalation_acknowledged_stops() -> None:
    """v1.33: 已确认告警不应升级."""
    alert = _make_alert(severity="P1", age_minutes=60, acknowledged=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    decision = compute_escalation(alert, now)
    assert decision.should_escalate is False
    assert "acknowledged" in decision.reason


def test_compute_escalation_idempotent() -> None:
    """v1.33: 已升级过的 P1 不应再升级 (除非 level 增加)."""
    alert = _make_alert(severity="P1", age_minutes=60, escalation_level=1)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    decision = compute_escalation(alert, now)
    # level=1 表示已经升级过, 不会再升级
    assert decision.should_escalate is False


def test_compute_escalation_not_firing() -> None:
    """v1.33: resolved 告警不应升级."""
    alert = _make_alert(severity="P1", age_minutes=60)
    alert.action_type = "alert_resolved"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    decision = compute_escalation(alert, now)
    assert decision.should_escalate is False
    assert "not firing" in decision.reason


def test_compute_escalation_p2_no_escalation() -> None:
    """v1.33: P2 告警不应自动升级."""
    alert = _make_alert(severity="P2", age_minutes=120)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    decision = compute_escalation(alert, now)
    assert decision.should_escalate is False


def test_thresholds_defined() -> None:
    """v1.33: 升级阈值应正确定义."""
    assert ESCALATION_THRESHOLDS["P1_to_P0"] == timedelta(minutes=10)
    assert ESCALATION_THRESHOLDS["P0_repeat"] == timedelta(minutes=30)
    assert ESCALATION_THRESHOLDS["P0_final"] == timedelta(hours=1)


# ===== 新增: 覆盖 compute_escalation 边界分支 (L65, L72-73) =====


def test_compute_escalation_no_created_at() -> None:
    """created_at 为 None 时应返回不升级, reason='no created_at'."""
    alert = _make_alert(severity="P1", age_minutes=10)
    alert.created_at = None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    decision = compute_escalation(alert, now)
    assert decision.should_escalate is False
    assert "no created_at" in decision.reason


def test_compute_escalation_invalid_detail_json() -> None:
    """detail JSON 解析失败时应回退到空 dict, severity 默认 P2 不升级."""
    alert = _make_alert(severity="P1", age_minutes=10)
    alert.detail = "not-valid-json{"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    decision = compute_escalation(alert, now)
    assert decision.should_escalate is False
    assert "no escalation" in decision.reason


def test_compute_escalation_none_detail() -> None:
    """detail 为 None 时应回退到空 dict, 不升级."""
    alert = _make_alert(severity="P1", age_minutes=10)
    alert.detail = None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    decision = compute_escalation(alert, now)
    assert decision.should_escalate is False


def test_compute_escalation_p0_already_final() -> None:
    """已升级到 level=3 的 P0 告警不应再升级 (跨级跳转终点)."""
    alert = _make_alert(severity="P0", age_minutes=120, escalation_level=3)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    decision = compute_escalation(alert, now)
    assert decision.should_escalate is False


def test_compute_escalation_p1_skip_when_already_escalated() -> None:
    """P1 已升级到 level=1 后即使超时也不应再次升级 (幂等)."""
    alert = _make_alert(severity="P1", age_minutes=60, escalation_level=1)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    decision = compute_escalation(alert, now)
    assert decision.should_escalate is False


# ===== 新增: 覆盖 run_escalation_check (L123-136) =====


async def test_run_escalation_check_scans_firing_alerts(
    db_session: AsyncSession,
) -> None:
    """run_escalation_check 应扫描 alert_fired 告警并返回决策列表."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    alert = OperationLog(
        operator_id=None,
        operator_role="system",
        action_type="alert_fired",
        target_type="alert",
        target_id=None,
        detail=json.dumps(
            {
                "rule": "HighErrorRate",
                "severity": "P1",
                "fingerprint": "fp-test",
            },
            ensure_ascii=False,
        ),
        created_at=now - timedelta(minutes=15),
    )
    db_session.add(alert)
    # 非 alert_fired 的不应被扫描
    db_session.add(
        OperationLog(
            operator_id=None,
            operator_role="system",
            action_type="alert_resolved",
            target_type="alert",
            detail="{}",
            created_at=now,
        )
    )
    await db_session.flush()

    decisions = await run_escalation_check(db_session)
    # 至少有一个决策 (P1 15分钟应升级)
    p1_decisions = [d for d in decisions if d.should_escalate]
    assert len(p1_decisions) >= 1


async def test_run_escalation_check_empty_db(db_session: AsyncSession) -> None:
    """无告警时应返回空决策列表."""
    decisions = await run_escalation_check(db_session)
    assert decisions == []


# ===== 新增: 覆盖 apply_escalation (L147-194) =====


async def test_apply_escalation_updates_detail_and_creates_log(db_session) -> None:
    """apply_escalation 应更新原告警 detail 并创建升级日志."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    alert = OperationLog(
        operator_id=None,
        operator_role="system",
        action_type="alert_fired",
        target_type="alert",
        detail=json.dumps(
            {
                "rule": "HighErrorRate",
                "severity": "P1",
                "fingerprint": "fp-1",
            },
            ensure_ascii=False,
        ),
        created_at=now - timedelta(minutes=15),
    )
    db_session.add(alert)
    await db_session.flush()

    decision = EscalationDecision(
        alert_id=alert.id,
        should_escalate=True,
        new_severity="P0",
        reason="P1 unconfirmed, escalating",
        detail={"severity": "P1", "rule": "HighErrorRate", "escalation_level": 1},
    )

    with patch("app.monitoring.escalation.CompositeNotifier") as MockNotifier:
        MockNotifier.return_value.send = AsyncMock(return_value={"webhook": True})
        executed = await apply_escalation(db_session, [decision])

    assert len(executed) == 1
    # 验证原告警 detail 已更新 (包含 escalation_level)
    assert "escalation_level" in (alert.detail or "")
    # 验证创建了升级日志
    from sqlalchemy import select

    logs = (
        (
            await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "alert_escalated"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(logs) == 1
    log_detail = json.loads(logs[0].detail)
    assert log_detail["new_severity"] == "P0"
    assert log_detail["alert_id"] == alert.id


async def test_apply_escalation_skips_non_escalating() -> None:
    """should_escalate=False 的决策应被跳过."""
    db = MagicMock()
    db.commit = AsyncMock()
    decision = EscalationDecision(
        alert_id=999,
        should_escalate=False,
        reason="no need",
    )
    with patch("app.monitoring.escalation.CompositeNotifier"):
        executed = await apply_escalation(db, [decision])
    assert len(executed) == 0
    db.commit.assert_not_awaited()


async def test_apply_escalation_skips_none_detail() -> None:
    """detail 为 None 的决策应被跳过 (即使 should_escalate=True)."""
    db = MagicMock()
    db.commit = AsyncMock()
    decision = EscalationDecision(
        alert_id=999,
        should_escalate=True,
        new_severity="P0",
        reason="test",
        detail=None,
    )
    with patch("app.monitoring.escalation.CompositeNotifier"):
        executed = await apply_escalation(db, [decision])
    assert len(executed) == 0


async def test_apply_escalation_skips_missing_alert(db_session) -> None:
    """alert_id 不存在时应跳过该决策."""
    decision = EscalationDecision(
        alert_id=99999,
        should_escalate=True,
        new_severity="P0",
        reason="test",
        detail={"severity": "P1", "escalation_level": 1},
    )
    with patch("app.monitoring.escalation.CompositeNotifier"):
        executed = await apply_escalation(db_session, [decision])
    assert len(executed) == 0


async def test_apply_escalation_handles_notify_failure(db_session) -> None:
    """notifier 发送失败应被捕获并记录, 不影响主流程."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    alert = OperationLog(
        operator_id=None,
        operator_role="system",
        action_type="alert_fired",
        target_type="alert",
        detail=json.dumps({"severity": "P1", "rule": "test"}, ensure_ascii=False),
        created_at=now - timedelta(minutes=15),
    )
    db_session.add(alert)
    await db_session.flush()

    decision = EscalationDecision(
        alert_id=alert.id,
        should_escalate=True,
        new_severity="P0",
        reason="test",
        detail={"severity": "P1", "rule": "test", "escalation_level": 1},
    )

    with patch("app.monitoring.escalation.CompositeNotifier") as MockNotifier:
        MockNotifier.return_value.send = AsyncMock(side_effect=Exception("notify boom"))
        executed = await apply_escalation(db_session, [decision])

    # 仍应执行 (notify 失败不影响主流程, 升级日志仍写入)
    assert len(executed) == 1


async def test_apply_escalation_skips_when_no_new_severity() -> None:
    """new_severity 为 None 时不应触发 notifier.send."""
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=MagicMock(detail="{}"))
        )
    )
    db.commit = AsyncMock()

    decision = EscalationDecision(
        alert_id=1,
        should_escalate=True,
        new_severity=None,
        reason="test",
        detail={"severity": "P1", "escalation_level": 1},
    )
    with patch("app.monitoring.escalation.CompositeNotifier") as MockNotifier:
        MockNotifier.return_value.send = AsyncMock()
        executed = await apply_escalation(db, [decision])

    assert len(executed) == 1
    MockNotifier.return_value.send.assert_not_awaited()


async def test_apply_escalation_no_commit_when_empty() -> None:
    """无执行的决策时不应调用 db.commit."""
    db = MagicMock()
    db.commit = AsyncMock()
    with patch("app.monitoring.escalation.CompositeNotifier"):
        executed = await apply_escalation(db, [])
    assert len(executed) == 0
    db.commit.assert_not_awaited()


# ===== 新增: 覆盖 escalate_pending_alerts 主入口 (L203-206) =====


async def test_escalate_pending_alerts_main_entry(db_session) -> None:
    """escalate_pending_alerts 主入口应完成扫描+升级全流程."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    alert = OperationLog(
        operator_id=None,
        operator_role="system",
        action_type="alert_fired",
        target_type="alert",
        detail=json.dumps(
            {
                "rule": "HighErrorRate",
                "severity": "P1",
                "fingerprint": "fp-main",
            },
            ensure_ascii=False,
        ),
        created_at=now - timedelta(minutes=15),
    )
    db_session.add(alert)
    await db_session.flush()

    # mock get_db 直接返回 db_session, 避免新 session 事务隔离问题
    async def _mock_get_db():
        yield db_session

    with patch("app.monitoring.escalation.get_db", _mock_get_db), patch(
        "app.monitoring.escalation.CompositeNotifier"
    ) as MockNotifier:
        MockNotifier.return_value.send = AsyncMock(return_value={})
        executed = await escalate_pending_alerts()

    assert len(executed) >= 1


async def test_escalate_pending_alerts_empty_generator() -> None:
    """get_db 不产出 session 时应返回空列表 (覆盖 return [])."""

    async def _empty_db():
        if False:  # 永不执行, 仅用于声明为 async generator
            yield

    with patch("app.monitoring.escalation.get_db", _empty_db):
        result = await escalate_pending_alerts()
    assert result == []


# ===== 新增: 跨级跳转与降级路径 =====


def test_compute_escalation_p0_cross_level_jump() -> None:
    """P0 已升级到 level=2 后 1 小时应跳到 level=3 (跨级跳转终点)."""
    alert = _make_alert(severity="P0", age_minutes=65, escalation_level=2)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    decision = compute_escalation(alert, now)
    assert decision.should_escalate is True
    assert decision.detail["escalation_level"] == 3
    assert "P0-1h" in decision.reason


def test_compute_escalation_p0_repeat_at_30m_level0() -> None:
    """P0 level=0 在 30 分钟时应升级到 level=2 (重复发送)."""
    alert = _make_alert(severity="P0", age_minutes=30, escalation_level=0)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    decision = compute_escalation(alert, now)
    assert decision.should_escalate is True
    assert decision.detail["escalation_level"] == 2


def test_compute_escalation_p1_to_p0_detail_has_timestamp() -> None:
    """P1 升级到 P0 时 detail 应包含 escalated_at 时间戳."""
    alert = _make_alert(severity="P1", age_minutes=15)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    decision = compute_escalation(alert, now)
    assert decision.should_escalate is True
    assert "escalated_at" in decision.detail
    assert "escalation_level" in decision.detail
    assert decision.detail["escalation_level"] == 1
