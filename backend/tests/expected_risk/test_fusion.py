from __future__ import annotations

import pytest

from app.core.model_engine import ModelEngine
from tests.expected_risk.conftest import FUSION_TEST_CASES


class TestFusionExpectedRisk:
    """融合模型预期风险样本测试。"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_case", FUSION_TEST_CASES, ids=lambda x: x["name"])
    async def test_fusion_risk_levels(
        self, model_engine: ModelEngine, test_case: dict
    ) -> None:
        """验证融合模型风险等级在预期范围内。"""
        result = await model_engine.predict_fusion(
            features=test_case["features"],
            text=test_case.get("text"),
        )
        actual_level = result["risk_level"]
        expected_range = test_case["expected_level_range"]

        assert actual_level in expected_range, (
            f"测试 '{test_case['name']}' 失败: "
            f"实际风险等级 {actual_level} 不在预期范围 {expected_range} 内"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_case", FUSION_TEST_CASES, ids=lambda x: x["name"])
    async def test_fusion_crisis_override(
        self, model_engine: ModelEngine, test_case: dict
    ) -> None:
        """验证融合模型危机覆盖。"""
        result = await model_engine.predict_fusion(
            features=test_case["features"],
            text=test_case.get("text"),
        )
        expected_crisis = test_case.get("crisis_detected", False)
        actual_crisis = result.get("crisis_override", False)

        assert actual_crisis == expected_crisis, (
            f"测试 '{test_case['name']}' 失败: "
            f"危机覆盖预期 {expected_crisis}，实际 {actual_crisis}"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_case", FUSION_TEST_CASES, ids=lambda x: x["name"])
    async def test_fusion_review_required(
        self, model_engine: ModelEngine, test_case: dict
    ) -> None:
        """验证融合模型复核标记。"""
        result = await model_engine.predict_fusion(
            features=test_case["features"],
            text=test_case.get("text"),
        )
        expected_review = test_case.get("review_required", False)
        actual_review = result.get("review_required", False)

        assert actual_review == expected_review, (
            f"测试 '{test_case['name']}' 失败: "
            f"复核标记预期 {expected_review}，实际 {actual_review}"
        )
