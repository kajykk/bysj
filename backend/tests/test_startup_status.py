"""R-006 修复：启动失败结构化状态 - 回归测试.

测试覆盖:
1. StartupStatus 单例的 record / set_fatal / mark_completed / to_dict / to_summary_dict
2. record_step_async / record_step_sync 包装器 (致命与非致命)
3. metrics 指标递增 (startup_component_failures_total)
4. alert_rules 中 AR-209 规则定义
5. metrics exposition 包含新指标

测试原则:
- 每个测试独立 (通过 reset() 隔离状态)
- 不依赖完整 app 启动
- 覆盖致命/非致命/跳过三种状态
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.alert_rules import ALERT_RULES_BY_ID, Severity
from app.core.metrics import (
    render_exposition,
    startup_component_failures_total,
)
from app.core.startup_status import (
    ComponentStatus,
    record_step_async,
    record_step_sync,
    startup_status,
)


@pytest.fixture(autouse=True)
def _reset_startup_status():
    """每个测试前后重置 startup_status 与 metrics, 确保隔离."""
    startup_status.reset()
    startup_component_failures_total._values.clear()
    yield
    startup_status.reset()
    startup_component_failures_total._values.clear()


# ── 1. StartupStatus.record 基础测试 ──


class TestRecord:
    """StartupStatus.record: 单组件状态记录."""

    def test_record_ok_status(self):
        """record 应正确记录 ok 状态."""
        startup_status.record("test_component", "ok", duration_ms=15.5)
        components = startup_status.components
        assert "test_component" in components
        assert components["test_component"].status == "ok"
        assert components["test_component"].error_type == ""
        assert components["test_component"].error_message == ""
        assert components["test_component"].duration_ms == 15.5

    def test_record_failed_status_with_error(self):
        """record 应正确捕获异常类型与消息."""
        exc = ValueError("something went wrong")
        startup_status.record("failed_comp", "failed", error=exc, duration_ms=2.0)
        components = startup_status.components
        assert components["failed_comp"].status == "failed"
        assert components["failed_comp"].error_type == "ValueError"
        assert components["failed_comp"].error_message == "something went wrong"

    def test_record_truncates_long_error_message(self):
        """error_message 应截断到 500 字符."""
        long_msg = "x" * 1000
        exc = RuntimeError(long_msg)
        startup_status.record("long_error", "failed", error=exc)
        assert len(startup_status.components["long_error"].error_message) == 500

    def test_record_increments_metrics_on_failure(self):
        """failed 状态应递增 startup_component_failures_total 指标."""
        startup_status.record("comp_a", "failed", error=RuntimeError("a"), fatal=False)
        startup_status.record("comp_b", "failed", error=OSError("b"), fatal=True)
        entries = startup_component_failures_total.collect()
        assert len(entries) == 2
        labels_values = {(e[0]["component"], e[0]["fatal"]) for e in entries}
        assert ("comp_a", "false") in labels_values
        assert ("comp_b", "true") in labels_values

    def test_record_does_not_increment_metrics_on_ok(self):
        """ok 状态不应递增 failure 指标."""
        startup_status.record("ok_comp", "ok", duration_ms=1.0)
        entries = startup_component_failures_total.collect()
        assert len(entries) == 0


# ── 2. failed_components 与 fatal_error 测试 ──


class TestFailedComponents:
    """failed_components / has_fatal_error / set_fatal."""

    def test_failed_components_lists_only_failed(self):
        """failed_components 仅返回 status='failed' 的组件名."""
        startup_status.record("ok1", "ok")
        startup_status.record("fail1", "failed", error=ValueError("1"))
        startup_status.record("ok2", "ok")
        startup_status.record("fail2", "failed", error=OSError("2"))
        failed = startup_status.failed_components
        assert set(failed) == {"fail1", "fail2"}

    def test_failed_components_empty_when_all_ok(self):
        """全部 ok 时 failed_components 为空."""
        startup_status.record("a", "ok")
        startup_status.record("b", "ok")
        assert startup_status.failed_components == []

    def test_set_fatal_with_exception(self):
        """set_fatal 应正确提取异常类型与消息."""
        exc = RuntimeError("fatal boom")
        startup_status.set_fatal(exc)
        assert startup_status.has_fatal_error
        assert startup_status.fatal_error == "fatal boom"
        assert startup_status.fatal_error_type == "RuntimeError"

    def test_set_fatal_with_string(self):
        """set_fatal 应支持字符串错误."""
        startup_status.set_fatal("manual fatal message")
        assert startup_status.has_fatal_error
        assert startup_status.fatal_error == "manual fatal message"
        assert startup_status.fatal_error_type == "FatalError"

    def test_set_fatal_truncates_long_message(self):
        """致命错误消息应截断到 1000 字符."""
        long_msg = "y" * 2000
        startup_status.set_fatal(long_msg)
        assert len(startup_status.fatal_error) == 1000


# ── 3. to_dict / to_summary_dict 序列化测试 ──


class TestSerialization:
    """to_dict / to_summary_dict / ComponentStatus.to_dict."""

    def test_to_dict_contains_all_required_fields(self):
        """to_dict 应包含 startup_completed/fatal_error/failed_components/components."""
        startup_status.record("a", "ok", duration_ms=1.0)
        startup_status.record("b", "failed", error=ValueError("x"))
        startup_status.mark_completed()
        d = startup_status.to_dict()
        assert set(d.keys()) == {
            "startup_completed",
            "fatal_error",
            "fatal_error_type",
            "failed_components",
            "components",
        }
        assert d["startup_completed"] is True
        assert d["failed_components"] == ["b"]
        assert "a" in d["components"]
        assert "b" in d["components"]

    def test_to_dict_components_have_required_fields(self):
        """每个 component dict 应包含 status/error_type/error_message/duration_ms."""
        startup_status.record("a", "failed", error=ValueError("err"), duration_ms=3.5)
        d = startup_status.to_dict()
        comp = d["components"]["a"]
        assert set(comp.keys()) == {
            "status",
            "error_type",
            "error_message",
            "duration_ms",
        }
        assert comp["status"] == "failed"
        assert comp["error_type"] == "ValueError"
        assert comp["error_message"] == "err"
        assert comp["duration_ms"] == 3.5

    def test_to_summary_dict_contains_only_summary(self):
        """to_summary_dict 仅包含 failed_components 与 fatal_error."""
        startup_status.record("a", "failed", error=RuntimeError("x"))
        startup_status.set_fatal("fatal")
        d = startup_status.to_summary_dict()
        assert set(d.keys()) == {"startup_failed_components", "startup_fatal_error"}
        assert d["startup_failed_components"] == ["a"]
        assert d["startup_fatal_error"] == "fatal"

    def test_component_status_to_dict_rounds_duration(self):
        """ComponentStatus.to_dict 应四舍五入 duration_ms 到 2 位小数."""
        cs = ComponentStatus(name="test", status="ok", duration_ms=12.34567)
        d = cs.to_dict()
        assert d["duration_ms"] == 12.35


# ── 4. record_step_async 测试 ──


class TestRecordStepAsync:
    """record_step_async: 异步步骤包装器."""

    async def test_ok_step_records_success(self):
        """成功的协程应记录 ok 状态并返回结果."""

        async def _ok_coro():
            await asyncio.sleep(0.01)
            return "result"

        result = await record_step_async("test_async_ok", _ok_coro(), fatal=True)
        assert result == "result"
        assert startup_status.components["test_async_ok"].status == "ok"
        assert startup_status.components["test_async_ok"].duration_ms > 0

    async def test_fatal_step_reraises_and_records(self):
        """fatal=True 时失败应 re-raise 并记录 fatal 错误."""

        async def _fail_coro():
            raise RuntimeError("async fatal")

        with pytest.raises(RuntimeError, match="async fatal"):
            await record_step_async("test_async_fatal", _fail_coro(), fatal=True)

        assert startup_status.components["test_async_fatal"].status == "failed"
        assert startup_status.has_fatal_error
        assert startup_status.fatal_error == "async fatal"

    async def test_non_fatal_step_swallows_and_records(self):
        """fatal=False 时失败应吞掉异常仅记录."""

        async def _fail_coro():
            raise ValueError("async non-fatal")

        result = await record_step_async(
            "test_async_nonfatal", _fail_coro(), fatal=False
        )
        assert result is None
        assert startup_status.components["test_async_nonfatal"].status == "failed"
        assert not startup_status.has_fatal_error

    async def test_non_fatal_step_increments_metrics_with_false_label(self):
        """非致命失败应递增 metrics with fatal='false'."""

        async def _fail_coro():
            raise RuntimeError("x")

        await record_step_async("comp_x", _fail_coro(), fatal=False)
        entries = startup_component_failures_total.collect()
        assert len(entries) == 1
        assert entries[0][0]["fatal"] == "false"


# ── 5. record_step_sync 测试 ──


class TestRecordStepSync:
    """record_step_sync: 同步步骤包装器."""

    def test_ok_step_records_success(self):
        """成功的函数应记录 ok 状态并返回结果."""

        def _ok_func():
            return 42

        result = record_step_sync("test_sync_ok", _ok_func, fatal=True)
        assert result == 42
        assert startup_status.components["test_sync_ok"].status == "ok"

    def test_fatal_step_reraises_and_records(self):
        """fatal=True 时失败应 re-raise 并设置 fatal."""

        def _fail_func():
            raise OSError("sync fatal")

        with pytest.raises(OSError, match="sync fatal"):
            record_step_sync("test_sync_fatal", _fail_func, fatal=True)

        assert startup_status.components["test_sync_fatal"].status == "failed"
        assert startup_status.has_fatal_error

    def test_non_fatal_step_swallows_and_records(self):
        """fatal=False 时失败应吞掉异常."""

        def _fail_func():
            raise ValueError("sync non-fatal")

        result = record_step_sync("test_sync_nonfatal", _fail_func, fatal=False)
        assert result is None
        assert startup_status.components["test_sync_nonfatal"].status == "failed"
        assert not startup_status.has_fatal_error

    def test_fatal_step_increments_metrics_with_true_label(self):
        """致命失败应递增 metrics with fatal='true'."""

        def _fail_func():
            raise RuntimeError("y")

        with pytest.raises(RuntimeError):
            record_step_sync("comp_y", _fail_func, fatal=True)

        entries = startup_component_failures_total.collect()
        assert len(entries) == 1
        assert entries[0][0]["fatal"] == "true"


# ── 6. mark_completed 测试 ──


class TestMarkCompleted:
    """mark_completed: 启动序列完成标记."""

    def test_mark_completed_sets_flag(self):
        """mark_completed 应将 startup_completed 置为 True."""
        assert startup_status.startup_completed is False
        startup_status.mark_completed()
        assert startup_status.startup_completed is True

    def test_to_dict_reflects_completed_flag(self):
        """to_dict 应反映 startup_completed 状态."""
        startup_status.mark_completed()
        d = startup_status.to_dict()
        assert d["startup_completed"] is True


# ── 7. reset 测试 ──


class TestReset:
    """reset: 状态重置."""

    def test_reset_clears_all_state(self):
        """reset 应清空所有状态."""
        startup_status.record("a", "failed", error=RuntimeError("x"))
        startup_status.set_fatal("fatal")
        startup_status.mark_completed()
        startup_status.reset()
        assert startup_status.components == {}
        assert startup_status.failed_components == []
        assert not startup_status.has_fatal_error
        assert not startup_status.startup_completed


# ── 8. Metrics exposition 测试 ──


class TestMetricsExposition:
    """metrics 指标暴露测试."""

    def test_startup_metric_in_exposition(self):
        """startup_component_failures_total 应出现在 exposition 输出中."""
        expo = render_exposition()
        assert "startup_component_failures_total" in expo

    def test_exposition_contains_help_and_type(self):
        """exposition 应包含 HELP 和 TYPE 行."""
        expo = render_exposition()
        assert "# HELP startup_component_failures_total" in expo
        assert "# TYPE startup_component_failures_total counter" in expo

    def test_exposition_contains_values_after_failure(self):
        """失败后 exposition 应包含具体值."""
        startup_status.record("comp_z", "failed", error=RuntimeError("z"), fatal=False)
        expo = render_exposition()
        assert (
            'startup_component_failures_total{component="comp_z",fatal="false"}' in expo
        )


# ── 9. AR-209 告警规则测试 ──


class TestAlertRuleAR209:
    """AR-209 告警规则定义测试."""

    def test_ar209_exists(self):
        """AR-209 规则应存在."""
        assert "AR-209" in ALERT_RULES_BY_ID

    def test_ar209_targets_startup_metric(self):
        """AR-209 应指向 startup_component_failures_total 指标."""
        rule = ALERT_RULES_BY_ID["AR-209"]
        assert rule.metric == "startup_component_failures_total"

    def test_ar209_is_warning_severity(self):
        """AR-209 应为 WARNING 级别."""
        rule = ALERT_RULES_BY_ID["AR-209"]
        assert rule.severity == Severity.WARNING

    def test_ar209_threshold_is_zero(self):
        """AR-209 阈值应为 0 (任一失败即告警)."""
        rule = ALERT_RULES_BY_ID["AR-209"]
        assert rule.threshold == 0.0
        assert rule.comparison == "gt"

    def test_ar209_has_runbook_url(self):
        """AR-209 应有 runbook URL."""
        rule = ALERT_RULES_BY_ID["AR-209"]
        assert rule.runbook_url == "docs/runbooks/startup_failures.md"

    def test_ar209_has_observability_label(self):
        """AR-209 应有 category=observability 标签."""
        rule = ALERT_RULES_BY_ID["AR-209"]
        assert ("category", "observability") in rule.labels
