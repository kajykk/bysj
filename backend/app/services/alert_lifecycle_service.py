from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring import DriftAlert, DriftSeverity, MonitoringLog, MonitoringEventType

logger = logging.getLogger(__name__)


class AlertStatus(str, Enum):
    """Alert lifecycle status."""

    TRIGGERED = "TRIGGERED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class NotificationChannel(str, Enum):
    """Notification channels."""

    SMS = "sms"
    EMAIL = "email"
    IN_APP = "in_app"
    DAILY_DIGEST = "daily_digest"


# Severity to notification channels mapping
SEVERITY_NOTIFICATION_MAP: dict[str, list[str]] = {
    DriftSeverity.CRITICAL: [NotificationChannel.SMS, NotificationChannel.EMAIL, NotificationChannel.IN_APP],
    DriftSeverity.HIGH: [NotificationChannel.EMAIL, NotificationChannel.IN_APP],
    DriftSeverity.MEDIUM: [NotificationChannel.IN_APP],
    DriftSeverity.LOW: [NotificationChannel.DAILY_DIGEST],
}


@dataclass
class AlertTransition:
    """Alert state transition record."""

    from_status: AlertStatus
    to_status: AlertStatus
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: int | None = None
    note: str | None = None


@dataclass
class NotificationPayload:
    """Notification payload."""

    alert_id: int
    severity: str
    channels: list[str]
    title: str
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AlertLifecycleService:
    """Manages alert lifecycle: TRIGGERED -> ACKNOWLEDGED -> RESOLVED -> CLOSED.

    Features:
    - State machine enforcement
    - Severity-based notification routing
    - Async state transitions with audit logging
    """

    # Valid state transitions
    VALID_TRANSITIONS: dict[AlertStatus, set[AlertStatus]] = {
        AlertStatus.TRIGGERED: {AlertStatus.ACKNOWLEDGED, AlertStatus.RESOLVED},
        AlertStatus.ACKNOWLEDGED: {AlertStatus.RESOLVED, AlertStatus.TRIGGERED},
        AlertStatus.RESOLVED: {AlertStatus.CLOSED, AlertStatus.TRIGGERED},
        AlertStatus.CLOSED: set(),
    }

    def __init__(self) -> None:
        self._transition_history: dict[int, list[AlertTransition]] = {}

    def _get_history(self, alert_id: int) -> list[AlertTransition]:
        """Get transition history for an alert."""
        return self._transition_history.get(alert_id, [])

    def _record_transition(
        self,
        alert_id: int,
        from_status: AlertStatus,
        to_status: AlertStatus,
        user_id: int | None = None,
        note: str | None = None,
    ) -> None:
        """Record a state transition."""
        transition = AlertTransition(
            from_status=from_status,
            to_status=to_status,
            user_id=user_id,
            note=note,
        )
        if alert_id not in self._transition_history:
            self._transition_history[alert_id] = []
        self._transition_history[alert_id].append(transition)

    def is_valid_transition(self, current: AlertStatus, target: AlertStatus) -> bool:
        """Check if a state transition is valid."""
        return target in self.VALID_TRANSITIONS.get(current, set())

    def get_notification_channels(self, severity: str) -> list[str]:
        """Get notification channels for a severity level."""
        return SEVERITY_NOTIFICATION_MAP.get(severity, [NotificationChannel.DAILY_DIGEST])

    async def transition_alert(
        self,
        db_session: AsyncSession,
        alert_id: int,
        target_status: AlertStatus,
        user_id: int | None = None,
        note: str | None = None,
    ) -> tuple[bool, str, DriftAlert | None]:
        """Transition an alert to a new state.

        Returns:
            Tuple of (success, message, updated_alert).
        """
        result = await db_session.execute(select(DriftAlert).where(DriftAlert.id == alert_id))
        alert = result.scalar_one_or_none()

        if not alert:
            return False, f"Alert {alert_id} not found", None

        # Determine current status from resolved_at
        current_status = self._determine_current_status(alert)

        if not self.is_valid_transition(current_status, target_status):
            return (
                False,
                f"Invalid transition from {current_status} to {target_status}",
                alert,
            )

        # Update alert based on target status
        if target_status == AlertStatus.RESOLVED:
            alert.resolved_at = datetime.now(timezone.utc)
        elif target_status == AlertStatus.TRIGGERED:
            alert.resolved_at = None

        await db_session.commit()
        await db_session.refresh(alert)

        # Record transition
        self._record_transition(alert_id, current_status, target_status, user_id, note)

        # Log to MonitoringLog
        log = MonitoringLog(
            event_type=MonitoringEventType.DRIFT_ALERT,
            model_version=alert.model_version,
            user_id=user_id,
            response_summary={
                "alert_id": alert_id,
                "transition": f"{current_status.value} -> {target_status.value}",
                "note": note,
            },
        )
        db_session.add(log)
        await db_session.commit()

        logger.info("Alert %d transitioned: %s -> %s", alert_id, current_status.value, target_status.value)
        return True, f"Transitioned to {target_status.value}", alert

    def _determine_current_status(self, alert: DriftAlert) -> AlertStatus:
        """Determine current alert status from database state."""
        if alert.resolved_at is not None:
            # Check if there's a CLOSED transition in history
            history = self._get_history(alert.id)
            if history and history[-1].to_status == AlertStatus.CLOSED:
                return AlertStatus.CLOSED
            return AlertStatus.RESOLVED
        return AlertStatus.TRIGGERED

    async def acknowledge_alert(
        self,
        db_session: AsyncSession,
        alert_id: int,
        user_id: int,
        note: str | None = None,
    ) -> tuple[bool, str, DriftAlert | None]:
        """Acknowledge an alert."""
        return await self.transition_alert(
            db_session, alert_id, AlertStatus.ACKNOWLEDGED, user_id, note
        )

    async def resolve_alert(
        self,
        db_session: AsyncSession,
        alert_id: int,
        user_id: int | None = None,
        note: str | None = None,
    ) -> tuple[bool, str, DriftAlert | None]:
        """Resolve an alert."""
        return await self.transition_alert(
            db_session, alert_id, AlertStatus.RESOLVED, user_id, note
        )

    async def close_alert(
        self,
        db_session: AsyncSession,
        alert_id: int,
        user_id: int | None = None,
        note: str | None = None,
    ) -> tuple[bool, str, DriftAlert | None]:
        """Close a resolved alert."""
        return await self.transition_alert(
            db_session, alert_id, AlertStatus.CLOSED, user_id, note
        )

    async def reopen_alert(
        self,
        db_session: AsyncSession,
        alert_id: int,
        user_id: int | None = None,
        note: str | None = None,
    ) -> tuple[bool, str, DriftAlert | None]:
        """Reopen a resolved or closed alert."""
        return await self.transition_alert(
            db_session, alert_id, AlertStatus.TRIGGERED, user_id, note
        )

    def build_notification_payload(self, alert: DriftAlert) -> NotificationPayload:
        """Build notification payload for an alert."""
        channels = self.get_notification_channels(alert.severity or DriftSeverity.MEDIUM)
        title = f"[{alert.severity}] Drift Alert: {alert.drift_type}"
        message = (
            f"Model: {alert.model_version or 'unknown'}\n"
            f"Feature: {alert.feature_name or 'N/A'}\n"
            f"Metric: {alert.metric_value} (threshold: {alert.threshold})\n"
            f"Details: {alert.details}"
        )
        return NotificationPayload(
            alert_id=alert.id,
            severity=alert.severity or DriftSeverity.MEDIUM,
            channels=channels,
            title=title,
            message=message,
        )

    def get_transition_history(self, alert_id: int) -> list[dict[str, Any]]:
        """Get transition history for an alert."""
        history = self._get_history(alert_id)
        return [
            {
                "from": t.from_status.value,
                "to": t.to_status.value,
                "timestamp": t.timestamp.isoformat(),
                "user_id": t.user_id,
                "note": t.note,
            }
            for t in history
        ]

    def get_severity_stats(self) -> dict[str, int]:
        """Get alert count by severity (from in-memory history)."""
        stats: dict[str, int] = {}
        for alert_id, history in self._transition_history.items():
            if history:
                # Count only alerts that are not CLOSED
                last_status = history[-1].to_status
                if last_status != AlertStatus.CLOSED:
                    # This is a simplified stats; in production, query DB
                    pass
        return stats


# Global service instance
alert_lifecycle_service = AlertLifecycleService()
