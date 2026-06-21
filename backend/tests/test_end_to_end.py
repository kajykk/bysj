"""
End-to-End Test Suite for Complete Prediction Pipeline.

Tests:
- TC-E2E-001: 验证完整预测链路
- TC-E2E-002: 验证多模态输入
- TC-E2E-003: 验证异常输入处理
- TC-E2E-004: 验证回退链路
- TC-E2E-005: 验证灰度发布
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Add backend to path
backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.ml.canary_controller import CanaryController, CanaryConfig
from app.ml.fusion_engine import FusionEngine
from app.ml.unified_model_interface import ModelRegistry, UnifiedModelWrapper

pytestmark = [pytest.mark.e2e, pytest.mark.slow]


class TestEndToEnd:
    """End-to-end test suite."""

    @pytest.fixture
    def mock_structured_model(self) -> MagicMock:
        """Create mock structured model."""
        model = MagicMock()
        model.predict.return_value = np.array([1])
        model.predict_proba.return_value = np.array([[0.3, 0.7]])
        return model

    @pytest.fixture
    def mock_text_model(self) -> MagicMock:
        """Create mock text model."""
        model = MagicMock()
        model.predict.return_value = np.array([0])
        model.predict_proba.return_value = np.array([[0.8, 0.2]])
        return model

    @pytest.fixture
    def mock_physio_model(self) -> MagicMock:
        """Create mock physiological model."""
        model = MagicMock()
        model.predict.return_value = np.array([1])
        model.predict_proba.return_value = np.array([[0.4, 0.6]])
        return model

    def test_complete_prediction_pipeline(self, mock_structured_model, mock_text_model, mock_physio_model) -> None:
        """TC-E2E-001: 验证完整预测链路."""
        # Setup registry
        registry = ModelRegistry()
        registry.register("structured", mock_structured_model, "sklearn")
        registry.register("text", mock_text_model, "sklearn")
        registry.register("physiological", mock_physio_model, "sklearn")

        # Setup fusion engine
        fusion = FusionEngine()

        # Simulate prediction
        structured_score = 60.0
        text_score = 30.0
        physio_score = 70.0

        modality_scores = {
            "structured": structured_score,
            "text": text_score,
            "physiological": physio_score,
        }

        result = fusion.fuse(modality_scores)

        assert "risk_score" in result
        assert "risk_level" in result
        assert "confidence" in result
        assert result["fusion_scheme"] == "full_three_modality"

    def test_multimodal_input(self, mock_structured_model, mock_text_model, mock_physio_model) -> None:
        """TC-E2E-002: 验证多模态输入."""
        fusion = FusionEngine()

        # Test with all modalities
        result_all = fusion.fuse({
            "structured": 50.0,
            "text": 60.0,
            "physiological": 40.0,
        })
        assert result_all["fusion_scheme"] == "full_three_modality"

        # Test with two modalities
        result_two = fusion.fuse({
            "structured": 50.0,
            "text": 60.0,
        })
        assert result_two["fusion_scheme"] == "dual_modality"

        # Test with one modality
        result_one = fusion.fuse({
            "structured": 50.0,
        })
        assert result_one["fusion_scheme"] == "single_modality"

    def test_abnormal_input_handling(self) -> None:
        """TC-E2E-003: 验证异常输入处理."""
        fusion = FusionEngine()

        # Empty input
        result = fusion.fuse({})
        assert result["fusion_scheme"] == "empty"
        assert result["risk_score"] == 0.0

        # Invalid scores
        result = fusion.fuse({
            "structured": -10.0,  # Below valid range
            "text": 110.0,  # Above valid range
        })
        # Should still produce a result
        assert "risk_score" in result

    def test_fallback_chain(self, mock_structured_model, mock_physio_model) -> None:
        """TC-E2E-004: 验证回退链路."""
        # Create failing primary model
        failing_model = MagicMock()
        failing_model.predict.side_effect = Exception("Model failed")

        # Create fallback model that returns 3 predictions
        fallback_model = MagicMock()
        fallback_model.predict.return_value = np.array([0, 1, 0])

        registry = ModelRegistry()
        registry.register("primary", failing_model, "test")
        registry.register("fallback", fallback_model, "test")
        registry.register("main", failing_model, "test", fallback_names=["fallback"])

        registry.setup_fallback_chain("main")

        wrapper = registry.get_model("main")
        X = np.random.randn(3, 10)

        # Should fallback to fallback model
        predictions = wrapper.predict(X)
        assert len(predictions) == 3
        fallback_model.predict.assert_called_once()

    def test_canary_release(self, mock_structured_model) -> None:
        """TC-E2E-005: 验证灰度发布."""
        old_model = MagicMock()
        old_model.predict.return_value = np.array([0])

        new_model = MagicMock()
        new_model.predict.return_value = np.array([1])

        controller = CanaryController(
            config=CanaryConfig(new_model_traffic_percentage=50.0),
            old_model=old_model,
            new_model=new_model,
        )

        X = np.random.randn(3, 10)

        # Test multiple users
        new_count = 0
        old_count = 0
        for i in range(100):
            result = controller.predict(X, user_id=f"user_{i}")
            if result["model_used"] == "new":
                new_count += 1
            else:
                old_count += 1

        # Should be roughly 50/50
        total = new_count + old_count
        new_ratio = new_count / total
        assert 0.4 <= new_ratio <= 0.6, f"New model ratio {new_ratio} not within expected range"

    def test_prediction_with_monitoring(self, mock_structured_model) -> None:
        """TC-E2E-006: 验证带监控的预测."""
        from app.ml.model_monitor import ModelMonitor

        monitor = ModelMonitor(
            model_name="structured",
            model_version="1.0.0",
        )

        # Record predictions
        for i in range(10):
            monitor.record_prediction(latency_ms=10.0 + i)

        health = monitor.get_health_status()
        assert health.status == "healthy"
        assert health.total_predictions == 10

    def test_drift_detection_integration(self) -> None:
        """TC-E2E-007: 验证漂移检测集成."""
        from app.ml.drift_detector import DriftDetector

        np.random.seed(42)
        reference_data = {"feature_1": np.random.normal(0, 1, 100)}
        detector = DriftDetector(reference_data=reference_data)

        # No drift - use same data as reference
        current_data = {"feature_1": reference_data["feature_1"].copy()}
        report = detector.detect_drift(current_data=current_data)

        assert report.is_drift_detected is False

    def test_model_version_tracking(self) -> None:
        """TC-E2E-008: 验证模型版本跟踪."""
        # Create a model with proper get_version method
        model = MagicMock()
        model.get_version.return_value = {"model_type": "test", "version": "1.0.0"}

        wrapper = UnifiedModelWrapper(model, "test")

        version = wrapper.get_version()
        assert "model_type" in version
        assert version["model_type"] == "test"
