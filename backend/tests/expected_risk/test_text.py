from __future__ import annotations

import pytest

from app.core.model_engine import ModelEngine
from tests.expected_risk.conftest import TEXT_TEST_CASES


class TestTextExpectedRisk:
    """文本模型预期风险样本测试。"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_case", TEXT_TEST_CASES, ids=lambda x: x["name"])
    async def test_text_risk_levels(self, model_engine: ModelEngine, test_case: dict) -> None:
        """验证文本模型风险等级在预期范围内。"""
        result = await model_engine.predict_text(test_case["text"])
        actual_level = result.get("risk_level", 0)
        expected_range = test_case["expected_level_range"]

        assert actual_level in expected_range, (
            f"测试 '{test_case['name']}' 失败: "
            f"实际风险等级 {actual_level} 不在预期范围 {expected_range} 内"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_case", TEXT_TEST_CASES, ids=lambda x: x["name"])
    async def test_text_crisis_detection(self, model_engine: ModelEngine, test_case: dict) -> None:
        """验证危机检测结果。"""
        result = await model_engine.predict_text(test_case["text"])
        actual_crisis = result.get("crisis_detected", False)
        expected_crisis = test_case.get("crisis_detected", False)

        assert actual_crisis == expected_crisis, (
            f"测试 '{test_case['name']}' 失败: "
            f"危机检测预期 {expected_crisis}，实际 {actual_crisis}"
        )
