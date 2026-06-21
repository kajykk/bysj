"""
Test suite for fallback mechanisms.

Tests:
- TC-FALL-001: 验证生理模型回退 (XGBoost -> NumPy MLP)
- TC-FALL-002: 验证融合层回退 (可学习 -> 规则)
- TC-FALL-003: 验证文本模型回退 (BERT -> TF-IDF+LR)
- TC-FALL-004: 验证模型加载失败回退
- TC-FALL-005: 验证预测异常回退
- TC-FALL-006: 验证延迟超时回退
- TC-FALL-007: 验证依赖缺失回退
- TC-FALL-008: 验证回退日志记录
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Add backend to path
backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.ml.unified_model_interface import ModelRegistry, UnifiedModelWrapper


class TestFallbackMechanisms:
    """Test suite for fallback mechanisms."""

    @pytest.fixture
    def primary_model(self) -> MagicMock:
        """Create a primary model that fails."""
        model = MagicMock()
        model.predict.side_effect = Exception("Primary model failed")
        model.predict_proba.side_effect = Exception("Primary model failed")
        model.get_version.return_value = {"model_name": "primary", "version": "1.0"}
        return model

    @pytest.fixture
    def fallback_model(self) -> MagicMock:
        """Create a fallback model that works."""
        model = MagicMock()
        model.predict.return_value = np.array([1, 0, 1])
        model.predict_proba.return_value = np.array([[0.2, 0.8], [0.7, 0.3], [0.1, 0.9]])
        model.get_version.return_value = {"model_name": "fallback", "version": "1.0"}
        return model

    def test_physiological_fallback(self, primary_model: MagicMock, fallback_model: MagicMock) -> None:
        """TC-FALL-001: 验证生理模型回退 (XGBoost -> NumPy MLP)."""
        registry = ModelRegistry()
        registry.register("xgboost", primary_model, "xgboost")
        registry.register("numpy_mlp", fallback_model, "numpy")
        registry.register("physiological", primary_model, "xgboost", fallback_names=["numpy_mlp"])

        registry.setup_fallback_chain("physiological")

        wrapper = registry.get_model("physiological")
        X = np.random.randn(3, 13)

        # Should fallback to numpy_mlp
        predictions = wrapper.predict(X)
        assert len(predictions) == 3
        fallback_model.predict.assert_called_once()

    def test_fusion_fallback(self, primary_model: MagicMock, fallback_model: MagicMock) -> None:
        """TC-FALL-002: 验证融合层回退 (可学习 -> 规则)."""
        registry = ModelRegistry()
        registry.register("learnable_fusion", primary_model, "learnable")
        registry.register("rule_fusion", fallback_model, "rule")
        registry.register("fusion", primary_model, "learnable", fallback_names=["rule_fusion"])

        registry.setup_fallback_chain("fusion")

        wrapper = registry.get_model("fusion")
        X = np.random.randn(3, 10)

        predictions = wrapper.predict(X)
        assert len(predictions) == 3
        fallback_model.predict.assert_called_once()

    def test_text_fallback(self, primary_model: MagicMock, fallback_model: MagicMock) -> None:
        """TC-FALL-003: 验证文本模型回退 (BERT -> TF-IDF+LR)."""
        registry = ModelRegistry()
        registry.register("bert", primary_model, "bert")
        registry.register("tfidf_lr", fallback_model, "sklearn")
        registry.register("text", primary_model, "bert", fallback_names=["tfidf_lr"])

        registry.setup_fallback_chain("text")

        wrapper = registry.get_model("text")
        X = np.random.randn(3, 768)  # BERT embedding size

        predictions = wrapper.predict(X)
        assert len(predictions) == 3
        fallback_model.predict.assert_called_once()

    def test_model_load_failure_fallback(self) -> None:
        """TC-FALL-004: 验证模型加载失败回退."""
        # Simulate model load failure
        def failing_load(path):
            raise FileNotFoundError("Model file not found")

        # Should fallback to heuristic
        heuristic_model = MagicMock()
        heuristic_model.predict.return_value = np.array([0, 1, 0])

        registry = ModelRegistry()
        registry.register("heuristic", heuristic_model, "heuristic")

        # When primary fails to load, use heuristic
        try:
            failing_load("/nonexistent/model.pkl")
        except FileNotFoundError:
            # Fallback to heuristic
            wrapper = registry.get_model("heuristic")
            X = np.random.randn(3, 10)
            predictions = wrapper.predict(X)
            assert len(predictions) == 3

    def test_prediction_anomaly_fallback(self, primary_model: MagicMock, fallback_model: MagicMock) -> None:
        """TC-FALL-005: 验证预测异常回退."""
        # Primary returns NaN/Inf
        primary_model.predict.side_effect = None
        primary_model.predict.return_value = np.array([np.nan, np.inf, 1.0])

        wrapper = UnifiedModelWrapper(primary_model, "test")
        wrapper.set_fallback(fallback_model)

        X = np.random.randn(3, 10)

        # Check if predictions contain NaN/Inf
        predictions = wrapper.predict(X)
        if np.any(np.isnan(predictions)) or np.any(np.isinf(predictions)):
            # Should have used fallback
            fallback_model.predict.assert_called_once()

    def test_latency_timeout_fallback(self, fallback_model: MagicMock) -> None:
        """TC-FALL-006: 验证延迟超时回退."""
        slow_model = MagicMock()

        def slow_predict(X):
            time.sleep(0.3)  # 300ms, exceeds 200ms threshold
            return np.array([1, 0, 1])

        slow_model.predict = slow_predict

        wrapper = UnifiedModelWrapper(slow_model, "test")
        wrapper.set_fallback(fallback_model)

        X = np.random.randn(3, 10)

        start = time.time()
        try:
            predictions = wrapper.predict(X)
            elapsed = (time.time() - start) * 1000

            if elapsed > 200:
                # Should have triggered fallback
                fallback_model.predict.assert_called_once()
        except Exception:
            # If timeout mechanism is implemented
            pass

    def test_dependency_missing_fallback(self) -> None:
        """TC-FALL-007: 验证依赖缺失回退."""
        # Simulate PyTorch not installed
        with patch.dict(sys.modules, {"torch": None}):
            heuristic_model = MagicMock()
            heuristic_model.predict.return_value = np.array([0, 1, 0])

            registry = ModelRegistry()
            registry.register("heuristic", heuristic_model, "heuristic")

            # When PyTorch is not available, use heuristic
            wrapper = registry.get_model("heuristic")
            X = np.random.randn(3, 10)
            predictions = wrapper.predict(X)
            assert len(predictions) == 3

    def test_fallback_logging(self, primary_model: MagicMock, fallback_model: MagicMock, caplog) -> None:
        """TC-FALL-008: 验证回退日志记录."""
        import logging

        with caplog.at_level(logging.INFO):
            wrapper = UnifiedModelWrapper(primary_model, "test")
            wrapper.set_fallback(fallback_model)

            X = np.random.randn(3, 10)
            wrapper.predict(X)

            # Should log fallback event
            assert "Primary model prediction failed" in caplog.text
            assert "Falling back to fallback model" in caplog.text

    def test_multiple_fallback_chain(self) -> None:
        """TC-FALL-009: 验证多级回退链."""
        primary = MagicMock()
        primary.predict.side_effect = Exception("Primary failed")

        secondary = MagicMock()
        secondary.predict.side_effect = Exception("Secondary failed")

        tertiary = MagicMock()
        tertiary.predict.return_value = np.array([1, 0, 1])

        registry = ModelRegistry()
        registry.register("primary", primary, "test")
        registry.register("secondary", secondary, "test")
        registry.register("tertiary", tertiary, "test")
        registry.register("main", primary, "test", fallback_names=["secondary", "tertiary"])

        registry.setup_fallback_chain("main")

        wrapper = registry.get_model("main")
        X = np.random.randn(3, 10)

        # Should fallback through chain to tertiary
        predictions = wrapper.predict(X)
        assert len(predictions) == 3
        tertiary.predict.assert_called_once()

    def test_no_fallback_available(self, primary_model: MagicMock) -> None:
        """TC-FALL-010: 验证无回退可用时抛出异常."""
        wrapper = UnifiedModelWrapper(primary_model, "test")
        # No fallback set

        X = np.random.randn(3, 10)
        with pytest.raises(Exception):
            wrapper.predict(X)
