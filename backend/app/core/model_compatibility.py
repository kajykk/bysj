"""Model compatibility checker for sklearn version alignment.

Ensures training and inference environments use the same sklearn version
to prevent serialization/deserialization issues.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Target sklearn version range for training and inference
# v1.31: 扩展支持范围以兼容主流生产环境 (1.7.x 和 1.8.x)
# v1.40: 统一到 >=1.5.0,<2.0.0，与 requirements.txt 和 requirements-ml.txt 保持一致
SKLEARN_MIN_VERSION = "1.5.0"
SKLEARN_MAX_VERSION = "2.0.0"

# Backward compatibility alias for tests
TARGET_SKLEARN_VERSION = SKLEARN_MIN_VERSION


@dataclass(frozen=True)
class ModelCompatibilityInfo:
    """Model compatibility information."""

    model_id: str
    format: str  # joblib, pickle, keras, json, etc.
    sklearn_version: str | None
    torch_version: str | None
    transformers_version: str | None
    tensorflow_version: str | None
    required_dependencies: list[str]
    fallback_strategy: str


# Model compatibility registry
MODEL_COMPATIBILITY_REGISTRY: dict[str, ModelCompatibilityInfo] = {
    "structured_logistic_regression_quick": ModelCompatibilityInfo(
        model_id="structured_logistic_regression_quick",
        format="joblib",
        sklearn_version="1.5.0",
        torch_version=None,
        transformers_version=None,
        tensorflow_version=None,
        required_dependencies=["scikit-learn>=1.5.0,<2.0.0", "joblib>=1.4.2"],
        fallback_strategy="heuristic_rule",
    ),
    "structured_random_forest_quick": ModelCompatibilityInfo(
        model_id="structured_random_forest_quick",
        format="joblib",
        sklearn_version="1.5.0",
        torch_version=None,
        transformers_version=None,
        tensorflow_version=None,
        required_dependencies=["scikit-learn>=1.5.0,<2.0.0", "joblib>=1.4.2"],
        fallback_strategy="heuristic_rule",
    ),
    "structured_best_ensemble_quick": ModelCompatibilityInfo(
        model_id="structured_best_ensemble_quick",
        format="joblib",
        sklearn_version="1.5.0",
        torch_version=None,
        transformers_version=None,
        tensorflow_version=None,
        required_dependencies=["scikit-learn>=1.5.0,<2.0.0", "joblib>=1.4.2"],
        fallback_strategy="heuristic_rule",
    ),
    "text_bert_classifier": ModelCompatibilityInfo(
        model_id="text_bert_classifier",
        format="transformers",
        sklearn_version=None,
        torch_version="2.2.0",
        transformers_version="4.36.2",
        tensorflow_version=None,
        required_dependencies=["torch>=2.2.0", "transformers>=4.36.2"],
        fallback_strategy="heuristic_rule",
    ),
    "text_improved_bilingual_model": ModelCompatibilityInfo(
        model_id="text_improved_bilingual_model",
        format="joblib",
        sklearn_version="1.5.0",
        torch_version=None,
        transformers_version=None,
        tensorflow_version=None,
        required_dependencies=["scikit-learn>=1.5.0,<2.0.0", "joblib>=1.4.2"],
        fallback_strategy="heuristic_rule",
    ),
    "fusion_dnn_best": ModelCompatibilityInfo(
        model_id="fusion_dnn_best",
        format="keras",
        sklearn_version=None,
        torch_version=None,
        transformers_version=None,
        tensorflow_version="2.20.0",
        required_dependencies=["tensorflow>=2.20.0"],
        fallback_strategy="heuristic_rule",
    ),
    "fusion_cross_modal_best": ModelCompatibilityInfo(
        model_id="fusion_cross_modal_best",
        format="keras",
        sklearn_version=None,
        torch_version=None,
        transformers_version=None,
        tensorflow_version="2.20.0",
        required_dependencies=["tensorflow>=2.20.0"],
        fallback_strategy="heuristic_rule",
    ),
    "fusion_transformer_best": ModelCompatibilityInfo(
        model_id="fusion_transformer_best",
        format="keras",
        sklearn_version=None,
        torch_version=None,
        transformers_version=None,
        tensorflow_version="2.20.0",
        required_dependencies=["tensorflow>=2.20.0"],
        fallback_strategy="heuristic_rule",
    ),
    "physiological_risk_model": ModelCompatibilityInfo(
        model_id="physiological_risk_model",
        format="joblib",
        sklearn_version="1.5.0",
        torch_version=None,
        transformers_version=None,
        tensorflow_version=None,
        required_dependencies=["scikit-learn>=1.5.0,<2.0.0", "joblib>=1.4.2"],
        fallback_strategy="heuristic_rule",
    ),
    "physiological_model_v2_dl": ModelCompatibilityInfo(
        model_id="physiological_model_v2_dl",
        format="json",
        sklearn_version=None,
        torch_version=None,
        transformers_version=None,
        tensorflow_version=None,
        required_dependencies=["numpy>=1.26.4"],
        fallback_strategy="heuristic_rule",
    ),
}


def check_sklearn_version() -> tuple[bool, str]:
    """Check if current sklearn version is within supported range.

    Returns:
        Tuple of (is_compatible, message).
    """
    try:
        import sklearn
        from packaging import version

        current_version = version.parse(sklearn.__version__)
        min_version = version.parse(SKLEARN_MIN_VERSION)
        max_version = version.parse(SKLEARN_MAX_VERSION)

        if min_version <= current_version < max_version:
            return True, f"sklearn version {sklearn.__version__} is within supported range [{SKLEARN_MIN_VERSION}, {SKLEARN_MAX_VERSION})"
        return (
            False,
            f"sklearn version mismatch: current {sklearn.__version__} outside supported range [{SKLEARN_MIN_VERSION}, {SKLEARN_MAX_VERSION})",
        )
    except ImportError:
        return False, "sklearn not installed"


def verify_model_compatibility(model: Any) -> tuple[bool, str]:
    """Verify model compatibility with current environment.

    Args:
        model: Loaded model object.

    Returns:
        Tuple of (is_compatible, message).
    """
    is_compat, message = check_sklearn_version()
    if not is_compat:
        logger.warning("Model compatibility check failed: %s", message)
        return is_compat, message

    # Check for known version-specific attributes
    if hasattr(model, "named_steps"):
        for step_name, step in model.named_steps.items():
            if step_name == "preprocessor":
                continue
            if hasattr(step, "sklearn_version"):
                model_sklearn = step.sklearn_version
                from packaging import version
                model_v = version.parse(model_sklearn)
                min_v = version.parse(SKLEARN_MIN_VERSION)
                max_v = version.parse(SKLEARN_MAX_VERSION)
                if not (min_v <= model_v < max_v):
                    return (
                        False,
                        f"Model trained with sklearn {model_sklearn}, outside supported range [{SKLEARN_MIN_VERSION}, {SKLEARN_MAX_VERSION})",
                    )

    return True, "Model compatibility verified"


def load_model_with_compatibility_check(model_path: Path) -> Any:
    """Load model with version compatibility check.

    Args:
        model_path: Path to model file.

    Returns:
        Loaded model.

    Raises:
        ValueError: If compatibility check fails or path is unsafe.
    """
    is_compat, message = check_sklearn_version()
    if not is_compat:
        warnings.warn(
            f"{message}. Model loading may fail or produce incorrect results.",
            RuntimeWarning,
            stacklevel=2,
        )

    # ML-005 修复：使用安全加载器（路径校验 + 大小校验 + 审计日志）
    from app.core.safe_pickle import safe_joblib_load

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        model = safe_joblib_load(model_path, model_id=str(model_path.name))

        # Check for version warnings
        version_warnings = [
            warning
            for warning in w
            if "version" in str(warning.message).lower()
            or "incompatible" in str(warning.message).lower()
        ]
        if version_warnings:
            for warning in version_warnings:
                logger.warning("Model loading warning: %s", warning.message)

    return model


def get_model_compatibility_info(model_id: str) -> ModelCompatibilityInfo | None:
    """Get compatibility info for a model.

    Args:
        model_id: Model identifier.

    Returns:
        Compatibility info or None if not found.
    """
    return MODEL_COMPATIBILITY_REGISTRY.get(model_id)


def check_all_model_compatibilities() -> dict[str, tuple[bool, str]]:
    """Check compatibility for all registered models.

    Returns:
        Dictionary mapping model_id to (is_compatible, message).
    """
    results: dict[str, tuple[bool, str]] = {}
    for model_id, info in MODEL_COMPATIBILITY_REGISTRY.items():
        is_compat = True
        messages: list[str] = []

        if info.sklearn_version:
            is_sklearn_compat, sklearn_msg = check_sklearn_version()
            if not is_sklearn_compat:
                is_compat = False
            messages.append(sklearn_msg)

        if info.torch_version:
            try:
                import torch

                current = torch.__version__
                if current != info.torch_version:
                    is_compat = False
                    messages.append(f"torch mismatch: current={current}, required={info.torch_version}")
                else:
                    messages.append(f"torch {current} OK")
            except ImportError:
                is_compat = False
                messages.append("torch not installed")

        if info.transformers_version:
            try:
                import transformers

                current = transformers.__version__
                if current != info.transformers_version:
                    is_compat = False
                    messages.append(f"transformers mismatch: current={current}, required={info.transformers_version}")
                else:
                    messages.append(f"transformers {current} OK")
            except ImportError:
                is_compat = False
                messages.append("transformers not installed")

        if info.tensorflow_version:
            try:
                import tensorflow as tf

                current = tf.__version__
                if current != info.tensorflow_version:
                    is_compat = False
                    messages.append(f"tensorflow mismatch: current={current}, required={info.tensorflow_version}")
                else:
                    messages.append(f"tensorflow {current} OK")
            except ImportError:
                is_compat = False
                messages.append("tensorflow not installed")

        results[model_id] = (is_compat, "; ".join(messages))

    return results
