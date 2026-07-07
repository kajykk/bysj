from __future__ import annotations

from typing import Any


class FusionPriorityEngine:
    """融合模型优先级规则引擎。

    规则优先级（从高到低）：
    1. 文本危机表达 -> 直接 critical
    2. 多模型一致高风险 -> 提升等级
    3. 模型分歧 -> 标记复核
    4. 低置信度 -> 降低权重
    """

    def apply_priority_rules(
        self,
        structured_result: dict[str, Any] | None,
        text_result: dict[str, Any] | None,
        physio_result: dict[str, Any] | None,
        base_fused_score: float,
        base_risk_level: int,
    ) -> dict[str, Any]:
        """应用优先级规则，返回调整后的结果和复核标记。"""

        review_required = False
        review_triggers: list[str] = []
        crisis_override = False

        # 规则 1: 文本危机表达优先级最高
        if text_result and text_result.get("crisis_detected"):
            base_risk_level = 4  # critical
            base_fused_score = max(base_fused_score, 90.0)
            crisis_override = True
            review_required = True
            review_triggers.append("crisis_override")

        # 规则 2: 多模型一致高风险时提升等级
        high_risk_count = 0
        for result in [structured_result, text_result, physio_result]:
            # L-24 修复：显式 None 检查，避免 0/0.0 等 falsy 值被误判
            _risk_level = result.get("risk_level") if result else None
            if _risk_level is not None and _risk_level >= 3:
                high_risk_count += 1
        if high_risk_count >= 2 and base_risk_level < 3:
            base_risk_level = 3  # high
            base_fused_score = max(base_fused_score, 65.0)

        # 规则 3: 单个模型 high，其他 low -> 标记复核
        if high_risk_count == 1:
            review_required = True
            review_triggers.append("single_modality_high_risk")

        # 规则 4: 模型分歧 (>40 分)
        scores = []
        for result in [structured_result, text_result, physio_result]:
            if result:
                # L-24 修复：显式 None 检查，避免 0.0 风险分数被替换为 0
                _score = result.get("risk_score")
                scores.append(_score if _score is not None else 0.0)
        if scores:
            score_range = max(scores) - min(scores)
            if score_range > 40:
                review_required = True
                review_triggers.append(f"model_disagreement_{int(score_range)}_points")

        # 规则 5: 低置信度 + 高风险
        for modality, result in [
            ("structured", structured_result),
            ("text", text_result),
            ("physiological", physio_result),
        ]:
            if result:
                confidence = result.get("confidence", 1.0)
                risk_level = result.get("risk_level", 0)
                if confidence < 0.5 and risk_level >= 3:
                    review_required = True
                    review_triggers.append(f"low_confidence_high_risk_{modality}")

        return {
            "risk_score": round(base_fused_score, 2),
            "risk_level": base_risk_level,
            "review_required": review_required,
            "review_triggers": review_triggers,
            "crisis_override": crisis_override,
        }
