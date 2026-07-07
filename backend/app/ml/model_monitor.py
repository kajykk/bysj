"""
Model Monitoring Integration Module.

Integrates drift detection into the model engine:
- Periodic drift detection triggers
- Performance logging and alerting
- Model health checks
- Monitoring dashboard data collection
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from app.ml.drift_detector import DriftDetector, DriftReport

logger = logging.getLogger(__name__)

# Default monitoring configuration
DEFAULT_MONITOR_CONFIG = {
    "drift_check_interval_minutes": 60,
    "performance_check_interval_minutes": 1440,  # Daily
    "alert_threshold_consecutive_drifts": 3,
    "max_history_size": 1000,
}


@dataclass
class MonitoringRecord:
    """Single monitoring record."""

    timestamp: str
    model_name: str
    model_version: str
    metrics: dict[str, float]
    drift_detected: bool
    drift_details: dict[str, Any] | None = None


@dataclass
class ModelHealth:
    """Model health status."""

    status: str  # "healthy", "degraded", "critical"
    last_check: str
    consecutive_drifts: int
    total_predictions: int
    average_latency_ms: float
    error_rate: float
    recommendations: list[str] = field(default_factory=list)


class ModelMonitor:
    """Model monitoring integration.

    Args:
        model_name: Name of the model being monitored.
        model_version: Version of the model.
        config: Monitoring configuration.
        drift_detector: Drift detector instance.
    """

    def __init__(
        self,
        model_name: str,
        model_version: str,
        config: dict[str, Any] | None = None,
        drift_detector: DriftDetector | None = None,
    ):
        """Initialize model monitor."""
        self.model_name = model_name
        self.model_version = model_version
        self.config = config or DEFAULT_MONITOR_CONFIG.copy()
        self.drift_detector = drift_detector or DriftDetector()

        # Monitoring history
        self.history: list[MonitoringRecord] = []
        self.consecutive_drifts = 0
        self.total_predictions = 0
        self.latency_history: list[float] = []
        self.error_count = 0
        # M-6 修复：保护 record_prediction/check_drift 中的状态修改，避免多线程竞态
        self._lock = threading.Lock()

        logger.info(
            "ModelMonitor initialized: model=%s, version=%s",
            model_name,
            model_version,
        )

    def record_prediction(
        self,
        latency_ms: float,
        prediction: float | None = None,
        error: bool = False,
    ) -> None:
        """Record a prediction event.

        Args:
            latency_ms: Prediction latency in milliseconds.
            prediction: Prediction value (optional).
            error: Whether an error occurred.
        """
        # M-6 修复：加锁保护状态修改，避免多线程并发导致计数错误或列表损坏
        with self._lock:
            self.total_predictions += 1
            self.latency_history.append(latency_ms)

            if error:
                self.error_count += 1

            # Keep history bounded
            max_size = self.config.get("max_history_size", 1000)
            if len(self.latency_history) > max_size:
                self.latency_history = self.latency_history[-max_size:]

    def check_drift(
        self,
        current_data: dict[str, np.ndarray] | None = None,
        current_predictions: np.ndarray | None = None,
        reference_predictions: np.ndarray | None = None,
        baseline_metrics: dict[str, float] | None = None,
        current_metrics: dict[str, float] | None = None,
    ) -> DriftReport:
        """Run drift detection check.

        Args:
            current_data: Current feature data.
            current_predictions: Current prediction distribution.
            reference_predictions: Reference prediction distribution.
            baseline_metrics: Baseline performance metrics.
            current_metrics: Current performance metrics.

        Returns:
            DriftReport with drift detection results.
        """
        report = self.drift_detector.detect_drift(
            current_data=current_data,
            current_predictions=current_predictions,
            reference_predictions=reference_predictions,
            baseline_metrics=baseline_metrics,
            current_metrics=current_metrics,
        )

        # C-3 修复：check_drift 的状态修改需要与 record_prediction 使用同一把锁，
        # 否则并发调用会导致 consecutive_drifts 计数错误、history 列表损坏。
        with self._lock:
            # Update consecutive drift counter
            if report.is_drift_detected:
                self.consecutive_drifts += 1
                logger.warning(
                    "Drift detected (consecutive: %d)",
                    self.consecutive_drifts,
                )
            else:
                self.consecutive_drifts = 0

            # Record monitoring event
            record = MonitoringRecord(
                timestamp=report.timestamp,
                model_name=self.model_name,
                model_version=self.model_version,
                metrics=current_metrics or {},
                drift_detected=report.is_drift_detected,
                drift_details=report.to_dict(),
            )
            self.history.append(record)

            # Keep history bounded
            max_size = self.config.get("max_history_size", 1000)
            if len(self.history) > max_size:
                self.history = self.history[-max_size:]

        return report

    def get_health_status(self) -> ModelHealth:
        """Get current model health status.

        Returns:
            ModelHealth with current status.
        """
        # H-ML-3 修复：在锁内拷贝共享状态，避免读到部分更新
        # record_prediction() 在锁内修改 latency_history（替换列表引用），
        # 若在锁外直接 np.mean(self.latency_history) 读取，可能读到部分更新的列表
        with self._lock:
            latency = list(self.latency_history)
            error_count = self.error_count
            total_predictions = self.total_predictions
            consecutive_drifts = self.consecutive_drifts

        # Calculate average latency（锁外计算，避免长时间持锁）
        avg_latency = np.mean(latency) if latency else 0.0

        # Calculate error rate
        error_rate = error_count / total_predictions if total_predictions > 0 else 0.0

        # Determine status
        alert_threshold = self.config.get("alert_threshold_consecutive_drifts", 3)

        if consecutive_drifts >= alert_threshold:
            status = "critical"
        elif consecutive_drifts > 0:
            status = "degraded"
        else:
            status = "healthy"

        # Generate recommendations
        recommendations = []
        if consecutive_drifts >= alert_threshold:
            recommendations.append("Consider retraining the model")
            recommendations.append("Investigate data distribution changes")
        elif consecutive_drifts > 0:
            recommendations.append("Monitor closely for continued drift")

        if error_rate > 0.01:  # 1% error rate
            recommendations.append("Investigate prediction errors")

        if avg_latency > 200:  # 200ms threshold
            recommendations.append("Investigate latency issues")

        return ModelHealth(
            status=status,
            last_check=time.strftime("%Y-%m-%d %H:%M:%S"),
            consecutive_drifts=consecutive_drifts,
            total_predictions=total_predictions,
            average_latency_ms=avg_latency,
            error_rate=error_rate,
            recommendations=recommendations,
        )

    def get_monitoring_summary(self) -> dict[str, Any]:
        """Get monitoring summary.

        Returns:
            Dictionary with monitoring summary.
        """
        health = self.get_health_status()

        # Calculate drift frequency
        drift_events = sum(1 for r in self.history if r.drift_detected)
        total_checks = len(self.history)
        drift_frequency = drift_events / total_checks if total_checks > 0 else 0.0

        return {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "health_status": health.status,
            "consecutive_drifts": health.consecutive_drifts,
            "total_predictions": health.total_predictions,
            "average_latency_ms": health.average_latency_ms,
            "error_rate": health.error_rate,
            "drift_frequency": drift_frequency,
            "total_checks": total_checks,
            "recommendations": health.recommendations,
            "last_check": health.last_check,
        }

    def should_trigger_alert(self) -> bool:
        """Check if alert should be triggered.

        Returns:
            True if alert should be triggered.
        """
        alert_threshold = self.config.get("alert_threshold_consecutive_drifts", 3)
        return self.consecutive_drifts >= alert_threshold

    def save_state(self, path: Path | str) -> None:
        """Save monitoring state.

        Args:
            path: Path to save state.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        state = {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "config": self.config,
            "consecutive_drifts": self.consecutive_drifts,
            "total_predictions": self.total_predictions,
            "error_count": self.error_count,
            "latency_history": self.latency_history[-100:],  # Last 100
            "history": [
                {
                    "timestamp": r.timestamp,
                    "drift_detected": r.drift_detected,
                    "metrics": r.metrics,
                }
                for r in self.history[-100:]  # Last 100
            ],
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

        logger.info("Saved monitoring state to %s", path)

    @classmethod
    def load_state(cls, path: Path | str) -> "ModelMonitor":
        """Load monitoring state.

        Args:
            path: Path to state file.

        Returns:
            ModelMonitor instance.
        """
        path = Path(path)
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)

        monitor = cls(
            model_name=state["model_name"],
            model_version=state["model_version"],
            config=state.get("config", DEFAULT_MONITOR_CONFIG),
        )

        monitor.consecutive_drifts = state.get("consecutive_drifts", 0)
        monitor.total_predictions = state.get("total_predictions", 0)
        monitor.error_count = state.get("error_count", 0)
        monitor.latency_history = state.get("latency_history", [])

        # 恢复 history，确保 drift_frequency 等基于历史的统计在重启后仍然准确
        saved_history = state.get("history", [])
        monitor.history = [
            MonitoringRecord(
                timestamp=h["timestamp"],
                model_name=state["model_name"],
                model_version=state["model_version"],
                metrics=h.get("metrics", {}),
                drift_detected=h.get("drift_detected", False),
            )
            for h in saved_history
        ]

        return monitor
