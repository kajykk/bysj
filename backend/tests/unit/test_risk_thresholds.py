from __future__ import annotations

from app.core.risk_thresholds import (
    MODALITY_RISK_THRESHOLDS,
    score_to_level,
)


class TestRiskThresholds:
    """风险阈值单元测试。"""

    def test_structured_thresholds(self) -> None:
        """structured 阈值按 v1.23 校准集分位点重选（20/70/93/97）。"""
        thresholds = MODALITY_RISK_THRESHOLDS["structured"]
        assert thresholds["mild"] == 20
        assert thresholds["moderate"] == 70
        assert thresholds["high"] == 93
        assert thresholds["critical"] == 97

    def test_physiological_thresholds(self) -> None:
        """physiological 阈值校准。"""
        thresholds = MODALITY_RISK_THRESHOLDS["physiological"]
        assert thresholds["mild"] == 35
        assert thresholds["moderate"] == 55
        assert thresholds["high"] == 75
        assert thresholds["critical"] == 90

    def test_fusion_thresholds(self) -> None:
        """fusion 阈值校准。"""
        thresholds = MODALITY_RISK_THRESHOLDS["fusion"]
        assert thresholds["mild"] == 22
        assert thresholds["moderate"] == 42
        assert thresholds["high"] == 62
        assert thresholds["critical"] == 82

    def test_score_to_level_structured(self) -> None:
        """structured 分数转等级。"""
        assert score_to_level(19, "structured") == 0
        assert score_to_level(20, "structured") == 1
        assert score_to_level(69, "structured") == 1
        assert score_to_level(70, "structured") == 2
        assert score_to_level(92, "structured") == 2
        assert score_to_level(93, "structured") == 3
        assert score_to_level(96, "structured") == 3
        assert score_to_level(97, "structured") == 4

    def test_score_to_level_physiological(self) -> None:
        """physiological 分数转等级。"""
        assert score_to_level(34, "physiological") == 0
        assert score_to_level(35, "physiological") == 1
        assert score_to_level(89, "physiological") == 3
        assert score_to_level(90, "physiological") == 4

    def test_score_to_level_default(self) -> None:
        """默认模态为 structured。"""
        assert score_to_level(25) == 1
