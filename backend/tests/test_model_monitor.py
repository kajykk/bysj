"""
Test suite for model monitoring integration.

Tests:
- TC-MON-001: 验证预测记录
- TC-MON-002: 验证漂移检测触发
- TC-MON-003: 验证健康状态计算
- TC-MON-004: 验证告警触发
- TC-MON-005: 验证监控摘要
- TC-MON-006: 验证状态保存与加载
- TC-MON-007: 验证连续漂移计数
- TC-MON-008: 验证延迟历史
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# Add backend to path
backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.ml.model_monitor import DEFAULT_MONITOR_CONFIG, ModelMonitor


class TestModelMonitor:
    """Test suite for model monitor."""

    @pytest.fixture
    def monitor(self) -> ModelMonitor:
        """Create a model monitor for testing."""
        return ModelMonitor(
            model_name="test_model",
            model_version="1.0.0",
        )

    def test_record_prediction(self, monitor: ModelMonitor) -> None:
        """TC-MON-001: 验证预测记录."""
        monitor.record_prediction(latency_ms=10.0, prediction=0.5)
        monitor.record_prediction(latency_ms=15.0, prediction=0.8)

        assert monitor.total_predictions == 2
        assert len(monitor.latency_history) == 2
        assert monitor.error_count == 0

    def test_record_prediction_with_error(self, monitor: ModelMonitor) -> None:
        """TC-MON-002: 验证错误预测记录."""
        monitor.record_prediction(latency_ms=10.0, error=True)

        assert monitor.total_predictions == 1
        assert monitor.error_count == 1

    def test_drift_detection(self, monitor: ModelMonitor) -> None:
        """TC-MON-003: 验证漂移检测触发."""
        np.random.seed(42)
        reference_data = {"feature_1": np.random.normal(0, 1, 100)}
        monitor.drift_detector.set_reference_data(reference_data)

        # No drift - use same data to ensure no drift
        current_data = {"feature_1": reference_data["feature_1"].copy()}
        report = monitor.check_drift(current_data=current_data)

        assert report.is_drift_detected is False
        assert monitor.consecutive_drifts == 0

    def test_consecutive_drift_counting(self, monitor: ModelMonitor) -> None:
        """TC-MON-004: 验证连续漂移计数."""
        np.random.seed(42)
        reference_data = {"feature_1": np.random.normal(0, 1, 100)}
        monitor.drift_detector.set_reference_data(reference_data)

        # Simulate consecutive drifts
        for _ in range(3):
            current_data = {"feature_1": np.random.normal(5, 1, 100)}  # Drifted
            monitor.check_drift(current_data=current_data)

        assert monitor.consecutive_drifts == 3

    def test_drift_reset(self, monitor: ModelMonitor) -> None:
        """TC-MON-005: 验证漂移计数重置."""
        np.random.seed(42)
        reference_data = {"feature_1": np.random.normal(0, 1, 100)}
        monitor.drift_detector.set_reference_data(reference_data)

        # Drift
        current_data = {"feature_1": np.random.normal(5, 1, 100)}
        monitor.check_drift(current_data=current_data)
        assert monitor.consecutive_drifts == 1

        # No drift - should reset (use same data as reference)
        current_data = {"feature_1": reference_data["feature_1"].copy()}
        monitor.check_drift(current_data=current_data)
        assert monitor.consecutive_drifts == 0

    def test_health_status_healthy(self, monitor: ModelMonitor) -> None:
        """TC-MON-006: 验证健康状态 - 健康."""
        health = monitor.get_health_status()

        assert health.status == "healthy"
        assert health.consecutive_drifts == 0

    def test_health_status_degraded(self, monitor: ModelMonitor) -> None:
        """TC-MON-007: 验证健康状态 - 降级."""
        np.random.seed(42)
        reference_data = {"feature_1": np.random.normal(0, 1, 100)}
        monitor.drift_detector.set_reference_data(reference_data)

        # One drift
        current_data = {"feature_1": np.random.normal(5, 1, 100)}
        monitor.check_drift(current_data=current_data)

        health = monitor.get_health_status()
        assert health.status == "degraded"

    def test_health_status_critical(self, monitor: ModelMonitor) -> None:
        """TC-MON-008: 验证健康状态 - 严重."""
        np.random.seed(42)
        reference_data = {"feature_1": np.random.normal(0, 1, 100)}
        monitor.drift_detector.set_reference_data(reference_data)

        # Multiple consecutive drifts
        for _ in range(3):
            current_data = {"feature_1": np.random.normal(5, 1, 100)}
            monitor.check_drift(current_data=current_data)

        health = monitor.get_health_status()
        assert health.status == "critical"
        assert len(health.recommendations) > 0

    def test_alert_trigger(self, monitor: ModelMonitor) -> None:
        """TC-MON-009: 验证告警触发."""
        np.random.seed(42)
        reference_data = {"feature_1": np.random.normal(0, 1, 100)}
        monitor.drift_detector.set_reference_data(reference_data)

        # Should not trigger initially
        assert monitor.should_trigger_alert() is False

        # Trigger 3 consecutive drifts
        for _ in range(3):
            current_data = {"feature_1": np.random.normal(5, 1, 100)}
            monitor.check_drift(current_data=current_data)

        assert monitor.should_trigger_alert() is True

    def test_monitoring_summary(self, monitor: ModelMonitor) -> None:
        """TC-MON-010: 验证监控摘要."""
        monitor.record_prediction(latency_ms=10.0)
        monitor.record_prediction(latency_ms=15.0)

        summary = monitor.get_monitoring_summary()

        assert summary["model_name"] == "test_model"
        assert summary["model_version"] == "1.0.0"
        assert summary["total_predictions"] == 2
        assert summary["average_latency_ms"] == 12.5

    def test_state_save_load(self, monitor: ModelMonitor, tmp_path: Path) -> None:
        """TC-MON-011: 验证状态保存与加载."""
        monitor.record_prediction(latency_ms=10.0)
        monitor.record_prediction(latency_ms=15.0)

        state_path = tmp_path / "monitor_state.json"
        monitor.save_state(state_path)

        assert state_path.exists()

        loaded_monitor = ModelMonitor.load_state(state_path)

        assert loaded_monitor.model_name == monitor.model_name
        assert loaded_monitor.model_version == monitor.model_version
        assert loaded_monitor.total_predictions == monitor.total_predictions

    def test_latency_history_bound(self, monitor: ModelMonitor) -> None:
        """TC-MON-012: 验证延迟历史边界."""
        # Record many predictions
        for i in range(1100):
            monitor.record_prediction(latency_ms=float(i))

        # Should be bounded
        max_size = DEFAULT_MONITOR_CONFIG["max_history_size"]
        assert len(monitor.latency_history) <= max_size

    def test_error_rate_calculation(self, monitor: ModelMonitor) -> None:
        """TC-MON-013: 验证错误率计算."""
        # 10 predictions, 2 errors
        for i in range(10):
            monitor.record_prediction(latency_ms=10.0, error=(i < 2))

        health = monitor.get_health_status()
        assert health.error_rate == 0.2

    def test_recommendations(self, monitor: ModelMonitor) -> None:
        """TC-MON-014: 验证建议生成."""
        np.random.seed(42)
        reference_data = {"feature_1": np.random.normal(0, 1, 100)}
        monitor.drift_detector.set_reference_data(reference_data)

        # Trigger critical state
        for _ in range(3):
            current_data = {"feature_1": np.random.normal(5, 1, 100)}
            monitor.check_drift(current_data=current_data)

        health = monitor.get_health_status()

        assert "Consider retraining the model" in health.recommendations
        assert "Investigate data distribution changes" in health.recommendations
