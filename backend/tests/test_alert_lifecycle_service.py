from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring import (
    DriftAlert,
    DriftSeverity,
    MonitoringEventType,
    MonitoringLog,
)
from app.services.alert_lifecycle_service import (
    SEVERITY_NOTIFICATION_MAP,
    AlertLifecycleService,
    AlertStatus,
    NotificationChannel,
    alert_lifecycle_service,
)


class TestAlertStatus:
    """T-BE-003a: AlertStatus 枚举单元测试"""

    def test_status_values(self) -> None:
        """验证状态枚举值"""
        assert AlertStatus.TRIGGERED == "TRIGGERED"
        assert AlertStatus.ACKNOWLEDGED == "ACKNOWLEDGED"
        assert AlertStatus.RESOLVED == "RESOLVED"
        assert AlertStatus.CLOSED == "CLOSED"


class TestNotificationChannel:
    """T-BE-003a: NotificationChannel 枚举单元测试"""

    def test_channel_values(self) -> None:
        """验证通知渠道枚举值"""
        assert NotificationChannel.SMS == "sms"
        assert NotificationChannel.EMAIL == "email"
        assert NotificationChannel.IN_APP == "in_app"
        assert NotificationChannel.DAILY_DIGEST == "daily_digest"


class TestSeverityNotificationMap:
    """T-BE-003a: 严重级别通知映射单元测试"""

    def test_critical_channels(self) -> None:
        """验证 CRITICAL 级别通知渠道"""
        channels = SEVERITY_NOTIFICATION_MAP[DriftSeverity.CRITICAL]
        assert NotificationChannel.SMS in channels
        assert NotificationChannel.EMAIL in channels
        assert NotificationChannel.IN_APP in channels

    def test_high_channels(self) -> None:
        """验证 HIGH 级别通知渠道"""
        channels = SEVERITY_NOTIFICATION_MAP[DriftSeverity.HIGH]
        assert NotificationChannel.EMAIL in channels
        assert NotificationChannel.IN_APP in channels
        assert NotificationChannel.SMS not in channels

    def test_medium_channels(self) -> None:
        """验证 MEDIUM 级别通知渠道"""
        channels = SEVERITY_NOTIFICATION_MAP[DriftSeverity.MEDIUM]
        assert channels == [NotificationChannel.IN_APP]

    def test_low_channels(self) -> None:
        """验证 LOW 级别通知渠道"""
        channels = SEVERITY_NOTIFICATION_MAP[DriftSeverity.LOW]
        assert channels == [NotificationChannel.DAILY_DIGEST]


