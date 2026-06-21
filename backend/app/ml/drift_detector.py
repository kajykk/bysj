"""
Drift Detection Module for Structured Model Monitoring.

Implements:
- Feature drift detection (KS test for numerical features)
- Prediction drift detection (PSI - Population Stability Index)
- Performance degradation monitoring
- Configurable thresholds and alerting
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Default thresholds
DEFAULT_DRIFT_THRESHOLDS = {
    "ks_test": 0.05,  # p-value threshold for KS test
    "psi": 0.25,  # PSI threshold (0.1=minor, 0.25=moderate, 0.5=major)
    "performance_drop": 0.05,  # 5% performance drop threshold
}


@dataclass
class DriftReport:
    """Drift detection report."""

    feature_drift: dict[str, dict[str, Any]]
    prediction_drift: dict[str, Any]
    performance_drift: dict[str, Any] | None
    is_drift_detected: bool
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "feature_drift": self.feature_drift,
            "prediction_drift": self.prediction_drift,
            "performance_drift": self.performance_drift,
            "is_drift_detected": self.is_drift_detected,
            "timestamp": self.timestamp,
        }


class DriftDetector:
    """Drift detector for structured model monitoring.

    Args:
        thresholds: Drift detection thresholds.
        reference_data: Reference data distribution.
    """

    def __init__(
        self,
        thresholds: dict[str, float] | None = None,
        reference_data: dict[str, np.ndarray] | None = None,
    ):
        """Initialize drift detector."""
        self.thresholds = thresholds or DEFAULT_DRIFT_THRESHOLDS.copy()
        self.reference_data = reference_data or {}

        logger.info(
            "DriftDetector initialized: thresholds=%s, reference_features=%d",
            self.thresholds,
            len(self.reference_data),
        )

    def set_reference_data(self, data: dict[str, np.ndarray]) -> None:
        """Set reference data distribution.

        Args:
            data: Dictionary of feature_name -> reference_values.
        """
        self.reference_data = data
        logger.info("Set reference data for %d features", len(data))

    def compute_ks_test(self, reference: np.ndarray, current: np.ndarray) -> dict[str, float]:
        """Compute Kolmogorov-Smirnov test.

        Args:
            reference: Reference data distribution.
            current: Current data distribution.

        Returns:
            Dictionary with KS statistic and p-value.
        """
        if len(reference) == 0 or len(current) == 0:
            logger.warning("Empty array detected in KS test: reference=%d, current=%d", len(reference), len(current))
            return {
                "statistic": 0.0,
                "p_value": 1.0,
                "is_drift": False,
                "error": "empty_array",
            }

        try:
            from scipy import stats

            statistic, p_value = stats.ks_2samp(reference, current)

            return {
                "statistic": float(statistic),
                "p_value": float(p_value),
                "is_drift": bool(p_value < self.thresholds["ks_test"]),
            }
        except ImportError:
            logger.warning("scipy not installed, using approximate KS test")
            return self._approximate_ks_test(reference, current)

    def _approximate_ks_test(self, reference: np.ndarray, current: np.ndarray) -> dict[str, float]:
        """Approximate KS test without scipy.

        Args:
            reference: Reference data distribution.
            current: Current data distribution.

        Returns:
            Dictionary with approximate KS statistic and p-value.
        """
        import warnings

        # Handle empty arrays
        if len(reference) == 0 or len(current) == 0:
            logger.warning("Empty array detected in KS test: reference=%d, current=%d", len(reference), len(current))
            return {
                "statistic": 0.0,
                "p_value": 1.0,
                "is_drift": False,
                "error": "empty_array",
            }

        # Handle single-value distributions
        if len(np.unique(reference)) == 1 and len(np.unique(current)) == 1:
            ref_val = reference[0]
            curr_val = current[0]
            statistic = 0.0 if ref_val == curr_val else 1.0
            return {
                "statistic": float(statistic),
                "p_value": 1.0 if statistic == 0.0 else 0.0,
                "is_drift": statistic > 0.0,
            }

        # Compute empirical CDFs
        ref_sorted = np.sort(reference)
        curr_sorted = np.sort(current)

        # Combine and sort all values
        all_values = np.sort(np.concatenate([ref_sorted, curr_sorted]))

        # Compute ECDFs
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            ref_cdf = np.searchsorted(ref_sorted, all_values, side="right") / len(ref_sorted)
            curr_cdf = np.searchsorted(curr_sorted, all_values, side="right") / len(curr_sorted)

        # KS statistic
        statistic = float(np.max(np.abs(ref_cdf - curr_cdf)))

        # Approximate p-value (simplified)
        n1, n2 = len(reference), len(current)
        en = np.sqrt(n1 * n2 / (n1 + n2))
        p_value = float(np.exp(-2 * (statistic * en) ** 2))

        return {
            "statistic": statistic,
            "p_value": p_value,
            "is_drift": bool(p_value < self.thresholds["ks_test"]),
        }

    def compute_psi(self, reference: np.ndarray, current: np.ndarray, bins: int = 10) -> dict[str, float]:
        """Compute Population Stability Index.

        Args:
            reference: Reference data distribution.
            current: Current data distribution.
            bins: Number of bins for PSI calculation.

        Returns:
            Dictionary with PSI value and interpretation.
        """
        import warnings

        # Handle empty arrays
        if len(reference) == 0 or len(current) == 0:
            logger.warning("Empty array detected in PSI: reference=%d, current=%d", len(reference), len(current))
            return {
                "psi": 0.0,
                "interpretation": "no_drift",
                "is_drift": False,
                "bins": bins,
                "error": "empty_array",
            }

        # Handle single-value distributions (all values identical)
        ref_unique = np.unique(reference)
        if len(ref_unique) == 1:
            curr_unique = np.unique(current)
            if len(curr_unique) == 1 and ref_unique[0] == curr_unique[0]:
                return {
                    "psi": 0.0,
                    "interpretation": "no_drift",
                    "is_drift": False,
                    "bins": 1,
                }
            else:
                # Single value reference but different current -> major drift
                return {
                    "psi": 1.0,
                    "interpretation": "major_drift",
                    "is_drift": True,
                    "bins": 1,
                }

        # Create bins based on reference data
        min_val = np.min(reference)
        max_val = np.max(reference)

        # Handle case where min == max (should be caught above, but double-check)
        if min_val == max_val:
            return {
                "psi": 0.0,
                "interpretation": "no_drift",
                "is_drift": False,
                "bins": 1,
                "error": "constant_distribution",
            }

        bin_edges = np.linspace(min_val, max_val, bins + 1)

        # Compute histograms
        ref_hist, _ = np.histogram(reference, bins=bin_edges)
        curr_hist, _ = np.histogram(current, bins=bin_edges)

        # Add small constant to avoid division by zero
        ref_sum = np.sum(ref_hist)
        curr_sum = np.sum(curr_hist)

        if ref_sum == 0 or curr_sum == 0:
            logger.warning("Zero sum histogram detected: ref_sum=%d, curr_sum=%d", ref_sum, curr_sum)
            return {
                "psi": 0.0,
                "interpretation": "no_drift",
                "is_drift": False,
                "bins": bins,
                "error": "zero_sum_histogram",
            }

        ref_dist = (ref_hist + 1e-10) / ref_sum
        curr_dist = (curr_hist + 1e-10) / curr_sum

        # Compute PSI with warning suppression for log(0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            psi_values = (curr_dist - ref_dist) * np.log(curr_dist / ref_dist)
            psi = float(np.sum(psi_values))

        # Interpretation
        if psi < 0.1:
            interpretation = "no_drift"
        elif psi < 0.25:
            interpretation = "minor_drift"
        elif psi < 0.5:
            interpretation = "moderate_drift"
        else:
            interpretation = "major_drift"

        return {
            "psi": psi,
            "interpretation": interpretation,
            "is_drift": psi >= self.thresholds["psi"],
            "bins": bins,
        }

    def detect_feature_drift(self, current_data: dict[str, np.ndarray]) -> dict[str, dict[str, Any]]:
        """Detect feature drift.

        Args:
            current_data: Dictionary of feature_name -> current_values.

        Returns:
            Dictionary of feature_name -> drift_results.
        """
        drift_results = {}

        for feature_name, current_values in current_data.items():
            if feature_name not in self.reference_data:
                logger.warning("No reference data for feature: %s", feature_name)
                continue

            reference_values = self.reference_data[feature_name]

            # KS test
            ks_result = self.compute_ks_test(reference_values, current_values)

            # PSI
            psi_result = self.compute_psi(reference_values, current_values)

            drift_results[feature_name] = {
                "ks_test": ks_result,
                "psi": psi_result,
                "is_drift": ks_result["is_drift"] or psi_result["is_drift"],
            }

        return drift_results

    def detect_prediction_drift(
        self,
        reference_predictions: np.ndarray,
        current_predictions: np.ndarray,
    ) -> dict[str, Any]:
        """Detect prediction drift.

        Args:
            reference_predictions: Reference prediction distribution.
            current_predictions: Current prediction distribution.

        Returns:
            Prediction drift results.
        """
        # KS test on predictions
        ks_result = self.compute_ks_test(reference_predictions, current_predictions)

        # PSI on predictions
        psi_result = self.compute_psi(reference_predictions, current_predictions)

        return {
            "ks_test": ks_result,
            "psi": psi_result,
            "is_drift": ks_result["is_drift"] or psi_result["is_drift"],
        }

    def detect_performance_drift(
        self,
        baseline_metrics: dict[str, float],
        current_metrics: dict[str, float],
    ) -> dict[str, Any]:
        """Detect performance degradation.

        Args:
            baseline_metrics: Baseline performance metrics.
            current_metrics: Current performance metrics.

        Returns:
            Performance drift results.
        """
        performance_changes = {}
        is_degraded = False

        for metric_name, baseline_value in baseline_metrics.items():
            if metric_name not in current_metrics:
                continue

            current_value = current_metrics[metric_name]
            change = baseline_value - current_value
            if baseline_value == 0:
                if current_value == 0:
                    # baseline 和 current 均为 0，无退化
                    relative_change = 0.0
                else:
                    # baseline=0 但 current 不为 0，表示严重退化（相对变化为无穷大）
                    relative_change = float('inf')
            else:
                relative_change = change / baseline_value

            performance_changes[metric_name] = {
                "baseline": baseline_value,
                "current": current_value,
                "change": change,
                "relative_change": relative_change,
                "is_degraded": relative_change > self.thresholds["performance_drop"],
            }

            if relative_change > self.thresholds["performance_drop"]:
                is_degraded = True

        return {
            "performance_changes": performance_changes,
            "is_degraded": is_degraded,
        }

    def detect_drift(
        self,
        current_data: dict[str, np.ndarray] | None = None,
        current_predictions: np.ndarray | None = None,
        reference_predictions: np.ndarray | None = None,
        baseline_metrics: dict[str, float] | None = None,
        current_metrics: dict[str, float] | None = None,
    ) -> DriftReport:
        """Run complete drift detection.

        Args:
            current_data: Current feature data.
            current_predictions: Current prediction distribution.
            reference_predictions: Reference prediction distribution.
            baseline_metrics: Baseline performance metrics.
            current_metrics: Current performance metrics.

        Returns:
            DriftReport with all drift detection results.
        """
        import time

        # Feature drift
        feature_drift = {}
        if current_data is not None:
            feature_drift = self.detect_feature_drift(current_data)

        # Prediction drift
        prediction_drift = {}
        if current_predictions is not None and reference_predictions is not None:
            prediction_drift = self.detect_prediction_drift(reference_predictions, current_predictions)

        # Performance drift
        performance_drift = None
        if baseline_metrics is not None and current_metrics is not None:
            performance_drift = self.detect_performance_drift(baseline_metrics, current_metrics)

        # Determine if drift is detected
        is_drift = any(r.get("is_drift", False) for r in feature_drift.values())
        is_drift = is_drift or prediction_drift.get("is_drift", False)
        is_drift = is_drift or (performance_drift.get("is_degraded", False) if performance_drift else False)

        report = DriftReport(
            feature_drift=feature_drift,
            prediction_drift=prediction_drift,
            performance_drift=performance_drift,
            is_drift_detected=is_drift,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        if is_drift:
            logger.warning("Drift detected! Check report for details.")

        return report

    def save_config(self, path: Path | str) -> None:
        """Save drift detector configuration.

        Args:
            path: Path to save configuration.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        config = {
            "thresholds": self.thresholds,
            "reference_features": list(self.reference_data.keys()),
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

        logger.info("Saved drift detector config to %s", path)

    @classmethod
    def load_config(cls, path: Path | str) -> "DriftDetector":
        """Load drift detector configuration.

        Args:
            path: Path to configuration file.

        Returns:
            DriftDetector instance.
        """
        path = Path(path)
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)

        return cls(thresholds=config.get("thresholds"))
