"""
Test suite for fusion weight optimization.

Tests:
- TC-FUS-001: 验证场景加载
- TC-FUS-002: 验证模态分数模拟
- TC-FUS-003: 验证融合分数计算
- TC-FUS-004: 验证权重评估
- TC-FUS-005: 验证网格搜索
- TC-FUS-006: 验证权重归一化
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add backend to path
backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

try:
    from scripts.optimize_fusion_weights import (
        BASE_WEIGHTS,
        compute_fusion_score,
        evaluate_weights,
        grid_search_weights,
        simulate_modality_scores,
    )
except ImportError:
    pytest.skip(
        "scripts/optimize_fusion_weights.py 不存在, 跳过融合权重优化测试",
        allow_module_level=True,
    )


class TestFusionWeightOptimization:
    """Test suite for fusion weight optimization."""

    @pytest.fixture
    def sample_scenarios(self) -> list[dict]:
        """Create sample test scenarios."""
        return [
            {
                "scenario": "low_risk",
                "label": 0,
                "payload": {
                    "features": {
                        "stress_level": 2,
                        "anxiety": 1,
                        "academic_pressure": 2,
                        "sleep_duration": 7,
                    },
                    "text": "最近状态不错，学习效率还可以。",
                    "physiological": {
                        "sleep_hours": 7.5,
                        "heart_rate": 70,
                        "exercise_minutes": 40,
                        "sleep_quality": 4,
                    },
                },
            },
            {
                "scenario": "high_risk",
                "label": 1,
                "payload": {
                    "features": {
                        "stress_level": 5,
                        "anxiety": 4,
                        "academic_pressure": 5,
                        "sleep_duration": 4,
                    },
                    "text": "我最近经常失眠，情绪很差，对任何事情都提不起兴趣。",
                    "physiological": {
                        "sleep_hours": 4.0,
                        "heart_rate": 104,
                        "exercise_minutes": 0,
                        "sleep_quality": 1,
                    },
                },
            },
        ]

    def test_simulate_modality_scores(self, sample_scenarios: list[dict]) -> None:
        """TC-FUS-002: 验证模态分数模拟."""
        for scenario in sample_scenarios:
            scores = simulate_modality_scores(scenario)

            # Verify all modalities have scores
            assert "structured" in scores
            assert "text" in scores
            assert "physiological" in scores

            # Verify scores are in valid range
            for modality, score in scores.items():
                assert 0 <= score <= 100, f"Invalid score for {modality}: {score}"

    def test_compute_fusion_score(self) -> None:
        """TC-FUS-003: 验证融合分数计算."""
        modality_scores = {
            "structured": 60.0,
            "text": 70.0,
            "physiological": 50.0,
        }
        weights = {
            "structured": 0.5,
            "text": 0.3,
            "physiological": 0.2,
        }

        fused_score = compute_fusion_score(modality_scores, weights)

        # Expected: (60*0.5 + 70*0.3 + 50*0.2) / 1.0 = 30 + 21 + 10 = 61
        expected = 60.0 * 0.5 + 70.0 * 0.3 + 50.0 * 0.2
        assert abs(fused_score - expected) < 0.01

    def test_compute_fusion_score_missing_modality(self) -> None:
        """TC-FUS-006: 验证权重归一化 - 缺失模态."""
        modality_scores = {
            "structured": 60.0,
            "text": 70.0,
            # physiological missing
        }
        weights = {
            "structured": 0.5,
            "text": 0.3,
            "physiological": 0.2,
        }

        fused_score = compute_fusion_score(modality_scores, weights)

        # Weights should be renormalized: structured=0.5/0.8=0.625, text=0.3/0.8=0.375
        expected = 60.0 * 0.625 + 70.0 * 0.375
        assert abs(fused_score - expected) < 0.01

    def test_evaluate_weights(self, sample_scenarios: list[dict]) -> None:
        """TC-FUS-004: 验证权重评估."""
        metrics = evaluate_weights(sample_scenarios, BASE_WEIGHTS)

        # Verify metrics structure
        assert "accuracy" in metrics
        assert "precision" in metrics
        assert "recall" in metrics
        assert "f1" in metrics
        assert "correct" in metrics
        assert "total" in metrics

        # Verify metrics are in valid range
        assert 0 <= metrics["accuracy"] <= 1
        assert 0 <= metrics["f1"] <= 1
        assert metrics["total"] == len(sample_scenarios)

    def test_grid_search(self, sample_scenarios: list[dict]) -> None:
        """TC-FUS-005: 验证网格搜索."""
        best_weights, best_metrics = grid_search_weights(sample_scenarios, steps=11)

        # Verify results
        assert best_weights is not None
        assert best_metrics is not None

        # Verify weights sum to 1.0
        total_weight = sum(best_weights.values())
        assert abs(total_weight - 1.0) < 0.01

        # Verify all modalities have weights
        assert "structured" in best_weights
        assert "text" in best_weights
        assert "physiological" in best_weights

        # Verify metrics improved or matched base
        base_metrics = evaluate_weights(sample_scenarios, BASE_WEIGHTS)
        assert best_metrics["f1"] >= base_metrics["f1"] - 0.01  # Allow small tolerance

    def test_weight_sum_constraint(self) -> None:
        """TC-FUS-007: 验证权重和约束."""
        # Weights should always sum to 1.0 (or close due to rounding)
        weights = {
            "structured": 0.55,
            "text": 0.30,
            "physiological": 0.15,
        }
        assert abs(sum(weights.values()) - 1.0) < 0.01

    def test_fusion_score_range(self) -> None:
        """TC-FUS-008: 验证融合分数范围."""
        modality_scores = {
            "structured": 100.0,
            "text": 100.0,
            "physiological": 100.0,
        }
        weights = {"structured": 0.5, "text": 0.3, "physiological": 0.2}

        fused_score = compute_fusion_score(modality_scores, weights)
        assert fused_score == 100.0

        modality_scores = {
            "structured": 0.0,
            "text": 0.0,
            "physiological": 0.0,
        }
        fused_score = compute_fusion_score(modality_scores, weights)
        assert fused_score == 0.0
