"""R-005 回归测试: fire-and-forget 任务可观测性模块.

验证 app/core/fire_forget_metrics.py 的核心功能:
- record_scheduled: 递增 scheduled 计数
- make_done_callback: 根据 task 结果递增 succeeded/failed/cancelled
- register_task: 一站式注册 (scheduled + done_callback)
- 指标在 Prometheus exposition 中可见

关联修复: R-005 (fire-and-forget 任务可观测性)
关联指标: fire_forget_tasks_total, fire_forget_task_duration_seconds
关联告警: AR-208 (fire_forget_task_failure_spike)
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from app.core.fire_forget_metrics import (
    make_done_callback,
    record_scheduled,
    register_task,
)
from app.core.metrics import (
    fire_forget_task_duration_seconds,
    fire_forget_tasks_total,
    render_exposition,
)


@pytest.fixture(autouse=True)
def _reset_fire_forget_metrics():
    """每个测试前重置 fire-forget 指标, 避免测试间污染."""
    fire_forget_tasks_total._values.clear()
    fire_forget_task_duration_seconds._values.clear()
    yield
    fire_forget_tasks_total._values.clear()
    fire_forget_task_duration_seconds._values.clear()


class TestRecordScheduled:
    """record_scheduled: 记录任务调度."""

    def test_increments_scheduled_counter(self):
        """调用后 fire_forget_tasks_total{status="scheduled"} 应递增."""
        record_scheduled("assessment_save")
        entries = fire_forget_tasks_total.collect()
        assert any(
            labels.get("task_type") == "assessment_save"
            and labels.get("status") == "scheduled"
            and value == 1.0
            for labels, value in entries
        )

    def test_multiple_task_types_independent(self):
        """不同 task_type 的计数应独立."""
        record_scheduled("assessment_save")
        record_scheduled("assessment_save")
        record_scheduled("warning_intervention")
        entries = fire_forget_tasks_total.collect()
        scheduled = {
            (labels.get("task_type"), labels.get("status")): value
            for labels, value in entries
            if labels.get("status") == "scheduled"
        }
        assert scheduled.get(("assessment_save", "scheduled")) == 2.0
        assert scheduled.get(("warning_intervention", "scheduled")) == 1.0

    def test_invalid_metric_does_not_raise(self):
        """指标采集失败应优雅降级, 不抛异常."""
        # 传入空字符串不会导致异常 (空 label 值是合法的)
        record_scheduled("")


class TestMakeDoneCallback:
    """make_done_callback: 根据 task 结果递增对应状态."""

    def test_succeeded_task_increments_succeeded(self):
        """完成的任务应递增 succeeded 计数."""
        callback = make_done_callback("assessment_save")
        mock_task = MagicMock()
        mock_task.cancelled.return_value = False
        mock_task.exception.return_value = None
        callback(mock_task)
        entries = fire_forget_tasks_total.collect()
        assert any(
            labels.get("task_type") == "assessment_save"
            and labels.get("status") == "succeeded"
            and value == 1.0
            for labels, value in entries
        )

    def test_failed_task_increments_failed(self):
        """抛异常的任务应递增 failed 计数."""
        callback = make_done_callback("review_task_create")
        mock_task = MagicMock()
        mock_task.cancelled.return_value = False
        mock_task.exception.return_value = ValueError("test error")
        callback(mock_task)
        entries = fire_forget_tasks_total.collect()
        assert any(
            labels.get("task_type") == "review_task_create"
            and labels.get("status") == "failed"
            and value == 1.0
            for labels, value in entries
        )

    def test_cancelled_task_increments_cancelled(self):
        """被取消的任务应递增 cancelled 计数."""
        callback = make_done_callback("validation_job")
        mock_task = MagicMock()
        mock_task.cancelled.return_value = True
        callback(mock_task)
        entries = fire_forget_tasks_total.collect()
        assert any(
            labels.get("task_type") == "validation_job"
            and labels.get("status") == "cancelled"
            and value == 1.0
            for labels, value in entries
        )

    def test_with_start_time_observes_duration(self):
        """提供 start_time 时应 observe 耗时直方图."""
        callback = make_done_callback("pdf_generation", start_time=0.0)
        mock_task = MagicMock()
        mock_task.cancelled.return_value = False
        mock_task.exception.return_value = None
        callback(mock_task)
        entries = fire_forget_task_duration_seconds.collect()
        assert any(labels.get("task_type") == "pdf_generation" for labels, _ in entries)


class TestRegisterTask:
    """register_task: 一站式注册."""

    async def test_registers_scheduled_and_callback(self):
        """register_task 应递增 scheduled 并添加 done_callback."""

        async def _noop():
            pass

        task = asyncio.ensure_future(_noop())
        register_task(task, "assessment_save")
        # scheduled 应已递增
        entries = fire_forget_tasks_total.collect()
        assert any(
            labels.get("task_type") == "assessment_save"
            and labels.get("status") == "scheduled"
            for labels, value in entries
        )
        # 等待任务完成, done_callback 应递增 succeeded
        await asyncio.wait_for(task, 1.0)
        # 任务完成后 succeeded 计数应递增
        entries = fire_forget_tasks_total.collect()
        assert any(
            labels.get("task_type") == "assessment_save"
            and labels.get("status") == "succeeded"
            and value == 1.0
            for labels, value in entries
        )

    async def test_returns_same_task(self):
        """register_task 应返回传入的 task (便于链式调用)."""

        async def _noop():
            pass

        task = asyncio.ensure_future(_noop())
        result = register_task(task, "test")
        assert result is task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


class TestMetricsExposition:
    """指标在 Prometheus exposition 中可见."""

    def test_fire_forget_metrics_in_exposition(self):
        """fire_forget_tasks_total 应出现在 render_exposition 输出中."""
        record_scheduled("assessment_save")
        expo = render_exposition()
        assert "fire_forget_tasks_total" in expo
        assert "fire_forget_task_duration_seconds" in expo

    def test_exposition_format_correct(self):
        """Prometheus exposition 格式应包含 HELP/TYPE 行."""
        record_scheduled("assessment_save")
        expo = render_exposition()
        assert "# HELP fire_forget_tasks_total" in expo
        assert "# TYPE fire_forget_tasks_total counter" in expo
        assert "# HELP fire_forget_task_duration_seconds" in expo
        assert "# TYPE fire_forget_task_duration_seconds histogram" in expo


class TestAlertRuleAR208:
    """AR-208 告警规则已正确注册."""

    def test_ar208_exists(self):
        """AR-208 规则应存在于 ALERT_RULES_BY_ID."""
        from app.core.alert_rules import ALERT_RULES_BY_ID

        assert "AR-208" in ALERT_RULES_BY_ID

    def test_ar208_targets_fire_forget_metric(self):
        """AR-208 应针对 fire_forget_tasks_total 指标."""
        from app.core.alert_rules import ALERT_RULES_BY_ID

        rule = ALERT_RULES_BY_ID["AR-208"]
        assert rule.metric == "fire_forget_tasks_total"
        assert rule.threshold == 5.0
        assert rule.duration_seconds == 300
