"""T-COV-CANARY: CanaryManager 单元测试.

覆盖 app/services/canary_manager.py 的所有公开方法和关键私有方法.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring import CanaryRecord, CanaryStatus
from app.services.canary_manager import (
    CanaryManager,
    RollbackThresholds,
    TrafficDecision,
)
from app.services.canary_manager import canary_manager as global_canary_manager

# DEFAULT_TRAFFIC_PERCENTAGES 是 CanaryManager 的类属性, 通过类访问
DEFAULT_TRAFFIC_PERCENTAGES = CanaryManager.DEFAULT_TRAFFIC_PERCENTAGES


def _naive_utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _default_thresholds() -> dict:
    return {
        "max_fallback_rate": 0.05,
        "max_drift_alerts_per_hour": 10,
        "max_avg_latency_ms": 500.0,
    }


@pytest.fixture
def canary_manager() -> CanaryManager:
    return CanaryManager()


@pytest.fixture(autouse=True)
def mock_observability_collector(monkeypatch):
    """Mock observability_collector 避免 start_canary / rollback_canary 写真实记录."""
    mock = MagicMock()
    mock.record_model_success = MagicMock()
    mock.record_fallback = MagicMock()
    monkeypatch.setattr(
        "app.services.canary_manager.observability_collector",
        mock,
    )
    return mock


@pytest.fixture
async def seeded_running_canary(db_session: AsyncSession) -> CanaryRecord:
    canary = CanaryRecord(
        version="v1.5.0-running",
        traffic_percent=50,
        status=CanaryStatus.RUNNING,
        auto_rollback_thresholds=_default_thresholds(),
        triggered_by=None,
        started_at=_naive_utcnow(),
    )
    db_session.add(canary)
    await db_session.flush()
    return canary


@pytest.fixture
async def seeded_paused_canary(db_session: AsyncSession) -> CanaryRecord:
    canary = CanaryRecord(
        version="v1.5.0-paused",
        traffic_percent=25,
        status=CanaryStatus.PAUSED,
        auto_rollback_thresholds=_default_thresholds(),
        triggered_by=None,
        started_at=_naive_utcnow(),
    )
    db_session.add(canary)
    await db_session.flush()
    return canary


@pytest.fixture
async def seeded_completed_canary(db_session: AsyncSession) -> CanaryRecord:
    canary = CanaryRecord(
        version="v1.4.0-completed",
        traffic_percent=100,
        status=CanaryStatus.COMPLETED,
        auto_rollback_thresholds=_default_thresholds(),
        triggered_by=None,
        started_at=_naive_utcnow() - timedelta(days=1),
        ended_at=_naive_utcnow(),
    )
    db_session.add(canary)
    await db_session.flush()
    return canary


@pytest.fixture
async def seeded_rolled_back_canary(db_session: AsyncSession) -> CanaryRecord:
    canary = CanaryRecord(
        version="v1.4.0-rolled-back",
        traffic_percent=10,
        status=CanaryStatus.ROLLED_BACK,
        auto_rollback_thresholds=_default_thresholds(),
        triggered_by=None,
        started_at=_naive_utcnow() - timedelta(days=2),
        ended_at=_naive_utcnow() - timedelta(days=1),
        rollback_reason="manual_rollback",
    )
    db_session.add(canary)
    await db_session.flush()
    return canary


class TestHashUserId:
    """_hash_user_id 私有方法测试."""

    def test_hash_consistency(self, canary_manager: CanaryManager) -> None:
        h1 = canary_manager._hash_user_id(12345)
        h2 = canary_manager._hash_user_id(12345)
        assert h1 == h2

    def test_hash_range(self, canary_manager: CanaryManager) -> None:
        for uid in range(-100, 100):
            h = canary_manager._hash_user_id(uid)
            assert 0 <= h < 100

    def test_hash_with_string_user_id(self, canary_manager: CanaryManager) -> None:
        h_int = canary_manager._hash_user_id(12345)
        h_str = canary_manager._hash_user_id("12345")
        assert h_int == h_str
        assert 0 <= h_str < 100

    def test_hash_with_negative_user_id(self, canary_manager: CanaryManager) -> None:
        h = canary_manager._hash_user_id(-1)
        assert 0 <= h < 100

    def test_hash_distribution_uniform(self, canary_manager: CanaryManager) -> None:
        hashes = [canary_manager._hash_user_id(i) for i in range(10000)]
        avg = len(hashes) / 100
        bucket_counts = [sum(1 for h in hashes if h == i) for i in range(100)]
        assert all(abs(c - avg) < avg * 0.5 for c in bucket_counts)


class TestIsCanaryUser:
    """is_canary_user 公开方法测试."""

    def test_zero_percent_returns_false(self, canary_manager: CanaryManager) -> None:
        assert canary_manager.is_canary_user(12345, 0) is False

    def test_negative_percent_returns_false(
        self, canary_manager: CanaryManager
    ) -> None:
        assert canary_manager.is_canary_user(12345, -10) is False

    def test_hundred_percent_returns_true(self, canary_manager: CanaryManager) -> None:
        assert canary_manager.is_canary_user(12345, 100) is True

    def test_over_hundred_percent_returns_true(
        self, canary_manager: CanaryManager
    ) -> None:
        assert canary_manager.is_canary_user(12345, 200) is True

    def test_fifty_percent_distribution(self, canary_manager: CanaryManager) -> None:
        canary_count = sum(
            1 for i in range(1000) if canary_manager.is_canary_user(i, 50)
        )
        assert 400 < canary_count < 600

    def test_one_percent_distribution(self, canary_manager: CanaryManager) -> None:
        canary_count = sum(
            1 for i in range(10000) if canary_manager.is_canary_user(i, 1)
        )
        assert 50 < canary_count < 200

    def test_ninety_nine_percent_distribution(
        self, canary_manager: CanaryManager
    ) -> None:
        canary_count = sum(
            1 for i in range(10000) if canary_manager.is_canary_user(i, 99)
        )
        assert 9800 < canary_count < 10000

    def test_string_user_id_consistent_with_int(
        self, canary_manager: CanaryManager
    ) -> None:
        for uid_int in [123, 456, 789]:
            assert canary_manager.is_canary_user(
                str(uid_int), 50
            ) == canary_manager.is_canary_user(uid_int, 50)

    def test_negative_user_id_returns_bool(self, canary_manager: CanaryManager) -> None:
        result = canary_manager.is_canary_user(-100, 50)
        assert isinstance(result, bool)

    def test_stable_allocation(self, canary_manager: CanaryManager) -> None:
        r1 = canary_manager.is_canary_user(99999, 25)
        r2 = canary_manager.is_canary_user(99999, 25)
        assert r1 == r2


class TestGetActiveCanary:
    """get_active_canary 异步方法测试."""

    async def test_no_running_canary_returns_none(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
    ) -> None:
        result = await canary_manager.get_active_canary(db_session)
        assert result is None

    async def test_returns_running_canary(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_running_canary: CanaryRecord,
    ) -> None:
        result = await canary_manager.get_active_canary(db_session)
        assert result is not None
        assert result.id == seeded_running_canary.id
        assert result.version == "v1.5.0-running"
        assert result.status == CanaryStatus.RUNNING

    async def test_returns_latest_by_started_at(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
    ) -> None:
        """多条 RUNNING 时 (数据完整性违规场景) scalar_one_or_none 抛 MultipleResultsFound.

        注: 正常情况下 start_canary 会阻止多个 RUNNING 同时存在, 此测试验证
        当出现数据完整性违规时, get_active_canary 不会静默返回错误记录.
        """
        from sqlalchemy.exc import MultipleResultsFound

        old_time = _naive_utcnow() - timedelta(hours=2)
        new_time = _naive_utcnow()
        old_canary = CanaryRecord(
            version="v1.4.0-old",
            traffic_percent=10,
            status=CanaryStatus.RUNNING,
            started_at=old_time,
        )
        new_canary = CanaryRecord(
            version="v1.5.0-new",
            traffic_percent=20,
            status=CanaryStatus.RUNNING,
            started_at=new_time,
        )
        db_session.add_all([old_canary, new_canary])
        await db_session.flush()
        # 多条 RUNNING 时, scalar_one_or_none 抛 MultipleResultsFound
        # (源码使用 scalar_one_or_none 而非 first, 强制要求数据完整性)
        with pytest.raises(MultipleResultsFound):
            await canary_manager.get_active_canary(db_session)

    async def test_returns_latest_single_running(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
    ) -> None:
        """单条 RUNNING 时返回该记录 (按 started_at desc 排序后取唯一一条)."""
        new_time = _naive_utcnow()
        new_canary = CanaryRecord(
            version="v1.5.0-new",
            traffic_percent=20,
            status=CanaryStatus.RUNNING,
            started_at=new_time,
        )
        db_session.add(new_canary)
        await db_session.flush()
        result = await canary_manager.get_active_canary(db_session)
        assert result is not None
        assert result.version == "v1.5.0-new"

    async def test_ignores_non_running_statuses(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_paused_canary: CanaryRecord,
        seeded_completed_canary: CanaryRecord,
        seeded_rolled_back_canary: CanaryRecord,
    ) -> None:
        result = await canary_manager.get_active_canary(db_session)
        assert result is None


class TestDecideVersion:
    """decide_version 异步方法测试."""

    async def test_no_active_canary(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
    ) -> None:
        decision = await canary_manager.decide_version(db_session, 12345, "v1.4.0")
        assert isinstance(decision, TrafficDecision)
        assert decision.use_canary is False
        assert decision.canary_version is None
        assert decision.stable_version == "v1.4.0"
        assert decision.reason == "no_active_canary"

    async def test_user_hit_canary(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_running_canary: CanaryRecord,
    ) -> None:
        target_user = None
        for uid in range(10000):
            if canary_manager._hash_user_id(uid) < 50:
                target_user = uid
                break
        assert target_user is not None
        decision = await canary_manager.decide_version(
            db_session, target_user, "v1.4.0"
        )
        assert decision.use_canary is True
        assert decision.canary_version == "v1.5.0-running"
        assert decision.stable_version == "v1.4.0"
        assert "canary_traffic_50%" in decision.reason

    async def test_user_miss_canary(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_running_canary: CanaryRecord,
    ) -> None:
        target_user = None
        for uid in range(10000):
            if canary_manager._hash_user_id(uid) >= 50:
                target_user = uid
                break
        assert target_user is not None
        decision = await canary_manager.decide_version(
            db_session, target_user, "v1.4.0"
        )
        assert decision.use_canary is False
        assert decision.canary_version == "v1.5.0-running"
        assert decision.stable_version == "v1.4.0"
        assert decision.reason == "stable_traffic"


class TestStartCanary:
    """start_canary 异步方法测试."""

    async def test_start_canary_success(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        mock_observability_collector,
    ) -> None:
        canary = await canary_manager.start_canary(
            db_session, version="v2.0.0", traffic_percent=5, triggered_by=1
        )
        assert canary.id is not None
        assert canary.version == "v2.0.0"
        assert canary.traffic_percent == 5
        assert canary.status == CanaryStatus.RUNNING
        assert canary.triggered_by == 1
        assert canary.started_at is not None
        assert canary.auto_rollback_thresholds["max_fallback_rate"] == 0.05
        assert canary.auto_rollback_thresholds["max_drift_alerts_per_hour"] == 10
        assert canary.auto_rollback_thresholds["max_avg_latency_ms"] == 500.0
        mock_observability_collector.record_model_success.assert_called_once()
        call_kwargs = mock_observability_collector.record_model_success.call_args.kwargs
        assert call_kwargs["model_version"] == "v2.0.0"
        assert call_kwargs["user_id"] == 1
        assert call_kwargs["response_summary"]["event"] == "canary_started"
        assert call_kwargs["response_summary"]["traffic_percent"] == 5

    async def test_start_canary_already_running_raises(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_running_canary: CanaryRecord,
    ) -> None:
        with pytest.raises(ValueError, match="Canary already running"):
            await canary_manager.start_canary(db_session, version="v2.0.0")

    async def test_custom_thresholds_merge(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
    ) -> None:
        canary = await canary_manager.start_canary(
            db_session,
            version="v2.0.0",
            traffic_percent=1,
            thresholds={"max_fallback_rate": 0.10, "max_drift_alerts_per_hour": 20},
        )
        assert canary.auto_rollback_thresholds["max_fallback_rate"] == 0.10
        assert canary.auto_rollback_thresholds["max_drift_alerts_per_hour"] == 20
        assert canary.auto_rollback_thresholds["max_avg_latency_ms"] == 500.0

    async def test_started_at_is_naive_datetime(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
    ) -> None:
        canary = await canary_manager.start_canary(
            db_session, version="v2.0.0", traffic_percent=1
        )
        assert canary.started_at is not None
        assert canary.started_at.tzinfo is None

    async def test_default_traffic_percent(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
    ) -> None:
        canary = await canary_manager.start_canary(db_session, version="v2.0.0")
        assert canary.traffic_percent == 1

    async def test_can_start_when_paused_exists(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_paused_canary: CanaryRecord,
    ) -> None:
        canary = await canary_manager.start_canary(db_session, version="v2.0.0")
        assert canary.status == CanaryStatus.RUNNING


class TestUpdateTrafficPercent:
    """update_traffic_percent 异步方法测试."""

    async def test_canary_not_found_raises(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
    ) -> None:
        with pytest.raises(ValueError, match="Canary 99999 not found"):
            await canary_manager.update_traffic_percent(db_session, 99999, 50)

    async def test_running_canary_update(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_running_canary: CanaryRecord,
    ) -> None:
        updated = await canary_manager.update_traffic_percent(
            db_session, seeded_running_canary.id, 80
        )
        assert updated.traffic_percent == 80
        assert updated.status == CanaryStatus.RUNNING

    async def test_paused_canary_update(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_paused_canary: CanaryRecord,
    ) -> None:
        updated = await canary_manager.update_traffic_percent(
            db_session, seeded_paused_canary.id, 60
        )
        assert updated.traffic_percent == 60
        assert updated.status == CanaryStatus.PAUSED

    async def test_completed_canary_raises(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_completed_canary: CanaryRecord,
    ) -> None:
        with pytest.raises(
            ValueError, match="Cannot update traffic for canary in status"
        ):
            await canary_manager.update_traffic_percent(
                db_session, seeded_completed_canary.id, 50
            )

    async def test_rolled_back_canary_raises(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_rolled_back_canary: CanaryRecord,
    ) -> None:
        with pytest.raises(
            ValueError, match="Cannot update traffic for canary in status"
        ):
            await canary_manager.update_traffic_percent(
                db_session, seeded_rolled_back_canary.id, 50
            )


class TestPauseCanary:
    """pause_canary 异步方法测试."""

    async def test_canary_not_found_raises(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
    ) -> None:
        with pytest.raises(ValueError, match="Canary 99999 not found"):
            await canary_manager.pause_canary(db_session, 99999)

    async def test_running_to_paused(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_running_canary: CanaryRecord,
    ) -> None:
        paused = await canary_manager.pause_canary(db_session, seeded_running_canary.id)
        assert paused.status == CanaryStatus.PAUSED
        assert paused.id == seeded_running_canary.id

    async def test_paused_canary_raises(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_paused_canary: CanaryRecord,
    ) -> None:
        with pytest.raises(ValueError, match="Cannot pause canary in status"):
            await canary_manager.pause_canary(db_session, seeded_paused_canary.id)

    async def test_completed_canary_raises(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_completed_canary: CanaryRecord,
    ) -> None:
        with pytest.raises(ValueError, match="Cannot pause canary in status"):
            await canary_manager.pause_canary(db_session, seeded_completed_canary.id)


class TestResumeCanary:
    """resume_canary 异步方法测试."""

    async def test_canary_not_found_raises(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
    ) -> None:
        with pytest.raises(ValueError, match="Canary 99999 not found"):
            await canary_manager.resume_canary(db_session, 99999)

    async def test_paused_to_running(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_paused_canary: CanaryRecord,
    ) -> None:
        resumed = await canary_manager.resume_canary(
            db_session, seeded_paused_canary.id
        )
        assert resumed.status == CanaryStatus.RUNNING
        assert resumed.id == seeded_paused_canary.id

    async def test_running_canary_raises(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_running_canary: CanaryRecord,
    ) -> None:
        with pytest.raises(ValueError, match="Cannot resume canary in status"):
            await canary_manager.resume_canary(db_session, seeded_running_canary.id)

    async def test_completed_canary_raises(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_completed_canary: CanaryRecord,
    ) -> None:
        with pytest.raises(ValueError, match="Cannot resume canary in status"):
            await canary_manager.resume_canary(db_session, seeded_completed_canary.id)


class TestRollbackCanary:
    """rollback_canary 异步方法测试."""

    async def test_canary_not_found_raises(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
    ) -> None:
        with pytest.raises(ValueError, match="Canary 99999 not found"):
            await canary_manager.rollback_canary(db_session, 99999, reason="test")

    async def test_running_canary_rollback(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_running_canary: CanaryRecord,
        mock_observability_collector,
    ) -> None:
        rolled_back = await canary_manager.rollback_canary(
            db_session, seeded_running_canary.id, reason="metrics_exceeded"
        )
        assert rolled_back.status == CanaryStatus.ROLLED_BACK
        assert rolled_back.rollback_reason == "metrics_exceeded"
        assert rolled_back.ended_at is not None
        assert rolled_back.ended_at.tzinfo is None

    async def test_paused_canary_rollback(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_paused_canary: CanaryRecord,
        mock_observability_collector,
    ) -> None:
        rolled_back = await canary_manager.rollback_canary(
            db_session, seeded_paused_canary.id, reason="manual"
        )
        assert rolled_back.status == CanaryStatus.ROLLED_BACK
        assert rolled_back.rollback_reason == "manual"

    async def test_ended_at_and_rollback_reason_set(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_running_canary: CanaryRecord,
    ) -> None:
        rolled_back = await canary_manager.rollback_canary(
            db_session, seeded_running_canary.id, reason="latency_too_high"
        )
        assert rolled_back.ended_at is not None
        assert rolled_back.rollback_reason == "latency_too_high"
        now_naive = _naive_utcnow()
        assert (now_naive - rolled_back.ended_at).total_seconds() < 5

    async def test_record_fallback_called(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_running_canary: CanaryRecord,
        mock_observability_collector,
    ) -> None:
        await canary_manager.rollback_canary(
            db_session, seeded_running_canary.id, reason="auto_rollback_triggered"
        )
        mock_observability_collector.record_fallback.assert_called_once()
        call_kwargs = mock_observability_collector.record_fallback.call_args.kwargs
        assert "canary_rollback: auto_rollback_triggered" in call_kwargs["reason"]
        assert call_kwargs["model_version"] == "v1.5.0-running"
        assert call_kwargs["response_summary"]["canary_id"] == seeded_running_canary.id
        assert (
            call_kwargs["response_summary"]["rollback_reason"]
            == "auto_rollback_triggered"
        )

    async def test_completed_canary_raises(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_completed_canary: CanaryRecord,
    ) -> None:
        with pytest.raises(ValueError, match="Cannot rollback canary in status"):
            await canary_manager.rollback_canary(
                db_session, seeded_completed_canary.id, reason="test"
            )

    async def test_rolled_back_canary_raises(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_rolled_back_canary: CanaryRecord,
    ) -> None:
        with pytest.raises(ValueError, match="Cannot rollback canary in status"):
            await canary_manager.rollback_canary(
                db_session, seeded_rolled_back_canary.id, reason="test"
            )


class TestCompleteCanary:
    """complete_canary 异步方法测试."""

    async def test_canary_not_found_raises(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
    ) -> None:
        with pytest.raises(ValueError, match="Canary 99999 not found"):
            await canary_manager.complete_canary(db_session, 99999)

    async def test_running_to_completed(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_running_canary: CanaryRecord,
    ) -> None:
        completed = await canary_manager.complete_canary(
            db_session, seeded_running_canary.id
        )
        assert completed.status == CanaryStatus.COMPLETED
        assert completed.ended_at is not None
        assert completed.ended_at.tzinfo is None
        assert completed.id == seeded_running_canary.id

    async def test_paused_canary_raises(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_paused_canary: CanaryRecord,
    ) -> None:
        with pytest.raises(ValueError, match="Cannot complete canary in status"):
            await canary_manager.complete_canary(db_session, seeded_paused_canary.id)

    async def test_completed_canary_raises(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_completed_canary: CanaryRecord,
    ) -> None:
        with pytest.raises(ValueError, match="Cannot complete canary in status"):
            await canary_manager.complete_canary(db_session, seeded_completed_canary.id)

    async def test_rolled_back_canary_raises(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_rolled_back_canary: CanaryRecord,
    ) -> None:
        with pytest.raises(ValueError, match="Cannot complete canary in status"):
            await canary_manager.complete_canary(
                db_session, seeded_rolled_back_canary.id
            )


class TestCheckAutoRollback:
    """check_auto_rollback 异步方法测试."""

    async def test_db_session_none_direct_evaluate(
        self,
        canary_manager: CanaryManager,
    ) -> None:
        should_rollback, reason = await canary_manager.check_auto_rollback(
            None, 1, {"fallback_rate": 0.10}
        )
        assert should_rollback is True
        assert "fallback_rate" in reason
        assert "exceeds threshold" in reason

    async def test_db_session_none_within_thresholds(
        self,
        canary_manager: CanaryManager,
    ) -> None:
        should_rollback, reason = await canary_manager.check_auto_rollback(
            None, 1, {"fallback_rate": 0.01}
        )
        assert should_rollback is False
        assert reason == "within_thresholds"

    async def test_canary_not_found_returns_not_running(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
    ) -> None:
        should_rollback, reason = await canary_manager.check_auto_rollback(
            db_session, 99999, {"fallback_rate": 0.50}
        )
        assert should_rollback is False
        assert reason == "canary_not_running"

    async def test_canary_status_not_running(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_paused_canary: CanaryRecord,
    ) -> None:
        should_rollback, reason = await canary_manager.check_auto_rollback(
            db_session, seeded_paused_canary.id, {"fallback_rate": 0.50}
        )
        assert should_rollback is False
        assert reason == "canary_not_running"

    async def test_metrics_within_thresholds(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_running_canary: CanaryRecord,
    ) -> None:
        should_rollback, reason = await canary_manager.check_auto_rollback(
            db_session,
            seeded_running_canary.id,
            {
                "fallback_rate": 0.01,
                "drift_alerts_per_hour": 2,
                "avg_latency_ms": 100.0,
            },
        )
        assert should_rollback is False
        assert reason == "within_thresholds"

    async def test_metrics_exceed_thresholds(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
        seeded_running_canary: CanaryRecord,
    ) -> None:
        should_rollback, reason = await canary_manager.check_auto_rollback(
            db_session,
            seeded_running_canary.id,
            {"fallback_rate": 0.50},
        )
        assert should_rollback is True
        assert "fallback_rate" in reason

    async def test_uses_canary_thresholds(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
    ) -> None:
        canary = CanaryRecord(
            version="v1.5.0-custom-threshold",
            traffic_percent=50,
            status=CanaryStatus.RUNNING,
            auto_rollback_thresholds={
                "max_fallback_rate": 0.20,
                "max_drift_alerts_per_hour": 50,
                "max_avg_latency_ms": 1000.0,
            },
            started_at=_naive_utcnow(),
        )
        db_session.add(canary)
        await db_session.flush()
        should_rollback, reason = await canary_manager.check_auto_rollback(
            db_session, canary.id, {"fallback_rate": 0.10}
        )
        assert should_rollback is False
        assert reason == "within_thresholds"

    async def test_canary_thresholds_none_uses_empty_dict(
        self,
        canary_manager: CanaryManager,
        db_session: AsyncSession,
    ) -> None:
        canary = CanaryRecord(
            version="v1.5.0-no-thresholds",
            traffic_percent=10,
            status=CanaryStatus.RUNNING,
            auto_rollback_thresholds=None,
            started_at=_naive_utcnow(),
        )
        db_session.add(canary)
        await db_session.flush()
        should_rollback, reason = await canary_manager.check_auto_rollback(
            db_session, canary.id, {"fallback_rate": 0.10}
        )
        assert should_rollback is True
        assert "fallback_rate" in reason


class TestEvaluateRollbackMetrics:
    """_evaluate_rollback_metrics 私有方法测试."""

    def test_fallback_rate_exceeds(self, canary_manager: CanaryManager) -> None:
        should, reason = canary_manager._evaluate_rollback_metrics(
            {"max_fallback_rate": 0.05}, {"fallback_rate": 0.10}
        )
        assert should is True
        assert "fallback_rate" in reason
        assert "exceeds threshold" in reason
        assert "10.00%" in reason
        assert "5.00%" in reason

    def test_fallback_rate_within(self, canary_manager: CanaryManager) -> None:
        should, reason = canary_manager._evaluate_rollback_metrics(
            {"max_fallback_rate": 0.05}, {"fallback_rate": 0.03}
        )
        assert should is False
        assert reason == "within_thresholds"

    def test_fallback_rate_equal_threshold_no_rollback(
        self, canary_manager: CanaryManager
    ) -> None:
        should, reason = canary_manager._evaluate_rollback_metrics(
            {"max_fallback_rate": 0.05}, {"fallback_rate": 0.05}
        )
        assert should is False
        assert reason == "within_thresholds"

    def test_drift_alerts_exceeds(self, canary_manager: CanaryManager) -> None:
        should, reason = canary_manager._evaluate_rollback_metrics(
            {"max_drift_alerts_per_hour": 10}, {"drift_alerts_per_hour": 25}
        )
        assert should is True
        assert "drift_alerts_per_hour" in reason
        assert "25" in reason
        assert "10" in reason

    def test_drift_alerts_within(self, canary_manager: CanaryManager) -> None:
        should, reason = canary_manager._evaluate_rollback_metrics(
            {"max_drift_alerts_per_hour": 10}, {"drift_alerts_per_hour": 5}
        )
        assert should is False
        assert reason == "within_thresholds"

    def test_avg_latency_exceeds(self, canary_manager: CanaryManager) -> None:
        should, reason = canary_manager._evaluate_rollback_metrics(
            {"max_avg_latency_ms": 500.0}, {"avg_latency_ms": 800.0}
        )
        assert should is True
        assert "avg_latency_ms" in reason
        assert "800.0" in reason
        assert "500.0" in reason

    def test_avg_latency_within(self, canary_manager: CanaryManager) -> None:
        should, reason = canary_manager._evaluate_rollback_metrics(
            {"max_avg_latency_ms": 500.0}, {"avg_latency_ms": 200.0}
        )
        assert should is False
        assert reason == "within_thresholds"

    def test_multiple_metrics_exceeds_returns_first(
        self,
        canary_manager: CanaryManager,
    ) -> None:
        should, reason = canary_manager._evaluate_rollback_metrics(
            {
                "max_fallback_rate": 0.05,
                "max_drift_alerts_per_hour": 10,
                "max_avg_latency_ms": 500.0,
            },
            {
                "fallback_rate": 0.20,
                "drift_alerts_per_hour": 50,
                "avg_latency_ms": 1000.0,
            },
        )
        assert should is True
        assert "fallback_rate" in reason
        assert "drift_alerts_per_hour" not in reason

    def test_empty_metrics(self, canary_manager: CanaryManager) -> None:
        should, reason = canary_manager._evaluate_rollback_metrics(
            {"max_fallback_rate": 0.05}, {}
        )
        assert should is False
        assert reason == "within_thresholds"

    def test_empty_thresholds_uses_defaults(
        self, canary_manager: CanaryManager
    ) -> None:
        should, reason = canary_manager._evaluate_rollback_metrics(
            {}, {"fallback_rate": 0.10}
        )
        assert should is True
        assert "fallback_rate" in reason
        assert "5.00%" in reason

    def test_custom_thresholds_override(self, canary_manager: CanaryManager) -> None:
        should, reason = canary_manager._evaluate_rollback_metrics(
            {"max_fallback_rate": 0.20}, {"fallback_rate": 0.10}
        )
        assert should is False
        assert reason == "within_thresholds"

    def test_partial_metrics_only_checks_present(
        self, canary_manager: CanaryManager
    ) -> None:
        should, reason = canary_manager._evaluate_rollback_metrics(
            {"max_fallback_rate": 0.05, "max_avg_latency_ms": 500.0},
            {"avg_latency_ms": 800.0},
        )
        assert should is True
        assert "avg_latency_ms" in reason

    def test_returns_tuple(self, canary_manager: CanaryManager) -> None:
        result = canary_manager._evaluate_rollback_metrics({}, {})
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)


class TestGetTrafficPercentages:
    """get_traffic_percentages 公开方法测试."""

    def test_returns_default_percentages(self, canary_manager: CanaryManager) -> None:
        percents = canary_manager.get_traffic_percentages()
        assert percents == [1, 5, 25, 50, 100]

    def test_returns_copy_not_reference(self, canary_manager: CanaryManager) -> None:
        percents = canary_manager.get_traffic_percentages()
        percents.append(200)
        assert canary_manager.get_traffic_percentages() == [1, 5, 25, 50, 100]
        assert DEFAULT_TRAFFIC_PERCENTAGES == [1, 5, 25, 50, 100]


class TestCanaryManagerMisc:
    """CanaryManager 杂项测试."""

    def test_default_traffic_percentages_constant(self) -> None:
        assert DEFAULT_TRAFFIC_PERCENTAGES == [1, 5, 25, 50, 100]

    def test_rollback_thresholds_defaults(self) -> None:
        thresholds = RollbackThresholds()
        assert thresholds.max_fallback_rate == 0.05
        assert thresholds.max_drift_alerts_per_hour == 10
        assert thresholds.max_avg_latency_ms == 500.0

    def test_traffic_decision_dataclass(self) -> None:
        decision = TrafficDecision(
            use_canary=True,
            canary_version="v2.0.0",
            stable_version="v1.4.0",
            reason="test",
        )
        assert decision.use_canary is True
        assert decision.canary_version == "v2.0.0"
        assert decision.stable_version == "v1.4.0"
        assert decision.reason == "test"

    def test_global_canary_manager_exists(self) -> None:
        assert global_canary_manager is not None
        assert isinstance(global_canary_manager, CanaryManager)
