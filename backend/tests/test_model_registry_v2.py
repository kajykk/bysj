"""
Test suite for Model Registry V2.

Tests:
- TC-GOV-001: 验证模型注册功能
- TC-GOV-002: 验证模型状态流转
- TC-GOV-003: 验证回退链查询
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from app.core.model_registry_v2 import ModelRegistryV2, ModelStatus, ModelType


class TestModelRegistryV2:
    """Test suite for Model Registry V2."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.registry_path = Path(self.temp_dir) / "test_registry.json"
        self.registry = ModelRegistryV2(registry_path=str(self.registry_path))

    def teardown_method(self) -> None:
        """Clean up test fixtures."""
        if self.registry_path.exists():
            self.registry_path.unlink()

    def test_register_model(self) -> None:
        """TC-GOV-001: 验证模型注册功能."""
        record = self.registry.register_model(
            model_id="test_xgboost",
            name="Test XGBoost",
            version="v1.0.0",
            model_type=ModelType.XGBOOST,
            status=ModelStatus.CANDIDATE,
            fallback_id="test_fallback",
            performance_threshold={"f1_score": 0.78},
            metrics={"f1_score": 0.81, "precision": 0.79, "recall": 0.83},
            artifact_path="models/test/model.pkl",
            training_config={"random_state": 42, "n_estimators": 200},
        )

        assert record.model_id == "test_xgboost"
        assert record.name == "Test XGBoost"
        assert record.version == "v1.0.0"
        assert record.model_type == ModelType.XGBOOST
        assert record.status == ModelStatus.CANDIDATE
        assert record.fallback_id == "test_fallback"
        assert record.performance_threshold == {"f1_score": 0.78}
        assert record.metrics["f1_score"] == 0.81
        assert record.artifact_path == "models/test/model.pkl"
        assert record.training_config["random_state"] == 42

    def test_get_model(self) -> None:
        """验证模型查询功能."""
        self.registry.register_model(
            model_id="test_model",
            name="Test Model",
            version="v1.0.0",
            model_type=ModelType.MLP,
        )

        record = self.registry.get_model("test_model")
        assert record is not None
        assert record.name == "Test Model"

        # Test non-existent model
        assert self.registry.get_model("non_existent") is None

    def test_status_transition(self) -> None:
        """TC-GOV-002: 验证模型状态流转."""
        self.registry.register_model(
            model_id="test_model",
            name="Test Model",
            version="v1.0.0",
            model_type=ModelType.XGBOOST,
            status=ModelStatus.CANDIDATE,
        )

        # Candidate -> Staging (valid)
        result = self.registry.promote_model("test_model", ModelStatus.STAGING)
        assert result is not None
        assert result.status == ModelStatus.STAGING

        # Staging -> Production (valid)
        result = self.registry.promote_model("test_model", ModelStatus.PRODUCTION)
        assert result is not None
        assert result.status == ModelStatus.PRODUCTION

        # Production -> Retired (valid)
        result = self.registry.promote_model("test_model", ModelStatus.RETIRED)
        assert result is not None
        assert result.status == ModelStatus.RETIRED

        # Retired -> anything (invalid)
        result = self.registry.promote_model("test_model", ModelStatus.PRODUCTION)
        assert result is None

    def test_invalid_status_transition(self) -> None:
        """验证无效状态流转被阻止."""
        self.registry.register_model(
            model_id="test_model",
            name="Test Model",
            version="v1.0.0",
            model_type=ModelType.XGBOOST,
            status=ModelStatus.CANDIDATE,
        )

        # Candidate -> Production (invalid, must go through Staging)
        result = self.registry.promote_model("test_model", ModelStatus.PRODUCTION)
        assert result is None

    def test_fallback_chain(self) -> None:
        """TC-GOV-003: 验证回退链查询."""
        self.registry.register_model(
            model_id="model_a",
            name="Model A",
            version="v1.0.0",
            model_type=ModelType.XGBOOST,
            fallback_id="model_b",
        )
        self.registry.register_model(
            model_id="model_b",
            name="Model B",
            version="v1.0.0",
            model_type=ModelType.MLP,
            fallback_id="model_c",
        )
        self.registry.register_model(
            model_id="model_c",
            name="Model C",
            version="v1.0.0",
            model_type=ModelType.LOGISTIC_REGRESSION,
            fallback_id=None,
        )

        chain = self.registry.get_fallback_chain("model_a")
        assert chain == ["model_a", "model_b", "model_c"]

    def test_circular_fallback_detection(self) -> None:
        """验证循环回退被检测."""
        self.registry.register_model(
            model_id="model_a",
            name="Model A",
            version="v1.0.0",
            model_type=ModelType.XGBOOST,
            fallback_id="model_b",
        )
        self.registry.register_model(
            model_id="model_b",
            name="Model B",
            version="v1.0.0",
            model_type=ModelType.MLP,
            fallback_id="model_a",  # Circular!
        )

        chain = self.registry.get_fallback_chain("model_a")
        # Should stop at model_b to avoid infinite loop
        assert chain == ["model_a", "model_b"]

    def test_performance_regression(self) -> None:
        """验证性能回归检测."""
        self.registry.register_model(
            model_id="test_model",
            name="Test Model",
            version="v1.0.0",
            model_type=ModelType.XGBOOST,
            performance_threshold={"f1_score": 0.78},
            metrics={"f1_score": 0.81},
        )

        # No regression
        result = self.registry.check_performance_regression(
            "test_model", {"f1_score": 0.80}
        )
        assert result["regression_detected"] is False

        # Regression detected
        result = self.registry.check_performance_regression(
            "test_model", {"f1_score": 0.75}
        )
        assert result["regression_detected"] is True
        assert len(result["regressions"]) == 1
        assert result["regressions"][0]["metric"] == "f1_score"
        assert abs(result["regressions"][0]["drop"] - 0.03) < 1e-9

    def test_persistence(self) -> None:
        """验证注册表持久化."""
        self.registry.register_model(
            model_id="test_model",
            name="Test Model",
            version="v1.0.0",
            model_type=ModelType.XGBOOST,
            metrics={"f1_score": 0.81},
        )

        # Create new registry instance with same path
        new_registry = ModelRegistryV2(registry_path=str(self.registry_path))
        record = new_registry.get_model("test_model")

        assert record is not None
        assert record.name == "Test Model"
        assert record.metrics["f1_score"] == 0.81

    def test_list_models(self) -> None:
        """验证模型列表功能."""
        self.registry.register_model(
            model_id="model_1",
            name="Model 1",
            version="v1.0.0",
            model_type=ModelType.XGBOOST,
        )
        self.registry.register_model(
            model_id="model_2",
            name="Model 2",
            version="v1.0.0",
            model_type=ModelType.MLP,
        )

        models = self.registry.list_models()
        assert len(models) == 2
        assert any(m["model_id"] == "model_1" for m in models)
        assert any(m["model_id"] == "model_2" for m in models)


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
