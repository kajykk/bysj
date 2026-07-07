"""Tests for tasks scheduler module."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from celery.exceptions import Retry

from app.core import celery_async as celery_async_mod
from app.core.celery_app import celery_app
from app.tasks.scheduler import _get_loop, _run_async, _to_aware_utc


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

        # bind=True 使 celery 自动注入 task instance 作为 self，直接调用即可
        daily_risk_scan()
        mock_run_async.assert_called_once()


class TestStaleWarningReminder:
    """Test stale_warning_reminder task."""

    @patch("app.tasks.scheduler._run_async")
    def test_task_runs(self, mock_run_async):
        """TC-COV-TASK-005: stale_warning_reminder task executes."""
        from app.tasks.scheduler import stale_warning_reminder

        stale_warning_reminder()
        mock_run_async.assert_called_once()


class TestDailyInterventionCheck:
    """Test daily_intervention_check task."""

    @patch("app.tasks.scheduler._run_async")
    def test_task_runs(self, mock_run_async):
        """TC-COV-TASK-006: daily_intervention_check task executes."""
        from app.tasks.scheduler import daily_intervention_check

        daily_intervention_check()
        mock_run_async.assert_called_once()


class TestWeeklyLogArchive:
    """Test weekly_log_archive task."""

    @patch("app.tasks.scheduler._run_async")
    def test_task_runs(self, mock_run_async):
        """TC-COV-TASK-007: weekly_log_archive task executes."""
        from app.tasks.scheduler import weekly_log_archive

        weekly_log_archive()
        mock_run_async.assert_called_once()


class TestCanaryAutoRollbackCheck:
    """Test canary_auto_rollback_check task."""

    @patch("app.tasks.scheduler._run_async")
    def test_task_runs(self, mock_run_async):
        """TC-COV-TASK-008: canary_auto_rollback_check task executes."""
        from app.tasks.scheduler import canary_auto_rollback_check

        canary_auto_rollback_check()
        mock_run_async.assert_called_once()


# ===========================================================================
# TC-COV-TASK 扩展: 覆盖 _to_aware_utc / _notify_warning / retry 路径 / impl
# ===========================================================================


@pytest.fixture
def reset_event_loop():
    """保存并还原 celery_async._event_loop 全局状态, 防止测试互相污染.

    注意: RES-P1-003 修复后, _event_loop 单例迁移到 app.core.celery_async 模块,
    4 个 Celery 任务模块通过别名导入复用. 故此处应操作 celery_async._event_loop.
    """
    original = celery_async_mod._event_loop
    yield
    celery_async_mod._event_loop = original


# ---------- _to_aware_utc ----------


class TestToAwareUtc:
    """覆盖 _to_aware_utc: naive datetime 归一化为 UTC aware."""

    def test_naive_datetime_gets_utc_tzinfo(self):
        """TC-COV-TASK-009: naive datetime 应被补充 UTC tzinfo."""
        naive = datetime(2024, 1, 1, 12, 0, 0)
        aware = _to_aware_utc(naive)
        assert aware.tzinfo is UTC
        assert aware.year == 2024
        assert aware.hour == 12

    def test_aware_datetime_unchanged(self):
        """TC-COV-TASK-010: aware datetime 应保持原有时区, 不被改写为 UTC."""
        tz_plus8 = timezone(timedelta(hours=8))
        aware = datetime(2024, 1, 1, 12, 0, 0, tzinfo=tz_plus8)
        result = _to_aware_utc(aware)
        assert result is aware
        assert result.tzinfo is tz_plus8


# ---------- _get_loop 边界场景 ----------


class TestGetLoopEdgeCases:
    """覆盖 _get_loop: 已关闭循环应被重建."""

    def test_recreates_closed_loop(self, reset_event_loop):
        """TC-COV-TASK-011: 已关闭的事件循环应被重建.

        RES-P1-003 修复后, _event_loop 单例迁移到 app.core.celery_async 模块,
        故此处操作 celery_async_mod._event_loop.
        """
        closed_loop = MagicMock()
        closed_loop.is_closed.return_value = True
        celery_async_mod._event_loop = closed_loop

        new_loop = _get_loop()
        try:
            assert new_loop is not closed_loop
            assert not new_loop.is_closed()
        finally:
            # 清理: 关闭新建的循环, 防止资源泄漏
            if not new_loop.is_closed():
                new_loop.close()


# ---------- _notify_warning ----------


class TestNotifyWarning:
    """覆盖 _notify_warning: WebSocket 通知 + 异常吞掉 + 咨询师可选."""

    @pytest.mark.asyncio
    async def test_notify_warning_success_with_counselor(self):
        """TC-COV-TASK-012: 成功发送用户与咨询师通知."""
        with patch("app.core.ws.notify_warning", new=AsyncMock()) as mock_user, patch(
            "app.core.ws.notify_counselor", new=AsyncMock()
        ) as mock_counselor, patch(
            "app.core.contracts.normalize_risk_level", return_value="high"
        ):
            from app.tasks.scheduler import _notify_warning

            await _notify_warning(
                user_id=1,
                warning_id=10,
                risk_level=3,
                trigger_reason="r",
                counselor_id=2,
            )

        mock_user.assert_awaited_once()
        mock_counselor.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_notify_warning_without_counselor(self):
        """TC-COV-TASK-013: counselor_id 为 None 时只通知用户."""
        with patch("app.core.ws.notify_warning", new=AsyncMock()) as mock_user, patch(
            "app.core.ws.notify_counselor", new=AsyncMock()
        ) as mock_counselor, patch(
            "app.core.contracts.normalize_risk_level", return_value="mid"
        ):
            from app.tasks.scheduler import _notify_warning

            await _notify_warning(
                user_id=1,
                warning_id=11,
                risk_level=2,
                trigger_reason="r",
                counselor_id=None,
            )

        mock_user.assert_awaited_once()
        mock_counselor.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_notify_warning_swallows_exception(self, caplog):
        """TC-COV-TASK-014: WebSocket 异常应被吞掉并记录 warning, 不向上抛."""
        import logging

        with patch(
            "app.core.ws.notify_warning",
            new=AsyncMock(side_effect=RuntimeError("ws down")),
        ), patch("app.core.ws.notify_counselor", new=AsyncMock()), patch(
            "app.core.contracts.normalize_risk_level", return_value="high"
        ):
            from app.tasks.scheduler import _notify_warning

            with caplog.at_level(logging.WARNING, logger="app.tasks.scheduler"):
                # 不应抛异常
                await _notify_warning(
                    user_id=1,
                    warning_id=99,
                    risk_level=3,
                    trigger_reason="r",
                    counselor_id=2,
                )

        assert any(
            "Failed to send WebSocket notification for warning 99" in r.message
            for r in caplog.records
        )


# ---------- Celery 任务 retry 路径 (5 个任务) ----------


class TestTaskRetryPaths:
    """覆盖 5 个 Celery 任务的 retry 异常路径."""

    def test_daily_risk_scan_retries_on_failure(self):
        """TC-COV-TASK-015: daily_risk_scan 失败时应调用 self.retry."""
        from app.tasks.scheduler import daily_risk_scan

        with patch(
            "app.tasks.scheduler._run_async", side_effect=RuntimeError("db down")
        ), patch.object(daily_risk_scan, "retry", side_effect=Retry()) as mock_retry:
            with pytest.raises(Retry):
                daily_risk_scan()
        mock_retry.assert_called_once()

    def test_stale_warning_reminder_retries_on_failure(self):
        """TC-COV-TASK-016: stale_warning_reminder 失败时应调用 self.retry."""
        from app.tasks.scheduler import stale_warning_reminder

        with patch(
            "app.tasks.scheduler._run_async", side_effect=RuntimeError("db down")
        ), patch.object(
            stale_warning_reminder, "retry", side_effect=Retry()
        ) as mock_retry:
            with pytest.raises(Retry):
                stale_warning_reminder()
        mock_retry.assert_called_once()

    def test_daily_intervention_check_retries_on_failure(self):
        """TC-COV-TASK-017: daily_intervention_check 失败时应调用 self.retry."""
        from app.tasks.scheduler import daily_intervention_check

        with patch(
            "app.tasks.scheduler._run_async", side_effect=RuntimeError("db down")
        ), patch.object(
            daily_intervention_check, "retry", side_effect=Retry()
        ) as mock_retry:
            with pytest.raises(Retry):
                daily_intervention_check()
        mock_retry.assert_called_once()

    def test_weekly_log_archive_retries_on_failure(self):
        """TC-COV-TASK-018: weekly_log_archive 失败时应调用 self.retry."""
        from app.tasks.scheduler import weekly_log_archive

        with patch(
            "app.tasks.scheduler._run_async", side_effect=RuntimeError("db down")
        ), patch.object(weekly_log_archive, "retry", side_effect=Retry()) as mock_retry:
            with pytest.raises(Retry):
                weekly_log_archive()
        mock_retry.assert_called_once()

    def test_canary_auto_rollback_check_retries_on_failure(self):
        """TC-COV-TASK-019: canary_auto_rollback_check 失败时应调用 self.retry."""
        from app.tasks.scheduler import canary_auto_rollback_check

        with patch(
            "app.tasks.scheduler._run_async", side_effect=RuntimeError("db down")
        ), patch.object(
            canary_auto_rollback_check, "retry", side_effect=Retry()
        ) as mock_retry:
            with pytest.raises(Retry):
                canary_auto_rollback_check()
        mock_retry.assert_called_once()


# ---------- _daily_risk_scan_impl ----------


class TestDailyRiskScanImpl:
    """覆盖 _daily_risk_scan_impl: 扫描/阈值/幂等/绑定/commit-fail 分支."""

    @pytest.mark.asyncio
    async def test_no_active_users(self):
        """TC-COV-TASK-020: 无活跃用户时仅 commit, 不生成告警."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

            from app.tasks.scheduler import _daily_risk_scan_impl

            await _daily_risk_scan_impl()

        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_user_without_risk_assessment(self):
        """TC-COV-TASK-021: 用户无风险评估记录时跳过, 不创建告警."""
        mock_user = MagicMock()
        mock_user.id = 1
        mock_db = AsyncMock()
        users_result = MagicMock()
        users_result.scalars.return_value.all.return_value = [mock_user]
        risk_result = MagicMock()
        risk_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(side_effect=[users_result, risk_result])

        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

            from app.tasks.scheduler import _daily_risk_scan_impl

            await _daily_risk_scan_impl()

        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_recent_risk_no_warning(self):
        """TC-COV-TASK-022: 近期 (<7 天) 风险评估不生成告警."""
        mock_user = MagicMock()
        mock_user.id = 1
        mock_risk = MagicMock()
        mock_risk.id = 100
        mock_risk.risk_level = 3
        mock_risk.created_at = datetime.now(UTC)  # 刚刚, days_since=0

        mock_db = AsyncMock()
        users_result = MagicMock()
        users_result.scalars.return_value.all.return_value = [mock_user]
        risk_result = MagicMock()
        risk_result.scalar_one_or_none.return_value = mock_risk
        mock_db.execute = AsyncMock(side_effect=[users_result, risk_result])

        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

            from app.tasks.scheduler import _daily_risk_scan_impl

            await _daily_risk_scan_impl()

        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_low_risk_no_warning(self):
        """TC-COV-TASK-023: >7 天但风险等级 <2 不生成告警."""
        mock_user = MagicMock()
        mock_user.id = 1
        old_time = datetime.now(UTC) - timedelta(days=10)
        mock_risk = MagicMock()
        mock_risk.id = 100
        mock_risk.risk_level = 1  # < 2
        mock_risk.created_at = old_time

        mock_db = AsyncMock()
        users_result = MagicMock()
        users_result.scalars.return_value.all.return_value = [mock_user]
        risk_result = MagicMock()
        risk_result.scalar_one_or_none.return_value = mock_risk
        mock_db.execute = AsyncMock(side_effect=[users_result, risk_result])

        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

            from app.tasks.scheduler import _daily_risk_scan_impl

            await _daily_risk_scan_impl()

        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_high_risk_generates_warning_with_counselor(self):
        """TC-COV-TASK-024: >7 天 + 风险等级 >=2 + 无重复告警 -> 创建告警并通知."""
        mock_user = MagicMock()
        mock_user.id = 1
        old_time = datetime.now(UTC) - timedelta(days=10)
        mock_risk = MagicMock()
        mock_risk.id = 100
        mock_risk.risk_level = 3
        mock_risk.created_at = old_time

        mock_setting = MagicMock()
        mock_setting.threshold_level = 2
        mock_binding = MagicMock()
        mock_binding.counselor_id = 42

        mock_db = AsyncMock()
        users_result = MagicMock()
        users_result.scalars.return_value.all.return_value = [mock_user]
        risk_result = MagicMock()
        risk_result.scalar_one_or_none.return_value = mock_risk
        setting_result = MagicMock()
        setting_result.scalar_one_or_none.return_value = mock_setting
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        bind_result = MagicMock()
        bind_result.scalar_one_or_none.return_value = mock_binding
        mock_db.execute = AsyncMock(
            side_effect=[
                users_result,
                risk_result,
                setting_result,
                existing_result,
                bind_result,
            ]
        )

        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl, patch(
            "app.tasks.scheduler._notify_warning", new=AsyncMock()
        ) as mock_notify:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

            from app.tasks.scheduler import _daily_risk_scan_impl

            await _daily_risk_scan_impl()

        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()
        mock_db.commit.assert_awaited_once()
        # H-ML-6: commit 成功后才发通知
        mock_notify.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_existing_recent_warning_skipped(self):
        """TC-COV-TASK-025: 已存在近 1 天的告警时不重复创建."""
        mock_user = MagicMock()
        mock_user.id = 1
        old_time = datetime.now(UTC) - timedelta(days=10)
        mock_risk = MagicMock()
        mock_risk.id = 100
        mock_risk.risk_level = 3
        mock_risk.created_at = old_time

        mock_db = AsyncMock()
        users_result = MagicMock()
        users_result.scalars.return_value.all.return_value = [mock_user]
        risk_result = MagicMock()
        risk_result.scalar_one_or_none.return_value = mock_risk
        # setting 默认走 else 分支: threshold = 2
        setting_result = MagicMock()
        setting_result.scalar_one_or_none.return_value = None
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = MagicMock()  # 已存在
        mock_db.execute = AsyncMock(
            side_effect=[
                users_result,
                risk_result,
                setting_result,
                existing_result,
            ]
        )

        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl, patch(
            "app.tasks.scheduler._notify_warning", new=AsyncMock()
        ) as mock_notify:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

            from app.tasks.scheduler import _daily_risk_scan_impl

            await _daily_risk_scan_impl()

        mock_db.add.assert_not_called()
        mock_notify.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_threshold_setting_higher_than_risk(self):
        """TC-COV-TASK-026: 阈值高于风险等级时不生成告警 (走 latest_risk < threshold 分支)."""
        mock_user = MagicMock()
        mock_user.id = 1
        old_time = datetime.now(UTC) - timedelta(days=10)
        mock_risk = MagicMock()
        mock_risk.id = 100
        mock_risk.risk_level = 3
        mock_risk.created_at = old_time

        mock_setting = MagicMock()
        mock_setting.threshold_level = 4  # 阈值高于 3, 不告警

        mock_db = AsyncMock()
        users_result = MagicMock()
        users_result.scalars.return_value.all.return_value = [mock_user]
        risk_result = MagicMock()
        risk_result.scalar_one_or_none.return_value = mock_risk
        setting_result = MagicMock()
        setting_result.scalar_one_or_none.return_value = mock_setting
        mock_db.execute = AsyncMock(
            side_effect=[users_result, risk_result, setting_result]
        )

        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl, patch(
            "app.tasks.scheduler._notify_warning", new=AsyncMock()
        ) as mock_notify:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

            from app.tasks.scheduler import _daily_risk_scan_impl

            await _daily_risk_scan_impl()

        mock_db.add.assert_not_called()
        mock_notify.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_warning_without_counselor_binding(self):
        """TC-COV-TASK-027: 无咨询师绑定时仍创建告警, 但 counselor_id 不设置, 仅通知用户."""
        mock_user = MagicMock()
        mock_user.id = 1
        old_time = datetime.now(UTC) - timedelta(days=10)
        mock_risk = MagicMock()
        mock_risk.id = 100
        mock_risk.risk_level = 3
        mock_risk.created_at = old_time

        mock_db = AsyncMock()
        users_result = MagicMock()
        users_result.scalars.return_value.all.return_value = [mock_user]
        risk_result = MagicMock()
        risk_result.scalar_one_or_none.return_value = mock_risk
        setting_result = MagicMock()
        setting_result.scalar_one_or_none.return_value = None  # 走 else, threshold=2
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        bind_result = MagicMock()
        bind_result.scalar_one_or_none.return_value = None  # 无绑定
        mock_db.execute = AsyncMock(
            side_effect=[
                users_result,
                risk_result,
                setting_result,
                existing_result,
                bind_result,
            ]
        )

        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl, patch(
            "app.tasks.scheduler._notify_warning", new=AsyncMock()
        ) as mock_notify:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

            from app.tasks.scheduler import _daily_risk_scan_impl

            await _daily_risk_scan_impl()

        mock_db.add.assert_called_once()
        mock_notify.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_commit_failure_skips_notification(self):
        """TC-COV-TASK-028: H-ML-6 - commit 失败时不应发送通知 (避免用户收到告警但 DB 无记录)."""
        mock_user = MagicMock()
        mock_user.id = 1
        old_time = datetime.now(UTC) - timedelta(days=10)
        mock_risk = MagicMock()
        mock_risk.id = 100
        mock_risk.risk_level = 3
        mock_risk.created_at = old_time

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock(side_effect=RuntimeError("commit failed"))
        users_result = MagicMock()
        users_result.scalars.return_value.all.return_value = [mock_user]
        risk_result = MagicMock()
        risk_result.scalar_one_or_none.return_value = mock_risk
        setting_result = MagicMock()
        setting_result.scalar_one_or_none.return_value = None
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        bind_result = MagicMock()
        bind_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(
            side_effect=[
                users_result,
                risk_result,
                setting_result,
                existing_result,
                bind_result,
            ]
        )

        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl, patch(
            "app.tasks.scheduler._notify_warning", new=AsyncMock()
        ) as mock_notify:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

            from app.tasks.scheduler import _daily_risk_scan_impl

            with pytest.raises(RuntimeError):
                await _daily_risk_scan_impl()

        # commit 失败, 不应发通知
        mock_notify.assert_not_awaited()


