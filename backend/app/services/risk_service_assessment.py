from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import update

from app.core.model_engine import model_engine
from app.core.risk_thresholds import get_threshold_by_modality
from app.models.assessment import StructuredAssessment
from app.models.risk import RiskAssessment
from app.services.intervention_service import InterventionRecommendation

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class AssessmentMixin:
    """风险评估相关方法 Mixin。

    包含启发式打分、风险等级映射、结构化评估主流程。
    依赖主类 RiskService 提供 `self.db`、`HEURISTIC_WEIGHTS` 类常量
    以及 ReportMixin 提供的 `_level_to_severity` staticmethod。
    """

    def _calculate_heuristic_score(self, features: dict) -> float:
        """根据配置权重计算启发式风险分数"""

        # C-01 修复：使用显式 None 检查替代 `or`，避免合法的 0 值被替换为默认值
        def _get_num(key: str, default: float) -> float:
            val = features.get(key)
            return float(val) if val is not None else default

        stress = _get_num("stress_level", 0)
        anxiety = _get_num("anxiety", 0)
        sleep = _get_num("sleep_duration", 7)
        financial = _get_num("financial_pressure", 0)
        social = _get_num("social_support", 3)
        panic = _get_num("panic_attack", 0)

        weights = self.HEURISTIC_WEIGHTS
        score = (
            stress * weights["stress_level"]
            + anxiety * weights["anxiety"]
            + financial * weights["financial_pressure"]
            + panic * weights["panic_attack"]
            + (7 - sleep) * weights["sleep_duration"]
            + (5 - social) * weights["social_support"]
        )
        return max(0.0, min(100.0, score))

    def _score_to_level(self, score: float, modality: str = "structured") -> int:
        """根据配置阈值将分数转换为风险等级"""
        thresholds = get_threshold_by_modality(modality)
        if score >= thresholds["critical"]:
            return 4
        if score >= thresholds["high"]:
            return 3
        if score >= thresholds["moderate"]:
            return 2
        if score >= thresholds["mild"]:
            return 1
        return 0

    async def assess_structured(self, user_id: int, payload: dict) -> dict:
        normalized_payload = dict(payload)

        identity_type = str(normalized_payload.get("identity_type", "")).strip().lower()
        is_student_raw = normalized_payload.get("is_student")
        is_student = identity_type == "student" or is_student_raw in (
            1,
            "1",
            True,
            "true",
            "True",
        )
        normalized_payload["is_student"] = 1 if is_student else 0

        if not is_student:
            normalized_payload["study_year"] = 0
            normalized_payload["academic_pressure"] = 0
        elif normalized_payload.get("study_year") is None:
            normalized_payload["study_year"] = 0
        normalized_payload.setdefault("assessment_type", "comprehensive")

        assessment = StructuredAssessment(
            user_id=user_id,
            assessment_type=normalized_payload.get("assessment_type", "comprehensive"),
            score=float(normalized_payload.get("total_score", 0)),
            severity=self._score_to_severity(
                float(normalized_payload.get("total_score", 0))
            ),
            data_payload=normalized_payload,
        )
        self.db.add(assessment)
        await self.db.flush()

        model_features = {
            k: normalized_payload.get(k, 0)
            for k in [
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
        }

        try:
            result = await model_engine.predict_structured(model_features)
            risk_factors = await model_engine.explain_prediction(
                model_features, "structured_logistic_regression_quick"
            )
        except Exception as exc:
            logger.exception(
                "risk.model.predict_failed user_id=%s, fallback_heuristic_enabled",
                user_id,
            )
            risk_score = self._calculate_heuristic_score(model_features)
            risk_level = self._score_to_level(risk_score)
            result = {
                "prediction": 1 if risk_level >= 2 else 0,
                "probability": round(risk_score / 100, 4),
                "risk_score": round(risk_score, 2),
                "risk_level": risk_level,
                "model_used": "heuristic_fallback",
                "error": str(exc),
            }
            # M-Svc-18 修复：使用显式 None 检查替代 `or`，避免合法的 0 值
            # （如 0 小时睡眠）被替换为默认值，错误降低风险分
            # （与 _calculate_heuristic_score 的 C-01 修复保持一致）
            stress_val = model_features.get("stress_level")
            stress = float(stress_val) if stress_val is not None else 0.0
            anxiety_val = model_features.get("anxiety")
            anxiety = float(anxiety_val) if anxiety_val is not None else 0.0
            sleep_val = model_features.get("sleep_duration")
            sleep = float(sleep_val) if sleep_val is not None else 7.0
            financial_val = model_features.get("financial_pressure")
            financial = float(financial_val) if financial_val is not None else 0.0
            social_val = model_features.get("social_support")
            social = float(social_val) if social_val is not None else 3.0
            risk_factors = [
                {
                    "feature": "anxiety",
                    "importance": round(abs(anxiety), 4),
                    "direction": "positive",
                },
                {
                    "feature": "stress_level",
                    "importance": round(abs(stress), 4),
                    "direction": "positive",
                },
                {
                    "feature": "financial_pressure",
                    "importance": round(abs(financial), 4),
                    "direction": "positive",
                },
                {
                    "feature": "sleep_duration",
                    "importance": round(abs(7 - sleep), 4),
                    "direction": "negative" if sleep >= 7 else "positive",
                },
                {
                    "feature": "social_support",
                    "importance": round(abs(5 - social), 4),
                    "direction": "negative",
                },
            ]

        logger.info(
            "risk.assessment.submitted user_id=%s assessment_type=%s total_score=%s predicted_level=%s predicted_score=%s",
            user_id,
            normalized_payload.get("assessment_type", "comprehensive"),
            normalized_payload.get("total_score", 0),
            result.get("risk_level"),
            result.get("risk_score"),
        )

        # PERF-P2-002: 清除该用户旧风险评估的 is_latest 标志
        await self.db.execute(
            update(RiskAssessment)
            .where(
                RiskAssessment.user_id == user_id,
                RiskAssessment.is_latest.is_(True),
            )
            .values(is_latest=False)
        )

        risk = RiskAssessment(
            user_id=user_id,
            risk_score=result["risk_score"],
            risk_level=result["risk_level"],
            structured_score=result["risk_score"],
            models_used=[result["model_used"]],
            risk_factors=risk_factors,
            assessment_type="structured",
            is_latest=True,
        )
        self.db.add(risk)
        await self.db.flush()

        # PERF-P1-004: warning + intervention 改为 fire-and-forget, 不阻塞响应
        # 原实现: await self._check_warning_trigger() + await self._auto_generate_intervention()
        #   共 7-10 次 DB 查询 (previous risk / warning setting / duplicate check / insert warning /
        #   binding lookup / plan FOR UPDATE / template lookup / binding lookup / insert plan+tasks)
        # 改造后: 调度异步任务在独立 session 中执行, 响应路径仅保留 flush + commit
        # 延迟导入避免与主模块 risk_service.py 形成循环导入
        from app.services.risk_service import _schedule_warning_and_intervention

        _schedule_warning_and_intervention(user_id, risk.id, result["risk_level"])

        intervention_level: str | None = None
        intervention_actions: list[str] = []
        dominant_modality = (
            "physiological"
            if result.get("model_used") == "physiological_risk_model"
            else "structured"
        )
        if result["risk_level"] >= 2:
            intervention_level, intervention_actions = (
                InterventionRecommendation.build_from_risk_level(
                    result["risk_level"],
                    dominant_modality=dominant_modality,
                )
            )
            # H-Svc-8 修复说明: 原 plan is None 清空逻辑已移至 fire-and-forget 任务
            # intervention_actions 为静态推荐 (build_from_risk_level), 非依赖 DB 的实际计划
            # 实际 plan 创建在异步任务中完成, 无模板时仅 log warning

        await self.db.commit()

        return {
            "assessment_id": assessment.id,
            "risk_score": result["risk_score"],
            "risk_level": result["risk_level"],
            "severity": self._level_to_severity(result["risk_level"]),
            "risk_factors": risk_factors,
            # PERF-P1-004: warning 异步处理, 同步返回 None (pending)
            "warning_generated": None,
            "warning_id": None,
            "intervention_level": intervention_level,
            "intervention_actions": intervention_actions,
        }

    @staticmethod
    def _score_to_severity(score: float) -> str:
        # L-Svc-5 说明：本函数与 _score_to_level 阈值不同，二者工作在不同量纲，属设计如此：
        # - _score_to_severity：将 StructuredAssessment.total_score（问卷原始分，PHQ-9 量纲 ~0-27）
        #   映射为测评严重度 none/mild/moderate/severe，阈值 4/9/14 为 PHQ-9 临床切分；
        # - _score_to_level：将模型 risk_score（0-100）映射为风险等级 0-4，阈值来自
        #   risk_thresholds 共享配置。二者量纲不同故阈值不一致，非缺陷。
        # 审计 L-Svc-5 建议统一阈值，但强行统一会破坏 test_risk_service.py::test_score_to_severity
        # 并使测评严重度失真（绝大多数原始分会落入 none）。若未来 total_score 改为 0-100 归一化可再统一。
        if score <= 4:
            return "none"
        if score <= 9:
            return "mild"
        if score <= 14:
            return "moderate"
        return "severe"
