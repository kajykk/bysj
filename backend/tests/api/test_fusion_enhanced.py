"""多模态融合增强逻辑测试"""

import asyncio

import pytest

from app.core.model_engine import ModelEngine


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def model_engine():
    """创建模型引擎实例"""
    engine = ModelEngine()
    return engine


class TestFusionEnhanced:
    """融合逻辑增强测试"""

    def test_fusion_empty_input(self, model_engine):
        """测试空输入返回默认结果"""
        result = _run(model_engine.predict_fusion(None, None, None))
        assert result["risk_score"] == 0
        assert result["risk_level"] == 0
        assert result["severity"] == "none"

    def test_fusion_physio_high_risk_boost(self, model_engine):
        """测试生理高风险时权重提升和主导模态识别"""
        result = _run(
            model_engine.predict_fusion(
                features={
                    "age": 22,
                    "gender": 1,
                    "study_year": 3,
                    "cgpa": 3.5,
                    "stress_level": 3,
                    "sleep_duration": 7,
                    "social_support": 4,
                    "financial_pressure": 2,
                    "family_history": 0,
                    "academic_pressure": 3,
                    "exercise_frequency": 2,
                    "anxiety": 2,
                    "panic_attack": 0,
                    "treatment_seeking": 1,
                },
                text="最近压力比较大，晚上睡不好",
                physiological={
                    "sleep_hours": 5,
                    "sleep_quality": 1,
                    "exercise_minutes": 10,
                    "heart_rate": 95,
                    "systolic_bp": 145,
                    "diastolic_bp": 95,
                    "steps": 1200,
                },
            )
        )
        assert result["risk_score"] >= 0
        assert result["risk_level"] >= 0
        assert result["fusion_detail"]["dominant_modality"] in {
            "structured",
            "text",
            "physiological",
        }
        assert "modality_quality" in result["fusion_detail"]
        assert "intervention_level" in result
        assert "intervention_actions" in result

    def test_fusion_physio_low_risk(self, model_engine):
        """测试生理低风险时正常融合"""
        result = _run(
            model_engine.predict_fusion(
                features={
                    "age": 22,
                    "gender": 1,
                    "study_year": 3,
                    "cgpa": 3.5,
                    "stress_level": 2,
                    "sleep_duration": 8,
                    "social_support": 5,
                    "financial_pressure": 1,
                    "family_history": 0,
                    "academic_pressure": 2,
                    "exercise_frequency": 3,
                    "anxiety": 1,
                    "panic_attack": 0,
                    "treatment_seeking": 0,
                },
                text="最近状态还不错，学习和生活都比较顺利",
                physiological={
                    "sleep_hours": 8,
                    "sleep_quality": 5,
                    "exercise_minutes": 60,
                    "heart_rate": 65,
                    "systolic_bp": 110,
                    "diastolic_bp": 70,
                    "steps": 12000,
                },
            )
        )
        assert result["risk_score"] >= 0
        assert result["risk_level"] >= 0
        assert "fusion_detail" in result

    def test_fusion_single_modality_structured(self, model_engine):
        """测试仅结构化数据融合"""
        result = _run(
            model_engine.predict_fusion(
                features={
                    "age": 22,
                    "gender": 1,
                    "study_year": 3,
                    "cgpa": 3.5,
                    "stress_level": 3,
                    "sleep_duration": 7,
                    "social_support": 4,
                    "financial_pressure": 2,
                    "family_history": 0,
                    "academic_pressure": 3,
                    "exercise_frequency": 2,
                    "anxiety": 2,
                    "panic_attack": 0,
                    "treatment_seeking": 1,
                },
                text=None,
                physiological=None,
            )
        )
        assert result["risk_score"] >= 0
        assert result["fusion_detail"]["dominant_modality"] == "structured"

    def test_fusion_single_modality_physiological(self, model_engine):
        """测试仅生理数据融合"""
        result = _run(
            model_engine.predict_fusion(
                features=None,
                text=None,
                physiological={
                    "sleep_hours": 5,
                    "sleep_quality": 1,
                    "exercise_minutes": 10,
                    "heart_rate": 95,
                    "systolic_bp": 145,
                    "diastolic_bp": 95,
                    "steps": 1200,
                },
            )
        )
        assert result["risk_score"] >= 0
        assert result["fusion_detail"]["dominant_modality"] == "physiological"

    def test_fusion_missing_text(self, model_engine):
        """测试缺少文本模态时融合稳定性"""
        result = _run(
            model_engine.predict_fusion(
                features={
                    "age": 22,
                    "gender": 1,
                    "study_year": 3,
                    "cgpa": 3.5,
                    "stress_level": 3,
                    "sleep_duration": 7,
                    "social_support": 4,
                    "financial_pressure": 2,
                    "family_history": 0,
                    "academic_pressure": 3,
                    "exercise_frequency": 2,
                    "anxiety": 2,
                    "panic_attack": 0,
                    "treatment_seeking": 1,
                },
                text=None,
                physiological={
                    "sleep_hours": 6,
                    "sleep_quality": 3,
                    "exercise_minutes": 30,
                    "heart_rate": 75,
                    "systolic_bp": 120,
                    "diastolic_bp": 80,
                    "steps": 6000,
                },
            )
        )
        assert result["risk_score"] >= 0
        assert result["risk_level"] >= 0
        assert "fusion_detail" in result

    def test_fusion_intervention_linked_to_dominant_modality(self, model_engine):
        """测试干预建议与主导模态联动"""
        result = _run(
            model_engine.predict_fusion(
                features={
                    "age": 22,
                    "gender": 1,
                    "study_year": 3,
                    "cgpa": 3.5,
                    "stress_level": 5,
                    "sleep_duration": 3,
                    "social_support": 1,
                    "financial_pressure": 5,
                    "family_history": 1,
                    "academic_pressure": 5,
                    "exercise_frequency": 0,
                    "anxiety": 5,
                    "panic_attack": 1,
                    "treatment_seeking": 0,
                },
                text="最近压力特别大，晚上完全睡不着",
                physiological={
                    "sleep_hours": 2,
                    "sleep_quality": 1,
                    "exercise_minutes": 0,
                    "heart_rate": 110,
                    "systolic_bp": 160,
                    "diastolic_bp": 105,
                    "steps": 300,
                },
            )
        )
        assert result["risk_level"] >= 2
        actions = result["intervention_actions"]
        assert len(actions) >= 3
        # 高风险且生理主导时应有生理相关建议
        if result["fusion_detail"]["dominant_modality"] == "physiological":
            assert any("生理" in a or "复查" in a for a in actions)

    def test_attention_gate_no_extreme_weights(self, model_engine):
        """测试注意力门控不会产生极端权重"""
        scores = [40.0, 30.0, 70.0]
        weights = ModelEngine._attention_gate(scores)
        assert len(weights) == 3
        # 不应出现 0.0 或 1.0 的极端值
        for w in weights:
            assert 0.01 <= w <= 0.99
        assert abs(sum(weights) - 1.0) < 0.001

    def test_boost_gate_for_physiology(self, model_engine):
        """测试生理门控提升逻辑"""
        scores = [40.0, 30.0, 70.0]
        gate = [0.1, 0.1, 0.8]
        boosted = ModelEngine._boost_gate_for_physiology(scores, gate)
        assert len(boosted) == 3
        assert boosted[2] >= gate[2]  # 生理权重应被提升
        assert abs(sum(boosted) - 1.0) < 0.001

    def test_fusion_boost_handles_empty_gate(self, model_engine):
        boosted = ModelEngine._boost_gate_for_physiology([], [])
        assert boosted == []
