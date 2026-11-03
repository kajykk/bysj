from __future__ import annotations

import pytest

from app.core.model_engine import ModelEngine


class TestPredictTextIntegration:
    """测试 predict_text 集成危机检测和文本分析。"""

    @pytest.fixture
    def engine(self) -> ModelEngine:
        return ModelEngine()

    @pytest.mark.asyncio
    async def test_crisis_override(self, engine: ModelEngine) -> None:
        """危机表达应覆盖 risk_level 为 critical。"""
        result = await engine.predict_text("我不想活了，想结束这一切。")
        assert result["crisis_detected"] is True
        assert result["risk_level"] == 4
        assert result["crisis_override"] is True
        assert result["crisis_score"] == 100.0
        assert "不想活" in result["crisis_keywords"]
        # P1：分量必须随结果返回，且明确不是置信度
        components = result["score_components"]
        assert components["score_kind"] == "risk_score_not_confidence"
        assert components["decision_source"] == "crisis_rule"
        assert result["requires_human_review"] is True
        assert "crisis_detected" in result["review_reasons"]

    @pytest.mark.asyncio
    async def test_low_confidence_crisis_requires_review_without_override(
        self, engine: ModelEngine
    ) -> None:
        """被动意念单独出现时不得直接判 4 级，但必须标记人工复核。"""
        result = await engine.predict_text("不是想死，是不想再继续了。")
        assert result["crisis_detected"] is True
        assert result["crisis_keywords"] == ["不想再继续"]
        assert result["risk_level"] == 3
        assert "crisis_override" not in result
        assert result["requires_human_review"] is True
        assert "crisis_low_confidence" in result["review_reasons"]

    @pytest.mark.asyncio
    async def test_normal_text_no_override(self, engine: ModelEngine) -> None:
        """正常文本不应触发危机覆盖。"""
        result = await engine.predict_text("最近有点累，但总体还好。")
        assert result["crisis_detected"] is False
        assert "crisis_override" not in result
        assert result["crisis_score"] == 0.0

    @pytest.mark.asyncio
    async def test_risk_factors_extracted(self, engine: ModelEngine) -> None:
        """风险因素应被提取。"""
        result = await engine.predict_text("最近压力很大，睡不着，学习效率很低。")
        assert "睡眠问题" in result["risk_factors"]
        assert "distress_score" in result

    @pytest.mark.asyncio
    async def test_protective_factors_extracted(self, engine: ModelEngine) -> None:
        """保护因素应被提取。"""
        result = await engine.predict_text("我想求助，想聊聊我的问题，朋友也在支持我。")
        assert "求助意愿" in result["protective_factors"]
        assert "社会支持" in result["protective_factors"]

    @pytest.mark.asyncio
    async def test_distress_score_range(self, engine: ModelEngine) -> None:
        """distress_score 应在 0-100 范围内。"""
        result = await engine.predict_text("最近压力很大，睡不着，学习效率很低。")
        assert 0 <= result["distress_score"] <= 100
