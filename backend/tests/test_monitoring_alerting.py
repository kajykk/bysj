"""Tests for monitoring alerting module."""

from __future__ import annotations

from app.monitoring.alerting import (
    MetricsSnapshot,
    AlertRule,
    AlertEvent,
    AlertingEngine,
    create_default_rules,
)


class TestAlertingEngine:
    """Test alerting engine."""

    def test_add_rule(self):
        """TC-COV-ALERT-001: Add rule to engine."""
        engine = AlertingEngine()
        rule = AlertRule(
            name="test_rule",
            condition=lambda m: m.error_rate > 0.1,
            severity="P0",
        )
        engine.add_rule(rule)
        assert len(engine.rules) == 1

    def test_evaluate_no_trigger(self):
        """TC-COV-ALERT-002: Evaluate with no triggers."""
        engine = AlertingEngine()
        rule = AlertRule(
            name="test_rule",
            condition=lambda m: m.error_rate > 0.1,
            severity="P0",
        )
        engine.add_rule(rule)
        metrics = MetricsSnapshot(error_rate=0.05)
        result = engine.evaluate(metrics)
        assert len(result) == 0

    def test_evaluate_trigger(self):
        """TC-COV-ALERT-003: Evaluate with trigger."""
        engine = AlertingEngine()
        rule = AlertRule(
            name="test_rule",
            condition=lambda m: m.error_rate > 0.1,
            severity="P0",
            cooldown_seconds=0,
        )
        engine.add_rule(rule)
        metrics = MetricsSnapshot(error_rate=0.2)
        result = engine.evaluate(metrics)
        assert len(result) == 1
        assert result[0].rule_name == "test_rule"
        assert result[0].severity == "P0"

    def test_evaluate_cooldown(self):
        """TC-COV-ALERT-004: Cooldown prevents re-trigger."""
        engine = AlertingEngine()
        rule = AlertRule(
            name="test_rule",
            condition=lambda m: True,
            severity="P0",
            cooldown_seconds=3600,
        )
        engine.add_rule(rule)
        metrics = MetricsSnapshot()
        result1 = engine.evaluate(metrics)
        assert len(result1) == 1
        result2 = engine.evaluate(metrics)
        assert len(result2) == 0

    def test_create_default_rules(self):
        """TC-COV-ALERT-005: Create default rules."""
        rules = create_default_rules()
        assert len(rules) == 4
        rule_names = [r.name for r in rules]
        assert "error_rate_spike" in rule_names
        assert "slow_request_p99" in rule_names
        assert "high_memory_usage" in rule_names
        assert "low_disk_space" in rule_names

    def test_default_rule_error_rate(self):
        """TC-COV-ALERT-006: Error rate rule triggers correctly."""
        rules = create_default_rules()
        error_rule = next(r for r in rules if r.name == "error_rate_spike")
        assert error_rule.condition(MetricsSnapshot(error_rate=0.06)) is True
        assert error_rule.condition(MetricsSnapshot(error_rate=0.04)) is False

    def test_default_rule_memory(self):
        """TC-COV-ALERT-007: Memory rule triggers correctly."""
        rules = create_default_rules()
        memory_rule = next(r for r in rules if r.name == "high_memory_usage")
        assert memory_rule.condition(MetricsSnapshot(memory_usage_percent=90)) is True
        assert memory_rule.condition(MetricsSnapshot(memory_usage_percent=80)) is False

    def test_default_rule_disk(self):
        """TC-COV-ALERT-008: Disk rule triggers correctly."""
        rules = create_default_rules()
        disk_rule = next(r for r in rules if r.name == "low_disk_space")
        assert disk_rule.condition(MetricsSnapshot(disk_usage_percent=95)) is True
        assert disk_rule.condition(MetricsSnapshot(disk_usage_percent=85)) is False

    def test_default_rule_p99(self):
        """TC-COV-ALERT-009: P99 latency rule triggers correctly."""
        rules = create_default_rules()
        p99_rule = next(r for r in rules if r.name == "slow_request_p99")
        assert p99_rule.condition(MetricsSnapshot(p99_response_time=4.0)) is True
        assert p99_rule.condition(MetricsSnapshot(p99_response_time=2.0)) is False

    def test_alert_event_defaults(self):
        """TC-COV-ALERT-010: AlertEvent defaults."""
        event = AlertEvent(rule_name="test", severity="P0", message="test message")
        assert event.resolved is False
        assert event.timestamp > 0

    def test_metrics_snapshot_defaults(self):
        """TC-COV-ALERT-011: MetricsSnapshot defaults."""
        metrics = MetricsSnapshot()
        assert metrics.error_rate == 0.0
        assert metrics.memory_usage_percent == 0.0
        assert metrics.timestamp > 0
