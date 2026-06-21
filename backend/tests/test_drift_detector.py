"""
Test suite for drift detection functionality.

Tests:
- TC-DRIFT-001: 验证 KS 检验计算
- TC-DRIFT-002: 验证 PSI 计算
- TC-DRIFT-003: 验证特征漂移检测
- TC-DRIFT-004: 验证预测漂移检测
- TC-DRIFT-005: 验证性能漂移检测
- TC-DRIFT-006: 验证漂移报告生成
- TC-DRIFT-007: 验证阈值配置
- TC-DRIFT-008: 验证配置保存与加载
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

from app.ml.drift_detector import DEFAULT_DRIFT_THRESHOLDS, DriftDetector, DriftReport


class TestDriftDetector:
    """Test suite for drift detector."""

    @pytest.fixture
    def detector(self) -> DriftDetector:
        """Create a drift detector with sample reference data."""
        np.random.seed(42)
        reference_data = {
            "feature_1": np.random.normal(0, 1, 1000),
            "feature_2": np.random.normal(5, 2, 1000),
        }
        return DriftDetector(reference_data=reference_data)

    def test_ks_test_no_drift(self, detector: DriftDetector) -> None:
        """TC-DRIFT-001: 验证 KS 检验 - 无漂移."""
        np.random.seed(42)
        reference = np.random.normal(0, 1, 1000)
        current = np.random.normal(0, 1, 1000)

        result = detector.compute_ks_test(reference, current)

        assert "statistic" in result
        assert "p_value" in result
        assert "is_drift" in result

        # Same distribution should not show drift
        assert result["is_drift"] is False

    def test_ks_test_with_drift(self, detector: DriftDetector) -> None:
        """TC-DRIFT-002: 验证 KS 检验 - 有漂移."""
        np.random.seed(42)
        reference = np.random.normal(0, 1, 1000)
        current = np.random.normal(3, 1, 1000)  # Shifted mean

        result = detector.compute_ks_test(reference, current)

        # Shifted distribution should show drift
        assert result["is_drift"] is True
        assert result["p_value"] < 0.05

    def test_psi_no_drift(self, detector: DriftDetector) -> None:
        """TC-DRIFT-003: 验证 PSI - 无漂移."""
        np.random.seed(42)
        reference = np.random.normal(0, 1, 1000)
        current = np.random.normal(0, 1, 1000)

        result = detector.compute_psi(reference, current)

        assert "psi" in result
        assert "interpretation" in result
        assert "is_drift" in result

        # Same distribution should have low PSI
        assert result["psi"] < 0.1
        assert result["is_drift"] is False

    def test_psi_with_drift(self, detector: DriftDetector) -> None:
        """TC-DRIFT-004: 验证 PSI - 有漂移."""
        np.random.seed(42)
        reference = np.random.normal(0, 1, 1000)
        current = np.random.normal(5, 2, 1000)  # Different distribution

        result = detector.compute_psi(reference, current)

        # Different distribution should have high PSI
        assert result["psi"] > 0.25
        assert result["is_drift"] is True

    def test_feature_drift_detection(self, detector: DriftDetector) -> None:
        """TC-DRIFT-005: 验证特征漂移检测."""
        np.random.seed(42)
        current_data = {
            "feature_1": np.random.normal(0, 1, 1000),  # No drift
            "feature_2": np.random.normal(10, 2, 1000),  # Drift
        }

        results = detector.detect_feature_drift(current_data)

        assert "feature_1" in results
        assert "feature_2" in results

        # feature_1 should not show drift
        assert results["feature_1"]["is_drift"] is False

        # feature_2 should show drift
        assert results["feature_2"]["is_drift"] is True

    def test_prediction_drift_detection(self, detector: DriftDetector) -> None:
        """TC-DRIFT-006: 验证预测漂移检测."""
        np.random.seed(42)
        reference_preds = np.random.uniform(0, 1, 1000)
        current_preds = np.random.uniform(0.5, 1, 1000)  # Shifted

        result = detector.detect_prediction_drift(reference_preds, current_preds)

        assert "ks_test" in result
        assert "psi" in result
        assert "is_drift" in result

    def test_performance_drift_detection(self, detector: DriftDetector) -> None:
        """TC-DRIFT-007: 验证性能漂移检测."""
        baseline_metrics = {
            "f1": 0.90,
            "accuracy": 0.95,
        }
        current_metrics = {
            "f1": 0.85,  # 5.5% drop
            "accuracy": 0.94,  # 1% drop
        }

        result = detector.detect_performance_drift(baseline_metrics, current_metrics)

        assert "performance_changes" in result
        assert "is_degraded" in result

        # F1 dropped more than 5%, should be degraded
        assert result["performance_changes"]["f1"]["is_degraded"] is True

        # Accuracy dropped less than 5%, should not be degraded
        assert result["performance_changes"]["accuracy"]["is_degraded"] is False

    def test_drift_report(self, detector: DriftDetector) -> None:
        """TC-DRIFT-008: 验证漂移报告生成."""
        np.random.seed(42)
        current_data = {
            "feature_1": np.random.normal(0, 1, 100),
            "feature_2": np.random.normal(10, 2, 100),
        }

        report = detector.detect_drift(current_data=current_data)

        assert isinstance(report, DriftReport)
        assert report.is_drift_detected is True
        assert report.timestamp is not None
        assert "feature_1" in report.feature_drift
        assert "feature_2" in report.feature_drift

    def test_threshold_configuration(self) -> None:
        """TC-DRIFT-009: 验证阈值配置."""
        custom_thresholds = {
            "ks_test": 0.01,
            "psi": 0.1,
            "performance_drop": 0.02,
        }

        detector = DriftDetector(thresholds=custom_thresholds)

        assert detector.thresholds["ks_test"] == 0.01
        assert detector.thresholds["psi"] == 0.1
        assert detector.thresholds["performance_drop"] == 0.02

    def test_config_save_load(self, tmp_path: Path) -> None:
        """TC-DRIFT-010: 验证配置保存与加载."""
        detector = DriftDetector(thresholds=DEFAULT_DRIFT_THRESHOLDS)

        config_path = tmp_path / "drift_config.json"
        detector.save_config(config_path)

        assert config_path.exists()

        loaded_detector = DriftDetector.load_config(config_path)

        assert loaded_detector.thresholds == detector.thresholds

    def test_empty_reference_data(self) -> None:
        """TC-DRIFT-011: 验证空参考数据处理."""
        detector = DriftDetector()

        current_data = {
            "feature_1": np.random.normal(0, 1, 100),
        }

        results = detector.detect_feature_drift(current_data)

        # Should return empty results since no reference data
        assert len(results) == 0

    def test_report_to_dict(self, detector: DriftDetector) -> None:
        """TC-DRIFT-012: 验证报告转字典."""
        report = detector.detect_drift()

        report_dict = report.to_dict()

        assert "feature_drift" in report_dict
        assert "prediction_drift" in report_dict
        assert "performance_drift" in report_dict
        assert "is_drift_detected" in report_dict
        assert "timestamp" in report_dict
