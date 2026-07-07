"""
Enhanced Fusion Engine with Modality Missing Handling and Confidence Weighting.

Features:
- Dynamic weight adjustment based on confidence scores
- Modality missing robustness with weight redistribution
- Single/dual modality degradation strategies
- Configurable fusion schemes

- Latency monitoring
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Default fusion weights
DEFAULT_WEIGHTS = {
    "structured": 0.55,
    "text": 0.30,
    "physiological": 0.15,
}

# Confidence thresholds
CONFIDENCE_THRESHOLDS = {
    "high": 0.8,
    "medium": 0.5,
    "low": 0.3,
}


class FusionEngine:
    """Enhanced fusion engine with modality missing handling.

    Args:
        weights: Base fusion weights for each modality.
        use_confidence_weighting: Whether to use confidence-based weight adjustment.
        use_modality_missing_handling: Whether to handle missing modalities.
    """

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        use_confidence_weighting: bool = True,
        use_modality_missing_handling: bool = True,
    ):
        """Initialize fusion engine."""
        self.weights = weights or DEFAULT_WEIGHTS.copy()
        self.use_confidence_weighting = use_confidence_weighting
        self.use_modality_missing_handling = use_modality_missing_handling

        # Validate weights sum to ~1.0
        total = sum(self.weights.values())
        if not (0.99 <= total <= 1.01):
            logger.warning("Weights sum to %.3f, normalizing", total)
            self.weights = {k: v / total for k, v in self.weights.items()}

        logger.info(
            "FusionEngine initialized: weights=%s, confidence=%s, missing_handling=%s",
            self.weights,
            use_confidence_weighting,
            use_modality_missing_handling,
        )

    def compute_confidence(
        self, modality: str, score: float, metadata: dict[str, Any] | None = None
    ) -> float:
        """Compute confidence score for a modality.

        Args:
            modality: Modality name.
            score: Risk score (0-100).
            metadata: Additional metadata for confidence calculation.

        Returns:
            Confidence score (0-1).
        """
        if not self.use_confidence_weighting:
            return 1.0

        # Base confidence from score extremity
        # Scores near 0 or 100 are more confident than scores near 50
        extremity = abs(score - 50) / 50  # 0 at 50, 1 at 0 or 100
        base_confidence = 0.5 + 0.5 * extremity

        # Modality-specific confidence adjustments
        if modality == "structured":
            # Structured data is generally more reliable
            base_confidence = min(1.0, base_confidence * 1.1)
        elif modality == "text":
            # Text confidence depends on length and sentiment clarity
            if metadata:
                text_length = metadata.get("text_length", 0)
                if text_length < 10:
                    base_confidence *= 0.7  # Short text is less reliable
                elif text_length > 100:
                    base_confidence = min(1.0, base_confidence * 1.05)
        elif modality == "physiological":
            # Physiological confidence depends on data completeness
            if metadata:
                missing_fields = metadata.get("missing_fields", 0)
                if missing_fields > 0:
                    base_confidence *= 1 - missing_fields * 0.2

        return float(np.clip(base_confidence, 0.1, 1.0))

    def redistribute_weights(self, available_modalities: set[str]) -> dict[str, float]:
        """Redistribute weights when modalities are missing.

        Args:
            available_modalities: Set of available modality names.

        Returns:
            Redistributed weights.
        """
        if not self.use_modality_missing_handling:
            return {k: v for k, v in self.weights.items() if k in available_modalities}

        # Get weights for available modalities
        available_weights = {
            k: v for k, v in self.weights.items() if k in available_modalities
        }

        if not available_weights:
            return {}

        # Normalize weights to sum to 1.0
        total = sum(available_weights.values())
        if total == 0:
            # Equal distribution if all weights are 0
            n = len(available_weights)
            return {k: 1.0 / n for k in available_weights}

        return {k: v / total for k, v in available_weights.items()}

    def fuse(
        self,
        modality_scores: dict[str, float],
        modality_metadata: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Fuse modality scores into a single risk score.

        Args:
            modality_scores: Dictionary of modality -> score.
            modality_metadata: Optional metadata for each modality.

        Returns:
            Dictionary with fused score and details.
        """
        if not modality_scores:
            return {
                "risk_score": 0.0,
                "risk_level": 0,
                "confidence": 0.0,
                "modality_contributions": {},
                "fusion_scheme": "empty",
            }

        # L-ML-6 修复：校验 modality_scores 值类型，None 或非数值类型会导致 TypeError
        for k, v in modality_scores.items():
            if v is None or not isinstance(v, (int, float)):
                raise TypeError(
                    f"modality_scores[{k!r}] 必须为数值类型，实际为 {type(v).__name__}"
                )

        modality_metadata = modality_metadata or {}
        available_modalities = set(modality_scores.keys())

        # Redistribute weights for missing modalities
        weights = self.redistribute_weights(available_modalities)

        if not weights:
            return {
                "risk_score": 0.0,
                "risk_level": 0,
                "confidence": 0.0,
                "modality_contributions": {},
                "fusion_scheme": "no_weights",
            }

        # Compute confidence for each modality
        confidences = {}
        for modality, score in modality_scores.items():
            metadata = modality_metadata.get(modality, {})
            confidences[modality] = self.compute_confidence(modality, score, metadata)

        # Apply confidence weighting
        final_weights = {}
        for modality in available_modalities:
            if modality in weights:
                if self.use_confidence_weighting:
                    final_weights[modality] = weights[modality] * confidences[modality]
                else:
                    final_weights[modality] = weights[modality]

        # Normalize final weights
        total_weight = sum(final_weights.values())
        if total_weight > 0:
            final_weights = {k: v / total_weight for k, v in final_weights.items()}

        # Compute fused score
        fused_score = sum(
            modality_scores[m] * final_weights.get(m, 0) for m in available_modalities
        )

        # Compute overall confidence
        overall_confidence = np.mean(list(confidences.values())) if confidences else 0.0

        # Determine risk level
        risk_level = self._score_to_level(fused_score)

        # Compute modality contributions
        modality_contributions = {}
        for modality in available_modalities:
            contribution = modality_scores[modality] * final_weights.get(modality, 0)
            modality_contributions[modality] = {
                "score": modality_scores[modality],
                "weight": final_weights.get(modality, 0),
                "confidence": confidences.get(modality, 0),
                "contribution": contribution,
            }

        # Determine fusion scheme
        if len(available_modalities) == 3:
            fusion_scheme = "full_three_modality"
        elif len(available_modalities) == 2:
            fusion_scheme = "dual_modality"
        elif len(available_modalities) == 1:
            fusion_scheme = "single_modality"
        else:
            fusion_scheme = "unknown"

        return {
            "risk_score": round(fused_score, 2),
            "risk_level": risk_level,
            "confidence": round(overall_confidence, 3),
            "modality_contributions": modality_contributions,
            "fusion_scheme": fusion_scheme,
            "available_modalities": list(available_modalities),
            "missing_modalities": list(set(self.weights.keys()) - available_modalities),
        }

    def _score_to_level(self, score: float) -> int:
        """Convert risk score to risk level using fusion modality thresholds.

        Args:
            score: Risk score (0-100).

        Returns:
            Risk level (0-4).
        """
        from app.core.risk_thresholds import MODALITY_RISK_THRESHOLDS

        thresholds = MODALITY_RISK_THRESHOLDS.get(
            "fusion",
            {
                "mild": 22,
                "moderate": 42,
                "high": 62,
                "critical": 82,
            },
        )
        if score >= thresholds["critical"]:
            return 4
        if score >= thresholds["high"]:
            return 3
        if score >= thresholds["moderate"]:
            return 2
        if score >= thresholds["mild"]:
            return 1
        return 0

    def save_config(self, path: Path | str) -> None:
        """Save fusion engine configuration.

        Args:
            path: Path to save configuration.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        config = {
            "weights": self.weights,
            "use_confidence_weighting": self.use_confidence_weighting,
            "use_modality_missing_handling": self.use_modality_missing_handling,
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

        logger.info("Saved fusion config to %s", path)

    @classmethod
    def load_config(cls, path: Path | str) -> "FusionEngine":
        """Load fusion engine configuration.

        M25 修复：加载配置前校验文件完整性，防止融合权重被篡改导致
        所有用户被判定为低风险（绕过预警系统）。

        Args:
            path: Path to configuration file.

        Returns:
            FusionEngine instance.

        Raises:
            FileNotFoundError: If config file does not exist.
            ValueError: If integrity check fails or weights are invalid.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Fusion config not found: {path}")

        # M25 修复：校验配置文件完整性
        from app.ml.model_loader import _verify_integrity

        _verify_integrity(path, require_checksum=True)

        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)

        # M25 修复：校验权重合法性（非负且和为 1.0）
        weights = config.get("weights")
        if weights is not None:
            weight_sum = (
                sum(weights.values()) if isinstance(weights, dict) else sum(weights)
            )
            if weight_sum <= 0:
                raise ValueError(f"融合权重总和必须为正数，实际为 {weight_sum}")
            if any(
                w < 0
                for w in (weights.values() if isinstance(weights, dict) else weights)
            ):
                raise ValueError("融合权重不能为负数")

        return cls(
            weights=weights,
            use_confidence_weighting=config.get("use_confidence_weighting", True),
            use_modality_missing_handling=config.get(
                "use_modality_missing_handling", True
            ),
        )
