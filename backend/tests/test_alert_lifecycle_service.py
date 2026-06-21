from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring import DriftAlert, DriftSeverity
from app.services.alert_lifecycle_service import (
    AlertLifecycleService,
    AlertStatus,
    NotificationChannel,
    SEVERITY_NOTIFICATION_MAP,
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
        assert service.is_valid_transition(AlertStatus.TRIGGERED, AlertStatus.ACKNOWLEDGED) is True
        assert service.is_valid_transition(AlertStatus.TRIGGERED, AlertStatus.RESOLVED) is True
        assert service.is_valid_transition(AlertStatus.ACKNOWLEDGED, AlertStatus.RESOLVED) is True
        assert service.is_valid_transition(AlertStatus.RESOLVED, AlertStatus.CLOSED) is True

    def test_invalid_transitions(self) -> None:
        """验证无效状态流转"""
        service = AlertLifecycleService()
        assert service.is_valid_transition(AlertStatus.TRIGGERED, AlertStatus.CLOSED) is False
        assert service.is_valid_transition(AlertStatus.CLOSED, AlertStatus.TRIGGERED) is False
        assert service.is_valid_transition(AlertStatus.ACKNOWLEDGED, AlertStatus.CLOSED) is False

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
        service._record_transition(1, AlertStatus.TRIGGERED, AlertStatus.ACKNOWLEDGED, user_id=5, note="investigating")
        history = service.get_transition_history(1)
        assert len(history) == 1
        assert history[0]["from"] == "TRIGGERED"
        assert history[0]["to"] == "ACKNOWLEDGED"
        assert history[0]["user_id"] == 5

    def test_determine_current_status_triggered(self) -> None:
        """验证确定当前状态: TRIGGERED"""
        service = AlertLifecycleService()
        alert = DriftAlert(id=1, drift_type="feature_drift", severity=DriftSeverity.MEDIUM)
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
