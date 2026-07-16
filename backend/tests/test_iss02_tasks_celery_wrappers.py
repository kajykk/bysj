"""ISS-02 第八轮: app.tasks/* Celery 包装任务 重试/错误处理胶水逻辑聚焦测试.

覆盖点: @celery_app.task(bind=True) 包装函数的控制流胶水
- 成功路径: _run_async(_impl()) 返回数据 / sync 内函数返回 -> 返回结果 dict 或 None
- 失败路径: 异常被捕获 -> self.retry(exc) 触发
  - alerts/observability/anomaly: 内层 except self.MaxRetriesExceededError -> 返回 {"error": str(exc)}
  - scheduler(_run_async 模式): raise self.retry(...) 无内层捕获 -> 传播 MaxRetriesExceededError

通过 PromiseProxy.__wrapped__ 直接调用原函数体 + MagicMock self + monkeypatch 注入,
无需真实 DB / celery worker. 不引入 numpy 链 -> 无 SIGSEGV 风险.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.tasks import alerts, anomaly_detection, observability, scheduler


def _make_task_self():
    """构造模拟的 Celery task self: retry() 触发 MaxRetriesExceededError."""
    self = MagicMock()
    self.MaxRetriesExceededError = type("MaxRetriesExceededError", (Exception,), {})
    self.retry = MagicMock(side_effect=self.MaxRetriesExceededError)
    return self


# ===== alerts: escalate_pending_alerts_task =====
def test_escalate_success(monkeypatch):
    monkeypatch.setattr(alerts, "_run_async", lambda coro: [{"alert_id": 1}])
    out = alerts.escalate_pending_alerts_task.__wrapped__.__func__(_make_task_self())
    assert out == {"escalated": 1}


def test_escalate_error_returns_dict(monkeypatch):
    monkeypatch.setattr(alerts, "_run_async", MagicMock(side_effect=RuntimeError("boom")))
    out = alerts.escalate_pending_alerts_task.__wrapped__.__func__(_make_task_self())
    assert out == {"error": "boom"}


# ===== alerts: archive_old_alerts_task =====
def test_archive_success(monkeypatch):
    monkeypatch.setattr(alerts, "_run_async", lambda coro: 5)
    out = alerts.archive_old_alerts_task.__wrapped__.__func__(_make_task_self())
    assert out == {"archived": 5}


def test_archive_error_returns_dict(monkeypatch):
    monkeypatch.setattr(alerts, "_run_async", MagicMock(side_effect=RuntimeError("boom")))
    out = alerts.archive_old_alerts_task.__wrapped__.__func__(_make_task_self())
    assert out == {"error": "boom"}


# ===== observability: flush_lock_stats_task =====
def test_flush_success(monkeypatch):
    monkeypatch.setattr(observability, "_run_async", lambda coro: True)
    out = observability.flush_lock_stats_task.__wrapped__.__func__(_make_task_self())
    assert out == {"success": True}


def test_flush_error_returns_dict(monkeypatch):
    monkeypatch.setattr(observability, "_run_async", MagicMock(side_effect=RuntimeError("boom")))
    out = observability.flush_lock_stats_task.__wrapped__.__func__(_make_task_self())
    assert out == {"error": "boom"}


# ===== anomaly_detection: detect_anomaly_access_task =====
def test_detect_success(monkeypatch):
    monkeypatch.setattr(anomaly_detection, "_run_async", lambda coro: {"detected": 3})
    out = anomaly_detection.detect_anomaly_access_task.__wrapped__.__func__(_make_task_self())
    assert out == {"detected": 3}


def test_detect_error_returns_dict(monkeypatch):
    monkeypatch.setattr(anomaly_detection, "_run_async", MagicMock(side_effect=RuntimeError("boom")))
    out = anomaly_detection.detect_anomaly_access_task.__wrapped__.__func__(_make_task_self())
    assert out == {"error": "boom"}


# ===== scheduler: _run_async(_impl()) 模式包装任务 (错误路径传播 MaxRetriesExceededError) =====
SCHEDULER_RUN_ASYNC_WRAPPERS = [
    scheduler.daily_risk_scan,
    scheduler.stale_warning_reminder,
    scheduler.daily_intervention_check,
    scheduler.weekly_log_archive,
    scheduler.mask_old_ips_task,
    scheduler.weekly_risk_assessment_archive,
    scheduler.weekly_monitoring_logs_archive,
    scheduler.canary_auto_rollback_check,
]


@pytest.mark.parametrize("task_fn", SCHEDULER_RUN_ASYNC_WRAPPERS)
def test_scheduler_wrapper_success(task_fn, monkeypatch):
    monkeypatch.setattr(scheduler, "_run_async", lambda coro: None)
    assert task_fn.__wrapped__.__func__(_make_task_self()) is None


@pytest.mark.parametrize("task_fn", SCHEDULER_RUN_ASYNC_WRAPPERS)
def test_scheduler_wrapper_error_raises(task_fn, monkeypatch):
    monkeypatch.setattr(scheduler, "_run_async", MagicMock(side_effect=RuntimeError("boom")))
    self = _make_task_self()
    with pytest.raises(self.MaxRetriesExceededError):
        task_fn.__wrapped__.__func__(self)


# ===== scheduler: sync 内函数包装任务 (cleanup_*) =====
def test_cleanup_training_jobs_success(monkeypatch):
    monkeypatch.setattr(
        "app.services.model_predict_service.cleanup_old_training_jobs", lambda: 3
    )
    assert scheduler.cleanup_training_jobs_task.__wrapped__.__func__(_make_task_self()) is None


def test_cleanup_training_jobs_error(monkeypatch):
    monkeypatch.setattr(
        "app.services.model_predict_service.cleanup_old_training_jobs",
        MagicMock(side_effect=RuntimeError("boom")),
    )
    self = _make_task_self()
    with pytest.raises(self.MaxRetriesExceededError):
        scheduler.cleanup_training_jobs_task.__wrapped__.__func__(self)


def test_cleanup_uploads_dir_success(monkeypatch):
    monkeypatch.setattr(scheduler, "_cleanup_uploads_dir_impl", lambda: 2)
    assert scheduler.cleanup_uploads_dir_task.__wrapped__.__func__(_make_task_self()) is None


def test_cleanup_uploads_dir_error(monkeypatch):
    monkeypatch.setattr(
        scheduler, "_cleanup_uploads_dir_impl", MagicMock(side_effect=RuntimeError("boom"))
    )
    self = _make_task_self()
    with pytest.raises(self.MaxRetriesExceededError):
        scheduler.cleanup_uploads_dir_task.__wrapped__.__func__(self)


def test_cleanup_experiment_artifacts_success(monkeypatch):
    monkeypatch.setattr(scheduler, "_cleanup_experiment_artifacts_impl", lambda: 1)
    assert scheduler.cleanup_experiment_artifacts_task.__wrapped__.__func__(_make_task_self()) is None


def test_cleanup_experiment_artifacts_error(monkeypatch):
    monkeypatch.setattr(
        scheduler,
        "_cleanup_experiment_artifacts_impl",
        MagicMock(side_effect=RuntimeError("boom")),
    )
    self = _make_task_self()
    with pytest.raises(self.MaxRetriesExceededError):
        scheduler.cleanup_experiment_artifacts_task.__wrapped__.__func__(self)
