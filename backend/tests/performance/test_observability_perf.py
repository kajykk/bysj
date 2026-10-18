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
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import OperationLog

# ===== 计时容差机制 (PERF-P2-002) =====

# 背景: 本文件 8 项基准断言的都是**墙钟耗时**。本机实测 `_compute_response_time`
# 查询本体仅 ~10ms，而阈值 300ms 有 30x 余量；但 backend-coverage 与 e2e /
# contract-test / frontend-coverage 等作业在同一台 runner 上并行抢 CPU/IO，
# 进程被调度出去几百毫秒就会踩线（第三十一批实测 `assert 421.86 < 300`，
# 第三十五批复现一次；两次本机单跑均 passed）。
#
# 处置: **不改阈值**（改阈值会把真实回归一起放过），而是给测量本身加容差——
# 先 warmup 若干次让 SQLite page cache / 解释器 JIT 稳定，再取 best-of-N 的
# **最小值**。最小值对单次调度尖峰免疫，而持续性的慢查询仍会稳定超标。
#
# 为便于确定性自测，`clock` 可注入：闸门用假时钟喂 [warmup=200ms, 100/900/20ms]
# 这类序列，直接断言"取的是最小值且 warmup 被消费"，不依赖真实耗时分布。
#
# 附注: `_compute_*` 全是只读聚合（SELECT + Python 后处理，无写入），重复调用
# 幂等且不改变断言对象，故可安全重复执行。
MEASURE_BEST_OF = 3
MEASURE_WARMUP = 1


async def measure_ms(
    fn: Callable[[], Awaitable[Any]],
    *,
    best_of: int = MEASURE_BEST_OF,
    warmup: int = MEASURE_WARMUP,
    clock: Callable[[], float] | None = None,
) -> tuple[float, Any]:
    """测量 `fn` 的耗时，返回 (最小耗时毫秒, 最后一次调用的返回值).

    先跑 `warmup` 次（结果丢弃，仅用于让缓存/JIT 稳定），再跑 `best_of` 次
    记录耗时，取其中最小值作为断言依据——最贴近"这条查询本身有多快"，
    而不是"这台机器当时有多挤"。

    `clock` 仅供自测注入假时钟；默认用 `time.perf_counter`。用 `None` 哨兵
    而非把 `time.perf_counter` 写进签名默认值，避免默认参数在定义时被求值成
    一个固定函数对象（那样 monkeypatch `time.perf_counter` 不会生效）。
    """
    if clock is None:
        clock = time.perf_counter
    assert best_of >= 1, "best_of 至少为 1，否则无样本可取"
    assert warmup >= 0, "warmup 不能为负"
    result: Any = None
    for _ in range(warmup):
        result = await fn()
    samples: list[float] = []
    for _ in range(best_of):
        t0 = clock()
        result = await fn()
        samples.append((clock() - t0) * 1000)
    return min(samples), result


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



    elapsed_ms, result = await measure_ms(
        lambda: _compute_trend(db_session, start, end, "1h", None, None, "severity")
    )

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

    elapsed_ms, result = await measure_ms(
        lambda: _compute_trend(db_session, start, end, "6h", None, None, "severity")
    )

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

    elapsed_ms, result = await measure_ms(
        lambda: _compute_response_time(db_session, start, end, None)
    )

    assert "response_time" in result
    assert "p99" in result["response_time"]
    assert result["total_fired"] == 5000
    assert result["total_acked"] == 5000
    assert result["total_pending"] == 0
    # PERF-P2-002: 阈值仍是 300ms（不放宽），只是测量改为 warmup + best-of-N 最小值，
    # 以区分"查询本身慢"与"CI runner 被并行作业挤顿"。
    assert (
        elapsed_ms < 300
    ), f"response_time 7d took {elapsed_ms:.1f}ms (target: <300ms)"


# ===== 计时容差机制的自测 (PERF-P2-002 闸门) =====
#
# 这一组不测查询性能，而是钉住 `measure_ms` 的**语义**：断言依据必须是
# best-of-N 的**最小值**（而不是首次/均值/末次），且 warmup 必须被消费掉。
# 用假时钟喂确定性序列，故断言本身不受机器负载影响——正是被测机制要解决的问题。


@pytest.mark.performance
async def test_measure_ms_uses_min_of_best_of_and_consumes_warmup() -> None:
    """闸门：取 best-of-N 最小值；warmup 的耗时不计入样本。

    `measure_ms` 只在 best_of 段调 `clock()`（warmup 段不碰时钟），每段 = clock()
    后减 clock()，故消耗 2 个读数/段。序列只排 3 段样本：
    (0.0→0.1)=100ms、(0.2→1.1)=900ms、(1.2→1.22)=20ms → 取最小 20ms。
    """
    ticks = iter([0.0, 0.1, 0.2, 1.1, 1.2, 1.22])
    calls = {"n": 0}

    async def _fn() -> str:
        calls["n"] += 1
        return f"r{calls['n']}"

    elapsed_ms, result = await measure_ms(_fn, clock=lambda: next(ticks))

    assert calls["n"] == 1 + 3, "warmup(1) + best_of(3) 必须恰好调用 4 次"
    assert elapsed_ms == pytest.approx(20.0), "断言依据必须是三条样本里的最小值 20ms"
    assert result == "r4", "返回最后一次调用的结果"

