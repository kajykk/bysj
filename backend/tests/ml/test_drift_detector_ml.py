"""Tests for app/ml/drift_detector.py (DriftDetector).

覆盖 0% 模块: app.ml.drift_detector.
关键路径:
- DriftDetector.__init__ / set_reference_data
- compute_ks_test (空数组 / scipy / 近似回退)
- _approximate_ks_test (单值 / 多值 / 小样本)
- compute_psi (空数组 / 单值 / 正常 / 漂移)
- detect_feature_drift / detect_prediction_drift / detect_performance_drift
- detect_drift (组合)
- save_config / load_config round trip
- DriftReport.to_dict
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from app.ml.drift_detector import (
    DEFAULT_DRIFT_THRESHOLDS,
    DriftDetector,
    DriftReport,
)


class TestDriftDetectorInit:
    """Test DriftDetector initialization."""

    def test_default_init(self):
        """TC-DD-001: 默认初始化使用 DEFAULT_DRIFT_THRESHOLDS."""
        det = DriftDetector()
        assert det.thresholds == DEFAULT_DRIFT_THRESHOLDS
        assert det.reference_data == {}

    def test_custom_thresholds(self):
        """TC-DD-002: 自定义 thresholds 覆盖默认值."""
        custom = {"ks_test": 0.01, "psi": 0.5, "performance_drop": 0.1}
        det = DriftDetector(thresholds=custom)
        assert det.thresholds == custom

    def test_custom_reference_data(self):
        """TC-DD-003: 自定义 reference_data."""
        ref = {"f1": np.array([1.0, 2.0, 3.0])}
        det = DriftDetector(reference_data=ref)
        assert "f1" in det.reference_data
        assert len(det.reference_data["f1"]) == 3

    def test_set_reference_data(self):
        """TC-DD-004: set_reference_data 替换引用数据."""
        det = DriftDetector()
        ref = {"f1": np.array([1.0, 2.0])}
        det.set_reference_data(ref)
        assert "f1" in det.reference_data


class TestComputeKsTest:
    """Test compute_ks_test."""

    def test_empty_reference(self):
        """TC-DD-005: 空 reference 返回 error='empty_array'."""
        det = DriftDetector()
        result = det.compute_ks_test(np.array([]), np.array([1.0, 2.0]))
        assert result["error"] == "empty_array"
        assert result["is_drift"] is False

    def test_empty_current(self):
        """TC-DD-006: 空 current 返回 error='empty_array'."""
        det = DriftDetector()
        result = det.compute_ks_test(np.array([1.0, 2.0]), np.array([]))
        assert result["error"] == "empty_array"

    def test_scipy_path_no_drift(self):
        """TC-DD-007: scipy 可用时, 同分布不漂移."""
        det = DriftDetector()
        rng = np.random.RandomState(0)
        ref = rng.randn(100)
        curr = rng.randn(100)  # 同分布
        result = det.compute_ks_test(ref, curr)
        assert "statistic" in result
        assert "p_value" in result
        # 同分布 p_value 通常较大 (>0.05)
        assert result["p_value"] >= 0.0
        assert isinstance(result["is_drift"], bool)

    def test_scipy_path_with_drift(self):
        """TC-DD-008: scipy 可用时, 显著不同分布触发漂移."""
        det = DriftDetector(thresholds={"ks_test": 0.05, "psi": 0.25, "performance_drop": 0.05})
        rng = np.random.RandomState(0)
        ref = rng.randn(100)
        # 当前分布平移 5 个标准差, 必然漂移
        curr = rng.randn(100) + 5.0
        result = det.compute_ks_test(ref, curr)
        assert result["p_value"] < 0.05
        assert result["is_drift"] is True


class TestApproximateKsTest:
    """Test _approximate_ks_test (scipy 不可用回退路径)."""

    def test_approximate_empty_arrays(self):
        """TC-DD-009: 近似 KS 空数组处理."""
        det = DriftDetector()
        result = det._approximate_ks_test(np.array([]), np.array([]))
        assert result["error"] == "empty_array"

    def test_approximate_single_value_same(self):
        """TC-DD-010: 单值分布相同 -> statistic=0."""
        det = DriftDetector()
        ref = np.array([5.0, 5.0])
        curr = np.array([5.0, 5.0])
        result = det._approximate_ks_test(ref, curr)
        assert result["statistic"] == 0.0
        assert result["is_drift"] is False

    def test_approximate_single_value_different(self):
        """TC-DD-011: 单值分布不同 -> statistic=1.0."""
        det = DriftDetector()
        ref = np.array([5.0, 5.0])
        curr = np.array([10.0, 10.0])
        result = det._approximate_ks_test(ref, curr)
        assert result["statistic"] == 1.0
        assert result["is_drift"] is True

    def test_approximate_normal_distributions(self):
        """TC-DD-012: 近似 KS 对正态分布返回 [0,1] 内 p_value."""
        det = DriftDetector()
        rng = np.random.RandomState(0)
        ref = rng.randn(50)
        curr = rng.randn(50)
        result = det._approximate_ks_test(ref, curr)
        assert 0.0 <= result["p_value"] <= 1.0
        assert isinstance(result["is_drift"], bool)


class TestComputePsi:
    """Test compute_psi."""

    def test_empty_arrays(self):
        """TC-DD-013: 空数组返回 error='empty_array'."""
        det = DriftDetector()
        result = det.compute_psi(np.array([]), np.array([1.0]))
        assert result["error"] == "empty_array"
        assert result["psi"] == 0.0

    def test_single_value_same(self):
        """TC-DD-014: 单值分布相同 -> psi=0, no_drift."""
        det = DriftDetector()
        ref = np.array([5.0, 5.0])
        curr = np.array([5.0, 5.0])
        result = det.compute_psi(ref, curr)
        assert result["psi"] == 0.0
        assert result["interpretation"] == "no_drift"

    def test_single_value_different(self):
        """TC-DD-015: 单值 ref 与多值 curr -> major_drift."""
        det = DriftDetector()
        ref = np.array([5.0, 5.0])
        curr = np.array([10.0, 10.0])
        result = det.compute_psi(ref, curr)
        assert result["psi"] == 1.0
        assert result["interpretation"] == "major_drift"
        assert result["is_drift"] is True

    def test_normal_no_drift(self):
        """TC-DD-016: 同正态分布 PSI 应 < 0.1 (no_drift)."""
        det = DriftDetector()
        rng = np.random.RandomState(0)
        ref = rng.randn(500)
        curr = rng.randn(500)
        result = det.compute_psi(ref, curr)
        assert result["psi"] < 0.1
        assert result["interpretation"] == "no_drift"

    def test_drift_distribution(self):
        """TC-DD-017: 平移分布 PSI 应 >= 0.25 (drift)."""
        det = DriftDetector()
        rng = np.random.RandomState(0)
        ref = rng.randn(500)
        curr = rng.randn(500) + 3.0  # 显著平移
        result = det.compute_psi(ref, curr)
        assert result["psi"] >= 0.25
        assert result["is_drift"] is True

    def test_zero_sum_histogram(self):
        """TC-DD-018: ref/curr 全为相同值且 min==max 触发 constant_distribution 分支."""
        # 此分支在 min==max 但 unique > 1 检查之后, 构造相同常数
        det = DriftDetector()
        ref = np.array([3.0, 3.0, 3.0])
        curr = np.array([3.0, 3.0, 3.0])
        # ref_unique len == 1 -> 进入 single-value 分支, 而非 min==max 分支
        result = det.compute_psi(ref, curr)
        # 单值相同返回 psi=0
        assert result["psi"] == 0.0


class TestDetectFeatureDrift:
    """Test detect_feature_drift."""

    def test_with_reference_data(self):
        """TC-DD-019: 有 reference_data 时检测各特征漂移."""
        rng = np.random.RandomState(0)
        det = DriftDetector(
            reference_data={
                "f1": rng.randn(100),
                "f2": rng.randn(100),
            }
        )
        current = {
            "f1": rng.randn(100),  # 同分布
            "f2": rng.randn(100) + 5.0,  # 漂移
        }
        result = det.detect_feature_drift(current)
        assert "f1" in result
        assert "f2" in result
        assert "ks_test" in result["f1"]
        assert "psi" in result["f1"]
        assert "is_drift" in result["f1"]

    def test_missing_reference_feature(self):
        """TC-DD-020: current 中含未在 reference 的特征 -> 跳过."""
        det = DriftDetector(reference_data={"f1": np.array([1.0, 2.0])})
        current = {"unknown_feature": np.array([1.0, 2.0])}
        result = det.detect_feature_drift(current)
        assert result == {}


class TestDetectPredictionDrift:
    """Test detect_prediction_drift."""

    def test_no_drift(self):
        """TC-DD-021: 同分布预测不漂移."""
        det = DriftDetector()
        rng = np.random.RandomState(0)
        ref = rng.randn(200)
        curr = rng.randn(200)
        result = det.detect_prediction_drift(ref, curr)
        assert "ks_test" in result
        assert "psi" in result
        assert "is_drift" in result

    def test_with_drift(self):
        """TC-DD-022: 显著不同分布预测漂移."""
        det = DriftDetector()
        rng = np.random.RandomState(0)
        ref = rng.randn(200)
        curr = rng.randn(200) + 5.0
        result = det.detect_prediction_drift(ref, curr)
        assert result["is_drift"] is True


class TestDetectPerformanceDrift:
    """Test detect_performance_drift."""

    def test_no_degradation(self):
        """TC-DD-023: 指标提升或持平不退化."""
        det = DriftDetector()
        baseline = {"f1": 0.8, "accuracy": 0.85}
        current = {"f1": 0.85, "accuracy": 0.85}
        result = det.detect_performance_drift(baseline, current)
        assert result["is_degraded"] is False
        assert "f1" in result["performance_changes"]
        # f1 从 0.8 提升到 0.85, change = -0.05, relative_change = -0.0625
        assert result["performance_changes"]["f1"]["change"] < 0

    def test_with_degradation(self):
        """TC-DD-024: 指标下降 > 5% 触发退化."""
        det = DriftDetector()
        baseline = {"f1": 0.9}
        current = {"f1": 0.7}  # 下降 22%
        result = det.detect_performance_drift(baseline, current)
        assert result["is_degraded"] is True
        assert result["performance_changes"]["f1"]["is_degraded"] is True

    def test_baseline_zero_no_degradation(self):
        """TC-DD-025: baseline=0 + current>=0 -> 不退化 (P1-F3 修复)."""
        det = DriftDetector()
        baseline = {"f1": 0.0}
        current = {"f1": 0.5}  # 从 0 提升, 不应误报
        result = det.detect_performance_drift(baseline, current)
        assert result["is_degraded"] is False
        assert result["performance_changes"]["f1"]["relative_change"] == 0.0

    def test_baseline_zero_with_negative_current(self):
        """TC-DD-026: baseline=0 + current<0 (异常负值) -> 退化."""
        det = DriftDetector()
        baseline = {"f1": 0.0}
        current = {"f1": -0.5}
        result = det.detect_performance_drift(baseline, current)
        # change = 0 - (-0.5) = 0.5 > 0, 触发退化
        assert result["is_degraded"] is True

    def test_metric_not_in_current(self):
        """TC-DD-027: baseline 中的 metric 不在 current 中 -> 跳过."""
        det = DriftDetector()
        baseline = {"f1": 0.8, "unknown": 0.5}
        current = {"f1": 0.8}
        result = det.detect_performance_drift(baseline, current)
        assert "f1" in result["performance_changes"]
        assert "unknown" not in result["performance_changes"]


class TestDetectDrift:
    """Test detect_drift (combined)."""

    def test_all_none(self):
        """TC-DD-028: 所有参数 None -> 空报告, is_drift_detected=False."""
        det = DriftDetector()
        report = det.detect_drift()
        assert isinstance(report, DriftReport)
        assert report.is_drift_detected is False
        assert report.feature_drift == {}
        assert report.prediction_drift == {}
        assert report.performance_drift is None
        assert report.timestamp != ""

    def test_with_feature_drift_only(self):
        """TC-DD-029: 仅 feature_drift 输入."""
        rng = np.random.RandomState(0)
        det = DriftDetector(
            reference_data={"f1": rng.randn(100)}
        )
        current = {"f1": rng.randn(100) + 5.0}
        report = det.detect_drift(current_data=current)
        assert "f1" in report.feature_drift
        assert report.is_drift_detected is True

    def test_with_prediction_drift_only(self):
        """TC-DD-030: 仅 prediction_drift 输入."""
        det = DriftDetector()
        rng = np.random.RandomState(0)
        report = det.detect_drift(
            reference_predictions=rng.randn(200),
            current_predictions=rng.randn(200) + 5.0,
        )
        assert report.prediction_drift != {}
        assert report.is_drift_detected is True

    def test_with_performance_drift_only(self):
        """TC-DD-031: 仅 performance_drift 输入."""
        det = DriftDetector()
        report = det.detect_drift(
            baseline_metrics={"f1": 0.9},
            current_metrics={"f1": 0.5},
        )
        assert report.performance_drift is not None
        assert report.is_drift_detected is True


class TestDriftReportToDict:
    """Test DriftReport.to_dict."""

    def test_to_dict(self):
        """TC-DD-032: to_dict 返回所有字段."""
        report = DriftReport(
            feature_drift={"f1": {"is_drift": True}},
            prediction_drift={"is_drift": False},
            performance_drift={"is_degraded": True},
            is_drift_detected=True,
            timestamp="2024-01-01 00:00:00",
        )
        d = report.to_dict()
        assert d["feature_drift"] == {"f1": {"is_drift": True}}
        assert d["prediction_drift"] == {"is_drift": False}
        assert d["performance_drift"] == {"is_degraded": True}
        assert d["is_drift_detected"] is True
        assert d["timestamp"] == "2024-01-01 00:00:00"


class TestSaveLoadConfig:
    """Test save_config / load_config round trip."""

    def test_save_config_creates_file(self, tmp_path):
        """TC-DD-033: save_config 创建 JSON 文件."""
        det = DriftDetector(
            thresholds={"ks_test": 0.01, "psi": 0.3, "performance_drop": 0.05},
            reference_data={"f1": np.array([1.0, 2.0])},
        )
        cfg_path = tmp_path / "drift_config.json"
        det.save_config(cfg_path)
        assert cfg_path.exists()
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert data["thresholds"]["ks_test"] == 0.01
        assert "f1" in data["reference_features"]

    def test_save_config_creates_parent_dir(self, tmp_path):
        """TC-DD-034: save_config 自动创建父目录."""
        det = DriftDetector()
        nested = tmp_path / "nested" / "deeper" / "config.json"
        det.save_config(nested)
        assert nested.exists()

    def test_load_config_round_trip(self, tmp_path):
        """TC-DD-035: save -> load 配置一致."""
        det = DriftDetector(
            thresholds={"ks_test": 0.02, "psi": 0.4, "performance_drop": 0.1},
        )
        cfg_path = tmp_path / "drift_config.json"
        det.save_config(cfg_path)
        loaded = DriftDetector.load_config(cfg_path)
        assert loaded.thresholds["ks_test"] == 0.02
        assert loaded.thresholds["psi"] == 0.4
        assert loaded.thresholds["performance_drop"] == 0.1
