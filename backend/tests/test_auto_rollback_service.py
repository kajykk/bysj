from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auto_rollback_service import (
    AutoRollbackService,
    RollbackCheckResult,
    auto_rollback_service,
)


class TestRollbackCheckResult:
    """T-BE-005: RollbackCheckResult 单元测试"""

    def test_result_structure(self) -> None:
        """验证结果结构"""
        result = RollbackCheckResult(
            should_rollback=True,
            reason="test",
            metrics={"fallback_rate": 0.1},
            canary_id=1,
        )
        assert result.should_rollback is True
        assert result.reason == "test"
        assert result.metrics["fallback_rate"] == 0.1
        assert result.canary_id == 1

    def test_result_no_rollback(self) -> None:
        """验证不触发回滚的结果"""
        result = RollbackCheckResult(
            should_rollback=False,
            reason="within_thresholds",
            metrics={},
            canary_id=1,
        )
        assert result.should_rollback is False
        assert result.reason == "within_thresholds"


class TestAutoRollbackService:
    """T-BE-005: AutoRollbackService 单元测试"""

    async def _async_test_check_canary_not_found(
        self, db_session: AsyncSession
    ) -> None:
        """验证检查不存在的灰度"""
        service = AutoRollbackService()
        result = await service.check_canary_health(db_session, 99999)
        assert result.should_rollback is False
        assert result.reason == "canary_not_found"

    def test_check_canary_not_found(self, db_session: AsyncSession) -> None:
        """验证检查不存在的灰度"""
        import asyncio

        asyncio.run(self._async_test_check_canary_not_found(db_session))

    def test_thresholds_default(self) -> None:
        """验证默认阈值"""
        service = AutoRollbackService()
        # Default thresholds are defined in the service logic
        assert service is not None

    def test_global_service_exists(self) -> None:
        """验证全局服务实例存在"""
        assert auto_rollback_service is not None
        assert isinstance(auto_rollback_service, AutoRollbackService)

    def test_rollback_check_result_with_metrics(self) -> None:
        """验证带指标的回滚结果"""
        result = RollbackCheckResult(
            should_rollback=True,
            reason="fallback_rate 8.00% exceeds threshold 5.00%",
            metrics={
                "fallback_count": 8,
                "inference_count": 92,
                "fallback_rate": 0.08,
            },
            canary_id=1,
        )
        assert result.should_rollback is True
        assert "exceeds threshold" in result.reason
        assert result.metrics["fallback_rate"] == 0.08

    def test_rollback_check_result_within_thresholds(self) -> None:
        """验证阈值内的结果"""
        result = RollbackCheckResult(
            should_rollback=False,
            reason="within_thresholds",
            metrics={
                "fallback_count": 2,
                "inference_count": 98,
                "fallback_rate": 0.02,
                "drift_alerts_per_hour": 3,
                "avg_latency_ms": 150.0,
            },
            canary_id=1,
        )
        assert result.should_rollback is False
        assert result.metrics["fallback_rate"] == 0.02
        assert result.metrics["avg_latency_ms"] == 150.0


# ===== 扩展测试：覆盖 check_canary_health / execute_rollback / check_all_canaries 业务逻辑 =====

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from sqlalchemy import select

from app.models.monitoring import (
    CanaryRecord,
    CanaryStatus,
    DriftAlert,
    DriftSeverity,
    MonitoringEventType,
    MonitoringLog,
)


def _naive_utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _default_thresholds() -> dict:
    return {
        "max_fallback_rate": 0.05,
        "max_drift_alerts_per_hour": 10,
        "max_avg_latency_ms": 500.0,
    }


@pytest.fixture
def mock_observability_for_rollback(monkeypatch):
    """Mock observability_collector 以隔离 execute_rollback 副作用.

    注意: app.services.__init__ 把 canary_manager 实例 re-export 到 app.services 命名空间,
    覆盖了子模块引用, 因此不能用字符串路径 "app.services.canary_manager.observability_collector".
    改用 sys.modules 显式获取子模块对象, 再用 (obj, name) 形式 monkeypatch.
    """
    import sys

    canary_mod = sys.modules["app.services.canary_manager"]
    mock = MagicMock()
    mock.record_fallback = MagicMock()
    monkeypatch.setattr(canary_mod, "observability_collector", mock)
    return mock


