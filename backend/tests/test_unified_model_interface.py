"""
Test suite for unified model interface.

Tests:
- TC-GOV-001: 验证模型注册
- TC-GOV-002: 验证统一预测接口
- TC-GOV-003: 验证统一概率预测接口
- TC-GOV-004: 验证版本信息获取
- TC-GOV-005: 验证回退机制
- TC-GOV-006: 验证回退链设置
- TC-GOV-007: 验证健康状态检查
- TC-GOV-008: 验证模型列表
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

# Add backend to path
backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.ml.unified_model_interface import ModelRegistry, UnifiedModelWrapper


class TestUnifiedModelInterface:
    """Test suite for unified model interface."""

    @pytest.fixture
    def mock_model(self) -> MagicMock:
        """Create a mock model."""
        model = MagicMock()
        model.predict.return_value = np.array([1, 0, 1])
        model.predict_proba.return_value = np.array([[0.2, 0.8], [0.7, 0.3], [0.1, 0.9]])
        model.get_version.return_value = {"model_name": "test", "model_version": "1.0"}
        model.get_latency.return_value = 5.0
        return model

    @pytest.fixture
    def mock_fallback(self) -> MagicMock:
        """Create a mock fallback model."""
        model = MagicMock()
        model.predict.return_value = np.array([0, 1, 0])
        model.predict_proba.return_value = np.array([[0.6, 0.4], [0.3, 0.7], [0.8, 0.2]])
        return model

    def test_model_wrapper_predict(self, mock_model: MagicMock) -> None:
        """TC-GOV-002: 验证统一预测接口."""
        wrapper = UnifiedModelWrapper(mock_model, "test")
        X = np.random.randn(3, 10)

        predictions = wrapper.predict(X)

        assert len(predictions) == 3
        mock_model.predict.assert_called_once()

    def test_model_wrapper_predict_proba(self, mock_model: MagicMock) -> None:
        """TC-GOV-003: 验证统一概率预测接口."""
        wrapper = UnifiedModelWrapper(mock_model, "test")
        X = np.random.randn(3, 10)

        probabilities = wrapper.predict_proba(X)

        assert probabilities.shape == (3, 2)
        mock_model.predict_proba.assert_called_once()

    def test_model_wrapper_get_version(self, mock_model: MagicMock) -> None:
        """TC-GOV-004: 验证版本信息获取."""
        wrapper = UnifiedModelWrapper(mock_model, "test")

        version = wrapper.get_version()

        assert "model_name" in version
        assert "model_version" in version

    def test_model_wrapper_fallback(self, mock_model: MagicMock, mock_fallback: MagicMock) -> None:
        """TC-GOV-005: 验证回退机制."""
        wrapper = UnifiedModelWrapper(mock_model, "test")
        wrapper.set_fallback(mock_fallback)

        # Make primary model fail
        mock_model.predict.side_effect = Exception("Primary model failed")

        X = np.random.randn(3, 10)
        predictions = wrapper.predict(X)

        # Should use fallback
        assert len(predictions) == 3
        mock_fallback.predict.assert_called_once()

    def test_model_registry_register(self, mock_model: MagicMock) -> None:
        """TC-GOV-001: 验证模型注册."""
        registry = ModelRegistry()
        registry.register("primary", mock_model, "test")

        retrieved = registry.get_model("primary")
        assert retrieved is not None
        assert retrieved.model_type == "test"

    def test_model_registry_fallback_chain(self, mock_model: MagicMock, mock_fallback: MagicMock) -> None:
        """TC-GOV-006: 验证回退链设置."""
        registry = ModelRegistry()
        registry.register("primary", mock_model, "test")
        registry.register("fallback", mock_fallback, "test")
        registry.register("main", mock_model, "test", fallback_names=["primary", "fallback"])

        registry.setup_fallback_chain("main")

        main_wrapper = registry.get_model("main")
        assert len(main_wrapper._fallback_models) > 0

    def test_model_registry_health_check(self, mock_model: MagicMock) -> None:
        """TC-GOV-007: 验证健康状态检查."""
        registry = ModelRegistry()
        registry.register("healthy_model", mock_model, "test")

        health = registry.get_health_status()

        assert "healthy_model" in health
        assert health["healthy_model"]["status"] == "healthy"

    def test_model_registry_list(self, mock_model: MagicMock) -> None:
        """TC-GOV-008: 验证模型列表."""
        registry = ModelRegistry()
        registry.register("model1", mock_model, "type1")
        registry.register("model2", mock_model, "type2")

        models = registry.list_models()

        assert len(models) == 2
        assert any(m["name"] == "model1" for m in models)
        assert any(m["name"] == "model2" for m in models)

    def test_fallback_on_predict_proba(self, mock_model: MagicMock, mock_fallback: MagicMock) -> None:
        """TC-GOV-009: 验证概率预测回退."""
        wrapper = UnifiedModelWrapper(mock_model, "test")
        wrapper.set_fallback(mock_fallback)

        # Make primary model fail
        mock_model.predict_proba.side_effect = Exception("Primary model failed")

        X = np.random.randn(3, 10)
        probabilities = wrapper.predict_proba(X)

        # Should use fallback
        assert probabilities.shape == (3, 2)
        mock_fallback.predict_proba.assert_called_once()

    def test_no_fallback_raises(self, mock_model: MagicMock) -> None:
        """TC-GOV-010: 验证无回退时抛出异常."""
        wrapper = UnifiedModelWrapper(mock_model, "test")

        # Make primary model fail
        mock_model.predict.side_effect = Exception("Primary model failed")

        X = np.random.randn(3, 10)
        with pytest.raises(Exception):
            wrapper.predict(X)

    def test_model_not_found(self) -> None:
        """TC-GOV-011: 验证模型未找到."""
        registry = ModelRegistry()

        with pytest.raises(KeyError):
            registry.get_model("nonexistent")