class TestAlertLifecycleService:
    """T-BE-003a: AlertLifecycleService 单元测试"""

    def test_valid_transitions(self) -> None:
        """验证有效状态流转"""
        service = AlertLifecycleService()
        assert (
            service.is_valid_transition(AlertStatus.TRIGGERED, AlertStatus.ACKNOWLEDGED)
            is True
        )
        assert (
            service.is_valid_transition(AlertStatus.TRIGGERED, AlertStatus.RESOLVED)
            is True
        )
        assert (
            service.is_valid_transition(AlertStatus.ACKNOWLEDGED, AlertStatus.RESOLVED)
            is True
        )
        assert (
            service.is_valid_transition(AlertStatus.RESOLVED, AlertStatus.CLOSED)
            is True
        )

    def test_invalid_transitions(self) -> None:
        """验证无效状态流转"""
        service = AlertLifecycleService()
        assert (
            service.is_valid_transition(AlertStatus.TRIGGERED, AlertStatus.CLOSED)
            is False
        )
        # C-Svc-2 修复：CLOSED -> TRIGGERED 已合法化（reopen_alert 文档承诺可重开），
        # 改测 CLOSED -> ACKNOWLEDGED（仍为非法跳转）
        assert (
            service.is_valid_transition(AlertStatus.CLOSED, AlertStatus.ACKNOWLEDGED)
            is False
        )
        assert (
            service.is_valid_transition(AlertStatus.ACKNOWLEDGED, AlertStatus.CLOSED)
            is False
        )

    def test_get_notification_channels(self) -> None:
        """验证获取通知渠道"""
        service = AlertLifecycleService()
        channels = service.get_notification_channels(DriftSeverity.CRITICAL)
        assert len(channels) == 3

    def test_build_notification_payload(self) -> None:
        """验证构建通知负载"""
        service = AlertLifecycleService()
        alert = DriftAlert(
            id=1,
            model_version="v1.5.0",
            feature_name="stress_level",
            drift_type="feature_drift",
            severity=DriftSeverity.HIGH,
            metric_value=0.35,
            threshold=0.25,
            details={"ks_statistic": 0.35},
        )
        payload = service.build_notification_payload(alert)
        assert payload.alert_id == 1
        assert payload.severity == DriftSeverity.HIGH
        assert NotificationChannel.EMAIL in payload.channels
        assert "stress_level" in payload.message

    def test_transition_history(self) -> None:
        """验证状态流转历史记录"""
        service = AlertLifecycleService()
        service._record_transition(
            1,
            AlertStatus.TRIGGERED,
            AlertStatus.ACKNOWLEDGED,
            user_id=5,
            note="investigating",
        )
        history = service.get_transition_history(1)
        assert len(history) == 1
        assert history[0]["from"] == "TRIGGERED"
        assert history[0]["to"] == "ACKNOWLEDGED"
        assert history[0]["user_id"] == 5

    def test_determine_current_status_triggered(self) -> None:
        """验证确定当前状态: TRIGGERED"""
        service = AlertLifecycleService()
        alert = DriftAlert(
            id=1, drift_type="feature_drift", severity=DriftSeverity.MEDIUM
        )
        assert service._determine_current_status(alert) == AlertStatus.TRIGGERED

    def test_determine_current_status_resolved(self) -> None:
        """验证确定当前状态: RESOLVED"""
        from datetime import datetime, timezone

        service = AlertLifecycleService()
        alert = DriftAlert(
            id=1,
            drift_type="feature_drift",
            severity=DriftSeverity.MEDIUM,
            resolved_at=datetime.now(timezone.utc),
        )
        assert service._determine_current_status(alert) == AlertStatus.RESOLVED

    def test_global_service_exists(self) -> None:
        """验证全局服务实例存在"""
        assert alert_lifecycle_service is not None
        assert isinstance(alert_lifecycle_service, AlertLifecycleService)


# =============================================================================
# 新增测试：覆盖 transition_alert / 状态推断 / wrapper 方法 / get_severity_stats
# 不修改上方已有测试。
# =============================================================================


async def _seed_alert(
    db_session: AsyncSession,
    *,
    severity: str = DriftSeverity.MEDIUM,
    drift_type: str = "feature_drift",
    model_version: str = "v1.0.0",
    feature_name: str = "stress_level",
    metric_value: float = 0.4,
    threshold: float = 0.3,
    resolved_at: datetime | None = None,
    acknowledged_at: datetime | None = None,
    closed_at: datetime | None = None,
) -> DriftAlert:
    """创建并持久化一条 DriftAlert，返回带 id 的实例。"""
    alert = DriftAlert(
        model_version=model_version,
        feature_name=feature_name,
        drift_type=drift_type,
        severity=severity,
        metric_value=metric_value,
        threshold=threshold,
        details={"ks_statistic": metric_value},
        resolved_at=resolved_at,
        acknowledged_at=acknowledged_at,
        closed_at=closed_at,
    )
    db_session.add(alert)
    await db_session.flush()
    await db_session.refresh(alert)
    return alert


