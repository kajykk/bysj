from __future__ import annotations

import math
from typing import Iterable

import numpy as np


class DriftDetector:
    """Lightweight drift detector utilities.

    Provides a stable Population Stability Index implementation that is safe for
    empty, single-valued, and extreme distributions.
    """

    def calculate_psi(
        self,
        baseline: Iterable[float] | np.ndarray,
        current: Iterable[float] | np.ndarray,
        buckets: int = 10,
    ) -> float:
        """Calculate PSI between baseline and current distributions.

        Returns 0.0 when input is insufficient or degenerate instead of raising,
        which keeps monitoring/fallback paths resilient.
        """
        base = self._clean_array(baseline)
        curr = self._clean_array(current)

        if base.size == 0 or curr.size == 0:
            return 0.0

        combined = np.concatenate((base, curr))
        min_value = float(np.min(combined))
        max_value = float(np.max(combined))
        if not math.isfinite(min_value) or not math.isfinite(max_value) or min_value == max_value:
            return 0.0

        bucket_count = max(2, int(buckets))
        edges = np.linspace(min_value, max_value, bucket_count + 1)
        edges[0] = -np.inf
        edges[-1] = np.inf

        base_counts, _ = np.histogram(base, bins=edges)
        curr_counts, _ = np.histogram(curr, bins=edges)

        epsilon = 1e-6
        base_pct = np.maximum(base_counts.astype(float) / max(1, base.size), epsilon)
        curr_pct = np.maximum(curr_counts.astype(float) / max(1, curr.size), epsilon)

        psi_values = (curr_pct - base_pct) * np.log(curr_pct / base_pct)
        psi = float(np.sum(psi_values))
        return psi if math.isfinite(psi) else 0.0

    def _clean_array(self, values: Iterable[float] | np.ndarray) -> np.ndarray:
        """Convert values to a finite float array."""
        try:
            array = np.asarray(list(values) if not isinstance(values, np.ndarray) else values, dtype=float)
        except (TypeError, ValueError):
            return np.array([], dtype=float)
        if array.size == 0:
            return array
        return array[np.isfinite(array)]
