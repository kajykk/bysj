from __future__ import annotations

from pathlib import Path

import pytest

from app.core.model_engine import ModelEngine

PHYSIO_MODEL_PATH = (
    Path(__file__).resolve().parents[2]
    / "models" / "artifacts" / "physiological_optimized" / "model.json"
)
skip_no_physio = pytest.mark.skipif(
    not PHYSIO_MODEL_PATH.exists(),
    reason="生理模型 artifacts 不存在 (models/artifacts/physiological_optimized/)",
)
pytestmark = skip_no_physio


class TestPredictPhysiologicalConfidence:
    """测试生理预测置信度计算。"""

    @pytest.fixture
    def engine(self) -> ModelEngine:
        return ModelEngine()

    @pytest.mark.asyncio
    async def test_complete_data_confidence(self, engine: ModelEngine) -> None:
        """完整数据应返回高置信度。"""
        physiological = {
            "sleep_hours": 8,
            "sleep_quality": 7,
            "exercise_minutes": 30,
            "heart_rate": 75,
            "systolic_bp": 120,
            "diastolic_bp": 80,
            "steps": 8000,
        }
        result = await engine.predict_physiological(physiological)
        assert result["confidence"] == 0.8
        assert result["data_quality"] == "complete"
        assert result["calibrated"] is True

    @pytest.mark.asyncio
    async def test_partial_data_confidence(self, engine: ModelEngine) -> None:
        """缺失 1-2 个字段应返回中等置信度。"""
        physiological = {
            "sleep_hours": 8,
            "sleep_quality": 7,
            "exercise_minutes": 30,
            "heart_rate": 75,
            "steps": 8000,  # 缺失 systolic_bp, diastolic_bp
        }
        result = await engine.predict_physiological(physiological)
        assert result["confidence"] == 0.6
        assert result["data_quality"] == "partial"

    @pytest.mark.asyncio
    async def test_poor_data_confidence(self, engine: ModelEngine) -> None:
        """缺失 3+ 个字段应返回低置信度。"""
        physiological = {
            "sleep_hours": 8,
            "steps": 8000,  # 缺失 5 个字段
        }
        result = await engine.predict_physiological(physiological)
        assert result["confidence"] == 0.3
        assert result["data_quality"] == "poor"

    @pytest.mark.asyncio
    async def test_threshold_calibration(self, engine: ModelEngine) -> None:
        """验证 physiological 专用阈值。"""
        physiological = {
            "sleep_hours": 3,
            "sleep_quality": 2,
            "exercise_minutes": 0,
            "heart_rate": 110,
            "systolic_bp": 150,
            "diastolic_bp": 95,
            "steps": 1000,
        }
        result = await engine.predict_physiological(physiological)
        # 高风险应至少为 high (level 3)
        assert result["risk_level"] >= 3
