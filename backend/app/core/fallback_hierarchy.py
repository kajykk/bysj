"""Fallback hierarchy manager for model prediction resilience.

Implements a 4-layer fallback strategy:
L1: Primary Model (主模型)
L2: Fusion Model (融合模型)
L3: Rule-Based Fallback (规则回退)
L4: Heuristic Fallback (启发式兜底)

Each layer logs structured information on success/failure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class FallbackResult:
    """Result from a fallback layer attempt."""

    success: bool
    layer: str
    layer_desc: str
    result: Any = None
    error: str | None = None
    fallback_to: str | None = None


@dataclass
class FallbackLog:
    """Structured log entry for fallback events."""

    request_id: str
    layers_attempted: list[FallbackResult] = field(default_factory=list)
    final_layer: str | None = None
    final_result: Any = None

    def add_attempt(self, result: FallbackResult) -> None:
        self.layers_attempted.append(result)
        if result.success:
            self.final_layer = result.layer
            self.final_result = result.result

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "layers_attempted": [
                {
                    "layer": r.layer,
                    "layer_desc": r.layer_desc,
                    "success": r.success,
                    "error": r.error,
                }
                for r in self.layers_attempted
            ],
            "final_layer": self.final_layer,
        }


class FallbackHierarchy:
    """Manages the 4-layer fallback hierarchy for model predictions.

    Usage:
        hierarchy = FallbackHierarchy()
        hierarchy.register_layer("L1_PRIMARY", "主模型", primary_predict)
        hierarchy.register_layer("L2_FUSION", "融合模型", fusion_predict)
        hierarchy.register_layer("L3_RULE_BASED", "规则回退", rule_predict)
        hierarchy.register_layer("L4_HEURISTIC", "启发式兜底", heuristic_predict)

        result = hierarchy.predict_with_fallback(features, request_id="req-123")
    """

    def __init__(self) -> None:
        self._layers: list[tuple[str, str, Callable]] = []

    def register_layer(self, layer_code: str, layer_desc: str, predict_fn: Callable) -> None:
        """Register a fallback layer.

        Args:
            layer_code: Layer identifier (e.g., 'L1_PRIMARY')
            layer_desc: Human-readable description
            predict_fn: Callable that takes features and returns prediction
        """
        self._layers.append((layer_code, layer_desc, predict_fn))
        logger.info("Registered fallback layer: %s (%s)", layer_code, layer_desc)

    def predict_with_fallback(self, features: Any, request_id: str | None = None) -> tuple[Any, FallbackLog]:
        """Execute prediction with fallback support.

        Args:
            features: Input features for prediction
            request_id: Optional request identifier for logging

        Returns:
            Tuple of (prediction_result, fallback_log)
        """
        log = FallbackLog(request_id=request_id or "unknown")

        for i, (layer_code, layer_desc, predict_fn) in enumerate(self._layers):
            try:
                result = predict_fn(features)
                success_result = FallbackResult(
                    success=True,
                    layer=layer_code,
                    layer_desc=layer_desc,
                    result=result,
                )
                log.add_attempt(success_result)
                self._log_success(layer_code, layer_desc, request_id)
                return result, log
            except Exception as exc:
                error_msg = str(exc)
                fallback_to = self._layers[i + 1][0] if i + 1 < len(self._layers) else None
                fail_result = FallbackResult(
                    success=False,
                    layer=layer_code,
                    layer_desc=layer_desc,
                    error=error_msg,
                    fallback_to=fallback_to,
                )
                log.add_attempt(fail_result)
                self._log_failure(layer_code, layer_desc, error_msg, fallback_to, request_id)

        # All layers failed
        logger.error(
            "[FALLBACK_EXHAUSTED] All %d fallback layers failed for request=%s",
            len(self._layers),
            request_id,
        )
        raise FallbackExhaustedError(f"All fallback layers failed for request={request_id}")

    @staticmethod
    def _log_success(layer: str, desc: str, request_id: str | None) -> None:
        logger.info(
            "[FALLBACK_SUCCESS] layer=%s (%s) request_id=%s",
            layer,
            desc,
            request_id,
        )

    @staticmethod
    def _log_failure(layer: str, desc: str, error: str, fallback_to: str | None, request_id: str | None) -> None:
        logger.warning(
            "[FALLBACK_FAILURE] layer=%s (%s) error=%s fallback_to=%s request_id=%s",
            layer,
            desc,
            error,
            fallback_to,
            request_id,
        )


class FallbackExhaustedError(Exception):
    """Raised when all fallback layers have failed."""

    pass


# Global fallback hierarchy instance
fallback_hierarchy = FallbackHierarchy()
