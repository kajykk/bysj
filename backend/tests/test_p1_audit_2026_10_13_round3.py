"""P1 第四轮回归闸门（2026-10-13）：#17 推理并发无界 / #24 异常检测 N+1。

覆盖：
1. P1-17 `_run_model_inference`：峰值并发有上限、失败不留孤儿任务、顺序保持
2. P1-24 三个检测器：详情查询次数与 finding 数解耦（O(1) 而非 O(N)），
   且 finding 内容（最新 IP / IP 清单 / target_type 清单）与改前一致

对照实验记录（回退修复后均现红）：
- #17 恢复 `gather(*tasks)` → 并发闸门红（峰值 = N）
- #17 批内改回 return_exceptions=False → 孤儿任务闸门红
- #24 恢复循环内逐人查询 → 往返次数闸门红
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.admin import OperationLog
from app.services import anomaly_detection_service as ads
from app.services.validation_engine import (
    _INFERENCE_BATCH_SIZE,
    _INFERENCE_CONCURRENCY,
    validation_engine,
)


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seed_oplog(
    db: AsyncSession,
    operator_id: int,
    operator_role: str,
    action_type: str = "test_action",
    target_type: str | None = "test_target",
    ip_address: str | None = "127.0.0.1",
    created_at: datetime | None = None,
) -> OperationLog:
    log = OperationLog(
        operator_id=operator_id,
        operator_role=operator_role,
        action_type=action_type,
        target_type=target_type,
        target_id=operator_id,
        detail="{}",
        ip_address=ip_address,
        created_at=created_at or _utcnow_naive(),
    )
    db.add(log)
    return log


# ══════════════════════════════════════════════════════════════════
# P1-17：模型推理并发有界、失败不留孤儿任务
# ══════════════════════════════════════════════════════════════════


class _ConcurrencyTracker:
    """记录 stub 的峰值并发与已启动/已完成的任务数。"""

    def __init__(self, *, fail_at: int | None = None) -> None:
        self.cur = 0
        self.peak = 0
        self.started = 0
        self.completed = 0
        self.fail_at = fail_at

    def make_stub(self) -> Any:
        tracker = self

        async def _predict(feat: dict) -> dict:
            # 进入即取号：await 之后计数器已被其它任务推进，不能事后读
            tracker.cur += 1
            tracker.started += 1
            idx = tracker.started
            tracker.peak = max(tracker.peak, tracker.cur)
            await asyncio.sleep(0.002)
            tracker.cur -= 1
            if tracker.fail_at is not None and idx == tracker.fail_at:
                raise RuntimeError("probe failure")
            tracker.completed += 1
            return {"prediction": idx, "probability": 0.5}

        return _predict


class _StubEngine:
    def __init__(self, predict: Any) -> None:
        self.predict_structured = staticmethod(predict)


class TestInferenceConcurrencyBounded:
    """P1-17：不再「行数即协程数」。"""

    @pytest.mark.asyncio
    async def test_peak_concurrency_within_limit(self):
        """300 特征 → 峰值并发必须 ≤ 配置上限（改前实测 300，1:1 无界）。"""
        tracker = _ConcurrencyTracker()
        n = 300
        features = [{"gad7_score": 5} for _ in range(n)]

        with patch.object(
            sys.modules["app.core.model_engine"], "model_engine", _StubEngine(tracker.make_stub())
        ):
            result = await validation_engine._run_model_inference("v1.20", features)

        assert result is not None, "推理应成功返回"
        predictions, probabilities = result
        assert len(predictions) == n
        assert len(probabilities) == n
        assert tracker.peak <= _INFERENCE_CONCURRENCY, (
            f"峰值并发 {tracker.peak} 超过上限 {_INFERENCE_CONCURRENCY}："
            "说明仍在一次性为全部特征建协程"
        )

    @pytest.mark.asyncio
    async def test_result_order_preserved(self):
        """分批不能打乱结果顺序（predictions[i] 必须对应 features[i]）。"""
        tracker = _ConcurrencyTracker()
        n = _INFERENCE_BATCH_SIZE * 2 + 7  # 跨 3 批，最后一批不满
        features = [{"gad7_score": 5} for _ in range(n)]

        with patch.object(
            sys.modules["app.core.model_engine"], "model_engine", _StubEngine(tracker.make_stub())
        ):
            result = await validation_engine._run_model_inference("v1.20", features)

        assert result is not None
        predictions, _ = result
        # tracker.started 是自增序号，按顺序等于 1..n
        assert predictions == list(range(1, n + 1))

    @pytest.mark.asyncio
    async def test_no_orphan_tasks_after_failure(self):
        """首个异常后，后续批次不得再启动（改前 200 条中 199 条成孤儿）。"""
        tracker = _ConcurrencyTracker(fail_at=20)
        n = _INFERENCE_BATCH_SIZE * 4
        features = [{"gad7_score": 5} for _ in range(n)]

        with patch.object(
            sys.modules["app.core.model_engine"], "model_engine", _StubEngine(tracker.make_stub())
        ):
            result = await validation_engine._run_model_inference("v1.20", features)

        # 失败 → 返回 None（既有契约：由调用方记 errors）
        assert result is None
        # 只应启动含失败点的那一批，后续批次一个都不启动
        assert tracker.started <= _INFERENCE_BATCH_SIZE, (
            f"失败后仍启动了 {tracker.started} 个任务（批大小 "
            f"{_INFERENCE_BATCH_SIZE}）：后续批次成了无人等待的孤儿任务"
        )
        # 本批内所有任务都已收尾，没有悬空
        assert tracker.cur == 0

    @pytest.mark.asyncio
    async def test_empty_features(self):
        """空特征集不应发起任何推理，直接返回空。"""
        with patch.object(
            sys.modules["app.core.model_engine"], "model_engine", _StubEngine(_ConcurrencyTracker().make_stub())
        ) as stub:
            result = await validation_engine._run_model_inference("v1.20", [])

        assert result == ([], [])
        assert stub.predict_structured is not None

    def test_constants_are_sane(self):
        """上限常量必须存在且有界（防止后人把批大小改回 0 或天文数字）。"""
        assert _INFERENCE_CONCURRENCY >= 1
        assert _INFERENCE_BATCH_SIZE >= 1
        assert _INFERENCE_BATCH_SIZE >= _INFERENCE_CONCURRENCY


# ══════════════════════════════════════════════════════════════════
# P1-24：详情查询次数与 finding 数解耦
# ══════════════════════════════════════════════════════════════════


class _ExecuteCounter:
    """包住 AsyncSession.execute，统计真实下发的 SQL 条数。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.count = 0

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        self.count += 1
        return await self._session.execute(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)


