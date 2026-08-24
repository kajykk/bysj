"""多模态融合预测层 (FU 层).

本模块从 `app.core.model_engine_predict` 拆分而来 (model_engine 包结构化拆分),
承担 ModelEngine 的多模态融合预测职责:

- 融合预测 (`predict_fusion`): 结构化/文本/生理三模态并行推理,
  经 FusionEngine 加权融合 + FusionPriorityEngine 优先级规则后输出最终风险

通过 Mixin 多继承模式装配到 ModelEngine:

    class ModelEngine(..., FusionMixin, ...):
        ...

依赖关系 (装配后由对应 Mixin / ModelEngine 主体提供):
- `self.predict_structured` / `self.predict_text` / `self.predict_physiological` → PredictMixin
- `self.fusion_engine` / `self.fusion_priority_engine` → ModelEngine.__init__
- `self._timed_async` / `self._build_intervention_plan` / `self._level_to_severity`
  → InferenceMixin / RiskMixin

向后兼容: 仅需 `from app.core.model_engine import model_engine` 即可继续使用,
本模块对调用方完全透明.
"""

from __future__ import annotations

import asyncio
from typing import Any


class FusionMixin:
    """多模态融合预测方法集合.

    这些方法通过 Mixin 装配到 ModelEngine, 依赖 PredictMixin 提供的各模态
    预测方法以及 ModelEngine.__init__ 提供的融合引擎实例.
    """

    async def predict_fusion(
        self,
        features: dict[str, float | int] | None = None,
        text: str | None = None,
        physiological: dict[str, float | int] | None = None,
    ) -> dict[str, Any]:
        async with self._timed_async("predict", "fusion"):
            if not any([features, text, physiological]):
                return {
                    "risk_score": 0,
                    "risk_level": 0,
                    "severity": "none",
                    "model_used": [],
                    "fusion_detail": {},
                    "intervention_level": "none",
                    "intervention_actions": [],
                }

            structured_result: dict[str, Any] | None = None
            text_result: dict[str, Any] | None = None
            physio_result: dict[str, Any] | None = None

            tasks: list[tuple[str, Any]] = []
            if features:
                tasks.append(("structured", self.predict_structured(features)))
            if text:
                tasks.append(("text", self.predict_text(text)))
            if physiological:
                tasks.append(("physio", self.predict_physiological(physiological)))

            results = await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)
            for (name, _), value in zip(tasks, results):
                if isinstance(value, Exception):
                    continue
                if name == "structured":
                    structured_result = value
                elif name == "text":
                    text_result = value
                elif name == "physio":
                    physio_result = value

            model_used: list[str] = []
            modality_scores: dict[str, dict[str, float | str]] = {}
            modality_scores_raw: dict[str, float] = {}
            modality_metadata: dict[str, dict[str, Any]] = {}

            if structured_result is not None and structured_result.get("risk_score") is not None:
                structured_score = float(structured_result["risk_score"])
                model_used.append(structured_result["model_used"])
                modality_scores["structured"] = {
                    "score": structured_score,
                    "model": structured_result["model_used"],
                }
                modality_scores_raw["structured"] = structured_score
                modality_metadata["structured"] = {
                    "data_quality": structured_result.get("data_quality", {}).get("quality_level", "complete"),
                    "missing_fields": len(structured_result.get("data_quality", {}).get("missing_fields", [])),
                    "fallback_used": structured_result.get("fallback_used", False),
                }

            if text_result is not None and text_result.get("sentiment_score") is not None:
                text_score = float(text_result["sentiment_score"]) * 100
                model_used.append(text_result["model_used"])
                modality_scores["text"] = {
                    "score": round(text_score, 2),
                    "model": text_result["model_used"],
                }
                modality_scores_raw["text"] = text_score
                modality_metadata["text"] = {
                    "text_length": len(text) if text else 0,
                    "crisis_detected": text_result.get("crisis_detected", False),
                }

            if physio_result is not None and physio_result.get("risk_score") is not None:
                physio_score = float(physio_result["risk_score"])
                model_used.append(physio_result["model_used"])
                modality_scores["physiological"] = {
                    "score": physio_score,
                    "model": physio_result["model_used"],
                }
                modality_scores_raw["physiological"] = physio_score
                modality_metadata["physiological"] = {
                    "confidence": physio_result.get("confidence", 0.8),
                    "data_quality": physio_result.get("data_quality", "complete"),
                }

            if not modality_scores_raw:
                return {
                    "risk_score": 0,
                    "risk_level": 0,
                    "severity": "none",
                    "model_used": [],
                    "fusion_detail": {},
                    "intervention_level": "none",
                    "intervention_actions": [],
                }

            fusion_result = self.fusion_engine.fuse(modality_scores_raw, modality_metadata)
            fused_score = fusion_result["risk_score"]
            risk_level = fusion_result["risk_level"]

            dominant_modality = ""
            contributions = fusion_result.get("modality_contributions", {})
            if contributions:
                dominant_modality = max(contributions.items(), key=lambda item: item[1]["contribution"])[0]

            modality_quality: dict[str, str] = {}
            for m, contrib in contributions.items():
                conf = contrib.get("confidence", 0.8)
                if conf >= 0.8:
                    modality_quality[m] = "primary"
                elif conf >= 0.5:
                    modality_quality[m] = "secondary"
                else:
                    modality_quality[m] = "low_confidence"

            fusion_detail: dict[str, Any] = {
                "modality_scores": modality_scores,
                "fusion_scheme": fusion_result.get("fusion_scheme", "unknown"),
                "overall_confidence": fusion_result.get("confidence", 0),
                "modality_contributions": contributions,
                "dominant_modality": dominant_modality,
                "modality_quality": modality_quality,
            }

            # 应用优先级规则 (新增)
            priority_result = self.fusion_priority_engine.apply_priority_rules(
                structured_result, text_result, physio_result, fused_score, risk_level
            )

            # 更新融合结果
            fused_score = priority_result["risk_score"]
            risk_level = priority_result["risk_level"]

            intervention_level, intervention_actions = self._build_intervention_plan(
                risk_level, fused_score, modality_scores
            )
            fusion_detail["intervention_summary"] = {
                "level": intervention_level,
                "actions": intervention_actions,
            }

            return {
                "risk_score": fused_score,
                "risk_level": risk_level,
                "severity": self._level_to_severity(risk_level),
                "model_used": model_used,
                "model_version": "v1.16-risk-calibration",
                "fusion_detail": fusion_detail,
                "intervention_level": intervention_level,
                "intervention_actions": intervention_actions,
                "review_required": priority_result["review_required"],
                "review_triggers": priority_result["review_triggers"],
                "crisis_override": priority_result["crisis_override"],
            }
