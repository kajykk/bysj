from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.model_compatibility import (
    MODEL_COMPATIBILITY_REGISTRY,
    TARGET_SKLEARN_VERSION,
    check_all_model_compatibilities,
    check_sklearn_version,
    get_model_compatibility_info,
)


class TestModelCompatibilityRegistry:
    """T-INFRA-007: 模型序列化兼容性文档单元测试"""

    def test_registry_not_empty(self) -> None:
        """验证兼容性注册表不为空"""
        assert len(MODEL_COMPATIBILITY_REGISTRY) > 0

    def test_registry_contains_key_models(self) -> None:
        """验证注册表包含关键模型"""
        key_models = [
            "structured_logistic_regression_quick",
            "text_bert_classifier",
            "fusion_dnn_best",
            "physiological_model_v2_dl",
        ]
        for model_id in key_models:
            assert model_id in MODEL_COMPATIBILITY_REGISTRY, f"Missing {model_id}"

    def test_model_info_has_required_fields(self) -> None:
        """验证每个模型信息包含必要字段"""
        for model_id, info in MODEL_COMPATIBILITY_REGISTRY.items():
            assert info.model_id == model_id
            assert info.format in ("joblib", "pickle", "keras", "json", "transformers")
            assert info.fallback_strategy == "heuristic_rule"
            assert isinstance(info.required_dependencies, list)
            assert len(info.required_dependencies) > 0

    def test_sklearn_models_have_version(self) -> None:
        """验证 sklearn 模型有版本要求"""
        sklearn_models = [
            k for k, v in MODEL_COMPATIBILITY_REGISTRY.items()
            if v.format == "joblib"
        ]
        for model_id in sklearn_models:
            info = MODEL_COMPATIBILITY_REGISTRY[model_id]
            assert info.sklearn_version is not None
            assert info.sklearn_version == TARGET_SKLEARN_VERSION

    def test_keras_models_have_tensorflow_version(self) -> None:
        """验证 keras 模型有 tensorflow 版本要求"""
        keras_models = [
            k for k, v in MODEL_COMPATIBILITY_REGISTRY.items()
            if v.format == "keras"
        ]
        for model_id in keras_models:
            info = MODEL_COMPATIBILITY_REGISTRY[model_id]
            assert info.tensorflow_version is not None

    def test_transformers_models_have_torch_and_transformers_version(self) -> None:
        """验证 transformers 模型有 torch 和 transformers 版本要求"""
        transformers_models = [
            k for k, v in MODEL_COMPATIBILITY_REGISTRY.items()
            if v.format == "transformers"
        ]
        for model_id in transformers_models:
            info = MODEL_COMPATIBILITY_REGISTRY[model_id]
            assert info.torch_version is not None
            assert info.transformers_version is not None

    def test_json_models_have_no_sklearn_version(self) -> None:
        """验证 json 格式模型没有 sklearn 版本要求"""
        json_models = [
            k for k, v in MODEL_COMPATIBILITY_REGISTRY.items()
            if v.format == "json"
        ]
        for model_id in json_models:
            info = MODEL_COMPATIBILITY_REGISTRY[model_id]
            assert info.sklearn_version is None
            assert info.torch_version is None
            assert info.tensorflow_version is None

    def test_get_model_compatibility_info_existing(self) -> None:
        """验证获取已注册模型的兼容性信息"""
        info = get_model_compatibility_info("physiological_model_v2_dl")
        assert info is not None
        assert info.format == "json"
        assert info.required_dependencies == ["numpy>=1.26.4"]

    def test_get_model_compatibility_info_nonexistent(self) -> None:
        """验证获取未注册模型返回 None"""
        info = get_model_compatibility_info("nonexistent_model")
        assert info is None

    def test_check_sklearn_version_match(self) -> None:
        """验证 sklearn 版本匹配检查"""
        with patch("sklearn.__version__", TARGET_SKLEARN_VERSION):
            is_compat, message = check_sklearn_version()
            assert is_compat is True
            assert TARGET_SKLEARN_VERSION in message

    def test_check_sklearn_version_mismatch(self) -> None:
        """验证 sklearn 版本不匹配检查"""
        with patch("sklearn.__version__", "1.2.0"):
            is_compat, message = check_sklearn_version()
            assert is_compat is False
            assert "mismatch" in message

    def test_check_all_model_compatibilities_structure(self) -> None:
        """验证批量兼容性检查结果结构"""
        results = check_all_model_compatibilities()
        assert len(results) == len(MODEL_COMPATIBILITY_REGISTRY)

        for model_id, (is_compat, message) in results.items():
            assert isinstance(is_compat, bool)
            assert isinstance(message, str)
            assert model_id in MODEL_COMPATIBILITY_REGISTRY

    def test_target_version_constant(self) -> None:
        """验证目标版本常量"""
        assert TARGET_SKLEARN_VERSION == "1.3.2"
        assert isinstance(TARGET_SKLEARN_VERSION, str)