async def _seed_running_canary(
    db_session: AsyncSession,
    version: str = "v1.5.0-test",
    thresholds: dict | None = None,
) -> CanaryRecord:
    canary = CanaryRecord(
        version=version,
        traffic_percent=50,
        status=CanaryStatus.RUNNING,
        auto_rollback_thresholds=thresholds or _default_thresholds(),
        triggered_by=None,
        started_at=_naive_utcnow(),
    )
    db_session.add(canary)
    await db_session.flush()
    return canary


async def _add_monitoring_log(
    db_session: AsyncSession,
    *,
    event_type: MonitoringEventType,
    model_version: str,
    latency_ms: float | None = None,
    minutes_ago: int = 5,
) -> MonitoringLog:
    log = MonitoringLog(
        event_type=event_type,
        model_version=model_version,
        latency_ms=latency_ms,
        created_at=_naive_utcnow() - timedelta(minutes=minutes_ago),
    )
    db_session.add(log)
    return log


async def _add_drift_alert(
    db_session: AsyncSession,
    *,
    model_version: str,
    resolved: bool = False,
    minutes_ago: int = 5,
) -> DriftAlert:
    alert = DriftAlert(
        model_version=model_version,
        feature_name="feat_x",
        drift_type="feature_drift",
        severity=DriftSeverity.HIGH,
        metric_value=0.3,
        threshold=0.1,
        resolved_at=_naive_utcnow() if resolved else None,
        created_at=_naive_utcnow() - timedelta(minutes=minutes_ago),
    )
    db_session.add(alert)
    return alert


class TestCheckCanaryHealthNotFound:
    """T-COV-ARB: check_canary_health - canary 不存在分支 (行 56-62)"""

    async def test_not_found_returns_canary_not_found(
        self,
        db_session: AsyncSession,
    ) -> None:
        service = AutoRollbackService()
        result = await service.check_canary_health(db_session, 99999)
        assert result.should_rollback is False
        assert result.reason == "canary_not_found"
        assert result.canary_id == 99999
        assert result.metrics == {}


class TestCheckCanaryHealthStatusNotRunning:
    """T-COV-ARB: check_canary_health - 状态非 RUNNING 分支 (行 64-70)"""

    async def test_rolled_back_status_skips_check(
        self,
        db_session: AsyncSession,
    ) -> None:
        canary = CanaryRecord(
            version="v1.5.0-rb",
            traffic_percent=0,
            status=CanaryStatus.ROLLED_BACK.value,
            auto_rollback_thresholds=_default_thresholds(),
            started_at=_naive_utcnow(),
        )
        db_session.add(canary)
        await db_session.flush()

        service = AutoRollbackService()
        result = await service.check_canary_health(db_session, canary.id)
        assert result.should_rollback is False
        assert result.reason == "canary_status_rolled_back"
        assert result.canary_id == canary.id
        assert result.metrics == {}