@pytest.mark.performance
async def test_measure_ms_not_fooled_by_single_spike() -> None:
    """闸门：一次调度尖峰(999ms)不应掩盖真实水平(5ms) —— 这正是 CI flake 的形态。"""
    # 两段：999ms 与 5ms → 取最小 5ms
    ticks = iter([0.0, 0.999, 1.0, 1.005])

    async def _fn() -> None:
        return None

    elapsed_ms, _ = await measure_ms(_fn, best_of=2, warmup=0, clock=lambda: next(ticks))

    assert elapsed_ms == pytest.approx(5.0), "尖峰 999ms 应被最小值过滤，剩 5ms"


@pytest.mark.performance
async def test_measure_ms_threshold_still_catches_real_regression() -> None:
    """闸门：取最小值**不**等于放水——持续性超阈值仍会红。"""
    # 三段都 ~400ms（远超 300ms 阈值）→ 最小值仍 400 → 断言会红
    ticks = iter([0.0, 0.4, 1.0, 1.4, 2.0, 2.4])

    async def _fn() -> None:
        return None

    elapsed_ms, _ = await measure_ms(_fn, clock=lambda: next(ticks))
    assert elapsed_ms == pytest.approx(400.0)
    assert not (elapsed_ms < 300), "真实回归必须仍被判红，机制不得掩盖"


@pytest.mark.performance
async def test_measure_ms_rejects_degenerate_params() -> None:
    """闸门：best_of<1 / warmup<0 直接拒绝（否则无样本或负数等待）。"""

    async def _fn() -> None:
        return None

    with pytest.raises(AssertionError):
        await measure_ms(_fn, best_of=0)
    with pytest.raises(AssertionError):
        await measure_ms(_fn, warmup=-1)


@pytest.mark.performance
def test_perf_file_has_no_bare_wallclock_assertions() -> None:
    """闸门：本文件的耗时断言必须统一走 measure_ms，禁止回退到裸 perf_counter 差值。

    反向钉：任何新增的性能用例若直接 `perf_counter()` 差值与阈值比较，会绕开
    warmup/best-of-N 容差，重新引入 CI 抖动（第三十一/三十五批的 flake 根因）。
    """
    import inspect

    import tests.performance.test_observability_perf as mod

    src = inspect.getsource(mod)
    # 反向钉：禁止出现「perf_counter() 前后相减」的裸墙钟计量模式。这种写法绕开
    # warmup + best-of-N 容差，正是第三十一/三十五批 CI flake 的根因。新用例请走
    # measure_ms。逐行扫描并跳过注释行，避免把说明文字当成代码命中。
    import re

    bare = []
    for line in src.splitlines():
        code = line.split("#", 1)[0]
        if re.search(r"time\.perf_counter\(\)\s*-\s*\w", code):
            bare.append(line.strip())
    assert not bare, (
        f"检测到裸墙钟差值计量：{bare}。请改用 measure_ms 以继承 warmup + "
        "best-of-N 容差"
    )
    # 7 个带阈值的性能用例（`*_under_*`）必须逐个走 measure_ms
    threshold_tests = re.findall(r"(?:async )?def (test_\w*under_\w*)\(", src)
    assert len(threshold_tests) == 7, f"阈值用例数变了: {threshold_tests}"
    for name in threshold_tests:
        body = inspect.getsource(getattr(mod, name))
        assert "await measure_ms(" in body, (
            f"{name} 未走 measure_ms（绕开了 warmup + best-of-N 容差）"
        )


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

    elapsed_ms, result = await measure_ms(
        lambda: _compute_channel_stats(db_session, start, end, None)
    )

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

    elapsed_ms, result = await measure_ms(
        lambda: _compute_silence_hit_rate(db_session, start, end)
    )

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

    elapsed_ms, result = await measure_ms(
        lambda: _compute_am_sync(db_session, start, end, None)
    )

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

    elapsed_ms, result = await measure_ms(lambda: _compute_lock_stats(db_session))

    assert "recent_flushes" in result
    assert "historical_recent" in result
    # LIMIT(10): 只返回最近 10 条 flush 日志
    assert len(result["recent_flushes"]) == 10
    assert elapsed_ms < 50, f"lock_stats took {elapsed_ms:.1f}ms (target: <50ms)"
