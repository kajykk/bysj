"""核心预测层 (PD 层).

本模块从 `app.core.model_engine` 拆分而来 (T-P2-001 PHASE_2 结构性优化),
承担 ModelEngine 的所有 ML 预测主流程职责:

- 结构化预测 (`predict_structured`) 及其 v1.21 / v1.23 实验路径与 v1.24 adapter
- 文本预测 (`predict_text`) 及其 ML / BERT 子路径
- Lite 预测 (`predict_lite`)
- 生理预测 (`predict_physiological`) 及其同步推理实现
- 多模态融合预测 (`predict_fusion`)
- SHAP 解释入口 (`explain_prediction`)

通过 Mixin 多继承模式装配到 ModelEngine:

    class ModelEngine(PredictMixin, FallbackMixin, RiskMixin):
        ...

依赖关系 (MixIn 装配后由对应 Mixin / ModelEngine 主体提供):
- `self._load_model_async` / `self._load_adapter_async`  → ModelEngine 主体
- `self._timed_async` / `self._patch_simple_imputer`    → ModelEngine 主体
- `self._route_structured` / `self._update_structured_monitoring` → ModelEngine 主体
- `self._build_structured_input` / `self.feature_order`  → ModelEngine 主体
- `self._incr_counter` / `self._incr_fallback`           → ModelEngine 主体
- `self._score_to_level` / `self._check_crisis_safety`   → RiskMixin
- `self._build_intervention_plan` / `self._level_to_severity` → RiskMixin
- `self._compute_shap_factors` / `self._compute_shap_factors_array` → RiskMixin
- `self._structured_heuristic_fallback` / `self._text_heuristic_fallback` → FallbackMixin
- `self._anxiety_only_fallback` / `self._physiological_heuristic_fallback` → FallbackMixin
- `self.crisis_detector` / `self.text_analyzer`         → ModelEngine.__init__
- `self.fusion_engine` / `self.fusion_priority_engine`  → ModelEngine.__init__
- `LiteFeatureExtractor`                                  → 通过延迟导入从 model_engine 获取

死代码清理: 删除 `_predict_keras_fusion` (无任何调用方, 28 行).

向后兼容: 仅需 `from app.core.model_engine import model_engine` 即可继续使用,
本模块对调用方完全透明.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.core.exceptions import ModelException
from app.core.feature_maps import (
    DEFAULTS as _DEFAULTS,
)
from app.core.feature_maps import (
    LITE_FEATURE_ORDER,
)
from app.core.model_registry import get_model_info

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PredictMixin:
    """核心预测方法集合.

    这些方法通过 Mixin 装配到 ModelEngine, 依赖 ModelEngine 主体及其他 Mixin
    提供的实例方法 (详见模块 docstring 中的依赖关系说明).
    """

    async def predict_structured(
        self, features: dict[str, float | int | str | bool]
    ) -> dict[str, Any]:
        import numpy as np
        import pandas as pd

        async with self._timed_async("predict", "structured"):
            raw: dict[str, Any] = dict(features)

            routing_info, routed_result = self._route_structured(raw)
            if routed_result is not None:
                if routed_result == "lite":
                    gad7 = raw.get("gad7_score", None)
                    transcript = raw.get("audio_transcript") or raw.get("text", "")
                    lite_result = await self.predict_lite(
                        gad7_score=float(gad7),
                        audio_transcript=str(transcript),
                        age=float(raw.get("age", 25)),
                        gender=int(raw.get("gender", 1)),
                        cgpa=float(raw.get("cgpa", 3.1)),
                    )
                    lite_result["routing_info"] = routing_info
                    return lite_result
                elif routed_result == "anxiety_only":
                    gad7 = raw.get("gad7_score", None)
                    fb = self._anxiety_only_fallback(float(gad7))
                    fb["routing_info"] = routing_info
                    return fb
                else:
                    return {
                        "prediction": None,
                        "probability": None,
                        "risk_score": None,
                        "risk_level": None,
                        "model_used": None,
                        "model_version": None,
                        "fallback_used": True,
                        "fallback_reason": "insufficient_information",
                        "routing_info": routing_info,
                        "warning": "信息不足以评估风险，请提供 GAD-7 评分或结构化特征",
                    }

            model = None
            model_used = "structured_logistic_regression_quick"
            model_version = "v1.20"
            fallback_used = False
            fallback_reason = None

            from app.core.config import settings

            force_fallback = (
                getattr(settings, "structured_model_mode", "primary") == "fallback"
            )

            if force_fallback:
                fallback_reason = "forced_by_config: STRUCTURED_MODEL_MODE=fallback"
                logger.warning("Structured model forced to fallback by config")

            if not force_fallback:
                try:
                    model = await self._load_model_async(
                        "structured_logistic_regression_quick"
                    )
                    self._patch_simple_imputer(model)
                except (FileNotFoundError, ValueError) as exc:
                    fallback_reason = f"model_load_failed: {exc}"
                    logger.warning(
                        "Structured model not available, using heuristic fallback: %s",
                        exc,
                    )

            structured_scaler = None
            if model is not None:
                try:
                    structured_scaler = await self._load_model_async(
                        "structured_scaler_v1.20"
                    )
                except (FileNotFoundError, ValueError) as exc:
                    logger.warning(
                        "Structured scaler not available, proceeding without scaling: %s",
                        exc,
                    )

            if model is not None:
                model_feature_names = list(getattr(model, "feature_names_in_", []))
                if model_feature_names:
                    input_dict = self._build_structured_input(
                        raw, model_feature_names, model
                    )
                    feature_df = pd.DataFrame(
                        [{col: input_dict[col] for col in model_feature_names}],
                        columns=model_feature_names,
                    )
                    if structured_scaler is not None:
                        feature_scaled = await asyncio.to_thread(
                            structured_scaler.transform, feature_df
                        )
                    else:
                        feature_scaled = feature_df.values
                else:
                    feature_array = np.array(
                        [[float(raw.get(k, 0)) for k in self.feature_order]]
                    )
                    if structured_scaler is not None:
                        feature_scaled = await asyncio.to_thread(
                            structured_scaler.transform, feature_array
                        )
                    else:
                        feature_scaled = feature_array
                prediction = await asyncio.to_thread(model.predict, feature_scaled)
                prediction = int(prediction[0])
                proba = await asyncio.to_thread(model.predict_proba, feature_scaled)
                probability = float(proba[0][1])
                risk_score = round(probability * 100, 2)
            else:
                model_used = "structured_heuristic_fallback"
                fallback_used = True
                self._incr_fallback()
                risk_score, probability, prediction = (
                    self._structured_heuristic_fallback(raw)
                )

            missing_fields: list[str] = []
            for field in self.feature_order:
                if field not in raw or raw[field] is None or raw[field] == "":
                    missing_fields.append(field)

            confidence_penalty = min(len(missing_fields) * 0.1, 0.3)

            if len(missing_fields) == 0:
                quality_level = "complete"
            elif len(missing_fields) <= 2:
                quality_level = "partial"
            else:
                quality_level = "poor"

            risk_level = self._score_to_level(risk_score, modality="structured")

            prob_extremity = abs(probability - 0.5) * 2
            base_confidence = 0.5 + prob_extremity * 0.3
            if fallback_used:
                base_confidence *= 0.7
            f_coverage = routing_info["feature_coverage_ratio"]
            coverage_factor = min(f_coverage / 0.9, 1.0) if f_coverage > 0 else 0.3
            quality_factor = {"complete": 1.0, "partial": 0.85, "poor": 0.6}.get(
                quality_level, 0.6
            )
            confidence = round(base_confidence * coverage_factor * quality_factor, 3)
            confidence = max(0.2, min(1.0, confidence))

            result: dict[str, Any] = {
                "prediction": prediction,
                "probability": round(probability, 4),
                "risk_score": risk_score,
                "risk_level": risk_level,
                "model_used": model_used,
                "model_version": model_version,
                "fallback_used": fallback_used,
                "confidence": confidence,
                "data_quality": {
                    "missing_fields": missing_fields,
                    "confidence_penalty": round(confidence_penalty, 2),
                    "quality_level": quality_level,
                },
            }
            if fallback_reason:
                result["fallback_reason"] = fallback_reason

            # PERF-P0-002 修复: v121 和 v123 独立无依赖, 并行执行减少串行等待
            # v121 加载 structured_v1.21_binary_lr + scaler, 返回 experimental_real_*
            # v123 加载 structured_v1.23_external_lr, 返回 experimental_external_*
            # 两者返回字段不冲突, 可安全并行; 内部 asyncio.to_thread 推理可真正并发
            # adapter 依赖 v123 的 experimental_external_score, 必须在 v123 完成后执行
            #
            # RES-P1-001 修复: 实验路径开关
            # structured_experimental_enabled=True (默认): 执行 3 路实验性推理, 提供对比数据
            # structured_experimental_enabled=False: 跳过实验路径, 减少 CPU 放大 4 倍 (生产环境可选关闭)
            # 关闭时 experimental_*/adapter 字段保持 None, 前端不显示实验对比卡片
            if settings.structured_experimental_enabled:
                v121_result, v123_result = await asyncio.gather(
                    self._run_experimental_v121(raw, risk_score),
                    self._run_experimental_v123(raw, risk_score),
                )
                result.update(v121_result)
                result.update(v123_result)
                result.update(
                    await self._run_adapter(
                        risk_score,
                        fallback_used,
                        result.get("experimental_external_score"),
                    )
                )
            else:
                # 实验路径关闭: 填充 None 占位字段, 保持响应结构一致
                result.update(
                    {
                        "experimental_real_score": None,
                        "experimental_real_level": None,
                        "experimental_real_probability": None,
                        "experimental_real_model": None,
                        "experimental_external_score": None,
                        "experimental_external_level": None,
                        "experimental_external_model": None,
                        "experimental_external_available": False,
                        "experimental_external_delta": None,
                        "adjusted_score": None,
                        "adjusted_delta": None,
                        "adjusted_safe_label": None,
                        "adapter_available": False,
                        "adapter_version": None,
                        "v123_raw_score": None,
                    }
                )
                logger.debug(
                    "experimental path skipped (structured_experimental_enabled=False)"
                )

            self._update_structured_monitoring(
                risk_score,
                risk_level,
                fallback_used,
                result.get("experimental_real_score"),
                result.get("experimental_real_model"),
                result.get("experimental_external_available"),
                result.get("experimental_external_score"),
                quality_level,
            )

            result["routing_info"] = routing_info

            return result

    async def _run_experimental_v121(
        self, raw: dict[str, Any], default_score: float
    ) -> dict[str, Any]:
        import numpy as np

        experimental_real_score = None
        experimental_real_level = None
        experimental_real_model = None
        experimental_real_probability = None

        v1_21_info = get_model_info("structured_v1.21_binary_lr")
        if v1_21_info is not None and v1_21_info.lifecycle != "deprecated":
            try:
                exp_model = await self._load_model_async("structured_v1.21_binary_lr")
                exp_scaler = await self._load_model_async("structured_v1.21_scaler")
                exp_feature_order = [
                    "age",
                    "gender",
                    "study_year",
                    "cgpa",
                    "stress_level",
                    "sleep_duration",
                    "social_support",
                    "financial_pressure",
                    "family_history",
                    "academic_pressure",
                    "exercise_frequency",
                    "anxiety",
                    "panic_attack",
                    "treatment_seeking",
                ]
                exp_values = []
                for feat in exp_feature_order:
                    val = raw.get(feat, _DEFAULTS.get(feat, 0))
                    exp_values.append(float(val) if val is not None else 0.0)
                exp_array = np.array([exp_values], dtype=float)
                try:
                    exp_scaled = await asyncio.to_thread(
                        exp_scaler.transform, exp_array
                    )
                except Exception as exc:
                    # P1-E 修复：scaler.transform 失败时回退到未缩放数据，但必须记录日志便于排查
                    logger.warning(
                        "exp_scaler.transform failed, using unscaled data: %s", exc
                    )
                    exp_scaled = exp_array
                exp_proba = await asyncio.to_thread(exp_model.predict_proba, exp_scaled)
                experimental_real_probability = float(exp_proba[0][1])
                experimental_real_score = round(experimental_real_probability * 100, 2)
                experimental_real_level = self._score_to_level(
                    experimental_real_score, modality="structured"
                )
                experimental_real_model = "structured_v1.21_binary_lr"
                logger.info(
                    "v1.22 experimental path: score=%.2f level=%d (default_score=%.2f)",
                    experimental_real_score,
                    experimental_real_level,
                    default_score,
                )
            except Exception as exc:
                logger.warning("v1.22 experimental real binary LR unavailable: %s", exc)
        else:
            logger.debug("v1.21 binary LR deprecated — skipping experimental path")

        return {
            "experimental_real_score": experimental_real_score,
            "experimental_real_level": experimental_real_level,
            "experimental_real_probability": experimental_real_probability,
            "experimental_real_model": experimental_real_model,
        }

    async def _run_experimental_v123(
        self, raw: dict[str, Any], default_score: float
    ) -> dict[str, Any]:
        import numpy as np

        experimental_external_score = None
        experimental_external_level = None
        experimental_external_model = None
        experimental_external_available = False

        try:
            ext_model = await self._load_model_async("structured_v1.23_external_lr")
            self._patch_simple_imputer(ext_model)
            ext_feature_order = [
                "age",
                "gender",
                "cgpa",
                "stress_level",
                "sleep_duration",
                "social_support",
                "financial_pressure",
                "family_history",
                "academic_pressure",
                "exercise_frequency",
                "anxiety",
                "panic_attack",
            ]
            ext_values = []
            for feat in ext_feature_order:
                val = raw.get(feat, _DEFAULTS.get(feat, 0))
                ext_values.append(float(val) if val is not None else 0.0)
            ext_array = np.array([ext_values], dtype=float)
            ext_proba = await asyncio.to_thread(ext_model.predict_proba, ext_array)
            experimental_external_probability = float(ext_proba[0][1])
            experimental_external_score = round(
                experimental_external_probability * 100, 2
            )
            experimental_external_level = self._score_to_level(
                experimental_external_score, modality="structured"
            )
            experimental_external_model = "structured_v1.23_external_lr"
            experimental_external_available = True
            logger.info(
                "v1.23 experimental path: score=%.2f level=%d (default_score=%.2f)",
                experimental_external_score,
                experimental_external_level,
                default_score,
            )
        except Exception as exc:
            logger.warning("v1.23 experimental external LR unavailable: %s", exc)

        delta = (
            round(experimental_external_score - default_score, 2)
            if experimental_external_score is not None
            else None
        )

        return {
            "experimental_external_score": experimental_external_score,
            "experimental_external_level": experimental_external_level,
            "experimental_external_model": experimental_external_model,
            "experimental_external_available": experimental_external_available,
            "experimental_external_delta": delta,
        }

    async def _run_adapter(
        self, risk_score: float, fallback_used: bool, v123_raw_score: float | None
    ) -> dict[str, Any]:
        adjusted_score = None
        adjusted_delta = None
        adjusted_safe_label = None
        adapter_available = False
        adapter_version = None

        try:
            adapter = await self._load_adapter_async()
            if adapter is not None:
                base_score = risk_score
                # C-01 修复：显式 None 检查，避免 0.0 分被替换为 base_score
                adapter_input = (
                    v123_raw_score if v123_raw_score is not None else base_score
                )
                adapter_result = adapter.transform(base_score, adapter_input)
                adjusted_score = adapter_result["score"]
                adjusted_delta = adapter_result["delta"]
                adjusted_safe_label = adapter_result["safe_label"]
                adapter_available = True
                adapter_version = adapter.version
                logger.info(
                    "v1.24 adapter: adjusted=%.2f label=%s (raw=%.2f)",
                    adjusted_score,
                    adjusted_safe_label,
                    v123_raw_score,
                )
        except Exception as exc:
            logger.warning("v1.24 adapter unavailable: %s", exc)

        if adapter_available:
            self._incr_counter("adapter_hit")
        else:
            self._incr_counter("adapter_miss")

        return {
            "adjusted_score": adjusted_score,
            "adjusted_delta": adjusted_delta,
            "adjusted_safe_label": adjusted_safe_label,
            "adapter_available": adapter_available,
            "adapter_version": adapter_version,
            "v123_raw_score": v123_raw_score,
        }

    async def predict_text(self, text: str) -> dict[str, Any]:
        async with self._timed_async("predict", "text"):
            # 1. 危机检测 (新增)
            crisis_result = self.crisis_detector.scan(text)

            # 2. ML 模型预测 (已有)
            ml_result = await self._predict_text_ml(text)

            # 3. 文本风险分析 (新增)
            text_analysis = self.text_analyzer.analyze(text)

            heuristic_score = float(text_analysis.get("heuristic_sentiment_score", 0.0))
            model_score = float(ml_result.get("sentiment_score", 0.0))

            model_extremity = abs(model_score - 0.5) * 2
            model_weight = 0.4 + model_extremity * 0.4
            heuristic_weight = 0.6 - model_extremity * 0.4

            disagreement = abs(model_score - heuristic_score)
            if disagreement > 0.5:
                model_weight = max(model_weight, 0.65)
                heuristic_weight = min(heuristic_weight, 0.35)

            total_w = model_weight + heuristic_weight
            model_weight /= total_w
            heuristic_weight /= total_w

            final_sentiment_score = round(
                model_score * model_weight + heuristic_score * heuristic_weight, 4
            )
            final_sentiment_label = (
                "negative" if final_sentiment_score >= 0.2 else "positive"
            )

            # 4. 合并结果
            result = {
                **ml_result,
                "sentiment_label": final_sentiment_label,
                "sentiment_score": round(final_sentiment_score, 4),
                "distress_score": round(final_sentiment_score * 100, 2),
                "crisis_score": crisis_result["crisis_score"],
                "risk_factors": text_analysis["risk_factors"],
                "protective_factors": text_analysis["protective_factors"],
                "crisis_detected": crisis_result["crisis_detected"],
                "crisis_keywords": crisis_result["matched_keywords"],
            }

            # 5. 如果检测到危机，覆盖 risk_level
            if crisis_result["crisis_detected"]:
                result["risk_level"] = 4  # critical
                result["crisis_override"] = True

            return result

    async def _predict_text_ml(self, text: str) -> dict[str, Any]:
        """ML 模型预测文本情感。

        三级回退策略：
        1. BERT 文本模型（若可用）
        2. TF-IDF + LR 主文本模型 -> 双语回退模型
        3. 启发式回退（基于 TextAnalyzer 启发式情感分数）

        Returns:
            包含 prediction/probability/sentiment_score/model_used 的字典。
        """
        # Level 1: BERT 文本模型
        bert_result = await self._predict_text_bert(text)
        if bert_result is not None:
            return bert_result

        # Level 2: TF-IDF + LR 主文本模型 -> 双语回退模型
        model_used = "text_depression_model"
        try:
            tfidf = await self._load_model_async("text_depression_tfidf")
            model = await self._load_model_async("text_depression_model")
        except Exception as exc:
            # P1-E 修复：主文本模型加载失败回退到改进版双语模型，必须记录日志便于排查
            logger.warning(
                "Primary text model unavailable, falling back to bilingual: %s", exc
            )
            try:
                tfidf = await self._load_model_async("text_improved_bilingual_tfidf")
                model = await self._load_model_async("text_improved_bilingual_model")
                model_used = "text_improved_bilingual_model"
            except Exception as bilingual_exc:
                # 三级回退：所有 ML 模型不可用时，使用启发式分数
                logger.warning(
                    "All text ML models unavailable, using heuristic fallback: %s",
                    bilingual_exc,
                )
                return self._text_heuristic_fallback(text)

        vector = await asyncio.to_thread(tfidf.transform, [text])
        prediction = await asyncio.to_thread(model.predict, vector)
        prediction = int(prediction[0])
        proba = await asyncio.to_thread(model.predict_proba, vector)
        probability = float(proba[0][1])
        return {
            "prediction": prediction,
            "probability": round(probability, 4),
            "sentiment_label": "negative" if prediction == 1 else "positive",
            "sentiment_score": round(probability, 4),
            "model_used": model_used,
        }

    async def _predict_text_bert(self, text: str) -> dict[str, Any] | None:
        try:
            bundle = await self._load_model_async("text_bert_classifier")
            tokenizer = bundle["tokenizer"]
            model = bundle["model"]
            inputs = await asyncio.to_thread(
                tokenizer,
                text,
                return_tensors="pt",
                truncation=True,
                padding=True,
                max_length=256,
            )
            import torch

            with torch.no_grad():
                outputs = await asyncio.to_thread(model, **inputs)
                logits = outputs.logits
                probs = torch.softmax(logits, dim=-1)[0]
                score = (
                    float(probs[1].item())
                    if probs.shape[-1] > 1
                    else float(probs[0].item())
                )
                prediction = int(torch.argmax(probs).item())
            return {
                "prediction": prediction,
                "probability": round(score, 4),
                "sentiment_label": "negative" if prediction == 1 else "positive",
                "sentiment_score": round(score, 4),
                "model_used": "text_bert_classifier",
            }
        except Exception as exc:
            # P1-E 修复：BERT 文本模型预测失败必须记录日志，便于排查模型加载/推理问题
            logger.warning("BERT text predict failed: %s", exc)
            return None

    async def predict_lite(
        self,
        gad7_score: float,
        audio_transcript: str,
        age: float | None = None,
        gender: int | None = None,
        cgpa: float | None = None,
    ) -> dict[str, Any]:
        import asyncio

        import numpy as np

        # LiteFeatureExtractor 定义在 model_engine.py, 此处延迟导入避免循环依赖
        from app.core.model_engine import LiteFeatureExtractor

        async with self._timed_async("predict", "lite"):
            length = len(audio_transcript)
            chinese_c = sum(1 for c in audio_transcript if "\u4e00" <= c <= "\u9fff")
            chinese_r = chinese_c / max(length, 1)

            if length < 20:
                logger.warning(
                    "Lite model: text too short (%d chars), "
                    "falling back to anxiety_only",
                    length,
                )
                self._incr_fallback()
                return self._anxiety_only_fallback(gad7_score)

            extractor = LiteFeatureExtractor()
            kw = extractor.extract(audio_transcript)

            feature_dict: dict[str, float] = {
                "gad7_score": gad7_score,
                "total_keywords": float(kw["total_keywords"]),
                "unique_categories": float(kw["unique_categories"]),
                "age": age if age is not None else 25.0,
                "gender": float(gender if gender is not None else 1),
                "cgpa": cgpa if cgpa is not None else 3.1,
                "text_length": float(length),
                "chinese_ratio": round(chinese_r, 4),
            }

            for cat in LiteFeatureExtractor.KEYWORD_CATEGORIES:
                feature_dict[f"kw_{cat}"] = float(kw["keyword_counts"].get(cat, 0))

            if chinese_r < 0.30:
                feature_dict["text_quality_flag"] = 1.0
            else:
                feature_dict["text_quality_flag"] = 2.0

            feature_dict["coverage_density"] = (
                kw["total_keywords"] / max(length, 1) * 100
            )

            try:
                model = await self._load_model_async("mmpsy_lite_model")
                scaler = await self._load_model_async("mmpsy_lite_scaler")

                feature_array = np.array(
                    [[feature_dict.get(f, 0.0) for f in LITE_FEATURE_ORDER]],
                    dtype=float,
                )
                scaled = await asyncio.to_thread(scaler.transform, feature_array)
                proba = await asyncio.to_thread(model.predict_proba, scaled)
                probability = float(proba[0][1])
                prediction = 1 if probability >= settings.lite_decision_threshold else 0
                risk_score = round(probability * 100, 2)
                risk_level = self._score_to_level(risk_score)

                safety = self._check_crisis_safety(audio_transcript)
                if safety["crisis_override"] and risk_level < 4:
                    risk_level = 4

                return {
                    "prediction": prediction,
                    "probability": round(probability, 4),
                    "risk_score": risk_score,
                    "risk_level": risk_level,
                    "model_used": "mmpsy_lite_model",
                    "model_version": "v1.25",
                    "model_family": "lite",
                    "fallback_used": False,
                    "crisis_override": safety["crisis_override"],
                    "safety_flags": safety["safety_flags"],
                    "requires_human_review": safety["requires_human_review"],
                    "crisis_keywords_matched": safety["crisis_keywords_matched"],
                }

            except Exception as exc:
                logger.warning(
                    "Lite model unavailable: %s, falling back to " "anxiety_only", exc
                )
                self._incr_fallback()
                return self._anxiety_only_fallback(gad7_score)

    async def predict_physiological(
        self, physiological: dict[str, float | int]
    ) -> dict[str, Any]:
        async with self._timed_async("predict", "physiological"):
            score = await self._predict_physiological(physiological)
            prediction = 1 if score >= 50 else 0
            probability = round(score / 100.0, 4)

            # 置信度计算 (新增)
            base_confidence = 0.8
            missing_count = 0
            for key in [
                "sleep_hours",
                "sleep_quality",
                "exercise_minutes",
                "heart_rate",
                "systolic_bp",
                "diastolic_bp",
                "steps",
            ]:
                if key not in physiological:
                    missing_count += 1
            confidence = base_confidence - (missing_count * 0.1)
            if confidence < 0.3:
                confidence = 0.3

            data_quality = (
                "complete"
                if missing_count == 0
                else "partial" if missing_count <= 2 else "poor"
            )

            return {
                "prediction": prediction,
                "probability": probability,
                "risk_score": round(score, 2),
                "risk_level": self._score_to_level(score, "physiological"),
                "model_used": "physiological_risk_model",
                "confidence": round(confidence, 2),
                "data_quality": data_quality,
                "calibrated": True,
            }

    async def _predict_physiological(self, data: dict[str, float | int]) -> float:
        fallback_reason = None

        # L-Core-5 修复：移除无效的 PyTorch 早期检查。生理模型 framework 为 numpy
        # （见 model_registry 中 physiological_model_v2_dl 的 feature_schema），
        # 不依赖 PyTorch；原检查会在无 PyTorch 环境下误判模型不可用，直接走 fallback。

        try:
            # M-06 修复：将 CPU 密集型的同步推理逻辑放到线程池中执行，避免阻塞事件循环
            # load_model/scaler.transform/predict_proba 等操作可能耗时较长
            prob = await asyncio.to_thread(self._predict_physiological_sync, data)
            return prob
        except ModelException:
            raise
        except FileNotFoundError as exc:
            if fallback_reason is None:
                fallback_reason = "model_not_found"
            logger.warning("MLP model not found, falling back to heuristic: %s", exc)
        except ImportError as exc:
            # L-Core-5：依赖缺失（如 numpy/pandas/sklearn），不再特指 PyTorch
            fallback_reason = "dependency_not_installed"
            logger.warning(
                "Required dependency not installed, falling back to heuristic: %s", exc
            )
        except Exception as exc:
            fallback_reason = "prediction_error"
            logger.warning("MLP prediction failed, falling back to heuristic: %s", exc)

        # Fallback to heuristic
        return self._physiological_heuristic_fallback(data, fallback_reason)

    def _predict_physiological_sync(self, data: dict[str, float | int]) -> float:
        """同步执行生理模型推理（M-06：从 _predict_physiological 提取，供 asyncio.to_thread 调用）。"""
        import numpy as np
        import pandas as pd

        from app.ml.model_loader import (
            CLEANER_STATS_PATH,
            check_model_exists,
            load_cleaner,
            load_feature_names,
            load_model,
            load_scaler,
        )

        if not check_model_exists():
            raise ModelException(
                code="MODEL_NOT_FOUND",
                message="Model artifacts not found (physiological_optimized)",
                status_code=503,
                layer="L1_PRIMARY_MODEL",
                fallback_to="L4_HEURISTIC",
            )

        model = load_model()
        scaler = load_scaler()
        feature_names = load_feature_names()

        # P1-ML-005 修复：加载训练时的 DataCleaner 统计量，确保推理时特征工程一致
        cleaner = None
        if CLEANER_STATS_PATH.exists():
            try:
                cleaner = load_cleaner()
            except Exception as clean_exc:
                logger.warning(
                    "Failed to load cleaner stats, using raw input: %s", clean_exc
                )

        # Build raw feature dict with original 7 features
        raw_data = {
            "sleep_hours": float(data.get("sleep_hours", 7)),
            "sleep_quality": float(data.get("sleep_quality", 5)),
            "exercise_minutes": float(data.get("exercise_minutes", 30)),
            "heart_rate": float(data.get("heart_rate", 70)),
            "systolic_bp": float(data.get("systolic_bp", 120)),
            "diastolic_bp": float(data.get("diastolic_bp", 80)),
            "steps": float(data.get("steps", 5000)),
        }

        # P1-ML-005 修复：应用训练时的 DataCleaner.transform_single
        # 执行与训练一致的：中位数填充 + 极端值裁剪 + Winsorization 边界裁剪
        if cleaner is not None:
            cleaned_data = cleaner.transform_single(raw_data)
        else:
            # 回退：仅应用固定生理阈值裁剪（无训练集统计量）
            from app.ml.data_cleaner import EXTREME_THRESHOLDS

            cleaned_data = {}
            for col, val in raw_data.items():
                if val is None or (isinstance(val, float) and np.isnan(val)):
                    cleaned_data[col] = 0.0
                else:
                    cleaned_data[col] = float(val)
                if col in EXTREME_THRESHOLDS:
                    low, high = EXTREME_THRESHOLDS[col]
                    cleaned_data[col] = max(low, min(high, cleaned_data[col]))

        # P1-ML-005 修复：使用训练时的 engineer_features 函数，确保派生特征计算公式一致
        from app.ml.feature_engineering import engineer_features

        df_single = pd.DataFrame([cleaned_data])
        df_engineered = engineer_features(df_single)

        # Build feature array in correct order
        feature_array = np.array(
            [[df_engineered.iloc[0][f] for f in feature_names]],
            dtype=np.float32,
        )
        scaled = scaler.transform(feature_array)
        # P1-ML-005 修复：移除推理时额外的 np.clip(scaled, -5.0, 5.0)
        # 训练时未应用此 clip，推理时应用会导致分布偏移
        for li, layer in enumerate(model.layers):
            if "bn_running_mean" in layer:
                rm = layer["bn_running_mean"]
                rv = layer["bn_running_var"]
                if np.allclose(rm, 0) and np.allclose(rv, 1):
                    logger.warning(
                        "PhysiologicalMLP layer %d BN running stats NOT loaded (mean=0, var=1), reloading model",
                        li,
                    )
                    model = load_model()
                    scaler = load_scaler()
                    feature_names = load_feature_names()
                    feature_array = np.array(
                        [[df_engineered.iloc[0][f] for f in feature_names]],
                        dtype=np.float32,
                    )
                    scaled = scaler.transform(feature_array)
                    # M-Core-7 修复：重载后重新验证 BN running stats，
                    # 若仍异常则抛 ModelException 走降级路径，避免带错误 stats 推理。
                    for verify_layer in model.layers:
                        if "bn_running_mean" in verify_layer:
                            v_rm = verify_layer["bn_running_mean"]
                            v_rv = verify_layer["bn_running_var"]
                            if np.allclose(v_rm, 0) and np.allclose(v_rv, 1):
                                raise ModelException(
                                    code="BN_STATS_LOAD_FAILED",
                                    message="BN running stats still invalid after model reload",
                                    status_code=503,
                                    layer="L1_PRIMARY_MODEL",
                                    fallback_to="L4_HEURISTIC",
                                )
                    break
        proba = model.predict_proba(scaled)
        prob = float(proba[0][0])
        return round(prob * 100, 2)

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

            results = await asyncio.gather(
                *(task for _, task in tasks), return_exceptions=True
            )
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

            if (
                structured_result is not None
                and structured_result.get("risk_score") is not None
            ):
                structured_score = float(structured_result["risk_score"])
                model_used.append(structured_result["model_used"])
                modality_scores["structured"] = {
                    "score": structured_score,
                    "model": structured_result["model_used"],
                }
                modality_scores_raw["structured"] = structured_score
                modality_metadata["structured"] = {
                    "data_quality": structured_result.get("data_quality", {}).get(
                        "quality_level", "complete"
                    ),
                    "missing_fields": len(
                        structured_result.get("data_quality", {}).get(
                            "missing_fields", []
                        )
                    ),
                    "fallback_used": structured_result.get("fallback_used", False),
                }

            if (
                text_result is not None
                and text_result.get("sentiment_score") is not None
            ):
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

            if (
                physio_result is not None
                and physio_result.get("risk_score") is not None
            ):
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

            fusion_result = self.fusion_engine.fuse(
                modality_scores_raw, modality_metadata
            )
            fused_score = fusion_result["risk_score"]
            risk_level = fusion_result["risk_level"]

            dominant_modality = ""
            contributions = fusion_result.get("modality_contributions", {})
            if contributions:
                dominant_modality = max(
                    contributions.items(), key=lambda item: item[1]["contribution"]
                )[0]

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

    async def explain_prediction(
        self, features: dict[str, float | int], model_id: str
    ) -> list[dict[str, Any]]:
        import numpy as np
        import pandas as pd

        model = await self._load_model_async(model_id)
        self._patch_simple_imputer(model)
        model_feature_names = list(getattr(model, "feature_names_in_", []))

        if model_feature_names:
            input_dict = self._build_structured_input(
                dict(features), model_feature_names, model
            )
            feature_df = pd.DataFrame(
                [{col: input_dict[col] for col in model_feature_names}],
                columns=model_feature_names,
            )
            try:
                factors = await asyncio.to_thread(
                    self._compute_shap_factors, model, feature_df, model_feature_names
                )
                return factors
            except Exception as exc:
                # P1-E 修复：SHAP 计算失败回退到简单特征重要性，必须记录日志便于排查
                logger.warning(
                    "SHAP factors computation failed, falling back to simple: %s", exc
                )
                fallback: list[dict[str, Any]] = []
                for f in model_feature_names[:5]:
                    val = input_dict.get(f, 0)
                    try:
                        val = float(val)
                    except (ValueError, TypeError):
                        val = 0.0
                    fallback.append(
                        {
                            "feature": f,
                            "importance": round(abs(val), 4),
                            "direction": "positive" if val >= 0 else "negative",
                        }
                    )
                return fallback
        else:
            feature_array = np.array(
                [[float(features.get(f, 0)) for f in self.feature_order]]
            )
            try:
                factors = await asyncio.to_thread(
                    self._compute_shap_factors_array,
                    model,
                    feature_array,
                    self.feature_order,
                )
                return factors
            except Exception as exc:
                # P1-E 修复：SHAP 计算失败回退到简单特征重要性，必须记录日志便于排查
                logger.warning(
                    "SHAP factors array computation failed, falling back to simple: %s",
                    exc,
                )
                fallback: list[dict[str, Any]] = []
                for f in self.feature_order[:5]:
                    val = float(features.get(f, 0))
                    fallback.append(
                        {
                            "feature": f,
                            "importance": round(abs(val), 4),
                            "direction": "positive" if val >= 0 else "negative",
                        }
                    )
                return fallback