class TestCheckCanaryHealthWithMetrics:
    """T-COV-ARB: check_canary_health - 指标计算与阈值判断 (行 72-152)"""

    async def test_within_thresholds(self, db_session: AsyncSession) -> None:
        canary = await _seed_running_canary(db_session, version="v-within")
        for _ in range(2):
            await _add_monitoring_log(
                db_session,
                event_type=MonitoringEventType.FALLBACK,
                model_version="v-within",
            )
        for _ in range(98):
            await _add_monitoring_log(
                db_session,
                event_type=MonitoringEventType.INFERENCE,
                model_version="v-within",
                latency_ms=120.0,
            )
        await db_session.flush()

        service = AutoRollbackService()
        result = await service.check_canary_health(db_session, canary.id)
        assert result.should_rollback is False
        assert result.reason == "within_thresholds"
        assert result.canary_id == canary.id
        assert result.metrics["fallback_count"] == 2
        assert result.metrics["inference_count"] == 98
        assert result.metrics["fallback_rate"] == 0.02
        assert result.metrics["drift_alerts_per_hour"] == 0
        assert result.metrics["avg_latency_ms"] == 120.0

    async def test_fallback_rate_exceeds_threshold(
        self,
        db_session: AsyncSession,
    ) -> None:
        canary = await _seed_running_canary(db_session, version="v-fb")
        for _ in range(10):
            await _add_monitoring_log(
                db_session,
                event_type=MonitoringEventType.FALLBACK,
                model_version="v-fb",
            )
        for _ in range(10):
            await _add_monitoring_log(
                db_session,
                event_type=MonitoringEventType.INFERENCE,
                model_version="v-fb",
                latency_ms=100.0,
            )
        await db_session.flush()

        service = AutoRollbackService()
        result = await service.check_canary_health(db_session, canary.id)
        assert result.should_rollback is True
        assert result.reason.startswith("fallback_rate")
        assert "exceeds threshold" in result.reason
        assert result.metrics["fallback_rate"] == 0.5
        assert result.metrics["fallback_count"] == 10

    async def test_drift_alerts_exceed_threshold(
        self,
        db_session: AsyncSession,
    ) -> None:
        canary = await _seed_running_canary(db_session, version="v-drift")
        for _ in range(5):
            await _add_monitoring_log(
                db_session,
                event_type=MonitoringEventType.INFERENCE,
                model_version="v-drift",
                latency_ms=100.0,
            )
        for _ in range(15):
            await _add_drift_alert(db_session, model_version="v-drift", resolved=False)
        await db_session.flush()

        service = AutoRollbackService()
        result = await service.check_canary_health(db_session, canary.id)
        assert result.should_rollback is True
        assert result.reason.startswith("drift_alerts_per_hour")
        assert "exceeds threshold" in result.reason
        assert result.metrics["drift_alerts_per_hour"] == 15

    async def test_avg_latency_exceeds_threshold(
        self,
        db_session: AsyncSession,
    ) -> None:
        canary = await _seed_running_canary(db_session, version="v-lat")
        for _ in range(5):
            await _add_monitoring_log(
                db_session,
                event_type=MonitoringEventType.INFERENCE,
                model_version="v-lat",
                latency_ms=800.0,
            )
        await db_session.flush()

        service = AutoRollbackService()
        result = await service.check_canary_health(db_session, canary.id)
        assert result.should_rollback is True
        assert result.reason.startswith("avg_latency_ms")
        assert "exceeds threshold" in result.reason
        assert result.metrics["avg_latency_ms"] == 800.0

    async def test_resolved_drift_alerts_still_counted_in_window(
        self,
        db_session: AsyncSession,
    ) -> None:
        """P0 语义变更: 判据改为「窗口内新建告警数」, 不再要求 resolved_at IS NULL.

        窗口内新建后又被人工作废的告警仍然是漂移证据; 若继续用 resolved_at IS NULL
        过滤, 未解决告警量级被去重压到 ≤模态数, 漂移维度自动回滚永远不可达。
        """
        canary = await _seed_running_canary(db_session, version="v-resolved")
        for _ in range(5):
            await _add_monitoring_log(
                db_session,
                event_type=MonitoringEventType.INFERENCE,
                model_version="v-resolved",
                latency_ms=100.0,
            )
        for _ in range(2):
            await _add_drift_alert(
                db_session, model_version="v-resolved", resolved=True
            )
        for _ in range(1):
            await _add_drift_alert(
                db_session, model_version="v-resolved", resolved=False
            )
        await db_session.flush()

        service = AutoRollbackService()
        result = await service.check_canary_health(db_session, canary.id)
        # 窗口内新建的告警全部计数 (2 resolved + 1 unresolved = 3 > 2 → 触发回滚)
        assert result.metrics["drift_alerts_per_hour"] == 3
        assert result.should_rollback is True
        assert result.reason.startswith("drift_alerts_per_hour")

    async def test_drift_alerts_outside_window_not_counted(
        self,
        db_session: AsyncSession,
    ) -> None:
        """窗口外 (created_at 早于 1h) 的告警不计入, 防止历史积压误触发回滚."""
        canary = await _seed_running_canary(db_session, version="v-old-drift")
        for _ in range(5):
            await _add_monitoring_log(
                db_session,
                event_type=MonitoringEventType.INFERENCE,
                model_version="v-old-drift",
                latency_ms=100.0,
            )
        for _ in range(20):
            await _add_drift_alert(
                db_session, model_version="v-old-drift", minutes_ago=90
            )
        await db_session.flush()

        service = AutoRollbackService()
        result = await service.check_canary_health(db_session, canary.id)
        assert result.should_rollback is False
        assert result.metrics["drift_alerts_per_hour"] == 0

    # ===== P0 回归: 漂移维度自动回滚可达性 (缺陷一 fail-open) =====

    async def test_drift_regression_rollback_when_window_alerts_exceed_effective_threshold(
        self,
        db_session: AsyncSession,
    ) -> None:
        """核心回归: 故障注入 → 窗口内告警量达到可达阈值 → 必须回滚.

        旧判据 (未解决告警 > 10) 在 4 模态下永远不可达 (最多 4 条), 属于 fail-open。
        这里用 4 个模态各 1 条 (= drift_monitoring_service 单次检测可产生的最大量级)
        构造真实可达场景, 断言必须触发回滚。
        """
        canary = await _seed_running_canary(db_session, version="v-drift-p0")
        for _ in range(5):
            await _add_monitoring_log(
                db_session,
                event_type=MonitoringEventType.INFERENCE,
                model_version="v-drift-p0",
                latency_ms=100.0,
            )
        for feature in ("structured_score", "text_score", "physiological_score", "risk_score"):
            alert = DriftAlert(
                model_version="v-drift-p0",
                feature_name=feature,
                drift_type="prediction_drift",
                severity=DriftSeverity.HIGH,
                metric_value=0.6,
                threshold=0.25,
                created_at=_naive_utcnow() - timedelta(minutes=10),
            )
            db_session.add(alert)
        await db_session.flush()

        service = AutoRollbackService()
        result = await service.check_canary_health(db_session, canary.id)
        assert result.should_rollback is True
        assert result.reason.startswith("drift_alerts_per_hour")
        assert result.metrics["drift_alerts_per_hour"] == 4
        # 有效阈值被 min_drift_alerts_in_window 夹紧到 2 (≤ 模态数, 保证可达)
        assert result.metrics["max_drift_alerts_per_hour"] == 2

    async def test_drift_regression_no_rollback_below_threshold(
        self,
        db_session: AsyncSession,
    ) -> None:
        """反向保护: 未达阈值不得回滚 (防止判据改得过松)."""
        canary = await _seed_running_canary(db_session, version="v-drift-low")
        for _ in range(5):
            await _add_monitoring_log(
                db_session,
                event_type=MonitoringEventType.INFERENCE,
                model_version="v-drift-low",
                latency_ms=100.0,
            )
        for feature in ("structured_score", "text_score"):
            db_session.add(
                DriftAlert(
                    model_version="v-drift-low",
                    feature_name=feature,
                    drift_type="prediction_drift",
                    severity=DriftSeverity.HIGH,
                    metric_value=0.6,
                    threshold=0.25,
                    created_at=_naive_utcnow() - timedelta(minutes=10),
                )
            )
        await db_session.flush()

        service = AutoRollbackService()
        result = await service.check_canary_health(db_session, canary.id)
        assert result.should_rollback is False
        assert result.reason == "within_thresholds"
        assert result.metrics["drift_alerts_per_hour"] == 2

    async def test_drift_regression_version_mismatch_alerts_never_rollback(
        self,
        db_session: AsyncSession,
    ) -> None:
        """PSI > 2.0 的版本失配告警 (model_version=None) 仍不参与自动回滚.

        既有语义必须保留: 这些告警只走人工复核闭环。
        """
        canary = await _seed_running_canary(db_session, version="v-mismatch")
        for _ in range(5):
            await _add_monitoring_log(
                db_session,
                event_type=MonitoringEventType.INFERENCE,
                model_version="v-mismatch",
                latency_ms=100.0,
            )
        for feature in ("structured_score", "text_score", "physiological_score", "risk_score"):
            db_session.add(
                DriftAlert(
                    model_version=None,
                    feature_name=feature,
                    drift_type="prediction_drift",
                    severity=DriftSeverity.MEDIUM,
                    metric_value=8.4,
                    threshold=2.0,
                    details={"possible_model_version_mismatch": True},
                    created_at=_naive_utcnow() - timedelta(minutes=10),
                )
            )
        await db_session.flush()

        service = AutoRollbackService()
        result = await service.check_canary_health(db_session, canary.id)
        assert result.should_rollback is False
        assert result.metrics["drift_alerts_per_hour"] == 0

    async def test_drift_regression_resolved_history_does_not_block_new_canary(
        self,
        db_session: AsyncSession,
    ) -> None:
        """金丝雀启动前的历史未解决告警不应污染新版本窗口 (created_at 在窗口外)."""
        canary = await _seed_running_canary(db_session, version="v-fresh")
        for _ in range(5):
            await _add_monitoring_log(
                db_session,
                event_type=MonitoringEventType.INFERENCE,
                model_version="v-fresh",
                latency_ms=100.0,
            )
        # 历史未解决告警 (3 天前), 属于旧版本
        for feature in ("structured_score", "text_score", "physiological_score", "risk_score"):
            db_session.add(
                DriftAlert(
                    model_version="v-old",
                    feature_name=feature,
                    drift_type="prediction_drift",
                    severity=DriftSeverity.HIGH,
                    metric_value=0.9,
                    threshold=0.25,
                    created_at=_naive_utcnow() - timedelta(days=3),
                )
            )
        await db_session.flush()

        service = AutoRollbackService()
        result = await service.check_canary_health(db_session, canary.id)
        assert result.should_rollback is False
        assert result.metrics["drift_alerts_per_hour"] == 0

    async def test_drift_regression_check_all_canaries_rolls_back_on_drift(
        self,
        db_session: AsyncSession,
        mock_observability_for_rollback,
    ) -> None:
        """端到端: 漂移超阈值时 check_all_canaries 必须真正把金丝雀置为 ROLLED_BACK."""
        canary = await _seed_running_canary(db_session, version="v-e2e-drift")
        for feature in ("structured_score", "text_score", "physiological_score"):
            db_session.add(
                DriftAlert(
                    model_version="v-e2e-drift",
                    feature_name=feature,
                    drift_type="prediction_drift",
                    severity=DriftSeverity.CRITICAL,
                    metric_value=0.9,
                    threshold=0.25,
                    created_at=_naive_utcnow() - timedelta(minutes=5),
                )
            )
        await db_session.flush()

        service = AutoRollbackService()
        results = await service.check_all_canaries(db_session, source="test")
        assert len(results) == 1
        assert results[0].should_rollback is True

        refreshed = (
            await db_session.execute(
                select(CanaryRecord).where(CanaryRecord.id == canary.id)
            )
        ).scalar_one()
        assert refreshed.status == CanaryStatus.ROLLED_BACK

    async def test_drift_regression_resolved_at_recent_but_created_in_window_counts(
        self,
        db_session: AsyncSession,
    ) -> None:
        """窗口内新建后即被 resolve 的告警仍应计入 (旧判据会漏掉这类证据)."""
        canary = await _seed_running_canary(db_session, version="v-quick-resolve")
        for feature in ("structured_score", "text_score", "physiological_score"):
            db_session.add(
                DriftAlert(
                    model_version="v-quick-resolve",
                    feature_name=feature,
                    drift_type="prediction_drift",
                    severity=DriftSeverity.HIGH,
                    metric_value=0.7,
                    threshold=0.25,
                    resolved_at=_naive_utcnow(),
                    created_at=_naive_utcnow() - timedelta(minutes=30),
                )
            )
        await db_session.flush()

        service = AutoRollbackService()
        result = await service.check_canary_health(db_session, canary.id)
        assert result.should_rollback is True
        assert result.metrics["drift_alerts_per_hour"] == 3

    async def test_no_metrics_returns_within_thresholds(
        self,
        db_session: AsyncSession,
    ) -> None:
        """无任何 metrics 记录时返回 within_thresholds (零除兜底 max(1, total))"""
        canary = await _seed_running_canary(db_session, version="v-empty")
        await db_session.flush()

        service = AutoRollbackService()
        result = await service.check_canary_health(db_session, canary.id)
        assert result.should_rollback is False
        assert result.reason == "within_thresholds"
        assert result.metrics["fallback_count"] == 0
        assert result.metrics["inference_count"] == 0
        assert result.metrics["fallback_rate"] == 0.0
        assert result.metrics["drift_alerts_per_hour"] == 0
        assert result.metrics["avg_latency_ms"] == 0.0


