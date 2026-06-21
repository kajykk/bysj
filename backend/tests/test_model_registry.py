"""Tests for model registry module."""

from __future__ import annotations

import pytest

from app.core.model_registry import (
    MODEL_PATHS,
    MODEL_REGISTRY,
    ModelMetadata,
    normalize_model_id,
    register_model,
    get_model_info,
    resolve_model_path,
    is_model_enabled,
)


class TestModelRegistry:
    """Test model registry functions."""

    def test_model_paths_not_empty(self):
        """TC-COV-REG-001: Model paths populated."""
        assert len(MODEL_PATHS) > 0

    def test_model_registry_not_empty(self):
        """TC-COV-REG-002: Model registry populated."""
        assert len(MODEL_REGISTRY) > 0

    def test_normalize_model_id(self):
        """TC-COV-REG-003: Normalize model ID."""
        assert normalize_model_id("test_model") == "test_model"

    def test_register_model(self):
        """TC-COV-REG-004: Register new model."""
        meta = register_model(
            "test_new_model",
            "models/test.pkl",
            version="v2",
            enabled=True,
            supports_fusion=False,
        )
        assert meta.name == "test_new_model"
        assert meta.path == "models/test.pkl"
        assert meta.version == "v2"
        assert "test_new_model" in MODEL_REGISTRY
        assert "test_new_model" in MODEL_PATHS
        # Cleanup
        del MODEL_REGISTRY["test_new_model"]
        del MODEL_PATHS["test_new_model"]

    def test_get_model_info_exists(self):
        """TC-COV-REG-005: Get info for existing model."""
        info = get_model_info("physiological_model_v2_dl")
        assert info is not None
        assert info.name == "physiological_model_v2_dl"
        assert info.supports_fusion is True

    def test_get_model_info_not_exists(self):
        """TC-COV-REG-006: Get info for missing model."""
        info = get_model_info("nonexistent_model")
        assert info is None

    def test_resolve_model_path(self):
        """TC-COV-REG-007: Resolve model path."""
        path = resolve_model_path("physiological_model_v2_dl")
        assert "model.json" in path

    def test_is_model_enabled_default(self):
        """TC-COV-REG-008: Unknown models are not enabled by default."""
        assert is_model_enabled("unknown_model") is False

    def test_is_model_enabled_disabled(self):
        """TC-COV-REG-009: Disabled model returns False."""
        register_model("disabled_model", "models/d.pkl", enabled=False)
        assert is_model_enabled("disabled_model") is False
        del MODEL_REGISTRY["disabled_model"]
        del MODEL_PATHS["disabled_model"]

    def test_model_metadata_defaults(self):
        """TC-COV-REG-010: ModelMetadata defaults."""
        meta = ModelMetadata(name="test", path="models/test.pkl")
        assert meta.version == "v1"
        assert meta.enabled is True
        assert meta.supports_fusion is False
        assert meta.feature_schema == {}
        assert meta.artifact_metadata == {}