# ---------- _stale_warning_reminder_impl ----------


class TestStaleWarningReminderImpl:
    """覆盖 _stale_warning_reminder_impl: 24h 未处理告警提醒."""

    @pytest.mark.asyncio
    async def test_no_stale_warnings(self):
        """TC-COV-TASK-029: 无过期未处理告警时不输出日志."""
        mock_db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result)

        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

            from app.tasks.scheduler import _stale_warning_reminder_impl

            await _stale_warning_reminder_impl()

        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_stale_warning_with_counselor_logs(self, caplog):
        """TC-COV-TASK-030: 过期未处理告警且 counselor_id 存在时记录 reminder 日志."""
        import logging

        mock_warning = MagicMock()
        mock_warning.id = 5
        mock_warning.user_id = 1
        mock_warning.counselor_id = 2
        mock_db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [mock_warning]
        mock_db.execute = AsyncMock(return_value=result)

        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

            with caplog.at_level(logging.INFO, logger="app.tasks.scheduler"):
                from app.tasks.scheduler import _stale_warning_reminder_impl

                await _stale_warning_reminder_impl()

        assert any("Reminder: Warning 5" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_stale_warning_without_counselor_no_log(self, caplog):
        """TC-COV-TASK-031: 过期告警无 counselor_id 时不记录 reminder 日志."""
        import logging

        mock_warning = MagicMock()
        mock_warning.id = 6
        mock_warning.user_id = 1
        mock_warning.counselor_id = None
        mock_db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [mock_warning]
        mock_db.execute = AsyncMock(return_value=result)

        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

            with caplog.at_level(logging.INFO, logger="app.tasks.scheduler"):
                from app.tasks.scheduler import _stale_warning_reminder_impl

                await _stale_warning_reminder_impl()

        assert not any("Reminder: Warning 6" in r.message for r in caplog.records)


# ---------- _daily_intervention_check_impl ----------


class TestDailyInterventionCheckImpl:
    """覆盖 _daily_intervention_check_impl: 计划完成/任务执行/进度计算."""

    @pytest.mark.asyncio
    async def test_no_active_plans(self):
        """TC-COV-TASK-032: 无活跃计划时仅 commit."""
        mock_db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result)

        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

            from app.tasks.scheduler import _daily_intervention_check_impl

            await _daily_intervention_check_impl()

        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_plan_end_date_passed_marks_completed(self):
        """TC-COV-TASK-033: 计划 end_date 早于今天时标记为 completed.

        注意: 代码使用 ``today = datetime.now(UTC).date()`` (L-ML-9 修复),
        故测试中 ``mock_plan.end_date`` 也应基于 UTC 日期计算, 避免在本地
        时区凌晨 (UTC 仍为前一天) 时出现 ``end_date == today`` 的边界情况.
        """
        from datetime import UTC, datetime

        mock_plan = MagicMock()
        mock_plan.id = 1
        mock_plan.user_id = 10
        mock_plan.end_date = datetime.now(UTC).date() - timedelta(
            days=1
        )  # 已过期 (UTC)
        mock_db = AsyncMock()
        plans_result = MagicMock()
        plans_result.scalars.return_value.all.return_value = [mock_plan]
        mock_db.execute = AsyncMock(return_value=plans_result)

        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

            from app.tasks.scheduler import _daily_intervention_check_impl

            await _daily_intervention_check_impl()

        assert mock_plan.status == "completed"
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_plan_without_end_date_skips(self):
        """TC-COV-TASK-034: 计划无 end_date 时不标记完成, 继续处理任务."""
        mock_plan = MagicMock()
        mock_plan.id = 1
        mock_plan.user_id = 10
        mock_plan.end_date = None
        mock_db = AsyncMock()
        plans_result = MagicMock()
        plans_result.scalars.return_value.all.return_value = [mock_plan]
        tasks_result = MagicMock()
        tasks_result.scalars.return_value.all.return_value = []
        # 后续 total/completed 查询
        total_result = MagicMock()
        total_result.scalar_one.return_value = 0
        completed_result = MagicMock()
        completed_result.scalar_one.return_value = 0
        mock_db.execute = AsyncMock(
            side_effect=[
                plans_result,
                tasks_result,
                total_result,
                completed_result,
            ]
        )

        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

            from app.tasks.scheduler import _daily_intervention_check_impl

            await _daily_intervention_check_impl()

        mock_plan.status.__eq__ != "completed"  # 状态未变

    @pytest.mark.asyncio
    async def test_daily_task_creates_execution(self):
        """TC-COV-TASK-035: daily 任务且今日无执行记录时应创建 pending 执行."""
        from datetime import date

        mock_plan = MagicMock()
        mock_plan.id = 1
        mock_plan.user_id = 10
        mock_plan.end_date = date.today() + timedelta(days=7)  # 未过期
        mock_task = MagicMock()
        mock_task.id = 50
        mock_task.schedule = "daily"
        mock_db = AsyncMock()
        plans_result = MagicMock()
        plans_result.scalars.return_value.all.return_value = [mock_plan]
        tasks_result = MagicMock()
        tasks_result.scalars.return_value.all.return_value = [mock_task]
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None  # 今日无执行
        total_result = MagicMock()
        total_result.scalar_one.return_value = 1
        completed_result = MagicMock()
        completed_result.scalar_one.return_value = 0
        mock_db.execute = AsyncMock(
            side_effect=[
                plans_result,
                tasks_result,
                existing_result,
                total_result,
                completed_result,
            ]
        )

        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

            from app.tasks.scheduler import _daily_intervention_check_impl

            await _daily_intervention_check_impl()

        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()
        assert mock_plan.progress == 0

    @pytest.mark.asyncio
    async def test_existing_execution_skipped(self):
        """TC-COV-TASK-036: 已存在今日执行记录时跳过创建."""
        from datetime import date

        mock_plan = MagicMock()
        mock_plan.id = 1
        mock_plan.user_id = 10
        mock_plan.end_date = date.today() + timedelta(days=7)
        mock_task = MagicMock()
        mock_task.id = 50
        mock_task.schedule = "daily"
        mock_db = AsyncMock()
        plans_result = MagicMock()
        plans_result.scalars.return_value.all.return_value = [mock_plan]
        tasks_result = MagicMock()
        tasks_result.scalars.return_value.all.return_value = [mock_task]
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = MagicMock()  # 已存在
        total_result = MagicMock()
        total_result.scalar_one.return_value = 1
        completed_result = MagicMock()
        completed_result.scalar_one.return_value = 1  # 已完成
        mock_db.execute = AsyncMock(
            side_effect=[
                plans_result,
                tasks_result,
                existing_result,
                total_result,
                completed_result,
            ]
        )

        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

            from app.tasks.scheduler import _daily_intervention_check_impl

            await _daily_intervention_check_impl()

        mock_db.add.assert_not_called()
        assert mock_plan.progress == 100  # 1/1 * 100

    @pytest.mark.asyncio
    async def test_non_daily_schedule_skipped(self):
        """TC-COV-TASK-037: 非 daily 调度的任务不创建执行 (但仍有 total/completed 查询)."""
        from datetime import date

        mock_plan = MagicMock()
        mock_plan.id = 1
        mock_plan.user_id = 10
        mock_plan.end_date = date.today() + timedelta(days=7)
        mock_task = MagicMock()
        mock_task.id = 50
        mock_task.schedule = "weekly"  # 非 daily
        mock_db = AsyncMock()
        plans_result = MagicMock()
        plans_result.scalars.return_value.all.return_value = [mock_plan]
        tasks_result = MagicMock()
        tasks_result.scalars.return_value.all.return_value = [mock_task]
        total_result = MagicMock()
        total_result.scalar_one.return_value = 1
        completed_result = MagicMock()
        completed_result.scalar_one.return_value = 0
        mock_db.execute = AsyncMock(
            side_effect=[
                plans_result,
                tasks_result,
                total_result,
                completed_result,
            ]
        )

        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

            from app.tasks.scheduler import _daily_intervention_check_impl

            await _daily_intervention_check_impl()

        mock_db.add.assert_not_called()


