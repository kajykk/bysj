"""v1.36 T3.2 / PERF-P1-001: 告警可观测性 - 性能测试.

TC-PERF-001: 8 项性能基准, 验证可观测性 API 在大数据量下仍能保持响应阈值.

PERF-P1-001 改造后 (SQL GROUP BY 下推):
- test_trend_7d_under_500ms (10K rows)       — SQL json_extract + GROUP BY
- test_trend_30d_under_500ms (10K rows)      — P95 目标统一 < 500ms
- test_response_time_7d_under_300ms (5K rows)— SQL json_extract + GROUP BY MIN
- test_response_time_p99_calculation          — 纯算法验证 (不变)
- test_channel_stats_7d_under_200ms (10K)    — SQL GROUP BY + COUNT/AVG/MAX
- test_silence_hit_rate_under_100ms (3K)     — SQL COUNT + GROUP BY
- test_am_sync_under_100ms (3K)              — SQL GROUP BY + AVG
- test_lock_stats_under_50ms (500)           — 未改造 (低数据量)

测试方法 (PERF-P1-001 改造后):
- 真实 db_session fixture (SQLite + aiosqlite)
- 批量插入 OperationLog (10K~5K 行)
- 测量 _compute_* 端到端执行时间 (含 3 次 SQL 查询 + Python 后处理)
- 阈值基于 SQL GROUP BY 下推后的预期性能, 留 2x~5x 缓冲

P95 延迟目标: 5s → 500ms (T-P2-010)
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import OperationLog

# ===== 辅助: 批量插入 OperationLog =====


async def _bulk_insert_trend_logs(
    db: AsyncSession, count: int, base: datetime | None = None
) -> None:
    """批量插入 alert_fired / alert_resolved 日志 (含 severity/rule)."""
    if base is None:
        base = datetime(2026, 5, 28, 0, 0, 0, tzinfo=timezone.utc)
    logs = []
    for i in range(count):
        ts = base + timedelta(seconds=i * 60)
        detail = json.dumps(
            {
                "rule": f"Rule_{i % 50}",
                "severity": ["P0", "P1", "P2", "P3"][i % 4],
                "fingerprint": f"fp-{i}",
            }
        )
        action = "alert_fired" if i % 5 else "alert_resolved"
        logs.append(
            OperationLog(
                action_type=action,
                target_type="alert",
                detail=detail,
                created_at=ts,
            )
        )
    db.add_all(logs)
    await db.flush()


async def _bulk_insert_response_time_logs(
    db: AsyncSession, count: int, base: datetime | None = None
) -> None:
    """批量插入 alert_fired + alert_acknowledged 日志 (含 fingerprint/severity)."""
    if base is None:
        base = datetime(2026, 5, 28, 0, 0, 0, tzinfo=timezone.utc)
    logs = []
    for i in range(count):
        fired_at = base + timedelta(seconds=i * 30)
        ack_at = fired_at + timedelta(seconds=60)
        fp = f"fp-perf-{i}"
        sev = ["P0", "P1", "P2", "P3"][i % 4]
        logs.append(
            OperationLog(
                action_type="alert_fired",
                target_type="alert",
                detail=json.dumps(
                    {"fingerprint": fp, "severity": sev, "rule": f"R{i % 20}"}
                ),
                created_at=fired_at,
            )
        )
        logs.append(
            OperationLog(
                action_type="alert_acknowledged",
                target_type="alert",
                detail=json.dumps({"fingerprint": fp}),
                created_at=ack_at,
            )
        )
    db.add_all(logs)
    await db.flush()


async def _bulk_insert_channel_logs(
    db: AsyncSession, count: int, base: datetime | None = None
) -> None:
    """批量插入 alert_channel_sent / alert_channel_failed 日志."""
    if base is None:
        base = datetime(2026, 5, 28, 0, 0, 0, tzinfo=timezone.utc)
    logs = []
    for i in range(count):
        detail = {
            "channel": ["webhook", "slack", "dingtalk", "email"][i % 4],
            "duration_ms": i % 1000,
            "fingerprint": f"fp-ch-{i}",
        }
        action = "alert_channel_failed" if i % 13 == 0 else "alert_channel_sent"
        logs.append(
            OperationLog(
                action_type=action,
                target_type="alert_channel",
                detail=json.dumps(detail),
                created_at=base + timedelta(seconds=i),
            )
        )
    db.add_all(logs)
    await db.flush()


async def _bulk_insert_silence_logs(
    db: AsyncSession, count: int, base: datetime | None = None
) -> tuple[int, int]:
    """批量插入 alert_fired + alert_silenced 日志.

    返回 (fired_count, silenced_count).
    """
    if base is None:
        base = datetime(2026, 5, 28, 0, 0, 0, tzinfo=timezone.utc)
    logs = []
    sil_count = 0
    for i in range(count):
        sev = ["P0", "P1", "P2", "P3"][i % 4]
        logs.append(
            OperationLog(
                action_type="alert_fired",
                target_type="alert",
                detail=json.dumps(
                    {
                        "fingerprint": f"fp-fire-{i}",
                        "severity": sev,
                        "rule": f"R{i % 20}",
                    }
                ),
                created_at=base + timedelta(seconds=i),
            )
        )
        if i % 3 == 0:
            logs.append(
                OperationLog(
                    action_type="alert_silenced",
                    target_type="alert",
                    detail=json.dumps(
                        {
                            "silence_name": f"sil-{i % 5}",
                            "severity": sev,
                            "fingerprint": f"fp-fire-{i}",
                        }
                    ),
                    created_at=base + timedelta(seconds=i + 1),
                )
            )
            sil_count += 1
    db.add_all(logs)
    await db.flush()
    return count, sil_count


async def _bulk_insert_am_sync_logs(
    db: AsyncSession, count: int, base: datetime | None = None
) -> tuple[int, int]:
    """批量插入 am_sync_success / am_sync_failed 日志.

    返回 (success_count, failed_count).
    """
    if base is None:
        base = datetime(2026, 5, 28, 0, 0, 0, tzinfo=timezone.utc)
    logs = []
    succ = 0
    fail = 0
    for i in range(count):
        op = "push_silence" if i % 2 == 0 else "expire_silence"
        is_fail = i % 11 == 0
        detail = {
            "operation": op,
            "duration_ms": i % 200,
            "am_silence_id": f"am-{i}",
        }
        if is_fail:
            detail["error"] = "am 500"
            action = "am_sync_failed"
            fail += 1
        else:
            action = "am_sync_success"
            succ += 1
        logs.append(
            OperationLog(
                action_type=action,
                target_type="alert_silence",
                detail=json.dumps(detail),
                created_at=base + timedelta(seconds=i),
            )
        )
    db.add_all(logs)
    await db.flush()
    return succ, fail


async def _bulk_insert_lock_logs(
    db: AsyncSession, count: int, base: datetime | None = None
) -> None:
    """批量插入 dedup_lock_stats 日志."""
    if base is None:
        base = datetime(2026, 5, 28, 0, 0, 0, tzinfo=timezone.utc)
    logs = []
    for i in range(count):
        detail = json.dumps(
            {
                "instance_id": f"node-{i % 3}",
                "acquired": 10,
                "skipped": 5,
                "fallback": 2,
                "errors": 0,
            }
        )
        logs.append(
            OperationLog(
                action_type="dedup_lock_stats",
                target_type="dedup_lock",
                detail=detail,
                created_at=base + timedelta(minutes=i * 5),
            )
        )
    db.add_all(logs)
    await db.flush()


# ===== 8 项性能测试 (PERF-P1-001 SQL GROUP BY 下推后) =====


@pytest.mark.performance
async def test_trend_7d_under_500ms(db_session: AsyncSession) -> None:
    """PERF-P1-001: 10K 行 trend 7d 聚合 < 500ms (SQL json_extract + GROUP BY)."""
    from app.api.v1.observability import _compute_trend

    base = datetime(2026, 5, 28, 0, 0, 0, tzinfo=timezone.utc)
    await _bulk_insert_trend_logs(db_session, 10000, base=base)

    start = datetime(2026, 5, 27, tzinfo=timezone.utc)
    end = datetime(2026, 6, 3, tzinfo=timezone.utc)

    t0 = time.perf_counter()
    result = await _compute_trend(db_session, start, end, "1h", None, None, "severity")
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert result["total"] > 0
    assert len(result["buckets"]) > 0
    # PERF-P1-001 目标: P95 < 500ms (原 Python 聚合 5s+)
    assert elapsed_ms < 500, f"trend 7d took {elapsed_ms:.1f}ms (target: <500ms)"


@pytest.mark.performance
async def test_trend_30d_under_500ms(db_session: AsyncSession) -> None:
    """PERF-P1-001: 10K 行 trend 30d 聚合 < 500ms (统一 P95 目标)."""
    from app.api.v1.observability import _compute_trend

    base = datetime(2026, 5, 4, 0, 0, 0, tzinfo=timezone.utc)
    await _bulk_insert_trend_logs(db_session, 10000, base=base)

    start = datetime(2026, 5, 4, tzinfo=timezone.utc)
    end = datetime(2026, 6, 3, tzinfo=timezone.utc)

    t0 = time.perf_counter()
    result = await _compute_trend(db_session, start, end, "6h", None, None, "severity")
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert result["total"] > 0
    # 30d 6h 桶 ≈ 120 桶
    assert len(result["buckets"]) <= 121
    # PERF-P1-001: 30d 也需满足 P95 < 500ms (原阈值 1500ms)
    assert elapsed_ms < 500, f"trend 30d took {elapsed_ms:.1f}ms (target: <500ms)"


@pytest.mark.performance
async def test_response_time_7d_under_300ms(db_session: AsyncSession) -> None:
    """PERF-P1-001: response_time 7d < 300ms (SQL json_extract + GROUP BY MIN)."""
    from app.api.v1.observability import _compute_response_time

    base = datetime(2026, 5, 27, 0, 0, 0, tzinfo=timezone.utc)
    await _bulk_insert_response_time_logs(db_session, 5000, base=base)

    start = datetime(2026, 5, 27, tzinfo=timezone.utc)
    end = datetime(2026, 6, 3, tzinfo=timezone.utc)

    t0 = time.perf_counter()
    result = await _compute_response_time(db_session, start, end, None)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert "response_time" in result
    assert "p99" in result["response_time"]
    assert result["total_fired"] == 5000
    assert result["total_acked"] == 5000
    assert result["total_pending"] == 0
    assert (
        elapsed_ms < 300
    ), f"response_time 7d took {elapsed_ms:.1f}ms (target: <300ms)"


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
async def test_channel_stats_7d_under_200ms(db_session: AsyncSession) -> None:
    """PERF-P1-001: channel_stats 7d < 200ms (SQL GROUP BY + COUNT/AVG/MAX)."""
    from app.api.v1.observability import _compute_channel_stats

    base = datetime(2026, 5, 27, 0, 0, 0, tzinfo=timezone.utc)
    await _bulk_insert_channel_logs(db_session, 10000, base=base)

    start = datetime(2026, 5, 27, tzinfo=timezone.utc)
    end = datetime(2026, 6, 3, tzinfo=timezone.utc)

    t0 = time.perf_counter()
    result = await _compute_channel_stats(db_session, start, end, None)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert "channels" in result
    assert "total_sent" in result
    assert result["total_sent"] > 0
    assert (
        elapsed_ms < 200
    ), f"channel_stats 7d took {elapsed_ms:.1f}ms (target: <200ms)"


@pytest.mark.performance
async def test_silence_hit_rate_under_100ms(db_session: AsyncSession) -> None:
    """PERF-P1-001: silence_hit_rate < 100ms (SQL COUNT + GROUP BY)."""
    from app.api.v1.observability import _compute_silence_hit_rate

    base = datetime(2026, 5, 27, 0, 0, 0, tzinfo=timezone.utc)
    fired_n, sil_n = await _bulk_insert_silence_logs(db_session, 3000, base=base)

    start = datetime(2026, 5, 27, tzinfo=timezone.utc)
    end = datetime(2026, 6, 3, tzinfo=timezone.utc)

    t0 = time.perf_counter()
    result = await _compute_silence_hit_rate(db_session, start, end)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert "total_fired" in result
    assert "hit_rate" in result
    assert result["total_fired"] == fired_n
    assert result["total_silenced"] == sil_n
    assert (
        elapsed_ms < 100
    ), f"silence_hit_rate took {elapsed_ms:.1f}ms (target: <100ms)"


@pytest.mark.performance
async def test_am_sync_under_100ms(db_session: AsyncSession) -> None:
    """PERF-P1-001: am_sync 聚合 < 100ms (SQL GROUP BY + AVG)."""
    from app.api.v1.observability import _compute_am_sync

    base = datetime(2026, 5, 27, 0, 0, 0, tzinfo=timezone.utc)
    succ_n, fail_n = await _bulk_insert_am_sync_logs(db_session, 3000, base=base)

    start = datetime(2026, 5, 27, tzinfo=timezone.utc)
    end = datetime(2026, 6, 3, tzinfo=timezone.utc)

    t0 = time.perf_counter()
    result = await _compute_am_sync(db_session, start, end, None)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert "total_success" in result
    assert "by_operation" in result
    assert result["total_success"] == succ_n
    assert result["total_failed"] == fail_n
    assert elapsed_ms < 100, f"am_sync took {elapsed_ms:.1f}ms (target: <100ms)"


@pytest.mark.performance
async def test_lock_stats_under_50ms(db_session: AsyncSession) -> None:
    """v1.36 T3.2: lock_stats 聚合 < 50ms (低数据量, 未改造).

    _compute_lock_stats 对 recent_flushes 有 LIMIT(10), 只返回最近 10 条.
    """
    from app.api.v1.observability import _compute_lock_stats

    base = datetime(2026, 5, 27, 0, 0, 0, tzinfo=timezone.utc)
    await _bulk_insert_lock_logs(db_session, 500, base=base)

    t0 = time.perf_counter()
    result = await _compute_lock_stats(db_session)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert "recent_flushes" in result
    assert "historical_recent" in result
    # LIMIT(10): 只返回最近 10 条 flush 日志
    assert len(result["recent_flushes"]) == 10
    assert elapsed_ms < 50, f"lock_stats took {elapsed_ms:.1f}ms (target: <50ms)"