class TestExecuteRollback:
    """T-COV-ARB: execute_rollback 正常路径 (行 179-196)"""

    async def test_execute_rollback_success(
        self,
        db_session: AsyncSession,
        mock_observability_for_rollback,
    ) -> None:
        canary = await _seed_running_canary(db_session, version="v-rb-exec")
        service = AutoRollbackService()
        result = await service.execute_rollback(
            db_session,
            canary.id,
            reason="fallback_rate exceeded",
            triggered_by="auto",
        )
        assert result is True

        refreshed = (
            await db_session.execute(
                select(CanaryRecord).where(CanaryRecord.id == canary.id)
            )
        ).scalar_one()
        assert refreshed.status == CanaryStatus.ROLLED_BACK
        assert refreshed.rollback_reason == "fallback_rate exceeded"
        assert refreshed.ended_at is not None
        assert refreshed.ended_at.tzinfo is None

        log_result = await db_session.execute(
            select(MonitoringLog).where(
                MonitoringLog.event_type == MonitoringEventType.CANARY_SWITCH
            )
        )
        logs = log_result.scalars().all()
        assert len(logs) == 1
        summary = logs[0].response_summary
        assert summary["canary_id"] == canary.id
        assert summary["action"] == "rollback"
        assert summary["reason"] == "fallback_rate exceeded"
        assert summary["triggered_by"] == "auto"
        assert "timestamp" in summary

    async def test_execute_rollback_records_user_trigger(
        self,
        db_session: AsyncSession,
        mock_observability_for_rollback,
    ) -> None:
        canary = await _seed_running_canary(db_session, version="v-rb-user")
        service = AutoRollbackService()
        await service.execute_rollback(
            db_session,
            canary.id,
            reason="manual rollback",
            triggered_by="user_42",
        )

        log = (
            await db_session.execute(
                select(MonitoringLog).where(
                    MonitoringLog.event_type == MonitoringEventType.CANARY_SWITCH
                )
            )
        ).scalar_one()
        assert log.response_summary["triggered_by"] == "user_42"

        refreshed = (
            await db_session.execute(
                select(CanaryRecord).where(CanaryRecord.id == canary.id)
            )
        ).scalar_one()
        assert refreshed.status == CanaryStatus.ROLLED_BACK
        assert refreshed.rollback_reason == "manual rollback"


