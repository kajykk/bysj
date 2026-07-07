"""v1.36: observability Celery 任务测试.

覆盖:
- flush_lock_stats_task: 成功 / 异常重试 / MaxRetriesExceededError 路径
- _flush_lock_stats_impl: success=True(commit) / success=False(rollback) / 异常(rollback)
- _get_loop / _run_async 辅助函数
- beat schedule 配置
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

from app.core.celery_app import celery_app

# ---------- 任务注册与 beat schedule ----------


def _ensure_tasks_loaded() -> None:
    """显式加载 observability tasks 模块, 确保任务已注册."""
    import app.tasks.observability  # noqa: F401


def test_flush_lock_stats_task_registered() -> None:
    """TC-COV-OBS-001: flush_lock_stats_task 应在 Celery 中注册."""
    _ensure_tasks_loaded()
    task_names = list(celery_app.tasks.keys())
    assert "app.tasks.observability.flush_lock_stats_task" in task_names


def test_flush_lock_stats_in_beat_schedule() -> None:
    """TC-COV-OBS-002: flush-lock-stats 应在 beat schedule 中, 60s 间隔."""
    schedule = celery_app.conf.beat_schedule
    assert "flush-lock-stats" in schedule
    assert (
        schedule["flush-lock-stats"]["task"]
        == "app.tasks.observability.flush_lock_stats_task"
    )
    assert schedule["flush-lock-stats"]["schedule"] == 60.0


# ---------- _get_loop / _run_async 辅助函数 ----------


def test_get_loop_caches_singleton() -> None:
    """TC-COV-OBS-003: _get_loop 多次调用应返回同一事件循环."""
    from app.tasks.observability import _get_loop

    loop1 = _get_loop()
    loop2 = _get_loop()
    assert loop1 is loop2


def test_run_async_executes_coroutine() -> None:
    """TC-COV-OBS-004: _run_async 应同步执行协程并返回结果."""
    from app.tasks.observability import _run_async

    async def coro():
        return "ok"

    assert _run_async(coro()) == "ok"


# ---------- flush_lock_stats_task: 成功路径 ----------


def test_flush_lock_stats_task_success() -> None:
    """TC-COV-OBS-005: _run_async 返回 True 时任务应返回 {"success": True}."""
    from app.tasks.observability import flush_lock_stats_task

    with patch("app.tasks.observability._run_async", return_value=True) as mock_run:
        result = flush_lock_stats_task()

    assert result == {"success": True}
    mock_run.assert_called_once()


def test_flush_lock_stats_task_returns_false_on_impl_failure() -> None:
    """TC-COV-OBS-006: _run_async 返回 False 时任务应返回 {"success": False}."""
    from app.tasks.observability import flush_lock_stats_task

    with patch("app.tasks.observability._run_async", return_value=False):
        result = flush_lock_stats_task()

    assert result == {"success": False}


# ---------- flush_lock_stats_task: 异常重试路径 ----------


def test_flush_lock_stats_task_retries_on_exception() -> None:
    """TC-COV-OBS-007: _run_async 抛异常时应调用 self.retry."""
    from celery.exceptions import Retry

    from app.tasks.observability import flush_lock_stats_task

    with patch(
        "app.tasks.observability._run_async", side_effect=RuntimeError("db down")
    ), patch.object(flush_lock_stats_task, "retry", side_effect=Retry()) as mock_retry:
        with pytest.raises(Retry):
            flush_lock_stats_task()
    mock_retry.assert_called_once()


def test_flush_lock_stats_task_max_retries_exceeded_returns_error() -> None:
    """TC-COV-OBS-008: 重试耗尽时应捕获 MaxRetriesExceededError 并返回 error dict."""
    from app.tasks.observability import flush_lock_stats_task

    with patch(
        "app.tasks.observability._run_async", side_effect=RuntimeError("persist fail")
    ), patch.object(
        flush_lock_stats_task,
        "retry",
        side_effect=flush_lock_stats_task.MaxRetriesExceededError,
    ):
        result = flush_lock_stats_task()

    assert result == {"error": "persist fail"}


def test_flush_lock_stats_task_logs(caplog) -> None:
    """TC-COV-OBS-009: 任务执行时应记录 start 与 completed 日志."""
    from app.tasks.observability import flush_lock_stats_task

    with patch("app.tasks.observability._run_async", return_value=True):
        with caplog.at_level(logging.INFO, logger="app.tasks.observability"):
            flush_lock_stats_task()

    assert any("flush_lock_stats_task started" in r.message for r in caplog.records)
    assert any("flush_lock_stats_task completed" in r.message for r in caplog.records)


def test_flush_lock_stats_task_max_retries_logs_error(caplog) -> None:
    """TC-COV-OBS-010: 重试耗尽时应记录 max retries exceeded 错误日志."""
    from app.tasks.observability import flush_lock_stats_task

    with patch(
        "app.tasks.observability._run_async", side_effect=RuntimeError("fail")
    ), patch.object(
        flush_lock_stats_task,
        "retry",
        side_effect=flush_lock_stats_task.MaxRetriesExceededError,
    ):
        with caplog.at_level(logging.ERROR, logger="app.tasks.observability"):
            result = flush_lock_stats_task()

    assert result == {"error": "fail"}
    assert any(
        "flush_lock_stats max retries exceeded" in r.message for r in caplog.records
    )


# ---------- _flush_lock_stats_impl ----------


@pytest.mark.asyncio
async def test_flush_lock_stats_impl_success_commits() -> None:
    """TC-COV-OBS-011: flush_lock_stats 返回 True 时应 commit 并返回 True."""
    from app.tasks.observability import _flush_lock_stats_impl

    mock_db = AsyncMock()
    with patch("app.tasks.observability.AsyncSessionLocal") as mock_sl, patch(
        "app.monitoring.dedup_lock.flush_lock_stats", new=AsyncMock(return_value=True)
    ) as mock_flush:
        mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await _flush_lock_stats_impl()

    assert result is True
    mock_flush.assert_awaited_once_with(mock_db)
    mock_db.commit.assert_awaited_once()
    mock_db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_flush_lock_stats_impl_failure_rolls_back(caplog) -> None:
    """TC-COV-OBS-012: M-ML-4 - flush_lock_stats 返回 False 时应 rollback 并记录 warning."""
    from app.tasks.observability import _flush_lock_stats_impl

    mock_db = AsyncMock()
    with patch("app.tasks.observability.AsyncSessionLocal") as mock_sl, patch(
        "app.monitoring.dedup_lock.flush_lock_stats", new=AsyncMock(return_value=False)
    ):
        mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

        with caplog.at_level(logging.WARNING, logger="app.tasks.observability"):
            result = await _flush_lock_stats_impl()

    assert result is False
    mock_db.rollback.assert_awaited_once()
    mock_db.commit.assert_not_awaited()
    assert any(
        "flush_lock_stats returned False, transaction rolled back" in r.message
        for r in caplog.records
    )


@pytest.mark.asyncio
async def test_flush_lock_stats_impl_exception_rolls_back_and_returns_false(
    caplog,
) -> None:
    """TC-COV-OBS-013: flush_lock_stats 抛异常时应 rollback, 记录 error 并返回 False."""
    from app.tasks.observability import _flush_lock_stats_impl

    mock_db = AsyncMock()
    with patch("app.tasks.observability.AsyncSessionLocal") as mock_sl, patch(
        "app.monitoring.dedup_lock.flush_lock_stats",
        new=AsyncMock(side_effect=RuntimeError("flush boom")),
    ):
        mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

        with caplog.at_level(logging.ERROR, logger="app.tasks.observability"):
            result = await _flush_lock_stats_impl()

    assert result is False
    mock_db.rollback.assert_awaited_once()
    mock_db.commit.assert_not_awaited()
    assert any(
        "flush_lock_stats transaction failed" in r.message for r in caplog.records
    )


@pytest.mark.asyncio
async def test_flush_lock_stats_impl_exception_during_commit_rolls_back() -> None:
    """TC-COV-OBS-014: success=True 但 commit 失败时应走异常分支 rollback + 返回 False."""
    from app.tasks.observability import _flush_lock_stats_impl

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock(side_effect=RuntimeError("commit failed"))
    with patch("app.tasks.observability.AsyncSessionLocal") as mock_sl, patch(
        "app.monitoring.dedup_lock.flush_lock_stats", new=AsyncMock(return_value=True)
    ):
        mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await _flush_lock_stats_impl()

    # commit 异常被外层 except 捕获 -> rollback + return False
    assert result is False
    mock_db.rollback.assert_awaited_once()
