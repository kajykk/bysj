"""
Test suite for enhanced fusion engine.

Tests:
- TC-FUS-009: 验证完整三模态融合
- TC-FUS-010: 验证双模态融合 (权重重分配)
- TC-FUS-011: 验证单模态降级
- TC-FUS-012: 验证置信度加权
- TC-FUS-013: 验证模态缺失处理
- TC-FUS-014: 验证空输入处理
- TC-FUS-015: 验证配置保存与加载
- TC-FUS-016: 验证风险等级转换
- TC-FUS-017: 验证权重归一化
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# Add backend to path
backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.ml.fusion_engine import DEFAULT_WEIGHTS, FusionEngine


class TestFusionEngine:
    """Test suite for fusion engine."""

    def test_full_three_modality_fusion(self) -> None:
        """TC-FUS-009: 验证完整三模态融合."""
        engine = FusionEngine()

        modality_scores = {
            "structured": 60.0,
            "text": 70.0,
            "physiological": 50.0,
        }

        result = engine.fuse(modality_scores)

        assert result["fusion_scheme"] == "full_three_modality"
        assert result["risk_score"] > 0
        assert result["risk_level"] >= 0
        assert "modality_contributions" in result
        assert len(result["modality_contributions"]) == 3

    def test_dual_modality_fusion(self) -> None:
        """TC-FUS-010: 验证双模态融合 (权重重分配)."""
        engine = FusionEngine()

        # Missing physiological modality
        modality_scores = {
            "structured": 60.0,
            "text": 70.0,
        }

        result = engine.fuse(modality_scores)

        assert result["fusion_scheme"] == "dual_modality"
        assert "physiological" in result["missing_modalities"]

        # Verify weights are redistributed
        contributions = result["modality_contributions"]
        total_weight = sum(c["weight"] for c in contributions.values())
        assert abs(total_weight - 1.0) < 0.01

    def test_single_modality_degradation(self) -> None:
        """TC-FUS-011: 验证单模态降级."""
        engine = FusionEngine()

        # Only structured modality available
        modality_scores = {
            "structured": 60.0,
        }

        result = engine.fuse(modality_scores)

        assert result["fusion_scheme"] == "single_modality"
        assert result["risk_score"] == 60.0  # Should equal the only score

    def test_confidence_weighting(self) -> None:
        """TC-FUS-012: 验证置信度加权."""
        engine = FusionEngine(use_confidence_weighting=True)

        # Score near 50 has lower confidence, near 0/100 has higher confidence
        modality_scores = {
            "structured": 50.0,  # Low confidence (near boundary)
            "text": 90.0,  # High confidence (extreme)
        }

        result = engine.fuse(modality_scores)

        contributions = result["modality_contributions"]
        text_confidence = contributions["text"]["confidence"]
        structured_confidence = contributions["structured"]["confidence"]

        # Text should have higher confidence due to extremity
        assert text_confidence > structured_confidence

    def test_modality_missing_handling(self) -> None:
        """TC-FUS-013: 验证模态缺失处理."""
        engine = FusionEngine(use_modality_missing_handling=True)

        modality_scores = {
            "structured": 60.0,
            "text": 70.0,
        }

        result = engine.fuse(modality_scores)

        # Verify missing modalities are tracked
        assert "physiological" in result["missing_modalities"]
        assert len(result["available_modalities"]) == 2

    def test_empty_input(self) -> None:
        """TC-FUS-014: 验证空输入处理."""
        engine = FusionEngine()

        result = engine.fuse({})

        assert result["fusion_scheme"] == "empty"
        assert result["risk_score"] == 0.0
        assert result["confidence"] == 0.0

    def test_config_save_load(self, tmp_path: Path) -> None:
        """TC-FUS-015: 验证配置保存与加载."""
        original_engine = FusionEngine(
            weights={"structured": 0.6, "text": 0.3, "physiological": 0.1},
            use_confidence_weighting=True,
            use_modality_missing_handling=True,
        )

        config_path = tmp_path / "fusion_config.json"
        original_engine.save_config(config_path)

        assert config_path.exists()

        loaded_engine = FusionEngine.load_config(config_path)

        assert loaded_engine.weights == original_engine.weights
        assert loaded_engine.use_confidence_weighting == original_engine.use_confidence_weighting
        assert loaded_engine.use_modality_missing_handling == original_engine.use_modality_missing_handling

    def test_risk_level_conversion(self) -> None:
        """TC-FUS-016: 验证风险等级转换 (v1.31: 适配 fusion 阈值 22/42/62/82)."""
        engine = FusionEngine()

        # fusion 阈值: mild=22, moderate=42, high=62, critical=82
        assert engine._score_to_level(0) == 0
        assert engine._score_to_level(10) == 0
        assert engine._score_to_level(20) == 0  # < 22 (mild)
        assert engine._score_to_level(22) == 1  # >= 22
        assert engine._score_to_level(40) == 1  # < 42
        assert engine._score_to_level(42) == 2  # >= 42
        assert engine._score_to_level(60) == 2  # < 62
        assert engine._score_to_level(62) == 3  # >= 62
        assert engine._score_to_level(80) == 3  # < 82
        assert engine._score_to_level(82) == 4  # >= 82
        assert engine._score_to_level(100) == 4

    def test_weight_normalization(self) -> None:
        """TC-FUS-017: 验证权重归一化."""
        # Weights that don't sum to 1.0 should be normalized
        engine = FusionEngine(weights={"structured": 1.0, "text": 1.0, "physiological": 1.0})

        total = sum(engine.weights.values())
        assert abs(total - 1.0) < 0.01

        # Each should be 1/3
        assert abs(engine.weights["structured"] - 0.333) < 0.01

    def test_confidence_computation(self) -> None:
        """TC-FUS-018: 验证置信度计算."""
        engine = FusionEngine(use_confidence_weighting=True)

        # Extreme scores should have higher confidence
        conf_high = engine.compute_confidence("structured", 90.0)
        conf_low = engine.compute_confidence("structured", 50.0)

        assert conf_high > conf_low
        assert 0 <= conf_high <= 1
        assert 0 <= conf_low <= 1

    def test_modality_specific_confidence(self) -> None:
        """TC-FUS-019: 验证模态特定置信度."""
        engine = FusionEngine(use_confidence_weighting=True)

        # Text with short length should have lower confidence
        conf_short_text = engine.compute_confidence(
            "text", 70.0, {"text_length": 5}
        )
        conf_long_text = engine.compute_confidence(
            "text", 70.0, {"text_length": 200}
        )

        assert conf_long_text > conf_short_text

    def test_no_confidence_weighting(self) -> None:
        """TC-FUS-020: 验证禁用置信度加权."""
        engine = FusionEngine(use_confidence_weighting=False)

        modality_scores = {
            "structured": 60.0,
            "text": 70.0,
        }

        result = engine.fuse(modality_scores)

        # All confidences should be 1.0
        for contrib in result["modality_contributions"].values():
            assert contrib["confidence"] == 1.0
