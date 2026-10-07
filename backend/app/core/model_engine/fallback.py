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
import math
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


def _finite(value: Any, default: float, *, field: str, clamp: tuple[float, float] | None = None) -> float:
    """把任意输入转为**有限**浮点数，必要时钳制到 ``clamp`` 区间。

    AUDIT-2026-10-08 (P0-5)：本层是 ML 不可用时的**降级终点**，若它自身被
    NaN/Inf 污染，整条降级链就失效 —— 上层再严谨也接不住。实测两个方向都出事：

    - ``_structured_heuristic_fallback``：``max(0.0, min(100.0, nan))`` 在 Python 里
      返回 **100.0**（``min(100.0, nan)`` 依比较语义返回先传入者），把「算不出来」
      变成**满级高风险**，误报方向同样有害（触发无必要的危机干预）。
    - ``_text_heuristic_fallback``：NaN 直接透传，``prediction = 1 if nan >= 0.5 else 0``
      → 0，即「无风险」—— 正是本系统最危险的失效方向。

    因此这里做三件事：非数值退回 ``default``、非有限值退回 ``default``、
    再钳制到业务区间。``default`` 一律取该字段的既有默认/校准值，保证正常输入
    的输出与改动前逐位一致。
    """
    if value is None:
        # 键存在但值为 None（如 API 层显式传 null）与「键缺失」同义，
        # 属正常输入形态，不记 warning —— 否则每次请求刷屏无意义日志。
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        logger.warning("fallback 字段 %s 非数值（%r），退回默认值 %s", field, type(value).__name__, default)
        return default
    if not math.isfinite(out):
        logger.warning("fallback 字段 %s 为非有限值（%r），退回默认值 %s", field, out, default)
        return default
    if clamp is not None:
        lo, hi = clamp
        if out < lo or out > hi:
            logger.warning("fallback 字段 %s 越界（%r, 区间 %s~%s），已钳制", field, out, lo, hi)
            out = min(max(out, lo), hi)
    return out


