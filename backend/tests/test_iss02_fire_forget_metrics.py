"""ISS-02 覆盖率提升：app/core/fire_forget_metrics.py 聚焦测试.

fire-and-forget 任务指标（观测性）。mock app.core.metrics 以断言指标调用，
并验证 done_callback 对 succeeded/failed/cancelled 的分类。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core import fire_forget_metrics as ffm


@pytest.fixture
def mock_metrics(monkeypatch):
    # 仅 patch 具体指标对象，避免整体替换 app.core.metrics（会连累 celery_breaker 的 import）
    total = MagicMock()
    duration = MagicMock()
    monkeypatch.setattr(
        "app.core.metrics.fire_forget_tasks_total", total
    )
    monkeypatch.setattr(
        "app.core.metrics.fire_forget_task_duration_seconds", duration
    )
    return MagicMock(
        fire_forget_tasks_total=total,
        fire_forget_task_duration_seconds=duration,
    )


class TestRecordScheduled:
    def test_inc_scheduled(self, mock_metrics):
        ffm.record_scheduled("assessment_save")
        mock_metrics.fire_forget_tasks_total.inc.assert_called_once_with(
            task_type="assessment_save", status="scheduled"
        )


class TestMakeDoneCallback:
    def _fake_task(self, *, cancelled=False, exc=None, result=None):
        t = MagicMock()
        t.cancelled.return_value = cancelled
        t.exception.return_value = exc
        t.result.return_value = result
        return t

    def test_succeeded(self, mock_metrics):
        cb = ffm.make_done_callback("assessment_save")
        cb(self._fake_task(result="ok"))
        mock_metrics.fire_forget_tasks_total.inc.assert_called_once_with(
            task_type="assessment_save", status="succeeded"
        )

    def test_failed(self, mock_metrics):
        cb = ffm.make_done_callback("review_task_create")
        cb(self._fake_task(exc=RuntimeError("boom")))
        mock_metrics.fire_forget_tasks_total.inc.assert_called_once_with(
            task_type="review_task_create", status="failed"
        )

    def test_cancelled(self, mock_metrics):
        cb = ffm.make_done_callback("warning_intervention")
        cb(self._fake_task(cancelled=True))
        mock_metrics.fire_forget_tasks_total.inc.assert_called_once_with(
            task_type="warning_intervention", status="cancelled"
        )

    def test_observes_duration_when_start_given(self, mock_metrics):
        start = 1.0
        cb = ffm.make_done_callback("pdf_generation", start_time=start)
        cb(self._fake_task(result="ok"))
        mock_metrics.fire_forget_task_duration_seconds.observe.assert_called_once()
        args, kwargs = mock_metrics.fire_forget_task_duration_seconds.observe.call_args
        assert kwargs.get("task_type") == "pdf_generation"
        assert args[0] >= 0  # duration >= 0


class TestRegisterTask:
    def test_register_records_scheduled_and_returns_task(self, mock_metrics):
        task = MagicMock()
        out = ffm.register_task(task, "validation_job")
        assert out is task
        # scheduled 被记录
        mock_metrics.fire_forget_tasks_total.inc.assert_any_call(
            task_type="validation_job", status="scheduled"
        )
        # 注册了 done_callback
        task.add_done_callback.assert_called_once()
