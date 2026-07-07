"""STAB-P1-014~018 修复: alert_rules.py 完整性测试.

验证告警规则集中定义的内部一致性与可接入性.
"""

from __future__ import annotations

from app.core.alert_rules import (
    ALERT_RULES,
    ALERT_RULES_BY_ID,
    ALERT_RULES_BY_NAME,
    Severity,
    get_rules_by_label,
    get_rules_by_severity,
    render_prometheus_rules,
    validate_rules,
)


class TestAlertRulesStructure:
    """规则集结构完整性."""

    def test_rules_non_empty(self) -> None:
        """规则集不能为空."""
        assert len(ALERT_RULES) > 0

    def test_rules_count_at_least_14(self) -> None:
        """至少 14 条规则 (覆盖 5 个维度 + 5 个告警相关 P1)."""
        assert len(ALERT_RULES) >= 14, f"仅 {len(ALERT_RULES)} 条规则, 期望 >= 14"

    def test_all_rules_have_unique_ids(self) -> None:
        """所有规则 ID 必须唯一."""
        ids = [rule.id for rule in ALERT_RULES]
        assert len(ids) == len(set(ids)), f"重复 ID: {set(ids)}"

    def test_all_rules_have_unique_names(self) -> None:
        """所有规则名称必须唯一."""
        names = [rule.name for rule in ALERT_RULES]
        assert len(names) == len(set(names)), f"重复名称: {set(names)}"

    def test_all_rules_have_runbook(self) -> None:
        """所有 critical 规则必须有 runbook_url."""
        for rule in ALERT_RULES:
            if rule.severity == Severity.CRITICAL:
                assert rule.runbook_url, f"Critical 规则 {rule.id} 缺少 runbook_url"

    def test_all_rules_have_labels(self) -> None:
        """所有规则至少有 category 标签."""
        for rule in ALERT_RULES:
            label_keys = [k for k, _ in rule.labels]
            assert "category" in label_keys, f"规则 {rule.id} 缺少 category 标签"


class TestAlertRulesIndex:
    """规则索引可查找."""

    def test_alert_rules_by_id_complete(self) -> None:
        """ID 索引包含所有规则."""
        assert len(ALERT_RULES_BY_ID) == len(ALERT_RULES)
        for rule in ALERT_RULES:
            assert ALERT_RULES_BY_ID[rule.id] is rule

    def test_alert_rules_by_name_complete(self) -> None:
        """名称索引包含所有规则."""
        assert len(ALERT_RULES_BY_NAME) == len(ALERT_RULES)
        for rule in ALERT_RULES:
            assert ALERT_RULES_BY_NAME[rule.name] is rule

    def test_get_rules_by_severity(self) -> None:
        """按严重程度过滤."""
        critical = get_rules_by_severity(Severity.CRITICAL)
        warning = get_rules_by_severity(Severity.WARNING)
        assert len(critical) + len(warning) <= len(ALERT_RULES)

    def test_get_rules_by_label_category(self) -> None:
        """按 category 标签过滤."""
        stability = get_rules_by_label("category", "stability")
        assert len(stability) > 0
        for rule in stability:
            assert ("category", "stability") in rule.labels


class TestAlertRulesCoverage:
    """告警规则覆盖 Gate 1→2 必备项."""

    def test_has_5xx_error_rate_rule(self) -> None:
        """必须有 5xx 错误率告警规则."""
        assert "high_5xx_error_rate" in ALERT_RULES_BY_NAME

    def test_has_db_pool_rule(self) -> None:
        """必须有 DB 连接池告警规则 (STAB-P1-015)."""
        assert "db_pool_exhaustion" in ALERT_RULES_BY_NAME

    def test_has_db_circuit_rule(self) -> None:
        """必须有 DB 熔断器告警规则 (STAB-P1-015)."""
        assert "db_circuit_open" in ALERT_RULES_BY_NAME

    def test_has_redis_circuit_rule(self) -> None:
        """必须有 Redis 熔断状态告警规则 (STAB-P1-016)."""
        assert "redis_unavailable" in ALERT_RULES_BY_NAME

    def test_has_model_fallback_rule(self) -> None:
        """必须有模型 fallback 率告警规则 (STAB-P1-017)."""
        assert "high_model_fallback_rate" in ALERT_RULES_BY_NAME

    def test_has_celery_failure_rule(self) -> None:
        """必须有 Celery 任务失败告警规则 (STAB-P1-018)."""
        assert "celery_task_failure_spike" in ALERT_RULES_BY_NAME


