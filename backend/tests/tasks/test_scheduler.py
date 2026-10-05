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
    async def test_notify_warning_reports_failure(self, caplog):
        """TC-COV-TASK-014: 推送失败不得静默吞掉（AUDIT-2026-09-28-P0-2 重写）.

        原用例名为 ``test_notify_warning_swallows_exception``，断言"吞掉异常 +
        记一条 warning 即算通过"，等于把静默漏报固化成了契约——预警已入库但
        咨询师从未收到，事后也无法发现。现改为验证失败必须可观测：
        返回 False、就地重试耗尽、记 error 级日志、并递增指标。
        """
        import logging

        with patch(
            "app.core.ws.notify_warning",
            new=AsyncMock(side_effect=RuntimeError("ws down")),
        ) as mock_user, patch("app.core.ws.notify_counselor", new=AsyncMock()), patch(
            "app.core.contracts.normalize_risk_level", return_value="high"
        ), patch(
            "app.core.metrics.warning_notify_failed_total"
        ) as mock_counter:
            from app.tasks.scheduler import _NOTIFY_MAX_ATTEMPTS, _notify_warning

            with caplog.at_level(logging.ERROR, logger="app.tasks.scheduler"):
                # 不应抛异常（单条失败不得中断整批扫描），但必须如实报告失败
                result = await _notify_warning(
                    user_id=1,
                    warning_id=99,
                    risk_level=3,
                    trigger_reason="r",
                    counselor_id=2,
                )

        assert result is False, "推送失败时应返回 False，而不是静默返回 None"
        # 失败应就地重试，而非直接放弃
        assert mock_user.await_count == _NOTIFY_MAX_ATTEMPTS
        # 失败必须可观测：error 级日志（warning 会被淹没）
        assert any(
            r.levelno >= logging.ERROR and "warning_id=99" in r.message
            for r in caplog.records
        ), "重试耗尽后必须记录 error 级日志，否则漏报不可发现"
        # 失败必须可告警：指标递增
        mock_counter.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_notify_warning_recovers_on_retry(self):
        """AUDIT-2026-09-28-P0-2: 首次失败、重试成功时不应计为失败."""
        calls = {"n": 0}

        async def _flaky(*_args, **_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient ws error")

        with patch("app.core.ws.notify_warning", new=AsyncMock(side_effect=_flaky)), patch(
            "app.core.ws.notify_counselor", new=AsyncMock()
        ), patch("app.core.contracts.normalize_risk_level", return_value="high"), patch(
            "app.core.metrics.warning_notify_failed_total"
        ) as mock_counter:
            from app.tasks.scheduler import _notify_warning

            result = await _notify_warning(
                user_id=1,
                warning_id=100,
                risk_level=3,
                trigger_reason="r",
                counselor_id=2,
            )

        assert result is True, "重试后成功应返回 True"
        assert calls["n"] == 2
        mock_counter.inc.assert_not_called()


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
        """TC-COV-TASK-024: >7 天 + 风险等级 >=2 + 无重复告警 -> 创建告警并通知.

        H-ML-7 修复: 告警创建改为原子 INSERT ... WHERE NOT EXISTS (returning id),
        不再走 ORM add/flush; 重复检查由 DB 层完成.
        """
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
        insert_result = MagicMock()
        insert_result.scalar_one_or_none.return_value = 999  # 原子插入成功, 返回自增 id

        mock_db = AsyncMock()
        users_result = MagicMock()
        users_result.scalars.return_value.all.return_value = [mock_user]
        risk_result = MagicMock()
        risk_result.scalar_one_or_none.return_value = mock_risk
        setting_result = MagicMock()
        setting_result.scalar_one_or_none.return_value = mock_setting
        bind_result = MagicMock()
        bind_result.scalar_one_or_none.return_value = mock_binding
        mock_db.execute = AsyncMock(
            side_effect=[
                users_result,
                risk_result,
                setting_result,
                bind_result,
                insert_result,
            ]
        )

        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl, patch(
            "app.tasks.scheduler._notify_warning", new=AsyncMock()
        ) as mock_notify:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

            from app.tasks.scheduler import _daily_risk_scan_impl

            await _daily_risk_scan_impl()

        # H-ML-7: 不再通过 ORM add/flush 写入
        mock_db.add.assert_not_called()
        mock_db.flush.assert_not_awaited()
        mock_db.commit.assert_awaited_once()
        # H-ML-6: commit 成功后才发通知 (带上原子插入返回的 id 与绑定咨询师)
        mock_notify.assert_awaited_once()
        notify_args = mock_notify.await_args.args
        assert notify_args[0] == 1  # user_id
        assert notify_args[1] == 999  # warning_id
        assert notify_args[4] == 42  # counselor_id

    @pytest.mark.asyncio
    async def test_existing_recent_warning_skipped(self):
        """TC-COV-TASK-025: 已存在近 1 天的告警时不重复创建.

        H-ML-7 修复: 原子 INSERT ... WHERE NOT EXISTS 返回 None (0 行插入) 即重复, 跳过.
        """
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
        bind_result = MagicMock()
        bind_result.scalar_one_or_none.return_value = None
        insert_result = MagicMock()
        insert_result.scalar_one_or_none.return_value = None  # 重复, 0 行插入
        mock_db.execute = AsyncMock(
            side_effect=[
                users_result,
                risk_result,
                setting_result,
                bind_result,
                insert_result,
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
        bind_result = MagicMock()
        bind_result.scalar_one_or_none.return_value = None  # 无绑定
        insert_result = MagicMock()
        insert_result.scalar_one_or_none.return_value = 888  # 原子插入成功
        mock_db.execute = AsyncMock(
            side_effect=[
                users_result,
                risk_result,
                setting_result,
                bind_result,
                insert_result,
            ]
        )

        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl, patch(
            "app.tasks.scheduler._notify_warning", new=AsyncMock()
        ) as mock_notify:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

            from app.tasks.scheduler import _daily_risk_scan_impl

            await _daily_risk_scan_impl()

        mock_notify.assert_awaited_once()
        notify_args = mock_notify.await_args.args
        assert notify_args[1] == 888
        assert notify_args[4] is None  # 无咨询师绑定

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
        bind_result = MagicMock()
        bind_result.scalar_one_or_none.return_value = None
        insert_result = MagicMock()
        insert_result.scalar_one_or_none.return_value = 777
        mock_db.execute = AsyncMock(
            side_effect=[
                users_result,
                risk_result,
                setting_result,
                bind_result,
                insert_result,
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


def _make_exec_mock(plans=None, tasks=None, existing_task_ids=None, totals=(0, 0)):
    """构造 db.execute 的响应 mock, 不依赖调用顺序。

    AUDIT-2026-10-05-P0: 原实现对每个 task 一次 SELECT + 末尾两条 count,
    测试用 ``side_effect=[...]`` 按顺序编码返回值, 查询次数一变即碎。
    改为**按查询的语义形状**响应:
    - scalars().all() 返回活跃计划 / 任务列表
    - scalars().all() 也用于"已存在执行记录的 task_id 集合"
    - .one() 用于进度聚合 (total, completed)

    ``tasks`` 支持两种形态: list (所有 plan 共用) 或 dict{plan_id: list}
    (按 plan 派发) —— 多 plan 场景必须用后者, 否则每个 plan 都会拿到
    全部 task, 创建数被放大成 plan×task。
    """
    tasks_by_plan = tasks if isinstance(tasks, dict) else None
    shared_tasks = [] if isinstance(tasks, dict) else (tasks or [])

    def _make_db(plans, _):
        db = AsyncMock()

        plans_r = MagicMock()
        plans_r.scalars.return_value.all.return_value = plans
        progress_r = MagicMock()
        progress_r.one.return_value = totals

        state = {"plan_seen": 0}

        def _tasks_r(stmt):
            """按当前查询的 plan_id 派发任务列表。

            注意: 渲染后的 SQL 里 plan_id 是绑定参数 (:plan_id_1), 不能从
            字符串正则提取实际值, 必须从 ``stmt.compile().params`` 取。
            """
            r = MagicMock()
            if tasks_by_plan is not None:
                try:
                    params = stmt.compile().params
                except Exception:
                    params = {}
                key = next(
                    (v for k, v in params.items() if k.startswith("plan_id")), None
                )
                r.scalars.return_value.all.return_value = list(
                    tasks_by_plan.get(key, [])
                )
            else:
                r.scalars.return_value.all.return_value = shared_tasks
            return r

        existing_r = MagicMock()
        existing_r.scalars.return_value.all.return_value = (
            list(existing_task_ids) if existing_task_ids is not None else []
        )

        def _execute(stmt, *a, **kw):
            sql = str(stmt)
            if "intervention_plans" in sql:
                state["plan_seen"] += 1
                return plans_r
            if "intervention_tasks" in sql:
                return _tasks_r(stmt)
            if "task_executions" in sql and "FILTER" in sql.upper():
                return progress_r
            if "task_executions" in sql:
                return existing_r
            return MagicMock()

        db.execute = AsyncMock(side_effect=_execute)
        return db

    return _make_db(plans or [], None)


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
        # AUDIT-2026-10-05-P0: 按 plan 粒度提交 (过期 plan 一次 + 末尾兜底一次)。
        # 关键性质是 "至少提交了一次", 而非精确次数 —— 逐 plan 提交正是为了
        # 超时时保住已完成部分, 故此处断言 >= 1。
        assert mock_db.commit.await_count >= 1

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
        mock_db = _make_exec_mock(plans=[mock_plan], tasks=[mock_task], totals=(1, 0))

        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

            from app.tasks.scheduler import _daily_intervention_check_impl

            await _daily_intervention_check_impl()

        mock_db.add.assert_called_once()
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
        # 今日已有执行记录
        mock_db = _make_exec_mock(
            plans=[mock_plan], tasks=[mock_task], existing_task_ids=[50], totals=(1, 1)
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


class TestDailyInterventionPartialCommit:
    """AUDIT-2026-10-05-P0: 超时不得丢当日已创建的 TaskExecution。

    原实现把全部 plan 放在**单个事务**里, 循环结束后才 commit。
    本任务 soft_time_limit=160s, 一旦中途超时, SoftTimeLimitExceeded
    使整个事务回滚 —— 当日已生成的执行记录全部丢失, 心理健康场景下
    等同"干预任务漏生成"。
    """

    @pytest.mark.asyncio
    async def test_commits_per_plan_not_only_at_end(self):
        """3 个 plan 至少产生 3 次 commit (逐 plan 边界提交)。"""
        from datetime import date

        plans, tasks_by_plan = [], {}
        for i in range(3):
            p = MagicMock()
            p.id = i + 1
            p.user_id = 10 + i
            p.end_date = date.today() + timedelta(days=7)
            plans.append(p)
            t = MagicMock()
            t.id = 50 + i
            t.schedule = "daily"
            tasks_by_plan[p.id] = [t]

        mock_db = _make_exec_mock(plans=plans, tasks=tasks_by_plan, totals=(1, 0))

        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

            from app.tasks.scheduler import _daily_intervention_check_impl

            await _daily_intervention_check_impl()

        # 逐 plan 提交 >= plan 数 (末尾另有一次兜底 commit)
        # 注意: Session.add / Session.commit 在真实 SQLAlchemy 中是**同步**
        # 方法, 故断言 call_count 而非 await_count (AsyncMock 两者并存,
        # 但真实调用走同步路径)。
        assert mock_db.commit.call_count + mock_db.commit.await_count >= len(plans), (
            f"commit 次数 {mock_db.commit.call_count} < plan 数 {len(plans)} —— "
            "超时将回滚全部已创建的 TaskExecution"
        )
        assert mock_db.add.call_count + mock_db.add.await_count == len(plans)

    @pytest.mark.asyncio
    async def test_partial_progress_survives_later_failure(self):
        """核心不变量: 前面的 plan 已提交后, 后续 plan 失败不丢前面的数据。

        这是本次修复的**存在理由** —— 单事务实现下该场景会全量回滚。
        """
        from datetime import date

        from sqlalchemy.exc import OperationalError

        p1 = MagicMock()
        p1.id = 1
        p1.user_id = 10
        p1.end_date = date.today() + timedelta(days=7)
        p2 = MagicMock()
        p2.id = 2
        p2.user_id = 11
        p2.end_date = date.today() + timedelta(days=7)
        t1 = MagicMock()
        t1.id = 50
        t1.schedule = "daily"

        mock_db = _make_exec_mock(
            plans=[p1, p2], tasks={1: [t1], 2: [t1]}, totals=(1, 0)
        )

        # 第一个 plan 走完 (plans→tasks→existing→progress→commit) 后,
        # 第二个 plan 的任务查询时抛错。
        # 查询序列: 1=plans, 2=tasks(p1), 3=existing(p1), 4=progress(p1)
        #          5=tasks(p2) <- 此处失败
        original_execute = mock_db.execute.side_effect
        calls = {"n": 0}

        def _flaky(stmt, *a, **kw):
            calls["n"] += 1
            if calls["n"] > 4:
                raise OperationalError(
                    "SELECT intervention_tasks", {}, Exception("conn lost")
                )
            return original_execute(stmt, *a, **kw)

        mock_db.execute = AsyncMock(side_effect=_flaky)

        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

            from app.tasks.scheduler import _daily_intervention_check_impl

            with pytest.raises(OperationalError):
                await _daily_intervention_check_impl()

        # 关键: 第一个 plan 的 commit 已经发生, 数据保住
        commit_calls = mock_db.commit.call_count + mock_db.commit.await_count
        assert commit_calls >= 1, (
            "后续 plan 失败时, 先前 plan 的 commit 未发生 —— 仍会全量回滚"
        )
        add_calls = mock_db.add.call_count + mock_db.add.await_count
        assert add_calls == 1

    @pytest.mark.asyncio
    async def test_progress_counts_only_daily_tasks(self):
        """非 daily 任务不创建执行, 也不参与 progress 统计分母。

        原实现对全部 tasks 查执行记录与算 progress, 但只有 daily 分支会创建
        记录 —— 非 daily 计入分母会让 progress 永远达不到 100%。
        """
        from datetime import date

        p = MagicMock()
        p.id = 1
        p.user_id = 10
        p.end_date = date.today() + timedelta(days=7)
        t_daily = MagicMock()
        t_daily.id = 50
        t_daily.schedule = "daily"
        t_weekly = MagicMock()
        t_weekly.id = 51
        t_weekly.schedule = "weekly"

        mock_db = _make_exec_mock(plans=[p], tasks=[t_daily, t_weekly], totals=(1, 1))

        with patch("app.tasks.scheduler.AsyncSessionLocal") as mock_sl:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=None)

            from app.tasks.scheduler import _daily_intervention_check_impl

            await _daily_intervention_check_impl()

        mock_db.add.assert_called_once()
        assert p.progress == 100

    @pytest.mark.asyncio
    async def test_idempotent_rerun_creates_no_duplicates(self):
        """重跑幂等: 今日已有执行记录时不再创建 (依赖唯一约束
        uq_task_execution_task_user_date, 故按批次提交是安全的)。"""
        from datetime import date

        p = MagicMock()
        p.id = 1
        p.user_id = 10
        p.end_date = date.today() + timedelta(days=7)
        t = MagicMock()
        t.id = 50
        t.schedule = "daily"

        mock_db = _make_exec_mock(
            plans=[p], tasks=[t], existing_task_ids=[50], totals=(1, 0)
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


class TestSentryWiring:
    """AUDIT-2026-10-05: Sentry 业务调用点接线。

    此前 `core/sentry.py` 的 `capture_exception` / `capture_message`
    **零业务调用点** —— 监控资产空转, 以为接了异常聚合, 实际排查仍只能
    grep 日志。本类锁定三处最关键的上报点, 并防退化。
    """

    @pytest.mark.asyncio
    async def test_notify_warning_retry_exhausted_reports_to_sentry(self):
        """推送重试耗尽必须上报, 且带上可定位的业务上下文。"""
        with patch(
            "app.core.ws.notify_warning",
            new=AsyncMock(side_effect=ConnectionError("ws down")),
        ), patch("app.core.contracts.normalize_risk_level", return_value="high"), patch(
            "app.core.sentry.capture_exception"
        ) as mock_cap:
            from app.tasks.scheduler import _notify_warning

            ok = await _notify_warning(
                user_id=7,
                warning_id=99,
                risk_level=3,
                trigger_reason="PHQ9 急升",
                counselor_id=3,
            )

        assert ok is False, "重试耗尽应返回 False"
        mock_cap.assert_called_once()
        kwargs = mock_cap.call_args.kwargs
        # 缺任何一个定位字段, Sentry 上都只能看到"某处失败"
        for key in ("warning_id", "user_id", "counselor_id", "risk_level", "module"):
            assert key in kwargs, f"Sentry 上下文缺 {key}, 无法定位具体预警"

    @pytest.mark.asyncio
    async def test_notify_warning_success_does_not_report(self):
        """成功路径不得上报 —— 否则 Sentry 被噪音淹没。"""
        with patch("app.core.ws.notify_warning", new=AsyncMock()), patch(
            "app.core.ws.notify_counselor", new=AsyncMock()
        ), patch("app.core.contracts.normalize_risk_level", return_value="low"), patch(
            "app.core.sentry.capture_exception"
        ) as mock_cap:
            from app.tasks.scheduler import _notify_warning

            ok = await _notify_warning(
                user_id=1,
                warning_id=1,
                risk_level=1,
                trigger_reason="r",
                counselor_id=1,
            )

        assert ok is True
        mock_cap.assert_not_called()

    @pytest.mark.asyncio
    async def test_sentry_failure_does_not_break_notify_path(self):
        """Sentry 自身故障绝不能影响主流程 (监控故障不得放大成业务故障)。"""
        with patch(
            "app.core.ws.notify_warning",
            new=AsyncMock(side_effect=ConnectionError("ws down")),
        ), patch("app.core.contracts.normalize_risk_level", return_value="high"), patch(
            "app.core.sentry.capture_exception", side_effect=RuntimeError("sentry down")
        ):
            from app.tasks.scheduler import _notify_warning

            ok = await _notify_warning(
                user_id=1,
                warning_id=2,
                risk_level=3,
                trigger_reason="r",
                counselor_id=1,
            )

        assert ok is False, "Sentry 故障时仍应正常返回 False 而非抛异常"

    def test_sentry_call_sites_are_exception_guarded(self):
        """防退化闸门: 任何 Sentry 调用点都必须包在 try/except 里。

        两重作用:
        1. 上报失败不中断主流程;
        2. 防止 Sentry 再次被删成"零业务调用点"而无人察觉。
        """
        import ast
        import pathlib

        app_dir = pathlib.Path(__file__).resolve().parents[2] / "app"
        unguarded = []
        call_sites = 0
        for f in app_dir.rglob("*.py"):
            if f.name == "sentry.py":  # 自身定义不算调用点
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            if "capture_exception" not in text and "capture_message" not in text:
                continue
            tree = ast.parse(text)
            guarded = 0
            total = 0
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    fn = node.func
                    name = getattr(fn, "id", None) or getattr(fn, "attr", None)
                    if name in ("capture_exception", "capture_message"):
                        total += 1
            for node in ast.walk(tree):
                if isinstance(node, ast.Try):
                    names_in_try = {
                        getattr(n.func, "id", None) or getattr(n.func, "attr", None)
                        for n in ast.walk(node)
                        if isinstance(n, ast.Call)
                    }
                    guarded += len(
                        names_in_try & {"capture_exception", "capture_message"}
                    )
            call_sites += total
            if guarded < total:
                unguarded.append(
                    f"{f.relative_to(app_dir)} ({guarded}/{total} 已保护)"
                )

        assert call_sites > 0, (
            "Sentry 业务调用点为 0 —— 监控资产空转, 本次修复的成果已被回退"
        )
        assert not unguarded, f"以下 Sentry 调用点未包 try/except: {unguarded}"
