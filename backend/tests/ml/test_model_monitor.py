"""Tests for app/ml/model_monitor.py (ModelMonitor).

覆盖 0% 模块: app.ml.model_monitor.
关键路径:
- ModelMonitor.__init__ (默认/自定义 config/drift_detector)
- record_prediction (with/without error, history bounding, threading.Lock)
- check_drift (with/without drift detected, consecutive_drifts 累积)
- get_health_status (healthy/degraded/critical + recommendations)
- get_monitoring_summary
- should_trigger_alert
- save_state / load_state round trip
"""

from __future__ import annotations

import json
import threading

import numpy as np
import pytest

from app.ml.drift_detector import DriftDetector, DriftReport
from app.ml.model_monitor import (
    DEFAULT_MONITOR_CONFIG,
    ModelHealth,
    ModelMonitor,
    MonitoringRecord,
)


class TestModelMonitorInit:
    """Test ModelMonitor initialization."""

    def test_default_init(self):
        """TC-MM-001: 默认初始化."""
        monitor = ModelMonitor("model_a", "v1.0")
        assert monitor.model_name == "model_a"
        assert monitor.model_version == "v1.0"
        assert monitor.config == DEFAULT_MONITOR_CONFIG
        assert isinstance(monitor.drift_detector, DriftDetector)
        assert monitor.history == []
        assert monitor.consecutive_drifts == 0
        assert monitor.total_predictions == 0
        assert monitor.latency_history == []
        assert monitor.error_count == 0

    def test_custom_config(self):
        """TC-MM-002: 自定义 config 覆盖默认."""
        custom = {
            "drift_check_interval_minutes": 30,
            "performance_check_interval_minutes": 720,
            "alert_threshold_consecutive_drifts": 5,
            "max_history_size": 500,
        }
        monitor = ModelMonitor("m", "v", config=custom)
        assert monitor.config["drift_check_interval_minutes"] == 30
        assert monitor.config["alert_threshold_consecutive_drifts"] == 5

    def test_custom_drift_detector(self):
        """TC-MM-003: 自定义 drift_detector."""
        det = DriftDetector(thresholds={"ks_test": 0.01, "psi": 0.5, "performance_drop": 0.1})
        monitor = ModelMonitor("m", "v", drift_detector=det)
        assert monitor.drift_detector.thresholds["ks_test"] == 0.01


