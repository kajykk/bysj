"""STAB-P1-009 测试: 金丝雀自动回滚备用监控 (asyncio.create_task fallback).

测试覆盖:
1. _canary_fallback_loop - 后台循环逻辑 (Celery 可用跳过 / 不可用执行)
2. start_canary_fallback_monitor / stop_canary_fallback_monitor - 启动/停止生命周期
3. is_canary_fallback_running - 运行状态查询
4. _is_test_environment - 测试环境检测
5. 源码静态扫描 - 确认关键设计点已实现
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import canary_fallback_monitor
from app.services.canary_fallback_monitor import (
    CANARY_FALLBACK_INTERVAL_SECONDS,
    _canary_fallback_loop,
    _is_test_environment,
    is_canary_fallback_running,
)


class TestIsTestEnvironment:
    """测试环境检测."""

    def test_returns_true_when_pytest_current_test_set(self, monkeypatch):
        """TC-CFB-001: PYTEST_CURRENT_TEST 已设置返回 True."""
        monkeypatch.setenv(
            "PYTEST_CURRENT_TEST", "tests/test_canary_fallback_monitor.py::test_x"
        )
        assert _is_test_environment() is True

    def test_returns_false_when_pytest_current_test_unset(self, monkeypatch):
        """TC-CFB-002: PYTEST_CURRENT_TEST 未设置返回 False."""
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        assert _is_test_environment() is False


class TestCanaryFallbackLoopSkipWhenCeleryAvailable:
    """测试 Celery 可用时跳过 fallback (避免双重执行)."""

    @pytest.mark.asyncio
    async def test_loop_skips_when_celery_closed(self):
        """TC-CFB-003: celery_breaker.state=closed 时不执行 rollback check."""
        # 构造 celery_breaker mock (state=closed)
        mock_breaker = MagicMock()
        mock_breaker.get_state_snapshot.return_value = {"state": "closed"}

        # mock auto_rollback_service.check_all_canaries (不应被调用)
        mock_rollback_service = MagicMock()
        mock_rollback_service.check_all_canaries = AsyncMock(return_value=[])

        # mock AsyncSessionLocal (不应被调用)
        mock_session_local = MagicMock()

        # 用 Event 控制循环执行次数
        iteration_done = asyncio.Event()

        async def fake_sleep(seconds):
            iteration_done.set()
            # 抛出 CancelledError 退出循环
            raise asyncio.CancelledError()

        with (
            patch("app.core.celery_breaker.celery_breaker", mock_breaker),
            patch(
                "app.services.auto_rollback_service.auto_rollback_service",
                mock_rollback_service,
            ),
            patch(
                "app.services.canary_fallback_monitor.AsyncSessionLocal",
                mock_session_local,
            ),
            patch("app.services.canary_fallback_monitor.asyncio.sleep", fake_sleep),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _canary_fallback_loop()

        # 验证 rollback check 未被调用
        mock_rollback_service.check_all_canaries.assert_not_called()
        # 验证 session 未被创建
        mock_session_local.assert_not_called()

    @pytest.mark.asyncio
    async def test_loop_logs_debug_when_celery_closed(self, caplog):
        """TC-CFB-004: celery_breaker.state=closed 记录 debug 日志."""
        mock_breaker = MagicMock()
        mock_breaker.get_state_snapshot.return_value = {"state": "closed"}

        async def fake_sleep(seconds):
            raise asyncio.CancelledError()

        with (
            patch("app.core.celery_breaker.celery_breaker", mock_breaker),
            patch("app.services.canary_fallback_monitor.asyncio.sleep", fake_sleep),
        ):
            with caplog.at_level(
                logging.DEBUG, logger="app.services.canary_fallback_monitor"
            ):
                with pytest.raises(asyncio.CancelledError):
                    await _canary_fallback_loop()

        # 应有 debug 日志 "skip (celery beat handles)"
        debug_logs = [
            r for r in caplog.records if r.levelname == "DEBUG" and "skip" in r.message
        ]
        assert len(debug_logs) >= 1


class TestCanaryFallbackLoopExecutesWhenCeleryUnavailable:
    """测试 Celery 不可用时执行 fallback rollback check."""

    @pytest.mark.asyncio
    async def test_loop_executes_when_celery_open(self):
        """TC-CFB-005: celery_breaker.state=open 时执行 rollback check."""
        mock_breaker = MagicMock()
        mock_breaker.get_state_snapshot.return_value = {
            "state": "open",
            "failure_count": 5,
        }

        # mock rollback check 返回空列表
        mock_rollback_service = MagicMock()
        mock_rollback_service.check_all_canaries = AsyncMock(return_value=[])

        # mock AsyncSessionLocal - async context manager
        mock_session = AsyncMock()
        mock_session_local = MagicMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=None)

        async def fake_sleep(seconds):
            raise asyncio.CancelledError()

        with (
            patch("app.core.celery_breaker.celery_breaker", mock_breaker),
            patch(
                "app.services.auto_rollback_service.auto_rollback_service",
                mock_rollback_service,
            ),
            patch(
                "app.services.canary_fallback_monitor.AsyncSessionLocal",
                mock_session_local,
            ),
            patch("app.services.canary_fallback_monitor.asyncio.sleep", fake_sleep),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _canary_fallback_loop()

        # 验证 rollback check 已被调用
        mock_rollback_service.check_all_canaries.assert_called_once()
        # 验证传入的是 mock_session
        call_args = mock_rollback_service.check_all_canaries.call_args
        assert call_args.args[0] is mock_session

    @pytest.mark.asyncio
    async def test_loop_executes_when_celery_half_open(self):
        """TC-CFB-006: celery_breaker.state=half_open 时执行 rollback check."""
        mock_breaker = MagicMock()
        mock_breaker.get_state_snapshot.return_value = {"state": "half_open"}

        mock_rollback_service = MagicMock()
        mock_rollback_service.check_all_canaries = AsyncMock(return_value=[])

        mock_session = AsyncMock()
        mock_session_local = MagicMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=None)

        async def fake_sleep(seconds):
            raise asyncio.CancelledError()

        with (
            patch("app.core.celery_breaker.celery_breaker", mock_breaker),
            patch(
                "app.services.auto_rollback_service.auto_rollback_service",
                mock_rollback_service,
            ),
            patch(
                "app.services.canary_fallback_monitor.AsyncSessionLocal",
                mock_session_local,
            ),
            patch("app.services.canary_fallback_monitor.asyncio.sleep", fake_sleep),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _canary_fallback_loop()

        mock_rollback_service.check_all_canaries.assert_called_once()

    @pytest.mark.asyncio
    async def test_loop_logs_warning_when_celery_unavailable(self, caplog):
        """TC-CFB-007: celery 不可用时记录 warning 日志."""
        mock_breaker = MagicMock()
        mock_breaker.get_state_snapshot.return_value = {"state": "open"}

        mock_rollback_service = MagicMock()
        mock_rollback_service.check_all_canaries = AsyncMock(return_value=[])

        mock_session = AsyncMock()
        mock_session_local = MagicMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=None)

        async def fake_sleep(seconds):
            raise asyncio.CancelledError()

        with (
            patch("app.core.celery_breaker.celery_breaker", mock_breaker),
            patch(
                "app.services.auto_rollback_service.auto_rollback_service",
                mock_rollback_service,
            ),
            patch(
                "app.services.canary_fallback_monitor.AsyncSessionLocal",
                mock_session_local,
            ),
            patch("app.services.canary_fallback_monitor.asyncio.sleep", fake_sleep),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _canary_fallback_loop()

        warning_logs = [
            r
            for r in caplog.records
            if r.levelname == "WARNING" and "celery_breaker=open" in r.message
        ]
        assert len(warning_logs) >= 1


class TestCanaryFallbackLoopRollbackTriggered:
    """测试 fallback 触发实际回滚时的日志."""

    @pytest.mark.asyncio
    async def test_loop_logs_rollback_count(self, caplog):
        """TC-CFB-008: 触发回滚时记录 rollback count."""
        mock_breaker = MagicMock()
        mock_breaker.get_state_snapshot.return_value = {"state": "open"}

        # 构造 2 个 should_rollback=True 的结果
        mock_result_1 = MagicMock(should_rollback=True)
        mock_result_2 = MagicMock(should_rollback=True)
        mock_result_3 = MagicMock(should_rollback=False)
        mock_rollback_service = MagicMock()
        mock_rollback_service.check_all_canaries = AsyncMock(
            return_value=[mock_result_1, mock_result_2, mock_result_3]
        )

        mock_session = AsyncMock()
        mock_session_local = MagicMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=None)

        async def fake_sleep(seconds):
            raise asyncio.CancelledError()

        with (
            patch("app.core.celery_breaker.celery_breaker", mock_breaker),
            patch(
                "app.services.auto_rollback_service.auto_rollback_service",
                mock_rollback_service,
            ),
            patch(
                "app.services.canary_fallback_monitor.AsyncSessionLocal",
                mock_session_local,
            ),
            patch("app.services.canary_fallback_monitor.asyncio.sleep", fake_sleep),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _canary_fallback_loop()

        # 应有 warning 日志 "2 canary(ies) triggered rollback"
        warning_logs = [
            r
            for r in caplog.records
            if r.levelname == "WARNING" and "2 canary" in r.message
        ]
        assert len(warning_logs) >= 1

    @pytest.mark.asyncio
    async def test_loop_logs_no_rollback_when_empty(self, caplog):
        """TC-CFB-009: 无需回滚时记录 debug 日志."""
        mock_breaker = MagicMock()
        mock_breaker.get_state_snapshot.return_value = {"state": "open"}

        mock_rollback_service = MagicMock()
        mock_rollback_service.check_all_canaries = AsyncMock(return_value=[])

        mock_session = AsyncMock()
        mock_session_local = MagicMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=None)

        async def fake_sleep(seconds):
            raise asyncio.CancelledError()

        with (
            patch("app.core.celery_breaker.celery_breaker", mock_breaker),
            patch(
                "app.services.auto_rollback_service.auto_rollback_service",
                mock_rollback_service,
            ),
            patch(
                "app.services.canary_fallback_monitor.AsyncSessionLocal",
                mock_session_local,
            ),
            patch("app.services.canary_fallback_monitor.asyncio.sleep", fake_sleep),
        ):
            with caplog.at_level(
                logging.DEBUG, logger="app.services.canary_fallback_monitor"
            ):
                with pytest.raises(asyncio.CancelledError):
                    await _canary_fallback_loop()

        debug_logs = [
            r
            for r in caplog.records
            if r.levelname == "DEBUG" and "no rollback needed" in r.message
        ]
        assert len(debug_logs) >= 1


class TestCanaryFallbackLoopErrorHandling:
    """测试循环内错误处理 (不退出循环)."""

    @pytest.mark.asyncio
    async def test_loop_continues_on_rollback_check_exception(self):
        """TC-CFB-010: rollback check 抛异常时记录错误但继续循环."""
        mock_breaker = MagicMock()
        mock_breaker.get_state_snapshot.return_value = {"state": "open"}

        mock_rollback_service = MagicMock()
        mock_rollback_service.check_all_canaries = AsyncMock(
            side_effect=RuntimeError("DB connection failed")
        )

        mock_session = AsyncMock()
        mock_session_local = MagicMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=None)

        async def fake_sleep(seconds):
            raise asyncio.CancelledError()

        with (
            patch("app.core.celery_breaker.celery_breaker", mock_breaker),
            patch(
                "app.services.auto_rollback_service.auto_rollback_service",
                mock_rollback_service,
            ),
            patch(
                "app.services.canary_fallback_monitor.AsyncSessionLocal",
                mock_session_local,
            ),
            patch("app.services.canary_fallback_monitor.asyncio.sleep", fake_sleep),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _canary_fallback_loop()

        # 即使 rollback check 抛异常, 循环仍继续到 sleep
        mock_rollback_service.check_all_canaries.assert_called_once()

    @pytest.mark.asyncio
    async def test_loop_continues_on_breaker_snapshot_exception(self):
        """TC-CFB-011: breaker.get_state_snapshot 抛异常时记录错误但继续循环."""
        mock_breaker = MagicMock()
        mock_breaker.get_state_snapshot.side_effect = RuntimeError("breaker corrupted")

        mock_rollback_service = MagicMock()
        mock_rollback_service.check_all_canaries = AsyncMock(return_value=[])

        async def fake_sleep(seconds):
            raise asyncio.CancelledError()

        with (
            patch("app.core.celery_breaker.celery_breaker", mock_breaker),
            patch(
                "app.services.auto_rollback_service.auto_rollback_service",
                mock_rollback_service,
            ),
            patch("app.services.canary_fallback_monitor.asyncio.sleep", fake_sleep),
        ):
            with pytest.raises(asyncio.CancelledError):
                await _canary_fallback_loop()

        # breaker 异常时, rollback check 不应被调用
        mock_rollback_service.check_all_canaries.assert_not_called()


class TestStartStopMonitor:
    """测试 start_canary_fallback_monitor / stop_canary_fallback_monitor 生命周期."""

    @pytest.mark.asyncio
    async def test_start_skips_in_test_environment(self, monkeypatch):
        """TC-CFB-012: 测试环境跳过启动."""
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_x")
        # 重置全局状态
        canary_fallback_monitor._canary_fallback_task = None

        # 使用 spec=[] 限制 mock 属性, hasattr 才能正确返回 False
        mock_app = MagicMock()
        mock_app.state = MagicMock(spec=[])
        await canary_fallback_monitor.start_canary_fallback_monitor(mock_app)

        # 验证任务未创建
        assert canary_fallback_monitor._canary_fallback_task is None
        # 验证 app.state.canary_fallback_task 未设置
        assert not hasattr(mock_app.state, "canary_fallback_task")

    @pytest.mark.asyncio
    async def test_start_creates_task_when_not_test(self, monkeypatch):
        """TC-CFB-013: 非测试环境创建后台任务."""
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        canary_fallback_monitor._canary_fallback_task = None

        # mock _canary_fallback_loop 为可 await 的 MagicMock (不实际循环)
        loop_started = asyncio.Event()

        async def fake_loop():
            loop_started.set()
            # 阻塞, 等待被 cancel
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                raise

        mock_app = MagicMock()
        with patch(
            "app.services.canary_fallback_monitor._canary_fallback_loop", fake_loop
        ):
            await canary_fallback_monitor.start_canary_fallback_monitor(mock_app)

        # 验证任务已创建
        assert canary_fallback_monitor._canary_fallback_task is not None
        assert not canary_fallback_monitor._canary_fallback_task.done()
        # 验证 app.state.canary_fallback_task 已设置
        assert (
            mock_app.state.canary_fallback_task
            is canary_fallback_monitor._canary_fallback_task
        )

        # 清理: 停止任务
        await canary_fallback_monitor.stop_canary_fallback_monitor()
        assert canary_fallback_monitor._canary_fallback_task is None

    @pytest.mark.asyncio
    async def test_start_skips_when_already_running(self, monkeypatch, caplog):
        """TC-CFB-014: 任务已在运行时跳过重复启动."""
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        # 模拟已有运行中任务
        existing_task = MagicMock()
        existing_task.done.return_value = False
        canary_fallback_monitor._canary_fallback_task = existing_task

        mock_app = MagicMock()
        await canary_fallback_monitor.start_canary_fallback_monitor(mock_app)

        # 验证未创建新任务
        assert canary_fallback_monitor._canary_fallback_task is existing_task

        # 清理
        canary_fallback_monitor._canary_fallback_task = None

    @pytest.mark.asyncio
    async def test_stop_no_op_when_task_none(self):
        """TC-CFB-015: 任务为 None 时 stop 是 no-op."""
        canary_fallback_monitor._canary_fallback_task = None
        # 不应抛异常
        await canary_fallback_monitor.stop_canary_fallback_monitor()
        assert canary_fallback_monitor._canary_fallback_task is None

    @pytest.mark.asyncio
    async def test_stop_cancels_running_task(self, monkeypatch):
        """TC-CFB-016: stop 取消运行中任务."""
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        loop_started = asyncio.Event()

        async def fake_loop():
            loop_started.set()
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                raise

        with patch(
            "app.services.canary_fallback_monitor._canary_fallback_loop", fake_loop
        ):
            mock_app = MagicMock()
            await canary_fallback_monitor.start_canary_fallback_monitor(mock_app)
            await loop_started.wait()
            # 现在 task 在 sleep 中
            await canary_fallback_monitor.stop_canary_fallback_monitor()

        # 验证任务已取消并清理
        assert canary_fallback_monitor._canary_fallback_task is None


class TestIsCanaryFallbackRunning:
    """测试 is_canary_fallback_running 状态查询."""

    def test_returns_false_when_task_none(self):
        """TC-CFB-017: 任务为 None 返回 False."""
        canary_fallback_monitor._canary_fallback_task = None
        assert is_canary_fallback_running() is False

    def test_returns_false_when_task_done(self):
        """TC-CFB-018: 任务已完成返回 False."""
        mock_task = MagicMock()
        mock_task.done.return_value = True
        canary_fallback_monitor._canary_fallback_task = mock_task
        assert is_canary_fallback_running() is False
        # 清理
        canary_fallback_monitor._canary_fallback_task = None

    def test_returns_true_when_task_running(self):
        """TC-CFB-019: 任务运行中返回 True."""
        mock_task = MagicMock()
        mock_task.done.return_value = False
        canary_fallback_monitor._canary_fallback_task = mock_task
        assert is_canary_fallback_running() is True
        # 清理
        canary_fallback_monitor._canary_fallback_task = None


class TestCanaryFallbackMonitorSourceStructure:
    """源码静态扫描 - 确认关键设计点已实现."""

    def test_interval_constant_is_30_seconds(self):
        """TC-CFB-020: 检查间隔常量为 30s (与 Celery beat 一致)."""
        assert CANARY_FALLBACK_INTERVAL_SECONDS == 30.0

    def test_loop_uses_celery_breaker_state(self):
        """TC-CFB-021: 循环内必须读取 celery_breaker.get_state_snapshot."""
        source = inspect.getsource(_canary_fallback_loop)
        assert "celery_breaker" in source
        assert "get_state_snapshot" in source
        assert '"closed"' in source or "'closed'" in source

    def test_loop_calls_auto_rollback_service(self):
        """TC-CFB-022: 循环内必须调用 auto_rollback_service.check_all_canaries."""
        source = inspect.getsource(_canary_fallback_loop)
        assert "auto_rollback_service" in source
        assert "check_all_canaries" in source

    def test_loop_handles_cancelled_error(self):
        """TC-CFB-023: 循环必须处理 CancelledError (应用关闭)."""
        source = inspect.getsource(_canary_fallback_loop)
        assert "CancelledError" in source

    def test_loop_continues_on_unexpected_exception(self):
        """TC-CFB-024: 循环遇到未预期异常不应退出 (持续监控)."""
        source = inspect.getsource(_canary_fallback_loop)
        # 必须有 except Exception 处理 (非 CancelledError)
        assert "except Exception" in source

    def test_start_checks_test_environment(self):
        """TC-CFB-025: start 必须检查测试环境跳过启动."""
        from app.services.canary_fallback_monitor import start_canary_fallback_monitor

        source = inspect.getsource(start_canary_fallback_monitor)
        assert "_is_test_environment" in source

    def test_start_assigns_task_to_app_state(self):
        """TC-CFB-026: start 必须将任务句柄存入 app.state.canary_fallback_task."""
        from app.services.canary_fallback_monitor import start_canary_fallback_monitor

        source = inspect.getsource(start_canary_fallback_monitor)
        assert "app.state.canary_fallback_task" in source
        assert "asyncio.create_task" in source

    def test_stop_cancels_task(self):
        """TC-CFB-027: stop 必须调用 task.cancel()."""
        from app.services.canary_fallback_monitor import stop_canary_fallback_monitor

        source = inspect.getsource(stop_canary_fallback_monitor)
        assert ".cancel()" in source
        assert "CancelledError" in source

    def test_main_lifespan_starts_and_stops_monitor(self):
        """TC-CFB-028: main.py lifespan 必须启动和停止 fallback monitor."""
        from app.main import lifespan

        source = inspect.getsource(lifespan)
        assert "start_canary_fallback_monitor" in source
        assert "stop_canary_fallback_monitor" in source

    def test_module_imports_auto_rollback_service_inside_loop(self):
        """TC-CFB-029: auto_rollback_service 必须在循环内导入 (避免循环依赖)."""
        source = inspect.getsource(_canary_fallback_loop)
        # 应在循环内 import (而非模块顶部)
        assert "from app.services.auto_rollback_service import" in source
