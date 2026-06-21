from __future__ import annotations

import warnings

import numpy as np
import pytest

from app.ml.drift_detector import DriftDetector


class TestDriftDetectorBoundary:
    """T-BE-012: 漂移检测边界情况单元测试"""

    def test_ks_test_empty_reference(self) -> None:
        """验证空 reference 数组不抛异常"""
        detector = DriftDetector()
        result = detector._approximate_ks_test(np.array([]), np.array([1, 2, 3]))
        assert result["statistic"] == 0.0
        assert result["p_value"] == 1.0
        assert result["is_drift"] is False
        assert result.get("error") == "empty_array"

    def test_ks_test_empty_current(self) -> None:
        """验证空 current 数组不抛异常"""
        detector = DriftDetector()
        result = detector._approximate_ks_test(np.array([1, 2, 3]), np.array([]))
        assert result["statistic"] == 0.0
        assert result["p_value"] == 1.0
        assert result["is_drift"] is False
        assert result.get("error") == "empty_array"

    def test_ks_test_single_value_same(self) -> None:
        """验证单值分布相同不抛异常"""
        detector = DriftDetector()
        result = detector._approximate_ks_test(np.array([5.0]), np.array([5.0]))
        assert result["statistic"] == 0.0
        assert result["p_value"] == 1.0
        assert result["is_drift"] is False

    def test_ks_test_single_value_different(self) -> None:
        """验证单值分布不同返回正确结果"""
        detector = DriftDetector()
        result = detector._approximate_ks_test(np.array([5.0]), np.array([10.0]))
        assert result["statistic"] == 1.0
        assert result["p_value"] == 0.0
        assert result["is_drift"] is True

    def test_psi_empty_reference(self) -> None:
        """验证 PSI 空 reference 不抛异常"""
        detector = DriftDetector()
        result = detector.compute_psi(np.array([]), np.array([1, 2, 3]))
        assert result["psi"] == 0.0
        assert result["is_drift"] is False
        assert result.get("error") == "empty_array"

    def test_psi_empty_current(self) -> None:
        """验证 PSI 空 current 不抛异常"""
        detector = DriftDetector()
        result = detector.compute_psi(np.array([1, 2, 3]), np.array([]))
        assert result["psi"] == 0.0
        assert result["is_drift"] is False
        assert result.get("error") == "empty_array"

    def test_psi_single_value_same(self) -> None:
        """验证 PSI 单值相同分布"""
        detector = DriftDetector()
        result = detector.compute_psi(np.array([5.0, 5.0, 5.0]), np.array([5.0, 5.0]))
        assert result["psi"] == 0.0
        assert result["interpretation"] == "no_drift"
        assert result["is_drift"] is False

    def test_psi_single_value_different(self) -> None:
        """验证 PSI 单值不同分布"""
        detector = DriftDetector()
        result = detector.compute_psi(np.array([5.0, 5.0]), np.array([10.0, 10.0]))
        assert result["psi"] == 1.0
        assert result["interpretation"] == "major_drift"
        assert result["is_drift"] is True

    def test_psi_constant_distribution(self) -> None:
        """验证 PSI 常量分布处理"""
        detector = DriftDetector()
        result = detector.compute_psi(np.array([5.0, 5.0, 5.0]), np.array([5.0, 5.0, 5.0]))
        assert result["psi"] == 0.0
        assert result["is_drift"] is False

    def test_psi_no_runtime_warning(self) -> None:
        """验证 PSI 计算不产生 RuntimeWarning"""
        detector = DriftDetector()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            detector.compute_psi(np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0, 3.0]))
            runtime_warnings = [x for x in w if issubclass(x.category, RuntimeWarning)]
            assert len(runtime_warnings) == 0, f"Unexpected RuntimeWarning: {runtime_warnings}"

    def test_ks_test_no_runtime_warning(self) -> None:
        """验证 KS 测试不产生 RuntimeWarning"""
        detector = DriftDetector()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            detector._approximate_ks_test(np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0, 3.0]))
            runtime_warnings = [x for x in w if issubclass(x.category, RuntimeWarning)]
            assert len(runtime_warnings) == 0, f"Unexpected RuntimeWarning: {runtime_warnings}"

    def test_psi_normal_distribution(self) -> None:
        """验证 PSI 正常分布计算正确"""
        detector = DriftDetector()
        np.random.seed(42)
        ref = np.random.normal(0, 1, 1000)
        curr = np.random.normal(0, 1, 1000)
        result = detector.compute_psi(ref, curr)
        assert result["psi"] >= 0.0
        assert result["interpretation"] in ["no_drift", "minor_drift", "moderate_drift", "major_drift"]
        assert "is_drift" in result

    def test_detect_feature_drift_with_empty(self) -> None:
        """验证特征漂移检测处理空数据"""
        detector = DriftDetector()
        detector.set_reference_data({"feature1": np.array([1.0, 2.0, 3.0])})
        result = detector.detect_feature_drift({"feature1": np.array([])})
        assert "feature1" in result
        assert result["feature1"]["ks_test"].get("error") == "empty_array"
        assert result["feature1"]["psi"].get("error") == "empty_array"

    def test_detect_feature_drift_with_constant(self) -> None:
        """验证特征漂移检测处理常量数据"""
        detector = DriftDetector()
        detector.set_reference_data({"feature1": np.array([5.0, 5.0, 5.0])})
        result = detector.detect_feature_drift({"feature1": np.array([5.0, 5.0, 5.0])})
        assert "feature1" in result
        assert result["feature1"]["psi"]["psi"] == 0.0
        assert result["feature1"]["is_drift"] is False
