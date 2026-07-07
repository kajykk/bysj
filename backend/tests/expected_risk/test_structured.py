from __future__ import annotations

import pytest

from app.core.model_engine import ModelEngine
from tests.expected_risk.conftest import STRUCTURED_TEST_CASES


class TestStructuredExpectedRisk:
    """结构化模型预期风险样本测试。"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "test_case", STRUCTURED_TEST_CASES, ids=lambda x: x["name"]
    )
    async def test_structured_risk_levels(
        self, model_engine: ModelEngine, test_case: dict
    ) -> None:
        """验证结构化模型风险等级在预期范围内。"""
        result = await model_engine.predict_structured(test_case["features"])
        actual_level = result["risk_level"]
        expected_range = test_case["expected_level_range"]

        assert actual_level in expected_range, (
            f"测试 '{test_case['name']}' 失败: "
            f"实际风险等级 {actual_level} 不在预期范围 {expected_range} 内"
        )
