from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import event_bus
from app.models.monitoring import (
    DriftAlert,
    DriftSeverity,
    MonitoringEventType,
    MonitoringLog,
)

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
    DriftSeverity.CRITICAL: [
        NotificationChannel.SMS,
        NotificationChannel.EMAIL,
        NotificationChannel.IN_APP,
    ],
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

    已知限制 (ISS-044):
    - ``_transition_history`` 仅存于进程内存，多实例部署下各实例不共享，
      转换历史会丢失且 ``get_severity_stats`` 统计不准。
    - 生产多实例场景需迁移至 Redis 或 DB（如复用 MonitoringLog 表）持久化，
      由共享存储统一维护状态转换记录。
    - TODO(多实例): 实现状态转换历史的 Redis 持久化（key: alert:transitions:{alert_id}）。
    """

    # Valid state transitions
    # C-Svc-2 修复：CLOSED 状态原设为空集（终态），但 reopen_alert 声明支持
    # 从 CLOSED 重开，且 transition_alert 中已实现 closed_at 清理逻辑，
    # 状态机与实现不一致导致 CLOSED 告警无法重开。补齐 CLOSED -> TRIGGERED 边。
    VALID_TRANSITIONS: dict[AlertStatus, set[AlertStatus]] = {
        AlertStatus.TRIGGERED: {AlertStatus.ACKNOWLEDGED, AlertStatus.RESOLVED},
        AlertStatus.ACKNOWLEDGED: {AlertStatus.RESOLVED, AlertStatus.TRIGGERED},
        AlertStatus.RESOLVED: {AlertStatus.CLOSED, AlertStatus.TRIGGERED},
        AlertStatus.CLOSED: {AlertStatus.TRIGGERED},
    }

    def __init__(self) -> None:
        # L-Svc-1 TODO：_transition_history 仅存于进程内存，多实例部署下各实例不共享，
        # 转换历史会丢失且 get_severity_stats 统计不准。生产多实例场景需迁移至 Redis
        # 或 DB（如复用 MonitoringLog 表）持久化，由共享存储统一维护状态转换记录。
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
        return SEVERITY_NOTIFICATION_MAP.get(
            severity, [NotificationChannel.DAILY_DIGEST]
        )

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
        # BUG-001 修复：添加 with_for_update() 行锁，防止并发 transition_alert 调用
        # 之间出现 TOCTOU 竞态（read-then-write 导致状态被覆盖）。
        # SQLite 静默忽略 FOR UPDATE 子句（无副作用），PostgreSQL/MySQL 加真正的行锁。
        # 注意：涉及数据一致性，需第二人审查。
        result = await db_session.execute(
            select(DriftAlert).where(DriftAlert.id == alert_id).with_for_update()
        )
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
            # H-Svc-3 修复：DateTime 列为 naive，写入前剥离 tzinfo
            alert.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)
        elif target_status == AlertStatus.TRIGGERED:
            # Reopen: 清除 resolved_at、acknowledged_at 和 closed_at
            alert.resolved_at = None
            alert.acknowledged_at = None
            alert.closed_at = None
        elif target_status == AlertStatus.ACKNOWLEDGED:
            # C-03 修复：持久化 ACKNOWLEDGED 状态到数据库，避免服务重启后丢失
            # H-Svc-3 修复：DateTime 列为 naive，写入前剥离 tzinfo
            alert.acknowledged_at = datetime.now(timezone.utc).replace(tzinfo=None)
        elif target_status == AlertStatus.CLOSED:
            # H-5 修复：持久化 CLOSED 状态到数据库，避免服务重启后内存 history 丢失
            # 导致 CLOSED 告警被误判为 RESOLVED
            # H-Svc-3 修复：DateTime 列为 naive，写入前剥离 tzinfo
            alert.closed_at = datetime.now(timezone.utc).replace(tzinfo=None)

        # Record transition (in-memory only)
        self._record_transition(alert_id, current_status, target_status, user_id, note)

        # C-1 修复：将 alert 状态更新与审计日志写入同一事务，单次 commit 保证原子性
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
        # M-11 修复：service 层不内部 commit，避免污染调用方事务。
        # 改用 flush() 将更改刷入 DB（同一事务内可见），由调用方（API 层）统一管理事务提交。
        await db_session.flush()
        await db_session.refresh(alert)

        logger.info(
            "Alert %d transitioned: %s -> %s",
            alert_id,
            current_status.value,
            target_status.value,
        )

        # R-C: 发布事件到 EventBus, 实时更新 Prometheus 指标 (端到端延迟 < 5s)
        # 注意: 此处使用 flush 后的 alert 数据, 实际 commit 由调用方负责.
        # 事件发布采用 fire-and-forget 模式 (put_nowait), 不阻塞业务主流程.
        # 即使后续 commit 失败, 指标略有偏差, 60s 周期轮询会自动修正.
        await self._publish_transition_event(
            alert, current_status, target_status, user_id
        )

        return True, f"Transitioned to {target_status.value}", alert

    async def _publish_transition_event(
        self,
        alert: DriftAlert,
        from_status: AlertStatus,
        to_status: AlertStatus,
        user_id: int | None,
    ) -> None:
        """R-C: 根据目标状态发布对应事件到 EventBus.

        事件类型映射:
        - TRIGGERED (重开): alert.fired
        - RESOLVED: alert.resolved
        - ACKNOWLEDGED: alert.escalated
        - CLOSED: 不发布事件 (终态, 无需实时指标)
        """
        # BUG-002 修复: DriftSeverity(str, Enum) 的 .value 返回字符串值.
        # 注意: DB 加载后 severity 可能是 plain str (String 列), 需兼容处理.
        severity = alert.severity or DriftSeverity.MEDIUM
        severity_str = severity.value if hasattr(severity, "value") else str(severity)
        event_data: dict[str, Any] = {
            "alert_id": alert.id,
            "severity": severity_str,
            "model_version": alert.model_version,
            "from_status": from_status.value,
            "to_status": to_status.value,
            "user_id": user_id,
            "fired_at": datetime.now(timezone.utc).isoformat(),
        }

        if to_status == AlertStatus.TRIGGERED:
            await event_bus.publish("alert.fired", event_data)
        elif to_status == AlertStatus.RESOLVED:
            await event_bus.publish("alert.resolved", event_data)
        elif to_status == AlertStatus.ACKNOWLEDGED:
            await event_bus.publish("alert.escalated", event_data)
        # CLOSED 状态不发布事件 (终态)

    def _determine_current_status(self, alert: DriftAlert) -> AlertStatus:
        """Determine current alert status from database state.

        C-03/H-5 修复：从数据库持久化字段推断状态，不依赖内存 history。
        优先级：CLOSED > RESOLVED > ACKNOWLEDGED > TRIGGERED
        """
        # H-5 修复：从数据库 closed_at 字段判断 CLOSED 状态，不依赖内存 history
        if alert.closed_at is not None:
            return AlertStatus.CLOSED
        if alert.resolved_at is not None:
            return AlertStatus.RESOLVED
        # C-03 修复：从数据库 acknowledged_at 字段判断 ACKNOWLEDGED 状态
        if alert.acknowledged_at is not None:
            return AlertStatus.ACKNOWLEDGED
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
        channels = self.get_notification_channels(
            alert.severity or DriftSeverity.MEDIUM
        )
        # BUG-002 修复：使用 .value 避免 DriftSeverity(str, Enum) 的 str() 返回
        # "DriftSeverity.CRITICAL" 这种 repr 形式（Python 3.11+ 行为变化）。
        severity_value = (alert.severity or DriftSeverity.MEDIUM).value
        title = f"[{severity_value}] Drift Alert: {alert.drift_type}"
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
        """统计各状态的告警数量（基于内存转换历史）。

        L-16 修复：原方法为空实现（循环体仅有 pass，始终返回空 dict）。
        现实现基本统计：按告警最近一次状态（排除 CLOSED）计数。
        注意：内存历史中不存储 severity 字段（severity 位于 DriftAlert 模型），
        故此处按状态统计；生产环境需从数据库按 DriftAlert.severity 统计。
        """
        stats: dict[str, int] = {}
        for history in self._transition_history.values():
            if not history:
                continue
            last_status = history[-1].to_status
            # 仅统计未关闭的告警
            if last_status == AlertStatus.CLOSED:
                continue
            status_key = last_status.value
            stats[status_key] = stats.get(status_key, 0) + 1
        return stats


# Global service instance
alert_lifecycle_service = AlertLifecycleService()