class TestDetermineCurrentStatusBranches:
    """覆盖 _determine_current_status 全部分支（行 203-210）"""

    def test_determine_closed(self) -> None:
        """closed_at 非空时判定为 CLOSED（行 203-204）"""
        service = AlertLifecycleService()
        alert = DriftAlert(
            id=1,
            drift_type="feature_drift",
            severity=DriftSeverity.MEDIUM,
            closed_at=datetime(2026, 6, 1, 12, 0, 0),
        )
        assert service._determine_current_status(alert) == AlertStatus.CLOSED

    def test_determine_acknowledged(self) -> None:
        """acknowledged_at 非空（resolved/closed 为空）时判定为 ACKNOWLEDGED（行 208-209）"""
        service = AlertLifecycleService()
        alert = DriftAlert(
            id=1,
            drift_type="feature_drift",
            severity=DriftSeverity.MEDIUM,
            acknowledged_at=datetime(2026, 6, 1, 12, 0, 0),
        )
        assert service._determine_current_status(alert) == AlertStatus.ACKNOWLEDGED

    def test_determine_priority_closed_over_resolved(self) -> None:
        """closed_at 与 resolved_at 同时存在时优先 CLOSED"""
        service = AlertLifecycleService()
        alert = DriftAlert(
            id=1,
            drift_type="feature_drift",
            severity=DriftSeverity.MEDIUM,
            resolved_at=datetime(2026, 6, 1, 12, 0, 0),
            closed_at=datetime(2026, 6, 2, 12, 0, 0),
        )
        assert service._determine_current_status(alert) == AlertStatus.CLOSED

    def test_determine_priority_resolved_over_acknowledged(self) -> None:
        """resolved_at 与 acknowledged_at 同时存在时优先 RESOLVED"""
        service = AlertLifecycleService()
        alert = DriftAlert(
            id=1,
            drift_type="feature_drift",
            severity=DriftSeverity.MEDIUM,
            acknowledged_at=datetime(2026, 6, 1, 12, 0, 0),
            resolved_at=datetime(2026, 6, 2, 12, 0, 0),
        )
        assert service._determine_current_status(alert) == AlertStatus.RESOLVED