class TestAlertRulesValidation:
    """规则集校验."""

    def test_validate_rules_no_errors(self) -> None:
        """validate_rules 应返回空列表 (无错误)."""
        errors = validate_rules()
        assert errors == [], f"规则校验错误: {errors}"

    def test_comparison_operators_valid(self) -> None:
        """所有比较运算符必须合法."""
        valid = {"gt", "lt", "gte", "lte", "eq"}
        for rule in ALERT_RULES:
            assert (
                rule.comparison in valid
            ), f"规则 {rule.id}: 非法运算符 {rule.comparison!r}"

    def test_duration_non_negative(self) -> None:
        """持续时长必须非负."""
        for rule in ALERT_RULES:
            assert rule.duration_seconds >= 0, f"规则 {rule.id}: duration_seconds < 0"


class TestPrometheusRendering:
    """Prometheus 规则渲染."""

    def test_render_returns_non_empty_string(self) -> None:
        """渲染结果非空."""
        output = render_prometheus_rules()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_groups_header(self) -> None:
        """渲染结果包含 groups: 头."""
        output = render_prometheus_rules()
        assert "groups:" in output
        assert "bysj-alerts" in output

    def test_render_contains_all_rules(self) -> None:
        """渲染结果包含所有规则."""
        output = render_prometheus_rules()
        for rule in ALERT_RULES:
            assert f"alert: {rule.name}" in output, f"规则 {rule.name} 未在渲染输出中"

    def test_render_contains_severity_labels(self) -> None:
        """渲染结果包含 severity 标签."""
        output = render_prometheus_rules()
        assert "severity: critical" in output
        assert "severity: warning" in output

    def test_render_contains_runbook_urls(self) -> None:
        """渲染结果包含 runbook_url."""
        output = render_prometheus_rules()
        assert "runbook_url:" in output


class TestMetricsExposition:
    """验证 metrics.py 暴露了告警阈值相关指标."""

    def test_db_pool_utilization_metric_exists(self) -> None:
        """STAB-P1-015: db_pool_utilization 指标必须存在."""
        from app.core.metrics import db_pool_utilization

        assert db_pool_utilization.name == "db_pool_utilization"

    def test_db_circuit_state_metric_exists(self) -> None:
        """STAB-P1-015: db_circuit_state 指标必须存在."""
        from app.core.metrics import db_circuit_state

        assert db_circuit_state.name == "db_circuit_state"

    def test_redis_circuit_state_metric_exists(self) -> None:
        """STAB-P1-016: redis_circuit_state 指标必须存在."""
        from app.core.metrics import redis_circuit_state

        assert redis_circuit_state.name == "redis_circuit_state"

    def test_model_fallback_rate_metric_exists(self) -> None:
        """STAB-P1-017: model_fallback_rate 指标必须存在."""
        from app.core.metrics import model_fallback_rate

        assert model_fallback_rate.name == "model_fallback_rate"

    def test_celery_task_failures_total_metric_exists(self) -> None:
        """STAB-P1-018: celery_task_failures_total 指标必须存在."""
        from app.core.metrics import celery_task_failures_total

        assert celery_task_failures_total.name == "celery_task_failures_total"
        assert "task_name" in celery_task_failures_total.labelnames

    def test_celery_worker_heartbeat_metric_exists(self) -> None:
        """STAB-P1-018: celery_worker_heartbeat 指标必须存在."""
        from app.core.metrics import celery_worker_heartbeat

        assert celery_worker_heartbeat.name == "celery_worker_heartbeat"


class TestCeleryFailureIntegration:
    """验证 celery_app on_task_failure 接入告警指标."""

    def test_on_task_failure_increments_counter(self) -> None:
        """任务失败时递增 celery_task_failures_total."""
        from app.core.celery_app import on_task_failure
        from app.core.metrics import reset_registry

        # 重置指标避免测试污染
        reset_registry()
        # 重新导入以重建指标实例 (reset_registry 清空 _values 不删除实例)
        from app.core.metrics import celery_task_failures_total as cft

        cft._values.clear()

        class FakeSender:
            name = "test_task"

        # 模拟任务失败
        on_task_failure(
            sender=FakeSender(),
            task_id="test-id-001",
            exception=ValueError("test error"),
            args=("safe_arg",),
            kwargs={"key": "value"},
        )

        # 验证计数器递增
        collected = cft.collect()
        assert len(collected) == 1
        labels, value = collected[0]
        assert labels == {"task_name": "test_task"}
        assert value == 1.0

    def test_on_task_failure_with_none_sender(self) -> None:
        """sender 为 None 时使用 unknown 作为 task_name."""
        from app.core.celery_app import on_task_failure
        from app.core.metrics import celery_task_failures_total as cft

        cft._values.clear()

        on_task_failure(
            sender=None,
            task_id="test-id-002",
            exception=RuntimeError("test"),
            args=None,
            kwargs=None,
        )

        collected = cft.collect()
        assert len(collected) == 1
        labels, value = collected[0]
        assert labels == {"task_name": "unknown"}
        assert value == 1.0
