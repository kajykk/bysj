"""Alerting engine for monitoring and notifications.

.. note::
    v1.34+ 生产告警已迁移至 ``app.services.alert_lifecycle_service``、
    ``app.tasks.alerts`` 与 ``app.monitoring.{am_sync, escalation, notifier}``。
    本引擎保留为**规则评估的纯逻辑参考实现**：不再内置阻塞式 webhook 通知
    （原 ``_send_notification`` 使用同步 ``requests.post`` + ``time.sleep`` 重试，
    会阻塞调用线程且与 async 告警管线重复，已于 N2 移除）。
    如需对接外部通知，请使用 ``app.monitoring.notifier``，或通过 ``notify``
    回调注入纯函数实现。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class MetricsSnapshot:
    """Snapshot of system metrics for alert evaluation."""

    error_rate: float = 0.0
    avg_response_time: float = 0.0
    p95_response_time: float = 0.0
    p99_response_time: float = 0.0
    memory_usage_percent: float = 0.0
    disk_usage_percent: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class AlertRule:
    """Alert rule definition."""

    name: str
    condition: Callable[[MetricsSnapshot], bool]
    severity: str  # P0, P1, P2
    cooldown_seconds: int = 300  # 5 minutes default
    description: str = ""


@dataclass
class AlertEvent:
    """Triggered alert event."""

    rule_name: str
    severity: str
    message: str
    timestamp: float = field(default_factory=time.time)
    resolved: bool = False


class AlertingEngine:
    """Engine for evaluating alert rules (纯规则评估，不发起阻塞 I/O).

    N2: 原内置的同步 webhook 通知（``_send_notification``，``requests.post`` +
    ``time.sleep`` 指数退避重试）已移除——它从未被生产代码实例化，且会阻塞
    调用线程。如需在规则触发时通知，通过构造函数注入 ``notify`` 回调
    （纯函数，由调用方决定异步/线程池等执行模型）。
    """

    def __init__(
        self,
        notify: Callable[[AlertRule, AlertEvent], None] | None = None,
    ) -> None:
        self.rules: list[AlertRule] = []
        self._last_triggered: dict[str, float] = {}
        # N2: 注入式通知回调；None 表示不通知。
        self._notify = notify

    def add_rule(self, rule: AlertRule) -> None:
        """Add an alert rule."""
        self.rules.append(rule)

    def evaluate(self, metrics: MetricsSnapshot) -> list[AlertEvent]:
        """Evaluate all rules against current metrics.

        Args:
            metrics: Current system metrics snapshot.

        Returns:
            List of triggered alert events.
        """
        triggered = []
        now = time.time()

        for rule in self.rules:
            if not rule.condition(metrics):
                continue

            # Check cooldown
            last_triggered = self._last_triggered.get(rule.name, 0)
            if now - last_triggered < rule.cooldown_seconds:
                continue

            self._last_triggered[rule.name] = now

            event = AlertEvent(
                rule_name=rule.name,
                severity=rule.severity,
                message=f"{rule.name}: {rule.description}",
                timestamp=now,
            )
            triggered.append(event)
            if self._notify is not None:
                self._notify(rule, event)

        return triggered


def create_default_rules() -> list[AlertRule]:
    """Create default alert rules.

    Returns:
        List of default alert rules.
    """
    return [
        AlertRule(
            name="error_rate_spike",
            condition=lambda m: m.error_rate > 0.05,
            severity="P0",
            cooldown_seconds=300,
            description="5分钟内错误率超过 5%",
        ),
        AlertRule(
            name="slow_request_p99",
            condition=lambda m: m.p99_response_time > 3.0,
            severity="P1",
            cooldown_seconds=600,
            description="P99 响应时间超过 3 秒",
        ),
        AlertRule(
            name="high_memory_usage",
            condition=lambda m: m.memory_usage_percent > 85,
            severity="P1",
            cooldown_seconds=300,
            description="内存使用率超过 85%",
        ),
        AlertRule(
            name="low_disk_space",
            condition=lambda m: m.disk_usage_percent > 90,
            severity="P2",
            cooldown_seconds=3600,
            description="磁盘使用率超过 90%",
        ),
    ]
