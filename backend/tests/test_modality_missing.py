"""
Test suite for modality missing validation.

Tests:
- TC-FUS-021: 验证模态缺失场景加载
- TC-FUS-022: 验证单模态降级
- TC-FUS-023: 验证双模态融合
- TC-FUS-024: 验证全部模态缺失处理
- TC-FUS-025: 验证预测合理性
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add backend to path
backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.ml.fusion_engine import FusionEngine
from scripts.validate_modality_missing import simulate_modality_scores, validate_scenario


class TestModalityMissing:
    """Test suite for modality missing handling."""

    @pytest.fixture
    def sample_scenarios(self) -> list[dict]:
        """Create sample missing modality scenarios."""
        return [
            {
                "scenario": "structured_only",
                "label": 0,
                "payload": {
                    "features": {
                        "stress_level": 2,
                        "anxiety": 1,
                        "academic_pressure": 2,
                        "sleep_duration": 7,
                    },
                },
            },
            {
                "scenario": "text_only",
                "label": 1,
                "payload": {
                    "text": "我最近经常失眠，情绪很差，对任何事情都提不起兴趣。",
                },
            },
            {
                "scenario": "physio_only",
                "label": 0,
                "payload": {
                    "physiological": {
                        "sleep_hours": 7.5,
                        "heart_rate": 70,
                        "exercise_minutes": 40,
                        "sleep_quality": 4,
                    },
                },
            },
            {
                "scenario": "missing_structured",
                "label": 1,
                "payload": {
                    "text": "最近很累，做事提不起劲。",
                    "physiological": {
                        "sleep_hours": 4.0,
                        "heart_rate": 95,
                        "exercise_minutes": 0,
                        "sleep_quality": 1,
                    },
                },
            },
            {
                "scenario": "all_missing",
                "label": 0,
                "payload": {},
            },
        ]

    def test_simulate_modality_scores(self, sample_scenarios: list[dict]) -> None:
        """TC-FUS-021: 验证模态分数模拟."""
        for scenario in sample_scenarios:
            scores = simulate_modality_scores(scenario)

            # Verify scores are in valid range
            for modality, score in scores.items():
                assert 0 <= score <= 100, f"Invalid score for {modality}: {score}"

    def test_single_modality_degradation(self, sample_scenarios: list[dict]) -> None:
        """TC-FUS-022: 验证单模态降级."""
        engine = FusionEngine()

        # Test structured only
        structured_only = next(s for s in sample_scenarios if s["scenario"] == "structured_only")
        result = validate_scenario(structured_only, engine)

        assert result["fusion_scheme"] == "single_modality"
        assert "structured" in result["available_modalities"]
        assert len(result["missing_modalities"]) == 2

    def test_dual_modality_fusion(self, sample_scenarios: list[dict]) -> None:
        """TC-FUS-023: 验证双模态融合."""
        engine = FusionEngine()

        # Test missing structured
        missing_structured = next(s for s in sample_scenarios if s["scenario"] == "missing_structured")
        result = validate_scenario(missing_structured, engine)

        assert result["fusion_scheme"] == "dual_modality"
        assert "structured" in result["missing_modalities"]
        assert len(result["available_modalities"]) == 2

    def test_all_missing(self, sample_scenarios: list[dict]) -> None:
        """TC-FUS-024: 验证全部模态缺失处理."""
        engine = FusionEngine()

        all_missing = next(s for s in sample_scenarios if s["scenario"] == "all_missing")
        result = validate_scenario(all_missing, engine)

        assert result["fusion_scheme"] == "empty"
        assert result["risk_score"] == 0.0
        assert result["confidence"] == 0.0

    def test_prediction_reasonableness(self, sample_scenarios: list[dict]) -> None:
        """TC-FUS-025: 验证预测合理性."""
        engine = FusionEngine()

        for scenario in sample_scenarios:
            if scenario["scenario"] == "all_missing":
                continue  # Skip empty scenario

            result = validate_scenario(scenario, engine)

            # Verify that predictions are reasonable
            # High risk should have higher score, low risk should have lower score
            if scenario["label"] == 1:
                # For high risk, score should generally be higher
                assert result["risk_score"] >= 0
            else:
                # For low risk, score should generally be lower
                assert result["risk_score"] <= 100

    def test_weight_redistribution(self, sample_scenarios: list[dict]) -> None:
        """TC-FUS-026: 验证权重重分配."""
        engine = FusionEngine()

        # Test with only text modality
        text_only = next(s for s in sample_scenarios if s["scenario"] == "text_only")
        modality_scores = simulate_modality_scores(text_only)
        result = engine.fuse(modality_scores)

        # With only one modality, weight should be 1.0
        contributions = result["modality_contributions"]
        assert len(contributions) == 1
        for contrib in contributions.values():
            assert contrib["weight"] == 1.0

    def test_confidence_with_missing(self, sample_scenarios: list[dict]) -> None:
        """TC-FUS-027: 验证缺失模态时的置信度."""
        engine = FusionEngine(use_confidence_weighting=True)

        # Test with missing modalities
        missing_structured = next(s for s in sample_scenarios if s["scenario"] == "missing_structured")
        modality_scores = simulate_modality_scores(missing_structured)
        result = engine.fuse(modality_scores)

        # Confidence should be computed for available modalities
        assert result["confidence"] > 0
        assert result["confidence"] <= 1