class TestRecordPrediction:
    """Test record_prediction."""

    def test_basic_record(self):
        """TC-MM-004: 基本 record_prediction."""
        monitor = ModelMonitor("m", "v")
        monitor.record_prediction(latency_ms=50.0, prediction=0.8)
        assert monitor.total_predictions == 1
        assert monitor.latency_history == [50.0]
        assert monitor.error_count == 0

    def test_record_with_error(self):
        """TC-MM-005: record_prediction 记录错误."""
        monitor = ModelMonitor("m", "v")
        monitor.record_prediction(latency_ms=50.0, error=True)
        assert monitor.error_count == 1
        assert monitor.total_predictions == 1

    def test_history_bounded(self):
        """TC-MM-006: latency_history 在 max_history_size 内截断."""
        monitor = ModelMonitor(
            "m", "v", config={"max_history_size": 5, "alert_threshold_consecutive_drifts": 3}
        )
        for i in range(10):
            monitor.record_prediction(latency_ms=float(i))
        # 截断后保留最后 5 条
        assert len(monitor.latency_history) == 5
        assert monitor.latency_history == [5.0, 6.0, 7.0, 8.0, 9.0]
        assert monitor.total_predictions == 10

    def test_concurrent_record_predictions(self):
        """TC-MM-007: 并发 record_prediction 不丢失数据 (M-6 修复)."""
        monitor = ModelMonitor("m", "v")
        N_THREADS = 8
        N_PER_THREAD = 100

        def worker():
            for _ in range(N_PER_THREAD):
                monitor.record_prediction(latency_ms=10.0)

        threads = [threading.Thread(target=worker) for _ in range(N_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert monitor.total_predictions == N_THREADS * N_PER_THREAD
        assert len(monitor.latency_history) == N_THREADS * N_PER_THREAD


class TestCheckDrift:
    """Test check_drift."""

    def test_no_drift(self):
        """TC-MM-008: 无漂移时 consecutive_drifts 重置为 0."""
        monitor = ModelMonitor("m", "v")
        # 注入 1 次漂移计数
        monitor.consecutive_drifts = 1
        # 调用 check_drift 但不传任何漂移输入 -> is_drift_detected=False
        report = monitor.check_drift()
        assert isinstance(report, DriftReport)
        assert report.is_drift_detected is False
        assert monitor.consecutive_drifts == 0  # 重置
        assert len(monitor.history) == 1

    def test_with_drift(self):
        """TC-MM-009: 检测到漂移时 consecutive_drifts 累积."""
        monitor = ModelMonitor(
            "m", "v",
            drift_detector=DriftDetector(
                reference_data={"f1": np.random.RandomState(0).randn(100)}
            ),
        )
        rng = np.random.RandomState(1)
        current = {"f1": rng.randn(100) + 5.0}  # 显著漂移
        report = monitor.check_drift(current_data=current)
        assert report.is_drift_detected is True
        assert monitor.consecutive_drifts == 1
        assert len(monitor.history) == 1
        # history 中应记录 drift_detected=True
        assert monitor.history[0].drift_detected is True

    def test_history_bounded(self):
        """TC-MM-010: history 在 max_history_size 内截断."""
        monitor = ModelMonitor(
            "m", "v", config={"max_history_size": 3, "alert_threshold_consecutive_drifts": 3}
        )
        for _ in range(5):
            monitor.check_drift()  # 无漂移输入
        assert len(monitor.history) == 3


class TestGetHealthStatus:
    """Test get_health_status."""

    def test_healthy(self):
        """TC-MM-011: 无漂移无错误 -> healthy."""
        monitor = ModelMonitor("m", "v")
        monitor.record_prediction(latency_ms=50.0)
        health = monitor.get_health_status()
        assert isinstance(health, ModelHealth)
        assert health.status == "healthy"
        assert health.consecutive_drifts == 0
        assert health.total_predictions == 1
        assert health.average_latency_ms == 50.0
        assert health.error_rate == 0.0
        assert health.recommendations == []

    def test_degraded(self):
        """TC-MM-012: 1-2 次连续漂移 -> degraded."""
        monitor = ModelMonitor("m", "v")
        monitor.consecutive_drifts = 1
        health = monitor.get_health_status()
        assert health.status == "degraded"
        assert any("Monitor closely" in r for r in health.recommendations)

    def test_critical(self):
        """TC-MM-013: >=3 次连续漂移 -> critical."""
        monitor = ModelMonitor("m", "v")
        monitor.consecutive_drifts = 3
        health = monitor.get_health_status()
        assert health.status == "critical"
        assert any("retraining" in r.lower() for r in health.recommendations)
        assert any("distribution" in r.lower() for r in health.recommendations)

    def test_high_error_rate_recommendation(self):
        """TC-MM-014: 错误率 > 1% 触发错误调查建议."""
        monitor = ModelMonitor("m", "v")
        # 100 次预测, 5 次错误 -> error_rate = 0.05
        for i in range(95):
            monitor.record_prediction(latency_ms=10.0)
        for i in range(5):
            monitor.record_prediction(latency_ms=10.0, error=True)
        health = monitor.get_health_status()
        assert any("error" in r.lower() for r in health.recommendations)

    def test_high_latency_recommendation(self):
        """TC-MM-015: 平均延迟 > 200ms 触发延迟调查建议."""
        monitor = ModelMonitor("m", "v")
        monitor.record_prediction(latency_ms=300.0)
        health = monitor.get_health_status()
        assert any("latency" in r.lower() for r in health.recommendations)

    def test_zero_predictions_no_division_error(self):
        """TC-MM-016: 0 次预测时不触发除零错误."""
        monitor = ModelMonitor("m", "v")
        health = monitor.get_health_status()
        assert health.error_rate == 0.0
        assert health.average_latency_ms == 0.0


class TestGetMonitoringSummary:
    """Test get_monitoring_summary."""

    def test_empty_summary(self):
        """TC-MM-017: 空监控历史 summary."""
        monitor = ModelMonitor("model_x", "v2.0")
        summary = monitor.get_monitoring_summary()
        assert summary["model_name"] == "model_x"
        assert summary["model_version"] == "v2.0"
        assert summary["health_status"] == "healthy"
        assert summary["total_checks"] == 0
        assert summary["drift_frequency"] == 0.0

    def test_with_history(self):
        """TC-MM-018: 含历史的 summary."""
        monitor = ModelMonitor("m", "v")
        # 触发 2 次 check_drift (1 漂移 + 1 无漂移)
        monitor.history = [
            MonitoringRecord(
                timestamp="t1",
                model_name="m",
                model_version="v",
                metrics={},
                drift_detected=True,
            ),
            MonitoringRecord(
                timestamp="t2",
                model_name="m",
                model_version="v",
                metrics={},
                drift_detected=False,
            ),
        ]
        summary = monitor.get_monitoring_summary()
        assert summary["total_checks"] == 2
        assert summary["drift_frequency"] == 0.5


class TestShouldTriggerAlert:
    """Test should_trigger_alert."""

    def test_below_threshold(self):
        """TC-MM-019: consecutive_drifts < threshold -> False."""
        monitor = ModelMonitor("m", "v")  # default threshold = 3
        monitor.consecutive_drifts = 2
        assert monitor.should_trigger_alert() is False

    def test_at_threshold(self):
        """TC-MM-020: consecutive_drifts >= threshold -> True."""
        monitor = ModelMonitor("m", "v")
        monitor.consecutive_drifts = 3
        assert monitor.should_trigger_alert() is True


class TestSaveLoadState:
    """Test save_state / load_state round trip."""

    def test_save_state_creates_file(self, tmp_path):
        """TC-MM-021: save_state 创建 JSON 文件."""
        monitor = ModelMonitor("m", "v1.0")
        monitor.record_prediction(latency_ms=10.0)
        monitor.consecutive_drifts = 2
        state_path = tmp_path / "monitor_state.json"
        monitor.save_state(state_path)
        assert state_path.exists()
        data = json.loads(state_path.read_text(encoding="utf-8"))
        assert data["model_name"] == "m"
        assert data["model_version"] == "v1.0"
        assert data["consecutive_drifts"] == 2
        assert data["total_predictions"] == 1

    def test_save_state_creates_parent_dir(self, tmp_path):
        """TC-MM-022: save_state 自动创建父目录."""
        monitor = ModelMonitor("m", "v")
        nested = tmp_path / "nested" / "deeper" / "state.json"
        monitor.save_state(nested)
        assert nested.exists()

    def test_load_state_round_trip(self, tmp_path):
        """TC-MM-023: save -> load 状态一致."""
        monitor = ModelMonitor(
            "model_x", "v2.5",
            config={
                "drift_check_interval_minutes": 30,
                "performance_check_interval_minutes": 720,
                "alert_threshold_consecutive_drifts": 5,
                "max_history_size": 500,
            },
        )
        monitor.record_prediction(latency_ms=10.0)
        monitor.record_prediction(latency_ms=20.0, error=True)
        monitor.consecutive_drifts = 2
        monitor.history = [
            MonitoringRecord(
                timestamp="t1",
                model_name="model_x",
                model_version="v2.5",
                metrics={"f1": 0.8},
                drift_detected=True,
            ),
        ]
        state_path = tmp_path / "state.json"
        monitor.save_state(state_path)
        loaded = ModelMonitor.load_state(state_path)
        assert loaded.model_name == "model_x"
        assert loaded.model_version == "v2.5"
        assert loaded.consecutive_drifts == 2
        assert loaded.total_predictions == 2
        assert loaded.error_count == 1
        assert loaded.latency_history == [10.0, 20.0]
        assert len(loaded.history) == 1
        assert loaded.history[0].drift_detected is True
        assert loaded.history[0].metrics == {"f1": 0.8}

    def test_load_state_default_config(self, tmp_path):
        """TC-MM-024: load_state 无 config 字段时使用默认."""
        state = {
            "model_name": "m",
            "model_version": "v",
            "consecutive_drifts": 0,
            "total_predictions": 0,
            "error_count": 0,
            "latency_history": [],
            "history": [],
        }
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        loaded = ModelMonitor.load_state(state_path)
        assert loaded.config == DEFAULT_MONITOR_CONFIG

    def test_load_state_empty_history(self, tmp_path):
        """TC-MM-025: load_state 无 history 字段时空列表."""
        state = {
            "model_name": "m",
            "model_version": "v",
            "consecutive_drifts": 0,
            "total_predictions": 0,
            "error_count": 0,
            "latency_history": [],
        }
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        loaded = ModelMonitor.load_state(state_path)
        assert loaded.history == []
