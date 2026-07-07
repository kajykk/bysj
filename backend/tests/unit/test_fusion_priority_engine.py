from __future__ import annotations

import pytest

from app.ml.fusion_priority_engine import FusionPriorityEngine


class TestFusionPriorityEngine:
    """融合优先级引擎单元测试。"""

    @pytest.fixture
    def engine(self) -> FusionPriorityEngine:
        return FusionPriorityEngine()

    def test_crisis_override(self, engine: FusionPriorityEngine) -> None:
        """文本危机表达应直接 critical。"""
        text_result = {"crisis_detected": True, "risk_score": 50, "risk_level": 2}
        result = engine.apply_priority_rules(None, text_result, None, 50.0, 2)
        assert result["risk_level"] == 4
        assert result["crisis_override"] is True
        assert result["review_required"] is True
        assert "crisis_override" in result["review_triggers"]

    def test_multi_model_high_risk(self, engine: FusionPriorityEngine) -> None:
        """两个模型 high 应提升等级。"""
        structured = {"risk_score": 70, "risk_level": 3}
        text = {"risk_score": 75, "risk_level": 3}
        result = engine.apply_priority_rules(structured, text, None, 50.0, 2)
        assert result["risk_level"] == 3
        assert result["risk_score"] >= 65.0

    def test_single_modality_high_risk(self, engine: FusionPriorityEngine) -> None:
        """单个模型 high 应标记复核。"""
        structured = {"risk_score": 70, "risk_level": 3}
        text = {"risk_score": 30, "risk_level": 1}
        result = engine.apply_priority_rules(structured, text, None, 50.0, 2)
        assert result["review_required"] is True
        assert "single_modality_high_risk" in result["review_triggers"]

    def test_model_disagreement(self, engine: FusionPriorityEngine) -> None:
        """模型分歧 >40 分应标记复核。"""
        structured = {"risk_score": 80, "risk_level": 3}
        text = {"risk_score": 30, "risk_level": 1}
        result = engine.apply_priority_rules(structured, text, None, 55.0, 2)
        assert result["review_required"] is True
        assert any("model_disagreement" in t for t in result["review_triggers"])

    def test_low_confidence_high_risk(self, engine: FusionPriorityEngine) -> None:
        """低置信度 + 高风险应标记复核。"""
        structured = {"risk_score": 70, "risk_level": 3, "confidence": 0.4}
        result = engine.apply_priority_rules(structured, None, None, 50.0, 2)
        assert result["review_required"] is True
        assert any("low_confidence" in t for t in result["review_triggers"])

    def test_no_rules_triggered(self, engine: FusionPriorityEngine) -> None:
        """无规则触发时应保持原值。"""
        structured = {"risk_score": 30, "risk_level": 1}
        text = {"risk_score": 25, "risk_level": 1}
        result = engine.apply_priority_rules(structured, text, None, 27.5, 1)
        assert result["risk_level"] == 1
        assert result["review_required"] is False
        assert result["review_triggers"] == []
