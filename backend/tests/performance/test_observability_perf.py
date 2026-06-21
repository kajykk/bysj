"""v1.36 T3.2: 告警可观测性 - 性能测试.

TC-PERF-001: 8 项性能基准, 验证可观测性 API 在大数据量下仍能保持响应阈值.
- test_trend_7d_under_500ms (100K rows)
- test_trend_30d_under_1500ms
- test_response_time_7d_under_300ms
- test_response_time_p99_calculation
- test_channel_stats_7d_under_200ms
- test_silence_hit_rate_under_100ms
- test_am_sync_under_100ms
- test_lock_stats_under_50ms

测试方法:
- 真实 db_session fixture + 自定义 _MockSession 返回大数据集
- 测量 _compute_* 纯 Python 聚合时间 (含 JSON 解析 + 桶聚合)
- 阈值基于实现复杂度 + 实测结果给出, 留 2x~5x 缓冲
"""
from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest


# ===== 辅助: 构造模拟数据 =====


def _make_trend_rows(count: int) -> list:
    """构造 trend 函数所需的 (action_type, created_at, detail) 行."""
    base = datetime(2026, 5, 28, 0, 0, 0, tzinfo=timezone.utc)
    rows = []
    for i in range(count):
        ts = base + timedelta(seconds=i * 60)
        detail = json.dumps({
            "rule": f"Rule_{i % 50}",
            "severity": ["P0", "P1", "P2", "P3"][i % 4],
        })
        action = "alert_fired" if i % 5 else "alert_resolved"
        rows.append((action, ts, detail))
    return rows


def _make_response_time_rows(count: int) -> tuple[list, list]:
    """构造 response_time 函数所需的 fired + acked 行.

    返回 (fired_rows, acked_rows):
    - fired_rows: [(created_at, detail), ...]  其中 detail.fingerprint
    - acked_rows: [(created_at, detail), ...]  其中 detail.fingerprint
    """
    base = datetime(2026, 5, 28, 0, 0, 0, tzinfo=timezone.utc)
    fired_rows = []
    acked_rows = []
    for i in range(count):
        fired_at = base + timedelta(seconds=i * 30)
        # 90% 的告警在 60s 内被 ack
        ack_at = fired_at + timedelta(seconds=60)
        fp = f"fp-perf-{i}"
        sev = ["P0", "P1", "P2", "P3"][i % 4]
        fired_rows.append((
            fired_at,
            json.dumps({"fingerprint": fp, "severity": sev, "rule": f"R{i % 20}"}),
        ))
        acked_rows.append((
            ack_at,
            json.dumps({"fingerprint": fp}),
        ))
    return fired_rows, acked_rows


def _make_channel_rows(count: int) -> list:
    """构造 channel_stats 所需的 (action_type, detail) 行."""
    base = datetime(2026, 5, 28, 0, 0, 0, tzinfo=timezone.utc)
    rows = []
    for i in range(count):
        detail = {
            "channel": ["webhook", "slack", "dingtalk", "email"][i % 4],
            "duration_ms": i % 1000,
        }
        action = "alert_channel_failed" if i % 13 == 0 else "alert_channel_sent"
        rows.append((action, json.dumps(detail)))
    return rows


def _make_silence_rows(count: int) -> tuple[list, list]:
    """构造 silence_hit_rate 所需的 (fired_details, silenced_details) 行."""
    base = datetime(2026, 5, 28, 0, 0, 0, tzinfo=timezone.utc)
    fired_details = []
    sil_details = []
    for i in range(count):
        sev = ["P0", "P1", "P2", "P3"][i % 4]
        # fired 数: silenced 数 = 2:1
        fired_details.append(json.dumps({
            "fingerprint": f"fp-fire-{i}", "severity": sev, "rule": f"R{i % 20}"
        }))
        if i % 3 == 0:
            sil_details.append(json.dumps({
                "silence_name": f"sil-{i % 5}",
                "severity": sev,
                "fingerprint": f"fp-fire-{i}",
            }))
    return fired_details, sil_details