class TestTransitionAlert:
    """覆盖 transition_alert 主流程（行 137-194）"""

    async def test_transition_alert_not_found(self, db_session: AsyncSession) -> None:
        """告警不存在时返回失败且 updated_alert 为 None（行 140-141）"""
        service = AlertLifecycleService()
        success, message, alert = await service.transition_alert(
            db_session, 9999, AlertStatus.ACKNOWLEDGED, user_id=1
        )
        assert success is False
        assert "not found" in message
        assert alert is None

    async def test_transition_to_acknowledged(self, db_session: AsyncSession) -> None:
        """TRIGGERED -> ACKNOWLEDGED 应写入 acknowledged_at（行 162-165）"""
        alert = await _seed_alert(db_session)
        service = AlertLifecycleService()
        success, message, updated = await service.transition_alert(
            db_session, alert.id, AlertStatus.ACKNOWLEDGED, user_id=1, note="ack"
        )
        assert success is True
        assert "ACKNOWLEDGED" in message
        assert updated.acknowledged_at is not None
        assert updated.resolved_at is None
        assert updated.closed_at is None

    async def test_transition_to_resolved(self, db_session: AsyncSession) -> None:
        """TRIGGERED -> RESOLVED 应写入 resolved_at（行 154-156）"""
        alert = await _seed_alert(db_session)
        service = AlertLifecycleService()
        success, message, updated = await service.transition_alert(
            db_session, alert.id, AlertStatus.RESOLVED, user_id=1
        )
        assert success is True
        assert updated.resolved_at is not None

    async def test_transition_to_closed(self, db_session: AsyncSession) -> None:
        """RESOLVED -> CLOSED 应写入 closed_at（行 166-170）"""
        alert = await _seed_alert(
            db_session, resolved_at=datetime(2026, 6, 1, 10, 0, 0)
        )
        service = AlertLifecycleService()
        success, message, updated = await service.transition_alert(
            db_session, alert.id, AlertStatus.CLOSED, user_id=1
        )
        assert success is True
        assert updated.closed_at is not None

    async def test_transition_reopen_clears_timestamps(
        self, db_session: AsyncSession
    ) -> None:
        """RESOLVED -> TRIGGERED 重开应清除全部时间戳（行 157-161）"""
        alert = await _seed_alert(
            db_session,
            resolved_at=datetime(2026, 6, 1, 10, 0, 0),
            acknowledged_at=datetime(2026, 6, 1, 9, 0, 0),
        )
        service = AlertLifecycleService()
        success, message, updated = await service.transition_alert(
            db_session, alert.id, AlertStatus.TRIGGERED, user_id=1, note="reopen"
        )
        assert success is True
        assert updated.resolved_at is None
        assert updated.acknowledged_at is None
        assert updated.closed_at is None

    async def test_transition_invalid_returns_alert(
        self, db_session: AsyncSession
    ) -> None:
        """非法跳转 TRIGGERED -> CLOSED 返回失败并携带原 alert（行 146-151）"""
        alert = await _seed_alert(db_session)
        service = AlertLifecycleService()
        success, message, returned = await service.transition_alert(
            db_session, alert.id, AlertStatus.CLOSED, user_id=1
        )
        assert success is False
        assert "Invalid transition" in message
        assert returned is alert

    async def test_transition_writes_monitoring_log(
        self, db_session: AsyncSession
    ) -> None:
        """状态转换应写入 MonitoringLog 审计记录（行 177-190）"""
        alert = await _seed_alert(db_session, model_version="v9.9.9")
        service = AlertLifecycleService()
        await service.transition_alert(
            db_session, alert.id, AlertStatus.RESOLVED, user_id=7, note="resolved by qa"
        )
        result = await db_session.execute(
            select(MonitoringLog).where(MonitoringLog.model_version == "v9.9.9")
        )
        logs = result.scalars().all()
        assert len(logs) == 1
        assert logs[0].event_type == MonitoringEventType.DRIFT_ALERT
        assert logs[0].user_id == 7
        assert logs[0].response_summary["alert_id"] == alert.id
        assert logs[0].response_summary["transition"] == "TRIGGERED -> RESOLVED"
        assert logs[0].response_summary["note"] == "resolved by qa"

    async def test_transition_records_history(self, db_session: AsyncSession) -> None:
        """状态转换应记录到内存 history（行 172-173）"""
        alert = await _seed_alert(db_session)
        service = AlertLifecycleService()
        await service.transition_alert(
            db_session,
            alert.id,
            AlertStatus.ACKNOWLEDGED,
            user_id=3,
            note="investigating",
        )
        history = service.get_transition_history(alert.id)
        assert len(history) == 1
        assert history[0]["from"] == "TRIGGERED"
        assert history[0]["to"] == "ACKNOWLEDGED"
        assert history[0]["user_id"] == 3
        assert history[0]["note"] == "investigating"

    async def test_transition_flush_exception_propagates(self) -> None:
        """db_session.flush 抛异常时应向上传播（行 190 异常路径）"""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = DriftAlert(
            id=1, drift_type="feature_drift", severity=DriftSeverity.MEDIUM
        )
        mock_db.execute.return_value = mock_result
        mock_db.flush.side_effect = RuntimeError("db connection lost")
        # AsyncMock 会将 add 视为协程，源码同步调用 add(log) 会产生未 await 警告；
        # 改为同步 MagicMock 以贴近真实 AsyncSession.add 行为。
        mock_db.add = MagicMock()
        service = AlertLifecycleService()
        with pytest.raises(RuntimeError, match="db connection lost"):
            await service.transition_alert(
                mock_db, 1, AlertStatus.ACKNOWLEDGED, user_id=1
            )


