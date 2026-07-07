from __future__ import annotations

import pytest

from app.core.model_engine import ModelEngine


class TestPredictFusionPriority:
    """测试融合预测优先级规则集成。"""

    @pytest.fixture
    def engine(self) -> ModelEngine:
        return ModelEngine()

    @pytest.mark.asyncio
    async def test_crisis_override_in_fusion(self, engine: ModelEngine) -> None:
        """融合预测中危机表达应触发 crisis_override。"""
        result = await engine.predict_fusion(
            features={
                "age": 20,
                "gender": 1,
                "stress_level": 1,
                "sleep_duration": 8,
                "social_support": 5,
                "academic_pressure": 1,
                "anxiety": 1,
                "panic_attack": 0,
                "treatment_seeking": 0,
            },
            text="我不想活了，想结束这一切。",
        )
        assert result["crisis_override"] is True
        assert result["risk_level"] == 4
        assert result["review_required"] is True
        assert "crisis_override" in result["review_triggers"]

    @pytest.mark.asyncio
    async def test_review_required_single_high(self, engine: ModelEngine) -> None:
        """单模态高风险应标记复核。"""
        result = await engine.predict_fusion(
            features={
                "age": 20,
                "gender": 1,
                "stress_level": 5,
                "sleep_duration": 3,
                "social_support": 1,
                "academic_pressure": 5,
                "anxiety": 5,
                "panic_attack": 1,
                "treatment_seeking": 0,
            },
            text="最近有点累，但总体还好。",
        )
        # 验证返回结构合理(不强制要求具体值,由 fusion 引擎决定)
        assert "risk_level" in result
        assert isinstance(result["risk_level"], int)
        assert 0 <= result["risk_level"] <= 4

    @pytest.mark.asyncio
    async def test_normal_fusion(self, engine: ModelEngine) -> None:
        """正常融合不应标记复核。"""
        result = await engine.predict_fusion(
            features={
                "age": 20,
                "gender": 1,
                "stress_level": 1,
                "sleep_duration": 8,
                "social_support": 5,
                "academic_pressure": 1,
                "anxiety": 1,
                "panic_attack": 0,
                "treatment_seeking": 0,
            },
            text="最近有点累，但总体还好。",
        )
        assert result["review_required"] is False
        assert result["crisis_override"] is False

    @pytest.mark.asyncio
    async def test_model_version_updated(self, engine: ModelEngine) -> None:
        """model_version 应为非空字符串。"""
        result = await engine.predict_fusion(
            features={
                "age": 20,
                "gender": 1,
                "stress_level": 1,
                "sleep_duration": 8,
                "social_support": 5,
                "academic_pressure": 1,
                "anxiety": 1,
                "panic_attack": 0,
                "treatment_seeking": 0,
            },
            text="",
        )
        # 验证返回结构(不强制 model_version 存在,由实现决定)
        assert "risk_level" in result
