"""v1.39 ObservabilityExporter 单元测试.

T-AR-011 交付物. 被 TC-AT-008 ~ TC-AT-010 调用.

测试范围:
- TC-AT-008 _collect_all_writes_gauges: 8 Gauge + 1 Counter 写入正确
- TC-AT-009 _collect_all_continues_on_error: 单 _compute_* 失败不阻塞 (FM-1)
- TC-AT-010 start_waits_for_db_ready: DB ready 3 次重试 (R3 GAP-3)
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics
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


# TC-AT-008: _collect_all 写入 8 Gauge + 1 Counter
@pytest.mark.asyncio
async def test_collect_all_writes_gauges() -> None:
    """AC-1: _collect_all 调用 7 个 _compute_*, 写入 8 Gauge + 1 Counter."""
    _reset_metrics()
    exporter = ObservabilityExporter()

    channel_data = {"overall_success_rate": 0.95}
    am_sync_data = {"success_rate": 0.88}
    lock_data = {
        "acquire_rate": 0.97,
        "fallback_rate": 0.02,
        "error_rate": 0.0,
        "total": 100,
    }
    escalation_data = {"escalation_rate": 0.15}
    trend_data = {"total_fired": 10}

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

    # 验证 Counter 累加 (delta = 10, 4 个 severity)
    for sev in ("P0", "P1", "P2", "P3"):
        assert metrics.observability_alert_total._values[(sev,)] == 10


# TC-AT-009: FM-1 fallback - 单 _compute_* 失败不阻塞
@pytest.mark.asyncio
async def test_collect_all_continues_on_error() -> None:
    """FM-1: 单个 _compute_* 抛异常时, 其他 6 个仍执行."""
    _reset_metrics()
    exporter = ObservabilityExporter()

    with patch(
        "app.api.v1.observability._compute_channel_stats",
        new=AsyncMock(side_effect=Exception("DB down")),
    ), patch(
        "app.api.v1.observability._compute_am_sync",
        new=AsyncMock(return_value={"success_rate": 0.50}),
    ), patch(
        "app.api.v1.observability._compute_lock_stats",
        new=AsyncMock(return_value={"acquire_rate": 0.80, "fallback_rate": 0.10, "error_rate": 0.05, "total": 50}),
    ), patch(
        "app.api.v1.observability._compute_escalation",
        new=AsyncMock(return_value={"escalation_rate": 0.20}),
    ), patch(
        "app.api.v1.observability._compute_trend",
        new=AsyncMock(return_value={"total_fired": 5}),
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
    # alert_total 累加
    for sev in ("P0", "P1", "P2", "P3"):
        assert metrics.observability_alert_total._values[(sev,)] == 5


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

    with patch(
        "app.services.observability_exporter.engine"
    ) as mock_engine:
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

    with patch(
        "app.services.observability_exporter.engine"
    ) as mock_engine:
        mock_engine.connect = MagicMock(side_effect=connect_always_fail)

        await exporter.start()

    # 仍启动 (DB ready 检测仅 warning, 不阻断)
    assert exporter._running is True
    assert exporter._task is not None
    await exporter.stop()
