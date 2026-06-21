"""v1.33: 告警升级策略测试"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.models.admin import OperationLog
from app.monitoring.escalation import (
    ESCALATION_THRESHOLDS,
    EscalationDecision,
    apply_escalation,
    compute_escalation,
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
