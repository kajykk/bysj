"""ISS-02 覆盖率提升：app/core/risk_thresholds.py 聚焦测试.

纯逻辑模块（风险分数→等级、模态阈值、融合阈值、回退决策），无外部依赖，可全量覆盖。
"""

from __future__ import annotations

import pytest

from app.core import risk_thresholds as rt


class TestGetThresholdByModality:
    def test_known_modalities(self):
        for mod in ("structured", "text", "physiological", "fusion"):
            t = rt.get_threshold_by_modality(mod)
            assert set(t) == {"mild", "moderate", "high", "critical"}
            assert t["mild"] < t["critical"]

    def test_unknown_modality_falls_back(self):
        # 未知模态回退到全局 RISK_LEVEL_THRESHOLDS
        assert rt.get_threshold_by_modality("does_not_exist") is rt.RISK_LEVEL_THRESHOLDS


class TestScoreToLevel:
    @pytest.mark.parametrize(
        "score,modality,expected",
        [
            (0, "structured", 0),
            (24, "structured", 0),
            (25, "structured", 1),  # mild 边界
            (45, "structured", 2),  # moderate 边界
            (65, "structured", 3),  # high 边界
            (85, "structured", 4),  # critical 边界
            (100, "structured", 4),
            (19, "text", 0),
            (20, "text", 1),
            (34, "text", 1),  # 低于 moderate=40
            (90, "physiological", 4),
            (80, "physiological", 3),  # physiological high=75, critical=90
        ],
    )
    def test_levels(self, score, modality, expected):
        assert rt.score_to_level(score, modality) == expected

    def test_default_modality_is_structured(self):
        # 默认参数应与显式 structured 一致
        for s in (0, 25, 45, 65, 85, 100):
            assert rt.score_to_level(s) == rt.score_to_level(s, "structured")


class TestGetFusionThreshold:
    def test_returns_score_threshold(self):
        assert rt.get_fusion_threshold(82) == 82
        assert rt.get_fusion_threshold(70) == 62  # high
        assert rt.get_fusion_threshold(42) == 42  # moderate

    def test_low_confidence_logs_but_returns_threshold(self):
        # 低置信度仅记录日志，不影响阈值返回
        assert rt.get_fusion_threshold(82, confidence=0.1) == 82

    def test_zero_score_returns_zero_not_mild(self):
        assert rt.get_fusion_threshold(0) == 0


class TestShouldFallback:
    def test_unavailable_always_fallback(self):
        assert rt.should_fallback(0.9, False) is True
        assert rt.should_fallback(None, False) is True

    def test_none_confidence_no_fallback_when_available(self):
        assert rt.should_fallback(None, True) is False

    def test_low_confidence_fallback(self):
        assert rt.should_fallback(0.3, True) is True

    def test_high_confidence_no_fallback(self):
        assert rt.should_fallback(0.99, True) is False


def test_constants_present():
    assert rt.RISK_LEVEL_LABELS[0] == "none"
    assert rt.RISK_LEVEL_LABELS[4] == "critical"
