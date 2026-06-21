from __future__ import annotations

import pytest

from app.core.review_reasons import REVIEW_REASON_LABELS, ReviewReason


class TestReviewReasons:
    """复核原因枚举单元测试。"""

    def test_enum_values(self) -> None:
        """枚举值完整性。"""
        assert ReviewReason.CRISIS_OVERRIDE == "crisis_override"
        assert ReviewReason.TEXT_HIGH_RISK == "text_high_risk"
        assert ReviewReason.MODEL_DISAGREEMENT == "model_disagreement"
        assert ReviewReason.SINGLE_MODALITY_HIGH_RISK == "single_modality_high_risk"
        assert ReviewReason.LOW_CONFIDENCE_HIGH_RISK == "low_confidence_high_risk"

    def test_labels(self) -> None:
        """中文标签完整性。"""
        assert REVIEW_REASON_LABELS[ReviewReason.CRISIS_OVERRIDE] == "检测到危机表达"
        assert REVIEW_REASON_LABELS[ReviewReason.TEXT_HIGH_RISK] == "文本高风险"
        assert REVIEW_REASON_LABELS[ReviewReason.MODEL_DISAGREEMENT] == "模型分歧"
        assert REVIEW_REASON_LABELS[ReviewReason.SINGLE_MODALITY_HIGH_RISK] == "单模态高风险"
        assert REVIEW_REASON_LABELS[ReviewReason.LOW_CONFIDENCE_HIGH_RISK] == "低置信度高风险"

    def test_all_enum_have_labels(self) -> None:
        """所有枚举值都有对应标签。"""
        for reason in ReviewReason:
            assert reason in REVIEW_REASON_LABELS
