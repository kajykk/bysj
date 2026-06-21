"""
Canary Release Controller for Model Deployment.

Implements:
- User ID based traffic allocation
- Parallel model execution (old + new)
- Result comparison and logging
- Gradual rollout support

- Safe rollback capability
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from app.ml.unified_model_interface import UnifiedModelWrapper

logger = logging.getLogger(__name__)


@dataclass
class CanaryConfig:
    """Canary release configuration."""

    new_model_traffic_percentage: float = 10.0  # Start with 10%
    user_id_salt: str = "canary_salt_v1"
    enable_parallel_execution: bool = True
    comparison_metrics: list[str] = field(default_factory=lambda: ["f1", "accuracy", "latency_ms"])


@dataclass
class ComparisonResult:
    """Result comparison between old and new models."""

    user_id: str
    old_model_result: dict[str, Any]
    new_model_result: dict[str, Any]
    old_model_latency_ms: float
    new_model_latency_ms: float
    timestamp: str
    differences: dict[str, float] = field(default_factory=dict)


class CanaryController:
    """Canary release controller for safe model deployment.

    Args:
        config: Canary configuration.
        old_model: Old model wrapper.
        new_model: New model wrapper.
    """

    def __init__(
        self,
        config: CanaryConfig | None = None,
        old_model: UnifiedModelWrapper | None = None,
        new_model: UnifiedModelWrapper | None = None,
    ):
        """Initialize canary controller."""
        self.config = config or CanaryConfig()
        self.old_model = old_model
        self.new_model = new_model
        self.comparison_history: list[ComparisonResult] = []
        self.new_model_requests = 0
        self.old_model_requests = 0

        logger.info(
            "CanaryController initialized: traffic=%.1f%%, parallel=%s",
            self.config.new_model_traffic_percentage,
            self.config.enable_parallel_execution,
        )

    def set_models(self, old_model: UnifiedModelWrapper, new_model: UnifiedModelWrapper) -> None:
        """Set old and new models.

        Args:
            old_model: Old model wrapper.
            new_model: New model wrapper.
        """
        self.old_model = old_model
        self.new_model = new_model

    def _hash_user_id(self, user_id: str) -> float:
        """Hash user ID to deterministic value.

        Args:
            user_id: User identifier.

        Returns:
            Float between 0 and 1.
        """
        hash_input = f"{user_id}:{self.config.user_id_salt}"
        hash_value = hashlib.sha256(hash_input.encode()).hexdigest()
        return int(hash_value, 16) / (2 ** 256)

    def should_use_new_model(self, user_id: str) -> bool:
        """Determine if user should use new model.

        Args:
            user_id: User identifier.

        Returns:
            True if user should use new model.
        """
        user_hash = self._hash_user_id(user_id)
        threshold = self.config.new_model_traffic_percentage / 100.0
        return user_hash < threshold

    def predict(
        self,
        X: np.ndarray,
        user_id: str = "anonymous",
    ) -> dict[str, Any]:
        """Make prediction with canary routing.

        Args:
            X: Input features.
            user_id: User identifier for routing.

        Returns:
            Prediction result with routing information.
        """
        use_new = self.should_use_new_model(user_id)

        if use_new and self.new_model is not None:
            self.new_model_requests += 1
            model_name = "new"
            model = self.new_model
        else:
            self.old_model_requests += 1
            model_name = "old"
            model = self.old_model

        # Make prediction
        start = time.perf_counter()
        predictions = model.predict(X)
        latency_ms = (time.perf_counter() - start) * 1000

        result = {
            "predictions": predictions,
            "model_used": model_name,
            "latency_ms": latency_ms,
            "user_id": user_id,
        }

        # Parallel execution for comparison
        if self.config.enable_parallel_execution and self.old_model is not None and self.new_model is not None:
            self._log_comparison(X, user_id)

        return result

    def _log_comparison(self, X: np.ndarray, user_id: str) -> None:
        """Log comparison between old and new models.

        Args:
            X: Input features.
            user_id: User identifier.
        """
        try:
            # Old model prediction
            old_start = time.perf_counter()
            old_predictions = self.old_model.predict(X)
            old_latency = (time.perf_counter() - old_start) * 1000

            # New model prediction
            new_start = time.perf_counter()
            new_predictions = self.new_model.predict(X)
            new_latency = (time.perf_counter() - new_start) * 1000

            # Calculate differences
            differences = {}
            if len(old_predictions) == len(new_predictions):
                differences["prediction_mismatch_rate"] = float(
                    np.mean(old_predictions != new_predictions)
                )

            comparison = ComparisonResult(
                user_id=user_id,
                old_model_result={"predictions": old_predictions.tolist()},
                new_model_result={"predictions": new_predictions.tolist()},
                old_model_latency_ms=old_latency,
                new_model_latency_ms=new_latency,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                differences=differences,
            )

            self.comparison_history.append(comparison)

            # Keep history bounded
            if len(self.comparison_history) > 10000:
                self.comparison_history = self.comparison_history[-10000:]

        except Exception as exc:
            logger.warning("Comparison logging failed: %s", exc)

    def get_comparison_summary(self) -> dict[str, Any]:
        """Get comparison summary.

        Returns:
            Dictionary with comparison statistics.
        """
        if not self.comparison_history:
            return {"message": "No comparison data available"}

        total_comparisons = len(self.comparison_history)
        mismatch_count = sum(
            1 for c in self.comparison_history
            if c.differences.get("prediction_mismatch_rate", 0) > 0
        )

        old_latencies = [c.old_model_latency_ms for c in self.comparison_history]
        new_latencies = [c.new_model_latency_ms for c in self.comparison_history]

        return {
            "total_comparisons": total_comparisons,
            "mismatch_count": mismatch_count,
            "mismatch_rate": mismatch_count / total_comparisons if total_comparisons > 0 else 0,
            "old_model": {
                "avg_latency_ms": np.mean(old_latencies) if old_latencies else 0,
                "p95_latency_ms": np.percentile(old_latencies, 95) if old_latencies else 0,
            },
            "new_model": {
                "avg_latency_ms": np.mean(new_latencies) if new_latencies else 0,
                "p95_latency_ms": np.percentile(new_latencies, 95) if new_latencies else 0,
            },
            "traffic_allocation": {
                "new_model_percentage": self.config.new_model_traffic_percentage,
                "new_model_requests": self.new_model_requests,
                "old_model_requests": self.old_model_requests,
            },
        }

    def adjust_traffic(self, new_percentage: float) -> None:
        """Adjust traffic allocation.

        Args:
            new_percentage: New traffic percentage for new model.
        """
        old_percentage = self.config.new_model_traffic_percentage
        self.config.new_model_traffic_percentage = new_percentage

        logger.info(
            "Traffic adjusted: %.1f%% -> %.1f%%",
            old_percentage,
            new_percentage,
        )

    def promote_new_model(self) -> None:
        """Promote new model to 100% traffic."""
        self.adjust_traffic(100.0)
        logger.info("New model promoted to 100% traffic")

    def rollback(self) -> None:
        """Rollback to old model (0% traffic for new model)."""
        self.adjust_traffic(0.0)
        logger.info("Rolled back to old model (0% traffic for new model)")

    def save_state(self, path: Path | str) -> None:
        """Save canary state.

        Args:
            path: Path to save state.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        state = {
            "config": {
                "new_model_traffic_percentage": self.config.new_model_traffic_percentage,
                "user_id_salt": self.config.user_id_salt,
                "enable_parallel_execution": self.config.enable_parallel_execution,
            },
            "statistics": {
                "new_model_requests": self.new_model_requests,
                "old_model_requests": self.old_model_requests,
                "total_comparisons": len(self.comparison_history),
            },
            "comparison_summary": self.get_comparison_summary(),
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

        logger.info("Saved canary state to %s", path)

    @classmethod
    def load_state(cls, path: Path | str) -> "CanaryController":
        """Load canary state.

        Args:
            path: Path to state file.

        Returns:
            CanaryController instance.
        """
        path = Path(path)
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)

        config = CanaryConfig(
            new_model_traffic_percentage=state["config"]["new_model_traffic_percentage"],
            user_id_salt=state["config"]["user_id_salt"],
            enable_parallel_execution=state["config"]["enable_parallel_execution"],
        )

        controller = cls(config=config)
        controller.new_model_requests = state["statistics"]["new_model_requests"]
        controller.old_model_requests = state["statistics"]["old_model_requests"]

        return controller