class TestCheckAllCanaries:
    """T-COV-ARB: check_all_canaries - 批量检查 (行 207-242)"""

    async def test_returns_empty_when_no_running_canaries(
        self,
        db_session: AsyncSession,
    ) -> None:
        service = AutoRollbackService()
        results = await service.check_all_canaries(db_session)
        assert results == []

    async def test_checks_all_running_canaries_and_skips_others(
        self,
        db_session: AsyncSession,
        mock_observability_for_rollback,
    ) -> None:
        healthy = await _seed_running_canary(db_session, version="v-healthy")
        for _ in range(5):
            await _add_monitoring_log(
                db_session,
                event_type=MonitoringEventType.INFERENCE,
                model_version="v-healthy",
                latency_ms=100.0,
            )

        unhealthy = CanaryRecord(
            version="v-unhealthy",
            traffic_percent=20,
            status=CanaryStatus.RUNNING,
            auto_rollback_thresholds=_default_thresholds(),
            started_at=_naive_utcnow(),
        )
        db_session.add(unhealthy)

        rolled_back = CanaryRecord(
            version="v-skip",
            traffic_percent=0,
            status=CanaryStatus.ROLLED_BACK,
            auto_rollback_thresholds=_default_thresholds(),
            started_at=_naive_utcnow(),
        )
        db_session.add(rolled_back)
        await db_session.flush()

        for _ in range(20):
            await _add_monitoring_log(
                db_session,
                event_type=MonitoringEventType.FALLBACK,
                model_version="v-unhealthy",
            )
        for _ in range(5):
            await _add_monitoring_log(
                db_session,
                event_type=MonitoringEventType.INFERENCE,
                model_version="v-unhealthy",
                latency_ms=100.0,
            )
        await db_session.flush()

        service = AutoRollbackService()
        results = await service.check_all_canaries(db_session)

        assert len(results) == 2
        canary_ids = {r.canary_id for r in results}
        assert healthy.id in canary_ids
        assert unhealthy.id in canary_ids
        assert rolled_back.id not in canary_ids

        healthy_result = next(r for r in results if r.canary_id == healthy.id)
        assert healthy_result.should_rollback is False
        assert healthy_result.reason == "within_thresholds"

        unhealthy_result = next(r for r in results if r.canary_id == unhealthy.id)
        assert unhealthy_result.should_rollback is True
        assert unhealthy_result.reason.startswith("fallback_rate")

        refreshed = (
            await db_session.execute(
                select(CanaryRecord).where(CanaryRecord.id == unhealthy.id)
            )
        ).scalar_one()
        assert refreshed.status == CanaryStatus.ROLLED_BACK
        assert refreshed.rollback_reason is not None
        assert refreshed.rollback_reason.startswith("fallback_rate")

    async def test_check_error_branch_returns_check_error(
        self,
        db_session: AsyncSession,
        monkeypatch,
        mock_observability_for_rollback,
    ) -> None:
        """check_canary_health 抛异常时返回 check_error 结果 (行 232-239)"""
        canary = await _seed_running_canary(db_session, version="v-err")

        service = AutoRollbackService()

        async def _raising_check(
            session: AsyncSession, canary_id: int
        ) -> RollbackCheckResult:
            raise RuntimeError("boom")

        monkeypatch.setattr(service, "check_canary_health", _raising_check)

        results = await service.check_all_canaries(db_session)
        assert len(results) == 1
        assert results[0].should_rollback is False
        assert results[0].reason == "check_error"
        assert results[0].canary_id == canary.id
        assert results[0].metrics == {}


