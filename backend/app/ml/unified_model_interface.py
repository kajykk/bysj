"""
Unified Model Interface for Model Governance.

Defines standard interfaces for all models:
- predict(): Standard prediction interface
- predict_proba(): Probability prediction interface
- load_model(): Model loading interface
- get_version(): Version information
- get_latency(): Latency reporting

- Version tracking
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class BaseModel(ABC):
    """Base class for all models with unified interface.

    All models must implement these methods to ensure
    consistent behavior across the system.
    """

    def __init__(self, model_name: str, model_version: str):
        """Initialize base model.

        Args:
            model_name: Name of the model.
            model_version: Version string.
        """
        self.model_name = model_name
        self.model_version = model_version
        self._last_latency_ms = 0.0

    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Make predictions.

        Args:
            X: Input features.

        Returns:
            Predicted labels.
        """
        pass

    @abstractmethod
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Make probability predictions.

        Args:
            X: Input features.

        Returns:
            Predicted probabilities.
        """
        pass

    @classmethod
    @abstractmethod
    def load_model(cls, path: Path | str) -> "BaseModel":
        """Load model from file.

        Args:
            path: Path to model file.

        Returns:
            Loaded model instance.
        """
        pass

    def get_version(self) -> dict[str, str]:
        """Get model version information.

        Returns:
            Dictionary with model name and version.
        """
        return {
            "model_name": self.model_name,
            "model_version": self.model_version,
        }

    def get_latency(self) -> float:
        """Get last prediction latency.

        Returns:
            Last prediction latency in milliseconds.
        """
        return self._last_latency_ms

    def _measure_latency(self, func, *args, **kwargs):
        """Measure execution latency.

        Args:
            func: Function to measure.
            *args: Function arguments.
            **kwargs: Function keyword arguments.

        Returns:
            Function result.
        """
        start = time.perf_counter()
        result = func(*args, **kwargs)
        self._last_latency_ms = (time.perf_counter() - start) * 1000
        return result


class UnifiedModelWrapper:
    """Wrapper that provides unified interface for any model.

    Args:
        model: Model instance to wrap.
        model_type: Type of model (xgboost, lightgbm, pytorch, numpy, etc.).
    """

    def __init__(self, model: Any, model_type: str):
        """Initialize unified model wrapper."""
        self.model = model
        self.model_type = model_type
        self._fallback_models: list[Any] = []

        logger.info("UnifiedModelWrapper created for %s", model_type)

    def set_fallback(self, fallback_model: Any) -> None:
        """Set fallback model.

        Args:
            fallback_model: Fallback model instance.
        """
        self._fallback_models.append(fallback_model)
        logger.info(
            "Fallback model set for %s (total: %d)",
            self.model_type,
            len(self._fallback_models),
        )

    def _try_predict(self, model: Any, X: np.ndarray) -> np.ndarray:
        """Try to predict with a model.

        Args:
            model: Model to use.
            X: Input features.

        Returns:
            Predicted labels.

        Raises:
            Exception: If prediction fails or contains NaN/Inf.
        """
        if hasattr(model, "predict"):
            predictions = model.predict(X)
        else:
            predictions = model(X)

        # Check for NaN/Inf in predictions
        if isinstance(predictions, np.ndarray):
            if np.any(np.isnan(predictions)) or np.any(np.isinf(predictions)):
                raise ValueError("Predictions contain NaN or Inf values")
        return predictions

    def _heuristic_predictions(self, X: np.ndarray) -> np.ndarray:
        """Final deterministic fallback when all configured models fail.

        ML-007 修复：返回保守的"有风险"默认值（1）而非全零（0）。

        在抑郁症预警系统中，假阴性（漏报）的代价远高于假阳性（误报）：
        - 假阴性 = 漏掉需要干预的用户，可能导致严重后果
        - 假阳性 = 触发额外评估，仅增加少量成本

        因此当所有模型均失败时，应采用保守策略：标记为"有风险"以触发
        进一步人工评估，而非返回"无风险"的全零预测。
        """
        rows = len(X) if hasattr(X, "__len__") else 1
        logger.warning(
            "[ML-007] 启发式回退：所有模型预测失败，返回保守默认值（prediction=1, "
            "rows=%d）。请检查模型可用性。",
            rows,
        )
        return np.ones(rows, dtype=int)

    def _heuristic_probabilities(self, X: np.ndarray) -> np.ndarray:
        """Final deterministic probability fallback when all configured models fail.

        ML-007 修复：返回 0.5（最大不确定性）的概率值，而非抛出异常。

        返回 0.5 的理由：
        - 0.5 表示最大不确定性，不会误导决策
        - 与 ``_heuristic_predictions`` 返回 1（有风险）保持逻辑一致
        - 触发后续人工审核流程
        """
        rows = len(X) if hasattr(X, "__len__") else 1
        logger.warning(
            "[ML-007] 启发式回退：所有模型概率预测失败，返回保守默认值（probability=0.5, "
            "rows=%d）。请检查模型可用性。",
            rows,
        )
        # 返回 shape=(rows, 2) 的概率矩阵，P(class=1)=0.5
        return np.full((rows, 2), 0.5, dtype=float)

    def _validate_probabilities(self, probabilities: np.ndarray) -> np.ndarray:
        """Validate probability output shape and range."""
        probabilities = np.asarray(probabilities, dtype=float)
        if np.any(np.isnan(probabilities)) or np.any(np.isinf(probabilities)):
            raise ValueError("Probabilities contain NaN or Inf values")
        if np.any(probabilities < 0) or np.any(probabilities > 1):
            raise ValueError("Probabilities outside [0, 1] range")
        return probabilities

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Make predictions with fallback support.

        Args:
            X: Input features.

        Returns:
            Predicted labels.
        """
        # Try primary model first
        try:
            return self._try_predict(self.model, X)
        except Exception as exc:
            logger.warning("Primary model prediction failed: %s", exc)

        # Try fallback models in order
        for i, fallback in enumerate(self._fallback_models):
            try:
                logger.info("Falling back to fallback model %d", i + 1)
                return self._try_predict(fallback, X)
            except Exception as exc:
                logger.warning("Fallback model %d failed: %s", i + 1, exc)

        # All models failed. Only use deterministic heuristic fallback when a
        # fallback chain was explicitly configured.
        if self._fallback_models:
            logger.warning("All configured models failed, using heuristic fallback")
            return self._heuristic_predictions(X)
        raise RuntimeError("All models in fallback chain failed")

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Make probability predictions with fallback support.

        Args:
            X: Input features.

        Returns:
            Predicted probabilities.
        """
        try:
            if hasattr(self.model, "predict_proba"):
                return self._validate_probabilities(self.model.predict_proba(X))
            else:
                raise AttributeError("Model does not have predict_proba method")
        except Exception as exc:
            logger.warning("Primary model predict_proba failed: %s", exc)
            for i, fallback in enumerate(self._fallback_models):
                try:
                    logger.info("Falling back to fallback model %d", i + 1)
                    if hasattr(fallback, "predict_proba"):
                        return self._validate_probabilities(fallback.predict_proba(X))
                except Exception as fallback_exc:
                    logger.warning(
                        "Fallback model %d predict_proba failed: %s",
                        i + 1,
                        fallback_exc,
                    )

            # ML-007 修复：与 predict() 保持一致，当配置了回退链时使用启发式概率回退
            if self._fallback_models:
                logger.warning(
                    "All configured models failed for predict_proba, using heuristic fallback"
                )
                return self._heuristic_probabilities(X)
            raise RuntimeError("All models in fallback chain failed for predict_proba")

    def get_version(self) -> dict[str, str]:
        """Get model version information.

        Returns:
            Dictionary with model information.
        """
        if hasattr(self.model, "get_version"):
            return self.model.get_version()
        else:
            return {
                "model_type": self.model_type,
                "model_class": self.model.__class__.__name__,
            }

    def get_latency(self) -> float:
        """Get last prediction latency.

        Returns:
            Last prediction latency in milliseconds.
        """
        if hasattr(self.model, "get_latency"):
            return self.model.get_latency()
        return 0.0


class ModelRegistry:
    """Registry for managing multiple models.

    Provides centralized model management with:
    - Model registration
    - Version tracking
    - Fallback chain management
    """

    def __init__(self):
        """Initialize model registry."""
        self._models: dict[str, UnifiedModelWrapper] = {}
        self._fallback_chains: dict[str, list[str]] = {}

        logger.info("ModelRegistry initialized")

    def register(
        self,
        name: str,
        model: Any,
        model_type: str,
        fallback_names: list[str] | None = None,
    ) -> None:
        """Register a model.

        Args:
            name: Model name.
            model: Model instance.
            model_type: Model type.
            fallback_names: List of fallback model names.
        """
        wrapper = UnifiedModelWrapper(model, model_type)
        self._models[name] = wrapper

        if fallback_names:
            self._fallback_chains[name] = fallback_names

        logger.info("Registered model: %s (type: %s)", name, model_type)

    def get_model(self, name: str) -> UnifiedModelWrapper:
        """Get a registered model.

        Args:
            name: Model name.

        Returns:
            UnifiedModelWrapper instance.

        Raises:
            KeyError: If model not found.
        """
        if name not in self._models:
            raise KeyError(f"Model not found: {name}")
        return self._models[name]

    def setup_fallback_chain(self, name: str) -> None:
        """Setup fallback chain for a model.

        Args:
            name: Primary model name.
        """
        if name not in self._fallback_chains:
            return

        wrapper = self._models[name]
        fallback_names = self._fallback_chains[name]

        # Add all available fallback models to the chain
        for fallback_name in fallback_names:
            if fallback_name in self._models:
                wrapper.set_fallback(self._models[fallback_name].model)
                logger.info(
                    "Setup fallback: %s -> %s",
                    name,
                    fallback_name,
                )

    def list_models(self) -> list[dict[str, str]]:
        """List all registered models.

        Returns:
            List of model information dictionaries.
        """
        return [
            {
                "name": name,
                "type": wrapper.model_type,
                "version": str(wrapper.get_version()),
            }
            for name, wrapper in self._models.items()
        ]

    def get_health_status(self) -> dict[str, Any]:
        """Get health status of all models.

        Returns:
            Dictionary with health status.
        """
        status = {}
        for name, wrapper in self._models.items():
            try:
                # Try to get version as health check
                version = wrapper.get_version()
                status[name] = {
                    "status": "healthy",
                    "version": version,
                }
            except Exception as exc:
                status[name] = {
                    "status": "unhealthy",
                    "error": str(exc),
                }

        return status