class TestWrapperMethods:
    """覆盖 acknowledge_alert / resolve_alert / close_alert / reopen_alert（行 220/232/244/256）"""

    async def test_acknowledge_alert(self, db_session: AsyncSession) -> None:
        """acknowledge_alert 委托 transition_alert 并落入 ACKNOWLEDGED（行 220）"""
        alert = await _seed_alert(db_session)
        service = AlertLifecycleService()
        success, _, updated = await service.acknowledge_alert(
            db_session, alert.id, user_id=2, note="looking"
        )
        assert success is True
        assert updated.acknowledged_at is not None

    async def test_resolve_alert(self, db_session: AsyncSession) -> None:
        """resolve_alert 委托 transition_alert 并落入 RESOLVED（行 232）"""
        alert = await _seed_alert(db_session)
        service = AlertLifecycleService()
        success, _, updated = await service.resolve_alert(
            db_session, alert.id, user_id=2
        )
        assert success is True
        assert updated.resolved_at is not None

    async def test_close_alert(self, db_session: AsyncSession) -> None:
        """close_alert 在 RESOLVED 后落入 CLOSED（行 244）"""
        alert = await _seed_alert(
            db_session, resolved_at=datetime(2026, 6, 1, 10, 0, 0)
        )
        service = AlertLifecycleService()
        success, _, updated = await service.close_alert(db_session, alert.id, user_id=2)
        assert success is True
        assert updated.closed_at is not None

    async def test_reopen_alert(self, db_session: AsyncSession) -> None:
        """reopen_alert 从 RESOLVED 重开回 TRIGGERED（行 256）"""
        alert = await _seed_alert(
            db_session, resolved_at=datetime(2026, 6, 1, 10, 0, 0)
        )
        service = AlertLifecycleService()
        success, _, updated = await service.reopen_alert(
            db_session, alert.id, user_id=2
        )
        assert success is True
        assert updated.resolved_at is None
        assert updated.acknowledged_at is None
        assert updated.closed_at is None

    async def test_reopen_from_closed(self, db_session: AsyncSession) -> None:
        """reopen_alert 从 CLOSED 重开（C-Svc-2: CLOSED -> TRIGGERED 已合法化）"""
        alert = await _seed_alert(
            db_session,
            resolved_at=datetime(2026, 6, 1, 10, 0, 0),
            closed_at=datetime(2026, 6, 2, 10, 0, 0),
        )
        service = AlertLifecycleService()
        success, message, updated = await service.reopen_alert(
            db_session, alert.id, user_id=2
        )
        assert success is True, message
        assert updated.closed_at is None
        assert updated.resolved_at is None


class TestGetSeverityStats:
    """覆盖 get_severity_stats（行 300-310）"""

    def test_stats_empty_when_no_history(self) -> None:
        """无转换历史时返回空 dict（行 300-301、310）"""
        service = AlertLifecycleService()
        assert service.get_severity_stats() == {}

    def test_stats_skips_empty_history_list(self) -> None:
        """告警对应空 history 列表时跳过（行 302-303）"""
        service = AlertLifecycleService()
        service._transition_history[42] = []
        assert service.get_severity_stats() == {}

    def test_stats_excludes_closed(self) -> None:
        """最近一次状态为 CLOSED 的告警不计入统计（行 306-307）"""
        service = AlertLifecycleService()
        service._record_transition(1, AlertStatus.RESOLVED, AlertStatus.CLOSED)
        assert service.get_severity_stats() == {}

    def test_stats_counts_by_last_status(self) -> None:
        """按告警最近一次未关闭状态计数（行 304-305、308-309）"""
        service = AlertLifecycleService()
        service._record_transition(1, AlertStatus.TRIGGERED, AlertStatus.ACKNOWLEDGED)
        service._record_transition(2, AlertStatus.TRIGGERED, AlertStatus.RESOLVED)
        service._record_transition(3, AlertStatus.TRIGGERED, AlertStatus.RESOLVED)
        stats = service.get_severity_stats()
        assert stats == {"ACKNOWLEDGED": 1, "RESOLVED": 2}