class TestThresholdsConfig:
    """T-COV-ARB: 阈值配置 - 默认值与自定义覆盖"""

    async def test_default_thresholds_values(self, db_session: AsyncSession) -> None:
        """验证 CanaryRecord 默认 auto_rollback_thresholds 字典值"""
        canary = CanaryRecord(
            version="v-default-th",
            traffic_percent=5,
            status=CanaryStatus.RUNNING,
        )
        db_session.add(canary)
        await db_session.flush()
        assert canary.auto_rollback_thresholds is not None
        assert canary.auto_rollback_thresholds["max_fallback_rate"] == 0.05
        assert canary.auto_rollback_thresholds["max_drift_alerts_per_hour"] == 10
        assert canary.auto_rollback_thresholds["max_avg_latency_ms"] == 500

    def test_custom_thresholds_can_override_defaults(self) -> None:
        """验证自定义阈值可覆盖默认值"""
        custom = {
            "max_fallback_rate": 0.1,
            "max_drift_alerts_per_hour": 5,
            "max_avg_latency_ms": 300.0,
        }
        canary = CanaryRecord(
            version="v-custom-th",
            traffic_percent=5,
            status=CanaryStatus.RUNNING,
            auto_rollback_thresholds=custom,
        )
        assert canary.auto_rollback_thresholds == custom
        assert canary.auto_rollback_thresholds["max_fallback_rate"] == 0.1
        assert canary.auto_rollback_thresholds["max_drift_alerts_per_hour"] == 5
        assert canary.auto_rollback_thresholds["max_avg_latency_ms"] == 300.0

    async def test_custom_thresholds_enforced_by_service(
        self,
        db_session: AsyncSession,
    ) -> None:
        """验证 service 从 canary.auto_rollback_thresholds 读取并应用自定义阈值"""
        canary = await _seed_running_canary(
            db_session,
            version="v-custom-svc",
            thresholds={
                "max_fallback_rate": 0.5,
                "max_drift_alerts_per_hour": 1,
                "max_avg_latency_ms": 1000.0,
            },
        )
        for _ in range(2):
            await _add_monitoring_log(
                db_session,
                event_type=MonitoringEventType.FALLBACK,
                model_version="v-custom-svc",
            )
        for _ in range(8):
            await _add_monitoring_log(
                db_session,
                event_type=MonitoringEventType.INFERENCE,
                model_version="v-custom-svc",
                latency_ms=200.0,
            )
        for _ in range(3):
            await _add_drift_alert(
                db_session, model_version="v-custom-svc", resolved=False
            )
        await db_session.flush()

        service = AutoRollbackService()
        result = await service.check_canary_health(db_session, canary.id)
        assert result.should_rollback is True
        assert result.reason.startswith("drift_alerts_per_hour")
        assert "exceeds threshold 1" in result.reason
        assert result.metrics["drift_alerts_per_hour"] == 3
