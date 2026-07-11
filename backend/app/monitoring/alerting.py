"""Alerting engine for monitoring and notifications."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Callable

import requests

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
    """Engine for evaluating alert rules and sending notifications."""

    def __init__(self):
        self.rules: list[AlertRule] = []
        self._last_triggered: dict[str, float] = {}
        self._webhook_url = os.getenv("ALERT_WEBHOOK_URL")

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
            self._send_notification(rule, event)

        return triggered

    def _send_notification(self, rule: AlertRule, event: AlertEvent) -> None:
        """Send alert notification via webhook.

        Args:
            rule: The triggered rule.
            event: The alert event.
        """
        if not self._webhook_url:
            logger.info("No webhook configured, skipping notification for %s", rule.name)
            return

        payload = {
            "rule": rule.name,
            "severity": rule.severity,
            "message": event.message,
            "timestamp": event.timestamp,
        }

        # Exponential backoff retry (max 3 attempts)
        for attempt in range(3):
            try:
                resp = requests.post(
                    self._webhook_url,
                    json=payload,
                    timeout=5,
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code < 500:
                    logger.info("Alert notification sent for %s (status: %s)", rule.name, resp.status_code)
                    return
            except Exception as e:
                logger.warning("Alert webhook attempt %d failed: %s", attempt + 1, e)
                time.sleep(2 ** attempt)

        logger.error("Failed to send alert notification for %s after 3 attempts", rule.name)


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
