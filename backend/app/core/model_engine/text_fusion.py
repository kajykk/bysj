"""文本通道融合的纯函数口径。

融合分是 **风险分**（0–1，越大越需要关注），不是「置信度」，
也不是校准后的患病概率。分量与权重随结果一起返回，供界面如实展示。

危机信号不参与加权平均：
* 高置信危机（明确自杀/自伤等）直接把 ``risk_level`` 置为 4；
* 弱危机信号（单条被动意念等）只升到 3 并强制人工复核，
  避免一个字面关键词把分数与等级同时推到 critical。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

MODEL_WEIGHT_BASE = 0.4
MODEL_WEIGHT_EXTREMITY_GAIN = 0.4
HEURISTIC_WEIGHT_BASE = 0.6
DISAGREEMENT_THRESHOLD = 0.5
DISAGREEMENT_MODEL_MIN_WEIGHT = 0.65
DISAGREEMENT_HEURISTIC_MAX_WEIGHT = 0.35
NEGATIVE_LABEL_THRESHOLD = 0.2
HIGH_FUSED_SCORE_REVIEW_THRESHOLD = 0.65


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def fuse_text_signals(
    *,
    ml_probability: float,
    heuristic_score: float,
    crisis_score: float,
    crisis_detected: bool,
    requires_corroboration: bool,
    matched_categories: Sequence[str] = (),
    critical_intent: bool | None = None,
) -> dict[str, Any]:
    """融合 ML 概率与启发式风险分，返回可解释的分量与复核建议。

    Args:
        ml_probability: 双语 TF-IDF + LR 的原始概率（0–1）。
        heuristic_score: 症状本体聚合分（0–1）。
        crisis_score: 危机规则强度（0–100）。
        crisis_detected: 是否存在有效危机命中。
        requires_corroboration: 危机命中是否为需要第二类信号佐证的弱信号。
        matched_categories: 命中的危机信号类别。
        critical_intent: D1 口径下是否带时间/计划/手段/明确意图。为 ``None``
            时退化为旧行为（``not requires_corroboration``），保证既有调用方
            语义不变。
    """
    model_score = _clamp01(ml_probability)
    heuristic_score = _clamp01(heuristic_score)

    model_extremity = abs(model_score - 0.5) * 2
    model_weight = MODEL_WEIGHT_BASE + model_extremity * MODEL_WEIGHT_EXTREMITY_GAIN
    heuristic_weight = HEURISTIC_WEIGHT_BASE - model_extremity * MODEL_WEIGHT_EXTREMITY_GAIN

    disagreement = abs(model_score - heuristic_score)
    if disagreement > DISAGREEMENT_THRESHOLD:
        model_weight = max(model_weight, DISAGREEMENT_MODEL_MIN_WEIGHT)
        heuristic_weight = min(heuristic_weight, DISAGREEMENT_HEURISTIC_MAX_WEIGHT)

    total_weight = model_weight + heuristic_weight
    model_weight = round(model_weight / total_weight, 4)
    heuristic_weight = round(heuristic_weight / total_weight, 4)

    model_contribution = model_score * model_weight
    heuristic_contribution = heuristic_score * heuristic_weight
    final_score = round(model_contribution + heuristic_contribution, 4)

    review_reasons: list[str] = []
    crisis_override = False
    risk_level: int | None = None

    if crisis_detected:
        review_reasons.append("crisis_detected")
        has_critical_intent = (
            not requires_corroboration
            if critical_intent is None
            else bool(critical_intent)
        )
        if has_critical_intent:
            risk_level = 4
            crisis_override = True
        else:
            # D1：无时间/计划/手段/明确意图的危机表达封顶 3 级，且强制人工复核。
            risk_level = 3
            review_reasons.append("crisis_low_confidence")
    elif final_score >= HIGH_FUSED_SCORE_REVIEW_THRESHOLD:
        review_reasons.append("high_fused_score")

    components = {
        "score_kind": "risk_score_not_confidence",
        "ml_probability": round(model_score, 4),
        "heuristic_score": round(heuristic_score, 4),
        "crisis_score": round(float(crisis_score), 2),
        "model_weight": model_weight,
        "heuristic_weight": heuristic_weight,
        "model_contribution": round(model_contribution, 4),
        "heuristic_contribution": round(heuristic_contribution, 4),
        "disagreement": round(disagreement, 4),
        "matched_categories": list(matched_categories),
        "crisis_override": crisis_override,
        "critical_intent": bool(
            crisis_detected
            and (
                not requires_corroboration
                if critical_intent is None
                else critical_intent
            )
        ),
        "decision_source": "crisis_rule" if crisis_detected else "fusion",
    }

    return {
        "sentiment_score": final_score,
        "sentiment_label": (
            "negative" if final_score >= NEGATIVE_LABEL_THRESHOLD else "positive"
        ),
        "distress_score": round(final_score * 100, 2),
        "risk_level": risk_level,
        "crisis_override": crisis_override,
        "requires_human_review": bool(review_reasons),
        "review_reasons": review_reasons,
        "score_components": components,
    }
