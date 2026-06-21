from __future__ import annotations

from enum import Enum


class ReviewReason(str, Enum):
    """人工复核原因枚举。"""

    CRISIS_OVERRIDE = "crisis_override"
    TEXT_HIGH_RISK = "text_high_risk"
    MODEL_DISAGREEMENT = "model_disagreement"
    SINGLE_MODALITY_HIGH_RISK = "single_modality_high_risk"
    LOW_CONFIDENCE_HIGH_RISK = "low_confidence_high_risk"


REVIEW_REASON_LABELS: dict[str, str] = {
    ReviewReason.CRISIS_OVERRIDE: "检测到危机表达",
    ReviewReason.TEXT_HIGH_RISK: "文本高风险",
    ReviewReason.MODEL_DISAGREEMENT: "模型分歧",
    ReviewReason.SINGLE_MODALITY_HIGH_RISK: "单模态高风险",
    ReviewReason.LOW_CONFIDENCE_HIGH_RISK: "低置信度高风险",
}
