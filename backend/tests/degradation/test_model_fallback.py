"""Degradation tests for model fallback mechanisms.

TC-DEG-001 ~ TC-DEG-005: Model unavailability and fallback behavior.
"""

from __future__ import annotations

import pytest

from app.core.contracts import normalize_risk_level
from app.ml.fusion_engine import FusionEngine

pytestmark = pytest.mark.degradation


class TestModelFallback:
    """Test model fallback behavior."""

    @pytest.mark.degradation
    def test_normalize_risk_level_with_none(self):
        """TC-DEG-001: normalize_risk_level handles None gracefully."""
        result = normalize_risk_level(None)
        assert result == "none"

    @pytest.mark.degradation
    def test_fusion_engine_empty_scores(self):
        """TC-DEG-002: FusionEngine handles empty scores."""
        engine = FusionEngine()
        result = engine.fuse({})
        assert result["risk_score"] == 0.0
        assert result["fusion_scheme"] == "empty"

    @pytest.mark.degradation
    def test_fusion_engine_single_modality(self):
        """TC-DEG-003: FusionEngine handles single modality."""
        engine = FusionEngine()
        result = engine.fuse({"structured": 80})
        assert result["fusion_scheme"] == "single_modality"
        assert result["risk_score"] > 0

    @pytest.mark.degradation
    def test_fusion_engine_missing_modality(self):
        """TC-DEG-004: FusionEngine redistributes weights when modality missing."""
        engine = FusionEngine()
        result = engine.fuse({"structured": 80, "text": 60})
        assert result["fusion_scheme"] == "dual_modality"
        assert result["risk_score"] > 0

    @pytest.mark.degradation
    def test_should_fallback_unavailable(self):
        """TC-DEG-005: should_fallback returns True when model unavailable."""
        from app.core.risk_thresholds import should_fallback
        assert should_fallback(0.9, False) is True
        assert should_fallback(None, False) is True
