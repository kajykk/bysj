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