class TestNotificationChannelsEdgeCases:
    """补充 get_notification_channels 边界（行 122 默认分支）"""

    def test_unknown_severity_defaults_to_daily_digest(self) -> None:
        """未知 severity 回退到 [DAILY_DIGEST]（行 122）"""
        service = AlertLifecycleService()
        assert service.get_notification_channels("UNKNOWN") == [
            NotificationChannel.DAILY_DIGEST
        ]

    def test_low_severity_channels(self) -> None:
        """LOW 级别返回 daily_digest"""
        service = AlertLifecycleService()
        assert service.get_notification_channels(DriftSeverity.LOW) == [
            NotificationChannel.DAILY_DIGEST
        ]

    def test_medium_severity_channels(self) -> None:
        """MEDIUM 级别返回 in_app"""
        service = AlertLifecycleService()
        assert service.get_notification_channels(DriftSeverity.MEDIUM) == [
            NotificationChannel.IN_APP
        ]

    def test_high_severity_channels(self) -> None:
        """HIGH 级别返回 email + in_app"""
        service = AlertLifecycleService()
        channels = service.get_notification_channels(DriftSeverity.HIGH)
        assert NotificationChannel.EMAIL in channels
        assert NotificationChannel.IN_APP in channels
        assert NotificationChannel.SMS not in channels


class TestBuildNotificationPayloadEdgeCases:
    """补充 build_notification_payload 边界"""

    def test_payload_severity_none_defaults_medium(self) -> None:
        """severity 为 None 时回退 MEDIUM（行 262、272）"""
        service = AlertLifecycleService()
        alert = DriftAlert(
            id=5,
            model_version="v1.0",
            feature_name="f",
            drift_type="feature_drift",
            severity=None,
            metric_value=0.1,
            threshold=0.2,
            details=None,
        )
        payload = service.build_notification_payload(alert)
        assert payload.severity == DriftSeverity.MEDIUM
        assert NotificationChannel.IN_APP in payload.channels

    def test_payload_with_none_optional_fields(self) -> None:
        """可选字段为 None 时 message 不报错且包含占位（行 264-269）"""
        service = AlertLifecycleService()
        alert = DriftAlert(
            id=7,
            model_version=None,
            feature_name=None,
            drift_type="prediction_drift",
            severity=DriftSeverity.CRITICAL,
            metric_value=None,
            threshold=None,
            details=None,
        )
        payload = service.build_notification_payload(alert)
        assert payload.alert_id == 7
        assert "unknown" in payload.message
        assert "N/A" in payload.message
        # Python 3.12: (str, Enum) 的 __format__ 返回 'DriftSeverity.CRITICAL' 而非 'CRITICAL'，
        # 源码 f"[{alert.severity}]" 产生 "[DriftSeverity.CRITICAL]"（标题 Bug，见报告），
        # 此处断言兼容两种格式。
        assert "CRITICAL" in payload.title


class TestTransitionAlertConcurrency:
    """TOCTOU 相关：验证状态机在连续状态变更场景下拒绝非法跳转

    说明：transition_alert 当前实现未使用 with_for_update() 行锁（见报告），
    此处验证应用层状态机对非法跳转的拒绝行为。
    """

    async def test_invalid_transition_after_acknowledge(
        self, db_session: AsyncSession
    ) -> None:
        """ACKNOWLEDGED 后直接尝试 CLOSED 应被状态机拒绝（ACKNOWLEDGED -> CLOSED 非法）"""
        alert = await _seed_alert(db_session)
        service = AlertLifecycleService()
        ok1, _, _ = await service.acknowledge_alert(db_session, alert.id, user_id=1)
        assert ok1 is True
        ok2, msg, _ = await service.close_alert(db_session, alert.id, user_id=1)
        assert ok2 is False
        assert "Invalid transition" in msg

    async def test_full_lifecycle_chain(self, db_session: AsyncSession) -> None:
        """完整生命周期 TRIGGERED -> ACK -> RESOLVED -> CLOSED -> TRIGGERED(reopen)"""
        alert = await _seed_alert(db_session)
        service = AlertLifecycleService()
        ok, _, a = await service.acknowledge_alert(db_session, alert.id, user_id=1)
        assert ok and a.acknowledged_at is not None
        ok, _, a = await service.resolve_alert(db_session, alert.id, user_id=1)
        assert ok and a.resolved_at is not None
        ok, _, a = await service.close_alert(db_session, alert.id, user_id=1)
        assert ok and a.closed_at is not None
        ok, _, a = await service.reopen_alert(db_session, alert.id, user_id=1)
        assert ok and a.closed_at is None and a.resolved_at is None
