from __future__ import annotations

import pytest

from app.core.model_engine.text_fusion import fuse_text_signals


def _fuse(**overrides):
    params = {
        "ml_probability": 0.5,
        "heuristic_score": 0.5,
        "crisis_score": 0.0,
        "crisis_detected": False,
        "requires_corroboration": False,
        "matched_categories": [],
    }
    params.update(overrides)
    return fuse_text_signals(**params)


class TestTextFusion:
    def test_balanced_scores_use_base_weights(self) -> None:
        result = _fuse(ml_probability=0.5, heuristic_score=0.5)
        components = result["score_components"]
        assert components["model_weight"] == 0.4
        assert components["heuristic_weight"] == 0.6
        assert result["sentiment_score"] == 0.5
        assert result["sentiment_label"] == "negative"
        assert result["requires_human_review"] is False
        assert result["risk_level"] is None
        assert components["decision_source"] == "fusion"

    def test_extreme_model_score_gets_more_weight(self) -> None:
        result = _fuse(ml_probability=0.9, heuristic_score=0.2)
        components = result["score_components"]
        assert components["model_weight"] == 0.72
        assert components["heuristic_weight"] == 0.28
        assert result["sentiment_score"] == 0.704

    def test_large_disagreement_caps_heuristic_weight(self) -> None:
        result = _fuse(ml_probability=0.3, heuristic_score=0.9)
        components = result["score_components"]
        assert components["disagreement"] == 0.6
        assert components["model_weight"] == 0.65
        assert components["heuristic_weight"] == 0.35

    def test_contributions_sum_to_score(self) -> None:
        result = _fuse(ml_probability=0.73, heuristic_score=0.41)
        components = result["score_components"]
        contributions = (
            components["model_contribution"] + components["heuristic_contribution"]
        )
        assert contributions == pytest.approx(result["sentiment_score"], abs=1e-3)
        assert components["model_weight"] + components["heuristic_weight"] == 1.0

    def test_scores_are_clamped(self) -> None:
        result = _fuse(ml_probability=1.4, heuristic_score=-0.3)
        components = result["score_components"]
        assert components["ml_probability"] == 1.0
        assert components["heuristic_score"] == 0.0

    def test_high_confidence_crisis_overrides_to_critical(self) -> None:
        result = _fuse(
            crisis_score=100.0,
            crisis_detected=True,
            matched_categories=["suicide"],
        )
        assert result["risk_level"] == 4
        assert result["crisis_override"] is True
        assert result["requires_human_review"] is True
        assert result["review_reasons"] == ["crisis_detected"]
        assert result["score_components"]["decision_source"] == "crisis_rule"
        assert result["score_components"]["matched_categories"] == ["suicide"]

    def test_low_confidence_crisis_only_raises_to_high(self) -> None:
        result = _fuse(
            crisis_score=85.0,
            crisis_detected=True,
            requires_corroboration=True,
            matched_categories=["passive_ideation"],
        )
        assert result["risk_level"] == 3
        assert result["crisis_override"] is False
        assert result["requires_human_review"] is True
        assert result["review_reasons"] == [
            "crisis_detected",
            "crisis_low_confidence",
        ]

    def test_high_fused_score_requests_review_without_crisis(self) -> None:
        result = _fuse(ml_probability=0.95, heuristic_score=0.9)
        assert result["risk_level"] is None
        assert result["crisis_override"] is False
        assert result["requires_human_review"] is True
        assert result["review_reasons"] == ["high_fused_score"]

    def test_low_fused_score_needs_no_review(self) -> None:
        result = _fuse(ml_probability=0.1, heuristic_score=0.1)
        assert result["requires_human_review"] is False
        assert result["review_reasons"] == []

    def test_score_kind_is_not_confidence(self) -> None:
        result = _fuse()
        assert result["score_components"]["score_kind"] == "risk_score_not_confidence"