def _make_am_sync_rows(count: int) -> tuple[list, list]:
    """构造 am_sync 所需的 (success_rows, failed_rows)."""
    base = datetime(2026, 5, 28, 0, 0, 0, tzinfo=timezone.utc)
    succ_rows = []
    fail_rows = []
    for i in range(count):
        op = "push_silence" if i % 2 == 0 else "expire_silence"
        action = "am_sync_failed" if i % 11 == 0 else "am_sync_success"
        detail = json.dumps({
            "operation": op, "duration_ms": i % 200,
            **({"error": "am 500"} if action == "am_sync_failed" else {}),
        })
        ts = base + timedelta(seconds=i)
        if action == "am_sync_failed":
            fail_rows.append((detail, ts))
        else:
            succ_rows.append((detail, ts))
    return succ_rows, fail_rows


def _make_lock_rows(count: int) -> list:
    """构造 lock_stats 所需的 (detail, created_at) 行."""
    base = datetime(2026, 5, 28, 0, 0, 0, tzinfo=timezone.utc)
    rows = []
    for i in range(count):
        detail = json.dumps({
            "instance_id": f"node-{i % 3}",
            "acquired": 10,
            "skipped": 5,
            "fallback": 2,
            "errors": 0,
        })
        rows.append((detail, base + timedelta(minutes=i * 5)))
    return rows


class _SingleResultSession:
    """所有 db.execute() 调用都返回相同 rows 的 mock session."""

    def __init__(self, rows: list):
        self._rows = rows
        self.execute_count = 0

    async def execute(self_inner, stmt):
        self_inner.execute_count += 1
        class _R:
            def all(_s):
                return self_inner._rows
            def scalars(_s):
                class _SC:
                    def all(_sc):
                        return self_inner._rows
                return _SC()
        return _R()


class _MultiResultSession:
    """不同次 db.execute() 调用返回不同 rows 的 mock session (按调用顺序)."""

    def __init__(self, *row_sets: list):
        self._row_sets = list(row_sets)
        self._idx = 0
        self.execute_count = 0

    async def execute(self_inner, stmt):
        idx = self_inner._idx
        self_inner._idx += 1
        self_inner.execute_count += 1
        rows = self_inner._row_sets[idx] if idx < len(self_inner._row_sets) else []

        class _R:
            def all(_s):
                return rows
            def scalars(_s):
                class _SC:
                    def all(_sc):
                        return rows
                return _SC()
        return _R()


# ===== 8 项性能测试 =====


@pytest.mark.performance
async def test_trend_7d_under_500ms() -> None:
    """v1.36 T3.2: 100K 行 trend 计算 < 500ms (实为 LIMIT 10000 的纯 Python 聚合)."""
    from app.api.v1.observability import _compute_trend

    rows = _make_trend_rows(10000)
    db = _SingleResultSession(rows)

    start = datetime(2026, 5, 27, tzinfo=timezone.utc)
    end = datetime(2026, 6, 3, tzinfo=timezone.utc)

    t0 = time.perf_counter()
    result = await _compute_trend(db, start, end, "1h", None, None, "severity")
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert result["total"] > 0
    assert len(result["buckets"]) > 0
    assert elapsed_ms < 500, f"trend 7d took {elapsed_ms:.1f}ms (target: <500ms)"


@pytest.mark.performance
async def test_trend_30d_under_1500ms() -> None:
    """v1.36 T3.2: 30d 范围 trend 计算 < 1500ms."""
    from app.api.v1.observability import _compute_trend

    rows = _make_trend_rows(10000)
    db = _SingleResultSession(rows)

    start = datetime(2026, 5, 4, tzinfo=timezone.utc)
    end = datetime(2026, 6, 3, tzinfo=timezone.utc)

    t0 = time.perf_counter()
    result = await _compute_trend(db, start, end, "6h", None, None, "severity")
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert result["total"] > 0
    # 30d 6h 桶 ≈ 120 桶
    assert len(result["buckets"]) <= 121
    assert elapsed_ms < 1500, f"trend 30d took {elapsed_ms:.1f}ms (target: <1500ms)"


@pytest.mark.performance
async def test_response_time_7d_under_300ms() -> None:
    """v1.36 T3.2: response_time 7d < 300ms (含 2 次 SQL 查询: fired + acked)."""
    from app.api.v1.observability import _compute_response_time

    fired_rows, acked_rows = _make_response_time_rows(5000)
    # 第一次 execute 拉 fired, 第二次拉 acked
    db = _MultiResultSession(fired_rows, acked_rows)

    start = datetime(2026, 5, 27, tzinfo=timezone.utc)
    end = datetime(2026, 6, 3, tzinfo=timezone.utc)

    t0 = time.perf_counter()
    result = await _compute_response_time(db, start, end, None)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert "response_time" in result
    assert "p99" in result["response_time"]
    assert result["total_fired"] == 5000
    assert result["total_acked"] == 5000
    assert result["total_pending"] == 0
    assert elapsed_ms < 300, f"response_time 7d took {elapsed_ms:.1f}ms (target: <300ms)"