def _clamp_score(value: float) -> float:
    """把风险分数钳制到 0~100。**对 NaN 无效** —— 故调用前必须已过 :func:`_finite`。"""
    if not math.isfinite(value):
        # 理论上不该到这里（各输入已 _finite）。真到了说明有新路径漏了清洗，
        # 显式抛错而非静默钳成 0 或 100。
        raise ValueError(f"fallback 内部算出非有限分数 {value!r}，拒绝钳制（疑似漏过 _finite）")
    return max(0.0, min(100.0, value))


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
        # 提取特征值（非数值 / NaN / Inf 一律退回既有默认值，见 _finite docstring）
        age = _finite(raw.get("age"), 20, field="age", clamp=(0, 120))
        cgpa = _finite(raw.get("cgpa"), 3.0, field="cgpa", clamp=(0, 4))
        stress_level = _finite(raw.get("stress_level"), 3, field="stress_level", clamp=(0, 10))
        sleep_duration = _finite(raw.get("sleep_duration"), 7, field="sleep_duration", clamp=(0, 24))
        social_support = _finite(raw.get("social_support"), 3, field="social_support", clamp=(0, 10))
        financial_pressure = _finite(raw.get("financial_pressure"), 3, field="financial_pressure", clamp=(0, 10))
        family_history = _finite(raw.get("family_history"), 0, field="family_history", clamp=(0, 1))
        academic_pressure = _finite(raw.get("academic_pressure"), 3, field="academic_pressure", clamp=(0, 10))
        exercise_frequency = _finite(raw.get("exercise_frequency"), 2, field="exercise_frequency", clamp=(0, 7))
        anxiety = _finite(raw.get("anxiety"), 3, field="anxiety", clamp=(0, 10))
        panic_attack = _finite(raw.get("panic_attack"), 0, field="panic_attack", clamp=(0, 1))
        treatment_seeking = _finite(raw.get("treatment_seeking"), 0, field="treatment_seeking", clamp=(0, 1))

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
        # AUDIT-2026-10-08 (P0-5): 原为 `max(0.0, min(100.0, base_score))` ——
        # Python 的 min(100.0, nan) 返回 100.0，会把 NaN 静默变成「满级高风险」。
        # 现在各输入已过 _finite，这里再用 _clamp_score 兜底并在漏网时显式抛错。
        risk_score = _clamp_score(base_score)
        probability = risk_score / 100.0
        prediction = 1 if risk_score >= 50 else 0

        logger.info(
            "Structured heuristic fallback: score=%.2f, probability=%.4f",
            risk_score,
            probability,
        )
        try:
            from app.core.model_engine.loading import _incr_model_fallback

            _incr_model_fallback("structured", "heuristic_fallback")
        except Exception:
            logger.warning("model_fallback_total inc failed (structured/heuristic)", exc_info=True)
        return risk_score, probability, prediction

    def _text_heuristic_fallback(self, text: str) -> dict[str, Any]:
        """启发式文本情感回退（所有 ML 模型不可用时使用）。

        基于 TextAnalyzer 的启发式情感分数构建结果，
        确保 predict_text 在模型缺失环境下仍能返回结构一致的响应。
        """
        analysis = self.text_analyzer.analyze(text)
        # AUDIT-2026-10-08 (P0-5): 原为 `float(analysis.get(..., 0.0))` 直接透传。
        # 实测 TextAnalyzer 产出 NaN 时：prediction = 1 if nan >= 0.5 else 0 → 0，
        # probability 字段也是 nan —— 即「文本回退路径」把「算不出来」表达成
        # 「无负面情绪」，是本系统最危险的失效方向。
        # 情感分语义区间为 [-1, 1]，此处同时做区间钳制防越界。
        heuristic_score = _finite(
            analysis.get("heuristic_sentiment_score"),
            0.0,
            field="heuristic_sentiment_score",
            clamp=(-1.0, 1.0),
        )
        prediction = 1 if heuristic_score >= 0.5 else 0
        self._incr_fallback()
        try:
            from app.core.model_engine.loading import _incr_model_fallback

            _incr_model_fallback("text", "heuristic_fallback")
        except Exception:
            logger.warning("model_fallback_total inc failed (text/heuristic)", exc_info=True)
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
        # AUDIT-2026-10-08 (P0-5): GAD-7 量表定义域 0~27。实测 NaN 输入时
        # `min(nan*1.29, 27.0)` → nan → risk_score=nan → _score_to_level 抛错，
        # 整条降级链在最末端炸掉（上层拿不到任何结果）。此处先清洗为有限值。
        gad7 = _finite(gad7_score, 0.0, field="gad7_score", clamp=(0, 27))
        estimated = min(gad7 * 1.29, 27.0)
        risk_score = _clamp_score(round(estimated / 27.0 * 100, 2))
        prediction = 1 if risk_score >= 50 else 0
        probability = risk_score / 100.0

        logger.info(
            "Anxiety-only fallback: gad7=%.1f -> score=%.2f",
            gad7,
            risk_score,
        )
        try:
            from app.core.model_engine.loading import _incr_model_fallback

            _incr_model_fallback("lite", "anxiety_only")
        except Exception:
            logger.warning("model_fallback_total inc failed (lite/anxiety_only)", exc_info=True)

        return {
            "prediction": prediction,
            "probability": round(probability, 4),
            "risk_score": risk_score,
            "risk_level": self._score_to_level(risk_score),
            "model_used": "anxiety_only_heuristic",
            "model_version": "v1.25",
            "model_family": "fallback",
            "fallback_used": True,
            # 默认值; 调用方(predict_lite)若知道更具体的失效原因会覆盖它。
            # AUDIT-2026-10-08 (P0-5): 旧值 "lite_model_unavailable_or_text_insufficient"
            # 会被套用在「模型加载成功但产出 NaN」场景上, 误导排查方向。
            "fallback_reason": "anxiety_only_heuristic",
        }

    def _physiological_heuristic_fallback(self, data: dict[str, float | int], reason: str | None = None) -> float:
        # AUDIT-2026-10-08 (P0-5): 各字段经 _finite 清洗（生理量测的合法区间已
        # 写入 clamp），避免 NaN 静默把整条降级链变成「无风险」。
        sleep_hours = _finite(data.get("sleep_hours"), 7, field="sleep_hours", clamp=(0, 24))
        sleep_quality = _finite(data.get("sleep_quality"), 5, field="sleep_quality", clamp=(0, 10))
        exercise_minutes = _finite(data.get("exercise_minutes"), 30, field="exercise_minutes", clamp=(0, 1440))
        heart_rate = _finite(data.get("heart_rate"), 70, field="heart_rate", clamp=(0, 250))
        systolic_bp = _finite(data.get("systolic_bp"), 120, field="systolic_bp", clamp=(0, 300))
        diastolic_bp = _finite(data.get("diastolic_bp"), 80, field="diastolic_bp", clamp=(0, 200))
        steps = _finite(data.get("steps"), 5000, field="steps", clamp=(0, 200000))

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

        # 各项均已 _finite, 加权求和必为有限值；仍用 _clamp_score 兜底
        heuristic_result = _clamp_score(round(total_risk, 2))
        try:
            from app.core.model_engine.loading import _incr_model_fallback

            _incr_model_fallback("physiological", reason or "heuristic_fallback")
        except Exception:
            logger.warning("model_fallback_total inc failed (physiological)", exc_info=True)
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
