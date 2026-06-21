"""Tests for tasks scheduler module."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.tasks.scheduler import _get_loop, _run_async


class TestGetLoop:
    """Test _get_loop."""

    def test_returns_loop(self):
        """TC-COV-TASK-001: Returns event loop."""
        loop = _get_loop()
        assert loop is not None
        assert not loop.is_closed()

    def test_caches_loop(self):
        """TC-COV-TASK-002: Returns same loop on subsequent calls."""
        loop1 = _get_loop()
        loop2 = _get_loop()
        assert loop1 is loop2


class TestRunAsync:
    """Test _run_async."""

    def test_runs_coro(self):
        """TC-COV-TASK-003: Runs coroutine and returns result."""
        async def sample_coro():
            return 42

        result = _run_async(sample_coro())
        assert result == 42


class TestDailyRiskScan:
    """Test daily_risk_scan task."""

    @patch("app.tasks.scheduler._run_async")
    def test_task_runs(self, mock_run_async):
        """TC-COV-TASK-004: daily_risk_scan task executes."""
        from app.tasks.scheduler import daily_risk_scan

        mock_self = MagicMock()
        daily_risk_scan(mock_self)
        mock_run_async.assert_called_once()


class TestStaleWarningReminder:
    """Test stale_warning_reminder task."""

    @patch("app.tasks.scheduler._run_async")
    def test_task_runs(self, mock_run_async):
        """TC-COV-TASK-005: stale_warning_reminder task executes."""
        from app.tasks.scheduler import stale_warning_reminder

        mock_self = MagicMock()
        stale_warning_reminder(mock_self)
        mock_run_async.assert_called_once()


class TestDailyInterventionCheck:
    """Test daily_intervention_check task."""

    @patch("app.tasks.scheduler._run_async")
    def test_task_runs(self, mock_run_async):
        """TC-COV-TASK-006: daily_intervention_check task executes."""
        from app.tasks.scheduler import daily_intervention_check

        mock_self = MagicMock()
        daily_intervention_check(mock_self)
        mock_run_async.assert_called_once()


class TestWeeklyLogArchive:
    """Test weekly_log_archive task."""

    @patch("app.tasks.scheduler._run_async")
    def test_task_runs(self, mock_run_async):
        """TC-COV-TASK-007: weekly_log_archive task executes."""
        from app.tasks.scheduler import weekly_log_archive

        mock_self = MagicMock()
        weekly_log_archive(mock_self)
        mock_run_async.assert_called_once()


class TestCanaryAutoRollbackCheck:
    """Test canary_auto_rollback_check task."""

    @patch("app.tasks.scheduler._run_async")
    def test_task_runs(self, mock_run_async):
        """TC-COV-TASK-008: canary_auto_rollback_check task executes."""
        from app.tasks.scheduler import canary_auto_rollback_check

        mock_self = MagicMock()
        canary_auto_rollback_check(mock_self)
        mock_run_async.assert_called_once()