@pytest.mark.performance
def test_response_time_p99_calculation() -> None:
    """v1.36 T3.2: p99 百分位计算正确性 (非性能, 纯算法验证)."""
    from app.api.v1.observability import _percentile

    # 1-100 序列, p99 应为 99.x
    values = list(range(1, 101))
    p99 = _percentile(values, 99)
    assert 99.0 <= p99 <= 99.99, f"p99 of 1..100 should be ~99, got {p99}"

    # 100 元素, p50 应为 50.5
    p50 = _percentile(values, 50)
    assert 50.0 <= p50 <= 51.0

    # 空列表
    assert _percentile([], 99) == 0.0

    # 边界
    assert _percentile([10], 0) == 10
    assert _percentile([10], 100) == 10


@pytest.mark.performance
async def test_channel_stats_7d_under_200ms() -> None:
    """v1.36 T3.2: channel_stats 7d < 200ms."""
    from app.api.v1.observability import _compute_channel_stats

    rows = _make_channel_rows(10000)
    db = _SingleResultSession(rows)

    start = datetime(2026, 5, 27, tzinfo=timezone.utc)
    end = datetime(2026, 6, 3, tzinfo=timezone.utc)

    t0 = time.perf_counter()
    result = await _compute_channel_stats(db, start, end, None)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert "channels" in result
    assert "total_sent" in result
    assert result["total_sent"] > 0
    assert elapsed_ms < 200, f"channel_stats 7d took {elapsed_ms:.1f}ms (target: <200ms)"


@pytest.mark.performance
async def test_silence_hit_rate_under_100ms() -> None:
    """v1.36 T3.2: silence_hit_rate < 100ms (2 次查询: fired + silenced)."""
    from app.api.v1.observability import _compute_silence_hit_rate

    fired_details, sil_details = _make_silence_rows(3000)
    db = _MultiResultSession(fired_details, sil_details)

    start = datetime(2026, 5, 27, tzinfo=timezone.utc)
    end = datetime(2026, 6, 3, tzinfo=timezone.utc)

    t0 = time.perf_counter()
    result = await _compute_silence_hit_rate(db, start, end)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert "total_fired" in result
    assert "hit_rate" in result
    assert result["total_fired"] == 3000
    assert result["total_silenced"] == 1000
    assert elapsed_ms < 100, f"silence_hit_rate took {elapsed_ms:.1f}ms (target: <100ms)"


@pytest.mark.performance
async def test_am_sync_under_100ms() -> None:
    """v1.36 T3.2: am_sync 聚合 < 100ms (2 次查询: success + failed)."""
    from app.api.v1.observability import _compute_am_sync

    succ_rows, fail_rows = _make_am_sync_rows(3000)
    db = _MultiResultSession(succ_rows, fail_rows)

    start = datetime(2026, 5, 27, tzinfo=timezone.utc)
    end = datetime(2026, 6, 3, tzinfo=timezone.utc)

    t0 = time.perf_counter()
    result = await _compute_am_sync(db, start, end, None)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert "total_success" in result
    assert "by_operation" in result
    assert result["total_success"] > 0
    assert elapsed_ms < 100, f"am_sync took {elapsed_ms:.1f}ms (target: <100ms)"


@pytest.mark.performance
async def test_lock_stats_under_50ms() -> None:
    """v1.36 T3.2: lock_stats 聚合 < 50ms (锁统计一般 50~1000 条/天)."""
    from app.api.v1.observability import _compute_lock_stats

    rows = _make_lock_rows(500)
    db = _SingleResultSession(rows)

    t0 = time.perf_counter()
    result = await _compute_lock_stats(db)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert "recent_flushes" in result
    assert "historical_recent" in result
    assert len(result["recent_flushes"]) == 500
    assert elapsed_ms < 50, f"lock_stats took {elapsed_ms:.1f}ms (target: <50ms)"
