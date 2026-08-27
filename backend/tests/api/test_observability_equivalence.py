"""R-C 等价重构红线：observability _compute_* 输出快照一致性测试.

每个用例在确定性种子数据上运行 _compute_*，并与 ``_snapshots/`` 中的基线
JSON 逐字段比对。重构前后基线必须完全一致（diff = 空）。

- 首次/更新基线：``$env:UPDATE_SNAPSHOT="1"; pytest ... -k observability_equivalence``
- 正常验证：直接运行本文件
"""

from __future__ import annotations

import json
import os
import pathlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import OperationLog

SNAPSHOT_DIR = pathlib.Path(__file__).parent / "_snapshots"
UPDATE_SNAPSHOT = os.environ.get("UPDATE_SNAPSHOT") == "1"

_BASE = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
_RANGE_START = datetime(2026, 5, 30, tzinfo=timezone.utc)
_RANGE_END = datetime(2026, 6, 4, tzinfo=timezone.utc)


def _check_snapshot(name: str, value: object) -> None:
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    path = SNAPSHOT_DIR / f"{name}.json"
    if UPDATE_SNAPSHOT:
        path.write_text(json.dumps(value, sort_keys=True, indent=2), encoding="utf-8")
        return
    assert path.exists(), f"缺少基线快照 {path}，请先以 UPDATE_SNAPSHOT=1 生成"
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert value == expected, f"{name} 输出与基线不一致（R-C 等价红线被破坏）"


async def _seed_trend(db: AsyncSession) -> None:
    for i in range(24):
        ts = _BASE + timedelta(hours=i)
        db.add(
            OperationLog(
                action_type="alert_fired" if i % 4 else "alert_resolved",
                target_type="alert",
                detail=json.dumps(
                    {"rule": f"Rule_{i % 3}", "severity": ["P0", "P1", "P2"][i % 3]}
                ),
                created_at=ts,
            )
        )
    await db.flush()


async def _seed_response_time(db: AsyncSession) -> None:
    for i in range(10):
        fired_at = _BASE + timedelta(minutes=i * 30)
        db.add(
            OperationLog(
                action_type="alert_fired",
                target_type="alert",
                detail=json.dumps(
                    {"fingerprint": f"fp-{i}", "severity": ["P0", "P1"][i % 2]}
                ),
                created_at=fired_at,
            )
        )
        if i % 3:  # 2/3 被确认，1/3 pending
            db.add(
                OperationLog(
                    action_type="alert_acknowledged",
                    target_type="alert",
                    detail=json.dumps({"fingerprint": f"fp-{i}"}),
                    created_at=fired_at + timedelta(minutes=2),
                )
            )
    await db.flush()


async def _seed_escalation(db: AsyncSession) -> None:
    for i in range(12):
        ts = _BASE + timedelta(minutes=i * 10)
        sev = ["P0", "P1", "P2"][i % 3]
        rule = f"Rule_{i % 2}"
        db.add(
            OperationLog(
                action_type="alert_fired",
                target_type="alert",
                detail=json.dumps({"rule": rule, "severity": sev}),
                created_at=ts,
            )
        )
        if i % 2 == 0:
            db.add(
                OperationLog(
                    action_type="alert_escalated",
                    target_type="alert",
                    detail=json.dumps(
                        {"rule": rule, "severity": sev, "to_level": "L2", "new_severity": "P1"}
                    ),
                    created_at=ts + timedelta(minutes=1),
                )
            )
    await db.flush()


async def _seed_channel(db: AsyncSession) -> None:
    for i in range(20):
        db.add(
            OperationLog(
                action_type="alert_channel_failed" if i % 7 == 0 else "alert_channel_sent",
                target_type="alert_channel",
                detail=json.dumps(
                    {
                        "channel": ["webhook", "email"][i % 2],
                        "duration_ms": i * 10,
                    }
                ),
                created_at=_BASE + timedelta(minutes=i),
            )
        )
    await db.flush()


async def _seed_silence(db: AsyncSession) -> None:
    for i in range(16):
        ts = _BASE + timedelta(minutes=i)
        db.add(
            OperationLog(
                action_type="alert_fired",
                target_type="alert",
                detail=json.dumps({"severity": ["P0", "P1"][i % 2]}),
                created_at=ts,
            )
        )
        if i % 2:
            db.add(
                OperationLog(
                    action_type="alert_silenced",
                    target_type="alert",
                    detail=json.dumps(
                        {"silence_name": f"sil-{i % 2}", "severity": ["P0", "P1"][i % 2]}
                    ),
                    created_at=ts,
                )
            )
    await db.flush()


