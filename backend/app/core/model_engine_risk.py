"""风险映射 + 干预 + 危机 + 门控 + SHAP 解释 (RM 层).

本模块从 `app.core.model_engine` 拆分而来 (T-P2-001 PHASE_2 结构性优化),
承担 ModelEngine 的风险等级映射、干预计划构建、危机安全检查、注意力门控
以及 SHAP 因子解释相关职责.

通过 Mixin 多继承模式装配到 ModelEngine:

    class ModelEngine(PredictMixin, FallbackMixin, RiskMixin):
        ...

拆分原因:
- 原 `model_engine.py` 行数达 2051 行, 单文件职责过重难以维护
- 风险/干预相关逻辑自成一域, 与模型加载、预测主流程解耦清晰
- 抽离为独立模块便于单独测试与演进风险策略

向后兼容: 仅需 `from app.core.model_engine import model_engine` 即可继续使用,
本模块对调用方完全透明.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.core.risk_thresholds import (
    RISK_LEVEL_LABELS,
    RISK_LEVEL_THRESHOLDS,
    get_threshold_by_modality,
)

if TYPE_CHECKING:
    import numpy as np
    import pandas as pd
    from sklearn.base import BaseEstimator

logger = logging.getLogger(__name__)


class RiskMixin:
    """风险映射 / 干预 / 危机 / 门控 / SHAP 解释方法集合.

    这些方法通过 Mixin 装配到 ModelEngine, 依赖 ModelEngine 实例的
    `_incr_crisis_override` 方法 (由 ModelEngine 主体提供).
    """

    @staticmethod
    def _score_to_level(score: float, modality: str | None = None) -> int:
        thresholds = (
            get_threshold_by_modality(modality) if modality else RISK_LEVEL_THRESHOLDS
        )
        if score >= thresholds["critical"]:
            return 4
        if score >= thresholds["high"]:
            return 3
        if score >= thresholds["moderate"]:
            return 2
        if score >= thresholds["mild"]:
            return 1
        return 0

    @staticmethod
    def score_to_level(score: float, modality: str | None = None) -> int:
        """公开接口：将分数转换为风险等级（_score_to_level 的公开别名）。"""
        return RiskMixin._score_to_level(score, modality)

    @staticmethod
    def _level_to_severity(level: int) -> str:
        return RISK_LEVEL_LABELS.get(level, "unknown")

    @staticmethod
    def _build_intervention_plan(
        risk_level: int,
        risk_score: float,
        modality_scores: dict[str, dict[str, float | str]],
    ) -> tuple[str, list[str]]:
        dominant_modality = ""
        if modality_scores:
            dominant_modality = max(
                modality_scores.items(), key=lambda item: float(item[1]["score"])
            )[0]

        if risk_level <= 0:
            return "none", ["保持日常心理健康维护", "推荐心理健康教育内容"]
        if risk_level == 1:
            return "low", [
                "推送轻度风险提醒",
                "推荐放松训练与睡眠管理",
                "建议 7 日内复测",
            ]
        if risk_level == 2:
            base_actions = ["触发咨询师关注", "推荐在线心理测评", "建议尽快预约辅导"]
            if dominant_modality == "physiological":
                base_actions.append("建议关注生理指标变化并规律作息")
            return "medium", base_actions
        if risk_level == 3:
            base_actions = [
                "发送高风险预警",
                "优先转介人工干预",
                "同步展示风险因素解释",
            ]
            if dominant_modality == "physiological":
                base_actions.insert(1, "建议进行生理指标专项复查")
            elif dominant_modality == "text":
                base_actions.insert(1, "建议关注情绪表达并提供心理支持资源")
            return "high", base_actions
        critical_actions = [
            "立即触发紧急预警",
            "建议人工重点随访",
            "必要时启动危机干预流程",
        ]
        if dominant_modality == "physiological":
            critical_actions.insert(1, "紧急排查生理异常并建议就医检查")
        return "critical", critical_actions

    def _check_crisis_safety(self, text: str) -> dict:
        matched = [kw for kw in settings.crisis_keywords if kw in text]
        if matched:
            self._incr_crisis_override()
            return {
                "safety_flags": ["crisis_keyword_detected"],
                "requires_human_review": True,
                "crisis_keywords_matched": matched,
                "crisis_override": True,
            }
        return {
            "safety_flags": [],
            "requires_human_review": False,
            "crisis_keywords_matched": [],
            "crisis_override": False,
        }

    @staticmethod
    def _attention_gate(scores: list[float]) -> list[float]:
        import numpy as np

        if not scores:
            return []
        arr = np.array(scores, dtype=float)
        # 使用温度系数避免极端权重
        temperature = max(10.0, np.max(arr) * 0.3)
        arr = arr / temperature
        arr = arr - np.max(arr)
        exp = np.exp(arr)
        total = float(exp.sum()) or 1.0
        weights = [float(v / total) for v in exp]
        # 确保最小权重不低于 0.05，避免信息完全丢失
        min_weight = 0.05
        weights = [max(w, min_weight) for w in weights]
        total = sum(weights) or 1.0
        return [float(v / total) for v in weights]

    @staticmethod
    def _boost_gate_for_physiology(
        scores: list[float], gate_weights: list[float]
    ) -> list[float]:
        if not scores or len(scores) != len(gate_weights):
            return gate_weights
        boosted = list(gate_weights)
        if len(boosted) >= 3:
            boosted[-1] = min(0.85, boosted[-1] + 0.15)
            remainder = max(0.0, 1.0 - boosted[-1])
            other_total = sum(boosted[:-1]) or 1.0
            for idx in range(len(boosted) - 1):
                boosted[idx] = boosted[idx] / other_total * remainder
        total = sum(boosted) or 1.0
        return [float(v / total) for v in boosted]

    @staticmethod
    def _compute_shap_factors(
        model: BaseEstimator,
        feature_df: pd.DataFrame,
        model_feature_names: list[str],
    ) -> list[dict[str, Any]]:
        import shap

        explainer = shap.Explainer(model, feature_df)
        shap_values = explainer(feature_df)
        factors: list[dict[str, Any]] = []
        for i, col in enumerate(model_feature_names):
            value = float(shap_values.values[0][i])
            factors.append(
                {
                    "feature": col,
                    "importance": round(abs(value), 4),
                    "direction": "positive" if value > 0 else "negative",
                }
            )
        factors.sort(key=lambda x: x["importance"], reverse=True)
        return factors[:5]

    @staticmethod
    def _compute_shap_factors_array(
        model: BaseEstimator,
        feature_array: np.ndarray,
        feature_order: list[str],
    ) -> list[dict[str, Any]]:
        import shap

        explainer = shap.Explainer(model, feature_array)
        shap_values = explainer(feature_array)
        factors: list[dict[str, Any]] = []
        for i, f in enumerate(feature_order):
            value = float(shap_values.values[0][i])
            factors.append(
                {
                    "feature": f,
                    "importance": round(abs(value), 4),
                    "direction": "positive" if value > 0 else "negative",
                }
            )
        factors.sort(key=lambda x: x["importance"], reverse=True)
        return factors[:5]