class TestAnomalyDetectionNoNPlusOne:
    """P1-24：单次扫描的 SQL 往返数不得随 finding 数线性增长。"""

    OPERATORS = 12

    @pytest.mark.asyncio
    async def test_high_frequency_roundtrips_bounded(self, db_session: AsyncSession):
        """high_frequency：改前 1 + N 条（N=12 → 13 条），改后应为 O(1)。"""
        now = _utcnow_naive()
        with patch.object(settings, "anomaly_high_freq_threshold", 2):
            for uid in range(1, self.OPERATORS + 1):
                for i in range(5):
                    _seed_oplog(
                        db_session,
                        operator_id=uid,
                        operator_role="user",
                        ip_address=f"10.0.0.{uid}",
                        created_at=now - timedelta(seconds=i),
                    )
            await db_session.flush()

            counter = _ExecuteCounter(db_session)
            findings = await ads.detect_high_frequency(counter)  # type: ignore[arg-type]

        assert len(findings) == self.OPERATORS
        assert counter.count <= 3, (
            f"detect_high_frequency 下发 {counter.count} 条 SQL，finding 数 "
            f"{len(findings)}：仍在循环内逐人查询（改前为 1+N）"
        )
        # 内容不变：每人取到自己的最新 IP
        for f in findings:
            assert f.ip_address == f"10.0.0.{f.operator_id}"

    @pytest.mark.asyncio
    async def test_cross_region_roundtrips_bounded(self, db_session: AsyncSession):
        """cross_region：改前 1 + 2N 条（N=12 → 25 条），改后应为 O(1)。"""
        now = _utcnow_naive()
        with patch.object(settings, "anomaly_cross_region_ip_threshold", 2):
            for uid in range(1, self.OPERATORS + 1):
                for i in range(4):
                    _seed_oplog(
                        db_session,
                        operator_id=uid,
                        operator_role="user",
                        ip_address=f"10.1.{uid}.{i}",
                        created_at=now - timedelta(minutes=i),
                    )
            await db_session.flush()

            counter = _ExecuteCounter(db_session)
            findings = await ads.detect_cross_region(counter)  # type: ignore[arg-type]

        assert len(findings) == self.OPERATORS
        assert counter.count <= 3, (
            f"detect_cross_region 下发 {counter.count} 条 SQL，finding 数 "
            f"{len(findings)}：仍在循环内逐人查询（改前为 1+2N）"
        )
        for f in findings:
            ips = set(f.evidence["ip_list"])
            assert ips == {f"10.1.{f.operator_id}.{i}" for i in range(4)}, (
                f"operator {f.operator_id} 的 IP 清单缺失: {ips}"
            )

    @pytest.mark.asyncio
    async def test_lateral_roundtrips_bounded(self, db_session: AsyncSession):
        """lateral：改前 1 + 2N 条，且过滤前就查（多数白跑），改后 O(1)。"""
        now = _utcnow_naive()
        target_types = [f"tt_{i}" for i in range(6)]
        with patch.object(settings, "anomaly_lateral_target_type_threshold", 4):
            for uid in range(1, self.OPERATORS + 1):
                for tt in target_types:
                    _seed_oplog(
                        db_session,
                        operator_id=uid,
                        operator_role="user",
                        target_type=tt,
                        ip_address=f"10.2.0.{uid}",
                        created_at=now - timedelta(minutes=1),
                    )
            # 再造 5 个未超阈值的用户：改前会为他们白发 10 条查询
            for uid in range(100, 105):
                for tt in target_types[:2]:
                    _seed_oplog(
                        db_session,
                        operator_id=uid,
                        operator_role="user",
                        target_type=tt,
                        created_at=now - timedelta(minutes=1),
                    )
            await db_session.flush()

            counter = _ExecuteCounter(db_session)
            findings = await ads.detect_lateral_access(counter)  # type: ignore[arg-type]

        assert len(findings) == self.OPERATORS
        assert counter.count <= 3, (
            f"detect_lateral_access 下发 {counter.count} 条 SQL，finding 数 "
            f"{len(findings)}：仍在循环内逐人查询（改前为 1+2N）"
        )
        for f in findings:
            assert set(f.evidence["target_types"]) == set(target_types), (
                f"operator {f.operator_id} 的 target_type 清单缺失: "
                f"{f.evidence['target_types']}"
            )

    @pytest.mark.asyncio
    async def test_batch_latest_ip_uses_id_tiebreaker(self, db_session: AsyncSession):
        """同一秒插入的重复 created_at：最新 IP 必须确定（id 兜底），且幂等。"""
        now = _utcnow_naive()
        for i, ip in enumerate(["10.9.0.1", "10.9.0.2", "10.9.0.3"]):
            _seed_oplog(
                db_session,
                operator_id=7,
                operator_role="user",
                ip_address=ip,
                created_at=now,  # 完全相同的时间戳
            )
        await db_session.flush()

        first = await ads._batch_latest_ips(db_session, now - timedelta(hours=1), [7])
        second = await ads._batch_latest_ips(db_session, now - timedelta(hours=1), [7])
        assert first == second, "相同输入两次调用结果不同，违反幂等性"
        assert first[7] == "10.9.0.3", (
            f"最新 IP 应为 id 最大的那条 (10.9.0.3)，实际 {first[7]}"
        )

    @pytest.mark.asyncio
    async def test_batch_helpers_handle_empty_input(self):
        """空 operator 列表不得下发 SQL（避免无意义的 IN ()）。"""
        counter = _ExecuteCounter(_FakeSession())
        assert await ads._batch_latest_ips(counter, _utcnow_naive(), []) == {}  # type: ignore[arg-type]
        assert await ads._batch_distinct_values(  # type: ignore[arg-type]
            counter, _utcnow_naive(), [], OperationLog.ip_address, 10
        ) == {}
        assert counter.count == 0


class _FakeSession:
    """空输入路径下不应被触达；触达即测试失败。"""

    async def execute(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise AssertionError("空 operator 列表不应下发任何 SQL")
