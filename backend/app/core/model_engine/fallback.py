"""启发式回退策略层 (FB 层).

本模块从 `app.core.model_engine` 拆分而来 (T-P2-001 PHASE_2 结构性优化,
model_engine 包结构化拆分时整体迁入 `app.core.model_engine.fallback`),
承担 ModelEngine 在 ML 模型不可用 / 输入信息不足场景下的启发式回退预测职责:

- 结构化特征启发式回退 (`_structured_heuristic_fallback`)
- 文本情感启发式回退 (`_text_heuristic_fallback`)
- 仅 GAD-7 焦虑评分回退 (`_anxiety_only_fallback`)
- 生理指标启发式回退 (`_physiological_heuristic_fallback`)

通过 Mixin 多继承模式装配到 ModelEngine:

    class ModelEngine(..., FallbackMixin, ...):
        ...

依赖关系 (装配后由对应 Mixin / ModelEngine 主体提供):
- `self.text_analyzer`            → ModelEngine.__init__
- `self._incr_fallback`           → InferenceMixin
- `self._score_to_level`          → RiskMixin

向后兼容: 仅需 `from app.core.model_engine import model_engine` 即可继续使用,
本模块对调用方完全透明.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# 标定依据：现有回退预测测试与风险等级校准样本（保持历史输出不变）。
_FALLBACK_WEIGHTS = {
    "stress": 5.0,
    "sleep_deficit": 2.5,
    "social_support_deficit": 2.5,
    "financial_pressure": 2.5,
    "family_history": 10.0,
    "academic_pressure": 3.0,
    "exercise_deficit": 2.0,
    "anxiety": 4.0,
    "panic_attack": 15.0,
    "treatment_seeking": 8.0,
    "cgpa_protective": 1.5,
    "age_protective": 0.3,
}

_PHYSIOLOGICAL_WEIGHTS = {
    "sleep": 0.25,
    "heart_rate": 0.20,
    "blood_pressure": 0.20,
    "exercise": 0.20,
    "steps": 0.15,
}


class FallbackMixin:
    """启发式回退策略方法集合.

    这些方法通过 Mixin 装配到 ModelEngine, 依赖 ModelEngine 实例提供的
    `text_analyzer` / `_incr_fallback` 以及 RiskMixin 提供的 `_score_to_level`.
    """

    def _structured_heuristic_fallback(self, raw: dict[str, Any]) -> tuple[float, float, int]:
        """启发式规则计算结构化风险分数（模型不可用时使用）。

        基于特征加权的风险评估，与测试用例期望对齐。
        权重经过校准，确保健康/中风险/高风险/极高风险样本输出符合预期范围。
        """
        # 提取特征值（使用默认值）
        age = float(raw.get("age", 20))
        cgpa = float(raw.get("cgpa", 3.0))
        stress_level = float(raw.get("stress_level", 3))
        sleep_duration = float(raw.get("sleep_duration", 7))
        social_support = float(raw.get("social_support", 3))
        financial_pressure = float(raw.get("financial_pressure", 3))
        family_history = float(raw.get("family_history", 0))
        academic_pressure = float(raw.get("academic_pressure", 3))
        exercise_frequency = float(raw.get("exercise_frequency", 2))
        anxiety = float(raw.get("anxiety", 3))
        panic_attack = float(raw.get("panic_attack", 0))
        treatment_seeking = float(raw.get("treatment_seeking", 0))

        # 风险因子加权（正向 = 增加风险）
        # 权重已校准：健康样本 ~8分，中等风险 ~54分，高风险/极高风险 ~100分
        risk_factors = (
            stress_level * _FALLBACK_WEIGHTS["stress"]
            + max(0, 8 - sleep_duration) * _FALLBACK_WEIGHTS["sleep_deficit"]
            + (5 - social_support) * _FALLBACK_WEIGHTS["social_support_deficit"]
            + financial_pressure * _FALLBACK_WEIGHTS["financial_pressure"]
            + family_history * _FALLBACK_WEIGHTS["family_history"]
            + academic_pressure * _FALLBACK_WEIGHTS["academic_pressure"]
            + (3 - exercise_frequency) * _FALLBACK_WEIGHTS["exercise_deficit"]
            + anxiety * _FALLBACK_WEIGHTS["anxiety"]
            + panic_attack * _FALLBACK_WEIGHTS["panic_attack"]
            + treatment_seeking * _FALLBACK_WEIGHTS["treatment_seeking"]
        )

        # 保护因子（负向 = 降低风险）
        protective_factors = (
            cgpa * _FALLBACK_WEIGHTS["cgpa_protective"] + (age - 18) * _FALLBACK_WEIGHTS["age_protective"]
        )

        # 基础风险分数
        base_score = risk_factors - protective_factors

        # 归一化到 0-100
        risk_score = max(0.0, min(100.0, base_score))
        probability = risk_score / 100.0
        prediction = 1 if risk_score >= 50 else 0

        logger.info(
            "Structured heuristic fallback: score=%.2f, probability=%.4f",
            risk_score,
            probability,
        )
        return risk_score, probability, prediction

    def _text_heuristic_fallback(self, text: str) -> dict[str, Any]:
        """启发式文本情感回退（所有 ML 模型不可用时使用）。

        基于 TextAnalyzer 的启发式情感分数构建结果，
        确保 predict_text 在模型缺失环境下仍能返回结构一致的响应。
        """
        analysis = self.text_analyzer.analyze(text)
        heuristic_score = float(analysis.get("heuristic_sentiment_score", 0.0))
        prediction = 1 if heuristic_score >= 0.5 else 0
        self._incr_fallback()
        logger.info(
            "Text heuristic fallback: score=%.4f prediction=%d",
            heuristic_score,
            prediction,
        )
        return {
            "prediction": prediction,
            "probability": round(heuristic_score, 4),
            "sentiment_label": "negative" if prediction == 1 else "positive",
            "sentiment_score": round(heuristic_score, 4),
            "model_used": "text_heuristic_fallback",
        }

    def _anxiety_only_fallback(self, gad7_score: float) -> dict:
        estimated = min(gad7_score * 1.29, 27.0)
        risk_score = round(estimated / 27.0 * 100, 2)
        prediction = 1 if risk_score >= 50 else 0
        probability = risk_score / 100.0

        logger.info(
            "Anxiety-only fallback: gad7=%.1f -> score=%.2f",
            gad7_score,
            risk_score,
        )

        return {
            "prediction": prediction,
            "probability": round(probability, 4),
            "risk_score": risk_score,
            "risk_level": self._score_to_level(risk_score),
            "model_used": "anxiety_only_heuristic",
            "model_version": "v1.25",
            "model_family": "fallback",
            "fallback_used": True,
            "fallback_reason": "lite_model_unavailable_or_text_insufficient",
        }

    def _physiological_heuristic_fallback(self, data: dict[str, float | int], reason: str | None = None) -> float:
        sleep_hours = float(data.get("sleep_hours", 7))
        sleep_quality = float(data.get("sleep_quality", 5))
        exercise_minutes = float(data.get("exercise_minutes", 30))
        heart_rate = float(data.get("heart_rate", 70))
        systolic_bp = float(data.get("systolic_bp", 120))
        diastolic_bp = float(data.get("diastolic_bp", 80))
        steps = float(data.get("steps", 5000))

        sleep_deviation = abs(sleep_hours - 7.5) / 7.5
        sleep_risk = (1 - sleep_quality / 10) * 0.4 + sleep_deviation * 0.6
        sleep_score = max(0, min(100, sleep_risk * 60))

        hr_deviation = abs(heart_rate - 70) / 40
        hr_score = max(0, min(100, hr_deviation * 35))

        if systolic_bp >= 140 or diastolic_bp >= 90:
            bp_elevation = max(0, (systolic_bp - 120) / 60 + (diastolic_bp - 80) / 40)
            bp_score = max(0, min(100, bp_elevation * 25))
        elif systolic_bp >= 120 or diastolic_bp >= 80:
            bp_score = 10
        else:
            bp_score = 0

        exercise_deficit = max(0, 1 - exercise_minutes / 45)
        exercise_score = max(0, min(100, exercise_deficit * 25))

        steps_deficit = max(0, 1 - steps / 8000)
        steps_score = max(0, min(100, steps_deficit * 15))

        total_risk = (
            sleep_score * _PHYSIOLOGICAL_WEIGHTS["sleep"]
            + hr_score * _PHYSIOLOGICAL_WEIGHTS["heart_rate"]
            + bp_score * _PHYSIOLOGICAL_WEIGHTS["blood_pressure"]
            + exercise_score * _PHYSIOLOGICAL_WEIGHTS["exercise"]
            + steps_score * _PHYSIOLOGICAL_WEIGHTS["steps"]
        )

        heuristic_result = round(total_risk, 2)
        logger.info(
            "Physiological heuristic fallback: sleep=%.2f hr=%.2f bp=%.2f ex=%.2f st=%.2f -> %.2f (reason: %s)",
            sleep_score,
            hr_score,
            bp_score,
            exercise_score,
            steps_score,
            heuristic_result,
            reason,
        )
        return heuristic_result
