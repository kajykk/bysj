"""v1.39 ObservabilityExporter 单元测试.

T-AR-011 交付物. 被 TC-AT-008 ~ TC-AT-010 调用.

测试范围:
- TC-AT-008 _collect_all_writes_gauges: 8 Gauge + 1 Counter 写入正确
- TC-AT-009 _collect_all_continues_on_error: 单 _compute_* 失败不阻塞 (FM-1)
- TC-AT-010 start_waits_for_db_ready: DB ready 3 次重试 (R3 GAP-3)

扩展测试 (覆盖率 20% → 75%+):
- Init / StartStop / WaitForDbReady / LoopExponentialBackoff
- H-8 修复 (行 202-224)
- _safe_set_* 异常容错与默认值回退
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics

# 注意: conftest.py 的 autouse fixture mock_observability_exporter 会替换
# app.services.observability_exporter.ObservabilityExporter 模块符号。
# 但本文件在模块加载时已捕获真实类引用, 测试内 ObservabilityExporter() 仍创建真实实例。
from app.services.observability_exporter import ObservabilityExporter


def _reset_metrics() -> None:
    """测试间重置 8 Gauge + 1 Counter."""
    metrics.observability_channel_success_rate._values.clear()
    metrics.observability_am_sync_success_rate._values.clear()
    metrics.observability_lock_acquire_rate._values.clear()
    metrics.observability_lock_fallback_rate._values.clear()
    metrics.observability_lock_error_rate._values.clear()
    metrics.observability_lock_acquire_total._values.clear()
    metrics.observability_escalation_rate._values.clear()
    metrics.observability_alert_total._values.clear()


def _make_db_mock() -> AsyncMock:
    """构造一个 AsyncSession spec 的 mock, 用于直接调用 _safe_set_*."""
    return AsyncMock(spec=AsyncSession)


def _time_window() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    return now - timedelta(minutes=5), now


# ============================================================================
# 原有 4 个测试 (保持不变)
# ============================================================================


# TC-AT-008: _collect_all 写入 8 Gauge + 1 Counter
@pytest.mark.asyncio
async def test_collect_all_writes_gauges() -> None:
    """AC-1: _collect_all 调用 7 个 _compute_*, 写入 8 Gauge + 1 Counter."""
    _reset_metrics()
    exporter = ObservabilityExporter()
    # H-8 修复后首次调用仅初始化基线不累加 Counter，测试稳态行为时跳过初始化
    exporter._counter_initialized = True

    channel_data = {"overall_success_rate": 0.95}
    am_sync_data = {"success_rate": 0.88}
    lock_data = {
        "memory": {
            "acquire_rate": 0.97,
            "fallback_rate": 0.02,
            "error_rate": 0.0,
            "total": 100,
        }
    }
    escalation_data = {"escalation_rate": 0.15}
    trend_data = {"by_status": {"firing": 10}}

    with patch(
        "app.api.v1.observability._compute_channel_stats",
        new=AsyncMock(return_value=channel_data),
    ), patch(
        "app.api.v1.observability._compute_am_sync",
        new=AsyncMock(return_value=am_sync_data),
    ), patch(
        "app.api.v1.observability._compute_lock_stats",
        new=AsyncMock(return_value=lock_data),
    ), patch(
        "app.api.v1.observability._compute_escalation",
        new=AsyncMock(return_value=escalation_data),
    ), patch(
        "app.api.v1.observability._compute_trend",
        new=AsyncMock(return_value=trend_data),
    ), patch(
        "app.services.observability_exporter.AsyncSessionLocal"
    ) as mock_session_local:
        # 模拟 AsyncSession context manager
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session_local.return_value.__aenter__.return_value = mock_session

        await exporter._collect_all()

    # 验证 7 Gauge 写入
    assert metrics.observability_channel_success_rate._values[("all",)] == 0.95
    assert metrics.observability_am_sync_success_rate._values[()] == 0.88
    assert metrics.observability_lock_acquire_rate._values[()] == 0.97
    assert metrics.observability_lock_fallback_rate._values[()] == 0.02
    assert metrics.observability_lock_error_rate._values[()] == 0.0
    assert metrics.observability_lock_acquire_total._values[()] == 100
    assert metrics.observability_escalation_rate._values[()] == 0.15

    # H-8 修复后 Counter 仅累加一次到 severity="total" 标签，避免 4 个 severity 膨胀计数
    assert metrics.observability_alert_total._values[("total",)] == 10


# TC-AT-009: FM-1 fallback - 单 _compute_* 失败不阻塞
@pytest.mark.asyncio
async def test_collect_all_continues_on_error() -> None:
    """FM-1: 单个 _compute_* 抛异常时, 其他 6 个仍执行."""
    _reset_metrics()
    exporter = ObservabilityExporter()
    # H-8 修复后首次调用仅初始化基线不累加 Counter，测试稳态行为时跳过初始化
    exporter._counter_initialized = True

    with patch(
        "app.api.v1.observability._compute_channel_stats",
        new=AsyncMock(side_effect=Exception("DB down")),
    ), patch(
        "app.api.v1.observability._compute_am_sync",
        new=AsyncMock(return_value={"success_rate": 0.50}),
    ), patch(
        "app.api.v1.observability._compute_lock_stats",
        new=AsyncMock(
            return_value={
                "memory": {
                    "acquire_rate": 0.80,
                    "fallback_rate": 0.10,
                    "error_rate": 0.05,
                    "total": 50,
                }
            }
        ),
    ), patch(
        "app.api.v1.observability._compute_escalation",
        new=AsyncMock(return_value={"escalation_rate": 0.20}),
    ), patch(
        "app.api.v1.observability._compute_trend",
        new=AsyncMock(return_value={"by_status": {"firing": 5}}),
    ), patch(
        "app.services.observability_exporter.AsyncSessionLocal"
    ) as mock_session_local:
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session_local.return_value.__aenter__.return_value = mock_session

        # 不应抛异常
        await exporter._collect_all()

    # channel 未写入 (失败)
    assert ("all",) not in metrics.observability_channel_success_rate._values

    # am_sync 写入 (成功)
    assert metrics.observability_am_sync_success_rate._values[()] == 0.50
    # lock 4 个写入
    assert metrics.observability_lock_acquire_rate._values[()] == 0.80
    assert metrics.observability_lock_fallback_rate._values[()] == 0.10
    assert metrics.observability_lock_error_rate._values[()] == 0.05
    assert metrics.observability_lock_acquire_total._values[()] == 50
    # escalation 写入
    assert metrics.observability_escalation_rate._values[()] == 0.20
    # H-8 修复后 Counter 仅累加一次到 severity="total" 标签，避免 4 个 severity 膨胀计数
    assert metrics.observability_alert_total._values[("total",)] == 5


# TC-AT-010: R3 GAP-3 - DB ready 3 次重试
@pytest.mark.asyncio
async def test_start_waits_for_db_ready() -> None:
    """R3 GAP-3: DB 第 1 次失败, 第 2 次成功 → exporter 启动成功."""
    exporter = ObservabilityExporter()

    # 模拟 engine.connect() 第 1 次失败, 第 2 次成功
    mock_conn_fail = AsyncMock()
    mock_conn_fail.execute = AsyncMock(side_effect=Exception("DB not ready"))

    mock_conn_ok = AsyncMock()
    mock_conn_ok.execute = AsyncMock(return_value=None)

    # 构造第 1 次 connect() 返回失败 context, 第 2 次返回成功
    call_count = {"n": 0}

    def connect_side_effect():
        call_count["n"] += 1
        if call_count["n"] == 1:
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(side_effect=Exception("DB not ready"))
            ctx.__aexit__ = AsyncMock(return_value=None)
            return ctx
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_conn_ok)
        ctx.__aexit__ = AsyncMock(return_value=None)
        return ctx

    # mock _collect_all 避免后台 _loop task 真实调用 DB (会挂起)
    # mock event_bus 避免全局状态在测试间累积 (前序测试注册的 handler 可能干扰)
    # mock asyncio.sleep 避免 _wait_for_db_ready 真实等待 1s 和 _loop 的 60s sleep
    with patch(
        "app.services.observability_exporter.engine"
    ) as mock_engine, patch.object(exporter, "_collect_all", new=AsyncMock()), patch(
        "app.services.observability_exporter.event_bus.start", new=AsyncMock()
    ), patch(
        "app.services.observability_exporter.event_bus.stop", new=AsyncMock()
    ), patch(
        "app.services.observability_exporter.asyncio.sleep", new=AsyncMock()
    ):
        mock_engine.connect = MagicMock(side_effect=connect_side_effect)

        await exporter.start()

    assert exporter._running is True
    assert exporter._task is not None
    assert call_count["n"] == 2, f"expected 2 connect calls, got {call_count['n']}"

    # 清理 (避免 asyncio task 持续运行)
    await exporter.stop()


@pytest.mark.asyncio
async def test_start_db_3_failures_continues() -> None:
    """R3 GAP-3: DB 3 次都失败 → exporter 仍启动 (不阻断)."""
    exporter = ObservabilityExporter()

    def connect_always_fail():
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("DB down"))
        ctx.__aexit__ = AsyncMock(return_value=None)
        return ctx

    # mock _collect_all 避免后台 _loop task 真实调用 DB (会挂起)
    # mock event_bus 避免全局状态在测试间累积
    # mock asyncio.sleep 避免 _wait_for_db_ready 真实等待
    with patch(
        "app.services.observability_exporter.engine"
    ) as mock_engine, patch.object(exporter, "_collect_all", new=AsyncMock()), patch(
        "app.services.observability_exporter.event_bus.start", new=AsyncMock()
    ), patch(
        "app.services.observability_exporter.event_bus.stop", new=AsyncMock()
    ), patch(
        "app.services.observability_exporter.asyncio.sleep", new=AsyncMock()
    ):
        mock_engine.connect = MagicMock(side_effect=connect_always_fail)

        await exporter.start()

    # 仍启动 (DB ready 检测仅 warning, 不阻断)
    assert exporter._running is True
    assert exporter._task is not None
    await exporter.stop()


# ============================================================================
# TestObservabilityExporterInit
# ============================================================================


class TestObservabilityExporterInit:
    """__init__ 初始状态验证."""

    def test_initial_state(self) -> None:
        exporter = ObservabilityExporter()
        assert exporter._task is None
        assert exporter._running is False
        assert exporter._prev_total_fired == 0
        assert exporter._counter_initialized is False

    def test_class_level_constants(self) -> None:
        assert ObservabilityExporter.INTERVAL_SECONDS == 60
        assert ObservabilityExporter.DB_READY_MAX_RETRIES == 3
        assert ObservabilityExporter.DB_READY_RETRY_DELAY_SECONDS == 1.0


# ============================================================================
# TestStartStop
# ============================================================================


class TestStartStop:
    """start / stop 生命周期管理."""

    async def test_start_early_return_when_already_running(self) -> None:
        """start 在 _running=True 时早退, 不重复创建 task."""
        exporter = ObservabilityExporter()
        exporter._running = True
        original_task = "pre-existing-task"
        exporter._task = original_task  # type: ignore[assignment]

        # 即使 DB ready 检测会失败也不应被调用 (早退前不执行)
        with patch.object(exporter, "_wait_for_db_ready", new=AsyncMock()) as m_wait:
            await exporter.start()

        # 早退: 未调用 _wait_for_db_ready, 未替换 _task
        m_wait.assert_not_awaited()
        assert exporter._task is original_task
        assert exporter._running is True

    async def test_start_creates_task_when_db_ready(self) -> None:
        """DB ready 成功后创建 task 并设 _running=True."""
        exporter = ObservabilityExporter()

        mock_conn = AsyncMock()
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        ctx.__aexit__ = AsyncMock(return_value=None)

        # mock event_bus 避免全局状态在测试间累积
        with patch(
            "app.services.observability_exporter.engine"
        ) as mock_engine, patch.object(
            exporter, "_loop", new=AsyncMock()
        ) as m_loop, patch(
            "app.services.observability_exporter.event_bus.start", new=AsyncMock()
        ), patch(
            "app.services.observability_exporter.event_bus.stop", new=AsyncMock()
        ):
            mock_engine.connect = MagicMock(return_value=ctx)
            await exporter.start()

        assert exporter._running is True
        assert exporter._task is not None
        # _loop 已被调度到后台 task (called=True 表示 coroutine 已构造)
        # 不直接 await, 由事件循环驱动
        assert m_loop.called

        await exporter.stop()

    async def test_start_db_failures_still_sets_running_true(self) -> None:
        """DB ready 3 次失败仍创建 task 并设 _running=True (warning 不阻断)."""
        exporter = ObservabilityExporter()

        def connect_always_fail():
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(side_effect=Exception("DB down"))
            ctx.__aexit__ = AsyncMock(return_value=None)
            return ctx

        # mock event_bus 避免全局状态在测试间累积
        # mock asyncio.sleep 避免 _wait_for_db_ready 真实等待
        with patch(
            "app.services.observability_exporter.engine"
        ) as mock_engine, patch.object(exporter, "_loop", new=AsyncMock()), patch(
            "app.services.observability_exporter.event_bus.start", new=AsyncMock()
        ), patch(
            "app.services.observability_exporter.event_bus.stop", new=AsyncMock()
        ), patch(
            "app.services.observability_exporter.asyncio.sleep", new=AsyncMock()
        ):
            mock_engine.connect = MagicMock(side_effect=connect_always_fail)
            await exporter.start()

        # 独立验证 _running=True (不阻断)
        assert exporter._running is True
        assert exporter._task is not None
        await exporter.stop()

    async def test_stop_with_no_task_sets_running_false(self) -> None:
        """stop 在 _task=None 时直接设 _running=False 返回."""
        exporter = ObservabilityExporter()
        exporter._running = True
        # _task 保持 None

        await exporter.stop()

        assert exporter._running is False
        assert exporter._task is None

    async def test_stop_cancels_task_and_catches_cancelled(self) -> None:
        """stop 在 _task 存在时 cancel 并 await, 捕获 CancelledError."""
        exporter = ObservabilityExporter()
        exporter._running = True

        async def long_loop() -> None:
            try:
                while True:
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                raise

        exporter._task = asyncio.create_task(long_loop())
        # 让 task 启动
        await asyncio.sleep(0)

        # stop 不应抛 CancelledError
        await exporter.stop()

        assert exporter._task is not None
        assert exporter._task.cancelled()  # type: ignore[union-attr]
        assert exporter._running is False

    async def test_stop_sets_running_false_even_with_task(self) -> None:
        """stop 验证 _running 被设为 False (即使 task 存在)."""
        exporter = ObservabilityExporter()
        exporter._running = True

        async def short_loop() -> None:
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                raise

        exporter._task = asyncio.create_task(short_loop())
        await asyncio.sleep(0)

        await exporter.stop()

        assert exporter._running is False


# ============================================================================
# TestWaitForDbReady
# ============================================================================


class TestWaitForDbReady:
    """_wait_for_db_ready: R3 GAP-3 最多 3 次重试."""

    @staticmethod
    def _ok_connect() -> tuple[MagicMock, AsyncMock]:
        mock_conn = AsyncMock()
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        ctx.__aexit__ = AsyncMock(return_value=None)
        return MagicMock(return_value=ctx), mock_conn

    @staticmethod
    def _fail_connect() -> MagicMock:
        def _factory() -> AsyncMock:
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(side_effect=Exception("DB not ready"))
            ctx.__aexit__ = AsyncMock(return_value=None)
            return ctx

        return MagicMock(side_effect=_factory)

    async def test_first_attempt_success(self) -> None:
        """第 1 次连接即成功 → 返回 True, attempt=1."""
        exporter = ObservabilityExporter()
        connect_mock, mock_conn = self._ok_connect()

        with patch("app.services.observability_exporter.engine") as mock_engine:
            mock_engine.connect = connect_mock
            result = await exporter._wait_for_db_ready()

        assert result is True
        assert mock_conn.execute.await_count == 1
        assert connect_mock.call_count == 1

    async def test_third_attempt_success(self) -> None:
        """前 2 次失败第 3 次成功 → 返回 True."""
        exporter = ObservabilityExporter()
        call_state = {"n": 0}

        def connect_side_effect() -> AsyncMock:
            call_state["n"] += 1
            if call_state["n"] < 3:
                ctx = AsyncMock()
                ctx.__aenter__ = AsyncMock(side_effect=Exception("DB down"))
                ctx.__aexit__ = AsyncMock(return_value=None)
                return ctx
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
            ctx.__aexit__ = AsyncMock(return_value=None)
            return ctx

        with patch("app.services.observability_exporter.engine") as mock_engine, patch(
            "app.services.observability_exporter.asyncio.sleep", new=AsyncMock()
        ):
            mock_engine.connect = MagicMock(side_effect=connect_side_effect)
            result = await exporter._wait_for_db_ready()

        assert result is True
        assert call_state["n"] == 3

    async def test_all_three_attempts_fail(self) -> None:
        """3 次全失败 → 返回 False."""
        exporter = ObservabilityExporter()

        with patch("app.services.observability_exporter.engine") as mock_engine, patch(
            "app.services.observability_exporter.asyncio.sleep", new=AsyncMock()
        ) as mock_sleep:
            mock_engine.connect = self._fail_connect()
            result = await exporter._wait_for_db_ready()

        assert result is False
        assert mock_sleep.await_count == 2  # 第 3 次失败后不 sleep

    async def test_sleeps_between_retries(self) -> None:
        """验证每次重试间隔 asyncio.sleep(1.0) 被调用."""
        exporter = ObservabilityExporter()

        with patch("app.services.observability_exporter.engine") as mock_engine, patch(
            "app.services.observability_exporter.asyncio.sleep", new=AsyncMock()
        ) as mock_sleep:
            mock_engine.connect = self._fail_connect()
            await exporter._wait_for_db_ready()

        # 3 次尝试, 2 次 sleep (第 3 次失败后不再 sleep)
        assert mock_sleep.await_count == 2
        for call in mock_sleep.call_args_list:
            assert call.args[0] == ObservabilityExporter.DB_READY_RETRY_DELAY_SECONDS

    async def test_uses_select_1_text(self) -> None:
        """验证使用 text('SELECT 1')."""
        exporter = ObservabilityExporter()
        connect_mock, mock_conn = self._ok_connect()

        with patch("app.services.observability_exporter.engine") as mock_engine:
            mock_engine.connect = connect_mock
            await exporter._wait_for_db_ready()

        # execute 被调用, 参数是 TextClause
        args = mock_conn.execute.call_args
        assert args is not None
        text_arg = args.args[0]
        # TextClause 有 .text 属性
        assert hasattr(text_arg, "text")
        assert text_arg.text == "SELECT 1"


# ============================================================================
# TestLoopExponentialBackoff
# ============================================================================


class TestLoopExponentialBackoff:
    """_loop 指数退避逻辑 (行 99-110)."""

    async def test_success_resets_retry_count(self) -> None:
        """_collect_all 成功时重置 retry_count=0, 失败后 backoff 从 2 重新开始."""
        exporter = ObservabilityExporter()
        exporter._running = True

        state = {"n": 0}

        async def collect() -> None:
            state["n"] += 1
            # 1: fail, 2: success, 3: fail, 4: success + stop
            if state["n"] in (1, 3):
                raise Exception(f"fail {state['n']}")
            if state["n"] == 4:
                exporter._running = False

        with patch.object(
            exporter, "_collect_all", new=AsyncMock(side_effect=collect)
        ), patch(
            "app.services.observability_exporter.asyncio.sleep", new=AsyncMock()
        ) as mock_sleep:
            await exporter._loop()

        # backoff 序列: 2 (fail1), 60 (success2), 2 (fail3 reset!), 60 (success4)
        sleeps = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleeps == [2, 60, 2, 60], f"actual: {sleeps}"

    async def test_backoff_grows_on_consecutive_failures(self) -> None:
        """连续失败时 backoff 指数增长: 2, 4, 8, 16."""
        exporter = ObservabilityExporter()
        exporter._running = True

        state = {"n": 0}

        async def collect() -> None:
            state["n"] += 1
            if state["n"] >= 4:
                exporter._running = False
            raise Exception(f"fail {state['n']}")

        with patch.object(
            exporter, "_collect_all", new=AsyncMock(side_effect=collect)
        ), patch(
            "app.services.observability_exporter.asyncio.sleep", new=AsyncMock()
        ) as mock_sleep:
            await exporter._loop()

        # 4 次失败: backoff = 2, 4, 8, 16
        sleeps = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleeps == [2, 4, 8, 16], f"actual: {sleeps}"

    async def test_backoff_capped_at_60(self) -> None:
        """retry_count >= 6 时 backoff 封顶 60s."""
        exporter = ObservabilityExporter()
        exporter._running = True

        state = {"n": 0}

        async def collect() -> None:
            state["n"] += 1
            if state["n"] >= 7:
                exporter._running = False
            raise Exception(f"fail {state['n']}")

        with patch.object(
            exporter, "_collect_all", new=AsyncMock(side_effect=collect)
        ), patch(
            "app.services.observability_exporter.asyncio.sleep", new=AsyncMock()
        ) as mock_sleep:
            await exporter._loop()

        # 7 次失败: 2, 4, 8, 16, 32, 60 (2^6=64 cap), 60 (2^7=128 cap)
        sleeps = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleeps == [2, 4, 8, 16, 32, 60, 60], f"actual: {sleeps}"

    async def test_loop_exits_when_running_false(self) -> None:
        """_running=False 时退出循环."""
        exporter = ObservabilityExporter()
        exporter._running = True

        async def collect() -> None:
            exporter._running = False

        with patch.object(
            exporter, "_collect_all", new=AsyncMock(side_effect=collect)
        ), patch(
            "app.services.observability_exporter.asyncio.sleep", new=AsyncMock()
        ) as mock_sleep:
            await exporter._loop()

        # 1 次成功 collect + 1 次 sleep(60), 然后下次 while 检查 _running=False 退出
        assert mock_sleep.await_count == 1
        assert mock_sleep.call_args.args[0] == 60

    async def test_exception_logged_via_logger_exception(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """验证异常被 logger.exception 记录."""
        exporter = ObservabilityExporter()
        exporter._running = True

        state = {"n": 0}

        async def collect() -> None:
            state["n"] += 1
            if state["n"] >= 2:
                exporter._running = False
            raise Exception("boom-trace-test")

        with patch.object(
            exporter, "_collect_all", new=AsyncMock(side_effect=collect)
        ), patch("app.services.observability_exporter.asyncio.sleep", new=AsyncMock()):
            with caplog.at_level(
                logging.ERROR, logger="app.services.observability_exporter"
            ):
                await exporter._loop()

        # logger.exception 等价 ERROR 级别 + exc_info
        assert any(
            "boom-trace-test" in r.message for r in caplog.records
        ), f"records: {[r.message for r in caplog.records]}"


# ============================================================================
# TestCollectAll (补充分支)
# ============================================================================


class TestCollectAll:
    """_collect_all 行为补充."""

    async def test_calls_all_five_safe_set_methods(self) -> None:
        """验证 5 个 _safe_set_* 被依次调用 (覆盖 8 个 metric)."""
        exporter = ObservabilityExporter()

        with patch.object(
            exporter, "_safe_set_channel", new=AsyncMock()
        ) as m_ch, patch.object(
            exporter, "_safe_set_am_sync", new=AsyncMock()
        ) as m_am, patch.object(
            exporter, "_safe_set_lock", new=AsyncMock()
        ) as m_lk, patch.object(
            exporter, "_safe_set_escalation", new=AsyncMock()
        ) as m_es, patch.object(
            exporter, "_safe_set_alert_total", new=AsyncMock()
        ) as m_at, patch(
            "app.services.observability_exporter.AsyncSessionLocal"
        ) as mock_session_local:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session_local.return_value.__aenter__.return_value = mock_session

            await exporter._collect_all()

        m_ch.assert_awaited_once()
        m_am.assert_awaited_once()
        m_lk.assert_awaited_once()
        m_es.assert_awaited_once()
        m_at.assert_awaited_once()

    async def test_propagates_session_creation_failure(self) -> None:
        """AsyncSessionLocal 创建 session 失败时异常向上传播 (由 _loop 捕获)."""
        exporter = ObservabilityExporter()

        with patch(
            "app.services.observability_exporter.AsyncSessionLocal"
        ) as mock_session_local:
            mock_session_local.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("session factory closed")
            )
            with pytest.raises(Exception, match="session factory closed"):
                await exporter._collect_all()


# ============================================================================
# TestSafeSetAlertTotalH8Fix (关键: 行 202-224)
# ============================================================================


class TestSafeSetAlertTotalH8Fix:
    """H-8 修复逻辑测试.

    首次调用仅初始化基线 (_prev_total_fired), 不累加 Counter.
    避免服务重启后 _prev_total_fired=0 导致历史告警被作为增量计入.
    """

    async def test_first_call_only_initializes_no_inc(self) -> None:
        """首次调用: 仅设 _prev_total_fired 和 _counter_initialized, 不 inc Counter."""
        _reset_metrics()
        exporter = ObservabilityExporter()
        assert exporter._counter_initialized is False
        db = _make_db_mock()
        start, end = _time_window()

        with patch(
            "app.api.v1.observability._compute_trend",
            new=AsyncMock(return_value={"by_status": {"firing": 100}}),
        ):
            await exporter._safe_set_alert_total(db, start, end)

        assert exporter._counter_initialized is True
        assert exporter._prev_total_fired == 100
        # Counter 未被 inc
        assert ("total",) not in metrics.observability_alert_total._values

    async def test_first_call_logs_counter_initialized(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """首次调用后 logger.info 输出 'counter initialized'."""
        _reset_metrics()
        exporter = ObservabilityExporter()
        db = _make_db_mock()
        start, end = _time_window()

        with patch(
            "app.api.v1.observability._compute_trend",
            new=AsyncMock(return_value={"by_status": {"firing": 50}}),
        ):
            with caplog.at_level(
                logging.INFO, logger="app.services.observability_exporter"
            ):
                await exporter._safe_set_alert_total(db, start, end)

        assert any(
            "counter initialized" in r.message for r in caplog.records
        ), f"records: {[r.message for r in caplog.records]}"

    async def test_second_call_incs_positive_delta(self) -> None:
        """后续调用 delta>0 时 inc(delta, severity='total')."""
        _reset_metrics()
        exporter = ObservabilityExporter()
        exporter._counter_initialized = True
        exporter._prev_total_fired = 100
        db = _make_db_mock()
        start, end = _time_window()

        with patch(
            "app.api.v1.observability._compute_trend",
            new=AsyncMock(return_value={"by_status": {"firing": 115}}),
        ):
            await exporter._safe_set_alert_total(db, start, end)

        # delta = 115 - 100 = 15
        assert metrics.observability_alert_total._values[("total",)] == 15
        assert exporter._prev_total_fired == 115

    async def test_zero_delta_no_inc(self) -> None:
        """后续调用 delta=0 时不 inc."""
        _reset_metrics()
        exporter = ObservabilityExporter()
        exporter._counter_initialized = True
        exporter._prev_total_fired = 100
        db = _make_db_mock()
        start, end = _time_window()

        with patch(
            "app.api.v1.observability._compute_trend",
            new=AsyncMock(return_value={"by_status": {"firing": 100}}),
        ):
            await exporter._safe_set_alert_total(db, start, end)

        # delta = 0, 不 inc
        assert ("total",) not in metrics.observability_alert_total._values
        # 但 _prev_total_fired 仍更新 (到同值)
        assert exporter._prev_total_fired == 100

    async def test_negative_delta_clamped_to_zero(self) -> None:
        """total_fired 减少 (delta<0) 时 max(0,...) 保护为 0, 不 inc."""
        _reset_metrics()
        exporter = ObservabilityExporter()
        exporter._counter_initialized = True
        exporter._prev_total_fired = 100
        db = _make_db_mock()
        start, end = _time_window()

        with patch(
            "app.api.v1.observability._compute_trend",
            new=AsyncMock(return_value={"by_status": {"firing": 95}}),
        ):
            await exporter._safe_set_alert_total(db, start, end)

        # delta = max(0, 95 - 100) = 0, 不 inc
        assert ("total",) not in metrics.observability_alert_total._values
        # _prev_total_fired 更新为 95
        assert exporter._prev_total_fired == 95

    async def test_compute_trend_exception_no_block(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """_compute_trend 抛异常时 logger.warning, 不影响其他."""
        _reset_metrics()
        exporter = ObservabilityExporter()
        db = _make_db_mock()
        start, end = _time_window()

        with patch(
            "app.api.v1.observability._compute_trend",
            new=AsyncMock(side_effect=RuntimeError("trend crashed")),
        ):
            with caplog.at_level(
                logging.WARNING, logger="app.services.observability_exporter"
            ):
                # 不应抛异常
                await exporter._safe_set_alert_total(db, start, end)

        # 初始化未完成
        assert exporter._counter_initialized is False
        assert ("total",) not in metrics.observability_alert_total._values
        assert any(
            "alert_total collect failed" in r.message for r in caplog.records
        ), f"records: {[r.message for r in caplog.records]}"

    async def test_total_fired_missing_key_defaults_to_zero(self) -> None:
        """by_status 或 firing 缺失时默认值回退为 0."""
        _reset_metrics()
        exporter = ObservabilityExporter()
        db = _make_db_mock()
        start, end = _time_window()

        with patch(
            "app.api.v1.observability._compute_trend",
            new=AsyncMock(return_value={}),  # 缺少 by_status 键
        ):
            await exporter._safe_set_alert_total(db, start, end)

        # 首次: _prev_total_fired = 0 (默认值)
        assert exporter._prev_total_fired == 0
        assert exporter._counter_initialized is True


# ============================================================================
# TestSafeSetChannel (补充)
# ============================================================================


class TestSafeSetChannel:
    """_safe_set_channel 异常容错与默认值回退."""

    async def test_exception_no_block(self, caplog: pytest.LogCaptureFixture) -> None:
        """_compute_channel_stats 抛异常时仅 warning 不阻塞."""
        _reset_metrics()
        exporter = ObservabilityExporter()
        db = _make_db_mock()
        start, end = _time_window()

        with patch(
            "app.api.v1.observability._compute_channel_stats",
            new=AsyncMock(side_effect=Exception("channel crashed")),
        ):
            with caplog.at_level(
                logging.WARNING, logger="app.services.observability_exporter"
            ):
                await exporter._safe_set_channel(db, start, end)

        assert ("all",) not in metrics.observability_channel_success_rate._values
        assert any("channel_stats collect failed" in r.message for r in caplog.records)

    async def test_default_when_key_missing(self) -> None:
        """cs.get('overall_success_rate', 0.0) 默认值回退."""
        _reset_metrics()
        exporter = ObservabilityExporter()
        db = _make_db_mock()
        start, end = _time_window()

        with patch(
            "app.api.v1.observability._compute_channel_stats",
            new=AsyncMock(return_value={}),  # 缺少 overall_success_rate
        ):
            await exporter._safe_set_channel(db, start, end)

        assert metrics.observability_channel_success_rate._values[("all",)] == 0.0


# ============================================================================
# TestSafeSetAmSync (新)
# ============================================================================


class TestSafeSetAmSync:
    """_safe_set_am_sync 异常容错与默认值回退."""

    async def test_exception_no_block(self, caplog: pytest.LogCaptureFixture) -> None:
        """_compute_am_sync 抛异常时仅 warning."""
        _reset_metrics()
        exporter = ObservabilityExporter()
        db = _make_db_mock()
        start, end = _time_window()

        with patch(
            "app.api.v1.observability._compute_am_sync",
            new=AsyncMock(side_effect=Exception("am sync crashed")),
        ):
            with caplog.at_level(
                logging.WARNING, logger="app.services.observability_exporter"
            ):
                await exporter._safe_set_am_sync(db, start, end)

        assert () not in metrics.observability_am_sync_success_rate._values
        assert any("am_sync collect failed" in r.message for r in caplog.records)

    async def test_default_when_key_missing(self) -> None:
        """am.get('success_rate', 0.0) 默认值回退."""
        _reset_metrics()
        exporter = ObservabilityExporter()
        db = _make_db_mock()
        start, end = _time_window()

        with patch(
            "app.api.v1.observability._compute_am_sync",
            new=AsyncMock(return_value={}),  # 缺少 success_rate
        ):
            await exporter._safe_set_am_sync(db, start, end)

        assert metrics.observability_am_sync_success_rate._values[()] == 0.0


# ============================================================================
# TestSafeSetLock (补充)
# ============================================================================


class TestSafeSetLock:
    """_safe_set_lock 异常容错与 4 个 metric 写入."""

    async def test_exception_no_block(self, caplog: pytest.LogCaptureFixture) -> None:
        """_compute_lock_stats 抛异常时不阻塞."""
        _reset_metrics()
        exporter = ObservabilityExporter()
        db = _make_db_mock()

        with patch(
            "app.api.v1.observability._compute_lock_stats",
            new=AsyncMock(side_effect=Exception("lock crashed")),
        ):
            with caplog.at_level(
                logging.WARNING, logger="app.services.observability_exporter"
            ):
                await exporter._safe_set_lock(db)

        # 4 个 lock metric 均未写入
        assert not metrics.observability_lock_acquire_rate._values
        assert not metrics.observability_lock_fallback_rate._values
        assert not metrics.observability_lock_error_rate._values
        assert not metrics.observability_lock_acquire_total._values
        assert any("lock_stats collect failed" in r.message for r in caplog.records)

    async def test_sets_four_metrics(self) -> None:
        """验证 4 个 metric (acquire_rate/fallback_rate/error_rate/acquire_total) 全部 set."""
        _reset_metrics()
        exporter = ObservabilityExporter()
        db = _make_db_mock()

        lock_data = {
            "memory": {
                "acquire_rate": 0.91,
                "fallback_rate": 0.05,
                "error_rate": 0.04,
                "total": 250,
            }
        }
        with patch(
            "app.api.v1.observability._compute_lock_stats",
            new=AsyncMock(return_value=lock_data),
        ):
            await exporter._safe_set_lock(db)

        assert metrics.observability_lock_acquire_rate._values[()] == 0.91
        assert metrics.observability_lock_fallback_rate._values[()] == 0.05
        assert metrics.observability_lock_error_rate._values[()] == 0.04
        assert metrics.observability_lock_acquire_total._values[()] == 250

    async def test_defaults_when_keys_missing(self) -> None:
        """.get() 默认值回退."""
        _reset_metrics()
        exporter = ObservabilityExporter()
        db = _make_db_mock()

        with patch(
            "app.api.v1.observability._compute_lock_stats",
            new=AsyncMock(return_value={}),
        ):
            await exporter._safe_set_lock(db)

        assert metrics.observability_lock_acquire_rate._values[()] == 0.0
        assert metrics.observability_lock_fallback_rate._values[()] == 0.0
        assert metrics.observability_lock_error_rate._values[()] == 0.0
        assert metrics.observability_lock_acquire_total._values[()] == 0


# ============================================================================
# TestSafeSetEscalation (新)
# ============================================================================


class TestSafeSetEscalation:
    """_safe_set_escalation 异常容错与默认值回退."""

    async def test_exception_no_block(self, caplog: pytest.LogCaptureFixture) -> None:
        """_compute_escalation 抛异常时不阻塞."""
        _reset_metrics()
        exporter = ObservabilityExporter()
        db = _make_db_mock()
        start, end = _time_window()

        with patch(
            "app.api.v1.observability._compute_escalation",
            new=AsyncMock(side_effect=Exception("escalation crashed")),
        ):
            with caplog.at_level(
                logging.WARNING, logger="app.services.observability_exporter"
            ):
                await exporter._safe_set_escalation(db, start, end)

        assert () not in metrics.observability_escalation_rate._values
        assert any("escalation collect failed" in r.message for r in caplog.records)

    async def test_default_when_key_missing(self) -> None:
        """es.get('escalation_rate', 0.0) 默认值回退."""
        _reset_metrics()
        exporter = ObservabilityExporter()
        db = _make_db_mock()
        start, end = _time_window()

        with patch(
            "app.api.v1.observability._compute_escalation",
            new=AsyncMock(return_value={}),
        ):
            await exporter._safe_set_escalation(db, start, end)

        assert metrics.observability_escalation_rate._values[()] == 0.0