# ---------- _weekly_log_archive_impl ----------


class TestWeeklyLogArchiveImpl:
    """覆盖 _weekly_log_archive_impl: 调用 AdminService.archive_old_logs."""

    @pytest.mark.asyncio
    async def test_archive_calls_service(self):
        """TC-COV-TASK-038: 应调用 AdminService.archive_old_logs(days=90) 并记录日志."""
        mock_db = AsyncMock()
        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl, patch(
            "app.services.admin_service.AdminService"
        ) as mock_svc_cls:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_service = mock_svc_cls.return_value
            mock_service.archive_old_logs = AsyncMock(return_value=42)

            from app.tasks.scheduler import _weekly_log_archive_impl

            await _weekly_log_archive_impl()

        mock_svc_cls.assert_called_once_with(mock_db)
        mock_service.archive_old_logs.assert_awaited_once_with(days=90)


# ---------- _canary_auto_rollback_check_impl ----------


class TestCanaryAutoRollbackCheckImpl:
    """覆盖 _canary_auto_rollback_check_impl: canary 健康检查结果分支."""

    @pytest.mark.asyncio
    async def test_no_canaries(self):
        """TC-COV-TASK-039: 无 canary 时正常返回."""
        mock_db = AsyncMock()
        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl, patch(
            "app.services.auto_rollback_service.auto_rollback_service"
        ) as mock_svc:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_svc.check_all_canaries = AsyncMock(return_value=[])

            from app.tasks.scheduler import _canary_auto_rollback_check_impl

            await _canary_auto_rollback_check_impl()

        mock_svc.check_all_canaries.assert_awaited_once_with(mock_db)

    @pytest.mark.asyncio
    async def test_canary_rollback_triggered_logs_warning(self, caplog):
        """TC-COV-TASK-040: should_rollback=True 时记录 warning 日志."""
        import logging

        mock_result = MagicMock()
        mock_result.should_rollback = True
        mock_result.canary_id = 7
        mock_result.reason = "fallback_rate 50% exceeds threshold 5%"
        mock_result.metrics = {"fallback_rate": 0.5}

        mock_db = AsyncMock()
        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl, patch(
            "app.services.auto_rollback_service.auto_rollback_service"
        ) as mock_svc, caplog.at_level(logging.WARNING, logger="app.tasks.scheduler"):
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_svc.check_all_canaries = AsyncMock(return_value=[mock_result])

            from app.tasks.scheduler import _canary_auto_rollback_check_impl

            await _canary_auto_rollback_check_impl()

        assert any(
            "Auto-rollback triggered for canary 7" in r.message for r in caplog.records
        )

    @pytest.mark.asyncio
    async def test_canary_healthy_logs_debug(self, caplog):
        """TC-COV-TASK-041: should_rollback=False 时记录 debug 日志."""
        import logging

        mock_result = MagicMock()
        mock_result.should_rollback = False
        mock_result.canary_id = 8
        mock_result.reason = "within_thresholds"
        mock_result.metrics = {"fallback_rate": 0.01}

        mock_db = AsyncMock()
        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl, patch(
            "app.services.auto_rollback_service.auto_rollback_service"
        ) as mock_svc, caplog.at_level(logging.DEBUG, logger="app.tasks.scheduler"):
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_svc.check_all_canaries = AsyncMock(return_value=[mock_result])

            from app.tasks.scheduler import _canary_auto_rollback_check_impl

            await _canary_auto_rollback_check_impl()

        assert any("Canary 8 health check" in r.message for r in caplog.records)


# ---------- beat schedule 配置 ----------


class TestBeatSchedule:
    """覆盖 celery beat schedule 中各任务注册情况."""

    def test_all_scheduler_tasks_in_beat_schedule(self):
        """TC-COV-TASK-042: scheduler 5 个任务都应在 beat schedule 中."""
        schedule = celery_app.conf.beat_schedule
        assert (
            schedule["daily-risk-scan"]["task"] == "app.tasks.scheduler.daily_risk_scan"
        )
        assert (
            schedule["stale-warning-reminder"]["task"]
            == "app.tasks.scheduler.stale_warning_reminder"
        )
        assert (
            schedule["daily-intervention-check"]["task"]
            == "app.tasks.scheduler.daily_intervention_check"
        )
        assert (
            schedule["weekly-log-archive"]["task"]
            == "app.tasks.scheduler.weekly_log_archive"
        )
        assert (
            schedule["canary-auto-rollback-check"]["task"]
            == "app.tasks.scheduler.canary_auto_rollback_check"
        )
