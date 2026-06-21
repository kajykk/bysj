from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.model_predict import PhysiologicalPredictRequest


class TestPhysiologicalValidation:
    """生理数据输入校验测试。"""

    def test_valid_data(self) -> None:
        """有效数据应通过校验。"""
        req = PhysiologicalPredictRequest(physiological={
            "sleep_hours": 8, "sleep_quality": 7, "exercise_minutes": 30,
            "heart_rate": 75, "systolic_bp": 120, "diastolic_bp": 80, "steps": 8000,
        })
        assert req.physiological["sleep_hours"] == 8

    def test_boundary_values(self) -> None:
        """边界值应通过校验。"""
        req = PhysiologicalPredictRequest(physiological={
            "sleep_hours": 0, "sleep_quality": 1, "exercise_minutes": 0,
            "heart_rate": 35, "systolic_bp": 70, "diastolic_bp": 40, "steps": 0,
        })
        assert req.physiological["sleep_hours"] == 0

        req = PhysiologicalPredictRequest(physiological={
            "sleep_hours": 16, "sleep_quality": 10, "exercise_minutes": 300,
            "heart_rate": 220, "systolic_bp": 220, "diastolic_bp": 140, "steps": 50000,
        })
        assert req.physiological["sleep_hours"] == 16

    def test_sleep_hours_negative(self) -> None:
        """睡眠时间为负应返回 422。"""
        with pytest.raises(ValidationError) as exc_info:
            PhysiologicalPredictRequest(physiological={"sleep_hours": -1})
        assert "超出有效范围" in str(exc_info.value)

    def test_sleep_hours_too_high(self) -> None:
        """睡眠时间过高应返回 422。"""
        with pytest.raises(ValidationError) as exc_info:
            PhysiologicalPredictRequest(physiological={"sleep_hours": 17})
        assert "超出有效范围" in str(exc_info.value)

    def test_heart_rate_too_high(self) -> None:
        """心率过高应返回 422。"""
        with pytest.raises(ValidationError) as exc_info:
            PhysiologicalPredictRequest(physiological={"heart_rate": 300})
        assert "超出有效范围" in str(exc_info.value)

    def test_steps_too_high(self) -> None:
        """步数过高应返回 422。"""
        with pytest.raises(ValidationError) as exc_info:
            PhysiologicalPredictRequest(physiological={"steps": 999999})
        assert "超出有效范围" in str(exc_info.value)

    def test_multiple_errors(self) -> None:
        """多个字段错误应全部返回。"""
        with pytest.raises(ValidationError) as exc_info:
            PhysiologicalPredictRequest(physiological={
                "sleep_hours": -1, "heart_rate": 300, "steps": 999999,
            })
        error_msg = str(exc_info.value)
        assert "sleep_hours" in error_msg
        assert "heart_rate" in error_msg
        assert "steps" in error_msg
