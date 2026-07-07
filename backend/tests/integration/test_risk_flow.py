"""Integration tests for risk assessment flow.

TC-INT-001 ~ TC-INT-003: End-to-end risk assessment flow.
"""

from __future__ import annotations

import pytest


class TestRiskFlow:
    """Test risk assessment integration flow."""

    @pytest.mark.integration
    def test_risk_level_normalization(self):
        """TC-INT-001: Risk level normalization across components."""
        from app.core.contracts import normalize_risk_level

        assert normalize_risk_level(0) == "none"
        assert normalize_risk_level(1) == "low"
        assert normalize_risk_level(2) == "medium"
        assert normalize_risk_level(3) == "high"
        assert normalize_risk_level(4) == "critical"

    @pytest.mark.integration
    def test_intervention_recommendation_flow(self):
        """TC-INT-002: Intervention recommendation based on risk level."""
        from app.services.intervention_service import InterventionRecommendation

        level, actions = InterventionRecommendation.build_from_risk_level(3)
        assert level == "high"
        assert len(actions) > 0

    @pytest.mark.integration
    def test_fusion_to_intervention_flow(self):
        """TC-INT-003: Fusion result to intervention flow."""
        from app.ml.fusion_engine import FusionEngine
        from app.services.intervention_service import InterventionRecommendation

        engine = FusionEngine()
        result = engine.fuse({"structured": 85, "text": 70})
        risk_score = result["risk_score"]

        # Map score to level (0-100 -> 0-4)
        level = min(4, int(risk_score / 20))
        intervention_level, actions = InterventionRecommendation.build_from_risk_level(
            level
        )

        assert intervention_level in ["none", "low", "medium", "high", "critical"]
        assert len(actions) > 0