async def _seed_am_sync(db: AsyncSession) -> None:
    for i in range(12):
        db.add(
            OperationLog(
                action_type="am_sync_failed" if i % 5 == 0 else "am_sync_success",
                target_type="alert_silence",
                detail=json.dumps(
                    {
                        "operation": ["push_silence", "delete_silence"][i % 2],
                        "duration_ms": i * 5,
                        "error": "timeout" if i % 5 == 0 else None,
                        "am_silence_id": f"am-{i}",
                    }
                ),
                created_at=_BASE + timedelta(minutes=i),
            )
        )
    await db.flush()


async def _seed_lock(db: AsyncSession) -> None:
    for i in range(6):
        db.add(
            OperationLog(
                action_type="dedup_lock_stats",
                target_type="dedup_lock",
                detail=json.dumps(
                    {
                        "acquired": i + 1,
                        "skipped": i,
                        "fallback": 1 if i % 2 else 0,
                        "errors": 0,
                        "instance_id": "inst-1",
                    }
                ),
                created_at=_BASE + timedelta(hours=i),
            )
        )
    await db.flush()


@pytest.mark.asyncio
class TestObservabilityEquivalence:
    async def test_trend_snapshot(self, db_session: AsyncSession):
        from app.api.v1.observability import _compute_trend

        await _seed_trend(db_session)
        result = await _compute_trend(
            db_session, _RANGE_START, _RANGE_END, "1h", None, None, "severity"
        )
        _check_snapshot("trend", result)

    async def test_response_time_snapshot(self, db_session: AsyncSession):
        from app.api.v1.observability import _compute_response_time

        await _seed_response_time(db_session)
        result = await _compute_response_time(db_session, _RANGE_START, _RANGE_END, None)
        _check_snapshot("response_time", result)

    async def test_escalation_snapshot(self, db_session: AsyncSession):
        from app.api.v1.observability import _compute_escalation

        await _seed_escalation(db_session)
        result = await _compute_escalation(db_session, _RANGE_START, _RANGE_END, None)
        _check_snapshot("escalation", result)

    async def test_channel_stats_snapshot(self, db_session: AsyncSession):
        from app.api.v1.observability import _compute_channel_stats

        await _seed_channel(db_session)
        result = await _compute_channel_stats(db_session, _RANGE_START, _RANGE_END, None)
        _check_snapshot("channel_stats", result)

    async def test_silence_hit_rate_snapshot(self, db_session: AsyncSession):
        from app.api.v1.observability import _compute_silence_hit_rate

        await _seed_silence(db_session)
        result = await _compute_silence_hit_rate(db_session, _RANGE_START, _RANGE_END)
        _check_snapshot("silence_hit_rate", result)

    async def test_am_sync_snapshot(self, db_session: AsyncSession):
        from app.api.v1.observability import _compute_am_sync

        await _seed_am_sync(db_session)
        result = await _compute_am_sync(db_session, _RANGE_START, _RANGE_END, None)
        _check_snapshot("am_sync", result)

    async def test_lock_stats_snapshot(self, db_session, monkeypatch):
        """FIX-ORDER-3：内存段注入固定值保证确定性。

        ``_compute_lock_stats`` 的 memory 段来自进程级活体计数器
        （dedup_lock.get_stats()），全量运行时会被先前的 API 测试（告警去重
        路径）污染——单跑为 0 匹配基线、全量必现失配。快照确定性边界应为
        DB 派生部分（historical_recent / recent_flushes，逐字段比对不受影响），
        活体内存统计按固定零值注入。生产代码不动。
        """
        from app.api.v1.observability import aggregate as obs_agg

        zero_mem = {"acquired": 0, "skipped": 0, "fallback": 0, "errors": 0}
        monkeypatch.setattr(
            obs_agg,
            "_fetch_lock_memory_stats",
            lambda: (zero_mem, None),
        )

        from app.api.v1.observability import _compute_lock_stats

        await _seed_lock(db_session)
        result = await _compute_lock_stats(db_session)
        _check_snapshot("lock_stats", result)
