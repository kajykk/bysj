from __future__ import annotations

import asyncio
import csv
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.model_engine import model_engine
from app.core.risk_thresholds import (
    RISK_LEVEL_LABELS,
    RISK_LEVEL_THRESHOLDS as SHARED_RISK_LEVEL_THRESHOLDS,
    get_fusion_threshold,
    get_threshold_by_modality,
    should_fallback,
)
from app.core.states import BindingStatus
from app.models.assessment import StructuredAssessment
from app.models.intervention import InterventionPlan, InterventionTask, InterventionTemplate
from app.models.risk import RiskAssessment, WarningNotification, WarningSetting
from app.models.user import UserCounselorBinding
from app.services.intervention_service import InterventionRecommendation

logger = logging.getLogger(__name__)

_pdf_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pdf_gen")


class RiskService:
    # 启发式回退算法的权重配置，可通过数据库或配置文件调整
    HEURISTIC_WEIGHTS = {
        "stress_level": 12.0,
        "anxiety": 14.0,
        "financial_pressure": 10.0,
        "panic_attack": 12.0,
        "sleep_duration": 5.0,
        "social_support": 6.0,
    }

    # 风险等级阈值配置，统一来自 shared constants
    RISK_LEVEL_THRESHOLDS = SHARED_RISK_LEVEL_THRESHOLDS

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _calculate_heuristic_score(self, features: dict) -> float:
        """根据配置权重计算启发式风险分数"""
        stress = float(features.get("stress_level", 0) or 0)
        anxiety = float(features.get("anxiety", 0) or 0)
        sleep = float(features.get("sleep_duration", 7) or 7)
        financial = float(features.get("financial_pressure", 0) or 0)
        social = float(features.get("social_support", 3) or 3)
        panic = float(features.get("panic_attack", 0) or 0)

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
        is_student = identity_type == "student" or is_student_raw in (1, "1", True, "true", "True")
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
            severity=self._score_to_severity(float(normalized_payload.get("total_score", 0))),
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
            risk_factors = await model_engine.explain_prediction(model_features, "structured_logistic_regression_quick")
        except Exception as exc:
            logger.exception("risk.model.predict_failed user_id=%s, fallback_heuristic_enabled", user_id)
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
            stress = float(model_features.get("stress_level", 0) or 0)
            anxiety = float(model_features.get("anxiety", 0) or 0)
            sleep = float(model_features.get("sleep_duration", 7) or 7)
            financial = float(model_features.get("financial_pressure", 0) or 0)
            social = float(model_features.get("social_support", 3) or 3)
            risk_factors = [
                {"feature": "anxiety", "importance": round(abs(anxiety), 4), "direction": "positive"},
                {"feature": "stress_level", "importance": round(abs(stress), 4), "direction": "positive"},
                {"feature": "financial_pressure", "importance": round(abs(financial), 4), "direction": "positive"},
                {"feature": "sleep_duration", "importance": round(abs(7 - sleep), 4), "direction": "negative" if sleep >= 7 else "positive"},
                {"feature": "social_support", "importance": round(abs(5 - social), 4), "direction": "negative"},
            ]

        logger.info(
            "risk.assessment.submitted user_id=%s assessment_type=%s total_score=%s predicted_level=%s predicted_score=%s",
            user_id,
            normalized_payload.get("assessment_type", "comprehensive"),
            normalized_payload.get("total_score", 0),
            result.get("risk_level"),
            result.get("risk_score"),
        )

        risk = RiskAssessment(
            user_id=user_id,
            risk_score=result["risk_score"],
            risk_level=result["risk_level"],
            structured_score=result["risk_score"],
            models_used=[result["model_used"]],
            risk_factors=risk_factors,
            assessment_type="structured",
        )
        self.db.add(risk)
        await self.db.flush()

        warning = await self._check_warning_trigger(user_id=user_id, current_risk=risk)

        intervention_level: str | None = None
        intervention_actions: list[str] = []
        dominant_modality = "physiological" if result.get("model_used") == "physiological_risk_model" else "structured"
        if result["risk_level"] >= 2:
            intervention_level, intervention_actions = InterventionRecommendation.build_from_risk_level(
                result["risk_level"],
                dominant_modality=dominant_modality,
            )
            await self._auto_generate_intervention(user_id=user_id, risk_level=result["risk_level"])

        await self.db.commit()

        return {
            "assessment_id": assessment.id,
            "risk_score": result["risk_score"],
            "risk_level": result["risk_level"],
            "severity": self._level_to_severity(result["risk_level"]),
            "risk_factors": risk_factors,
            "warning_generated": warning is not None,
            "warning_id": warning.id if warning else None,
            "intervention_level": intervention_level,
            "intervention_actions": intervention_actions,
        }

    async def get_risk_report(self, user_id: int) -> dict:
        recent_stmt = (
            select(RiskAssessment)
            .where(RiskAssessment.user_id == user_id)
            .order_by(RiskAssessment.created_at.desc())
            .limit(20)
        )
        recent_rows = (await self.db.execute(recent_stmt)).scalars().all()
        if not recent_rows:
            return {
                "risk_level": 0,
                "risk_score": 0,
                "severity": "none",
                "trend": "stable",
                "main_factors": [],
                "advice": ["当前暂无评估记录，建议先完成一次测评。"],
                "assessed_at": None,
                "physiological_score": None,
                "modality_contributions": {"structured": None, "text": None, "physiological": None},
            }

        # 综合风险分：优先取 fusion，其次 structured，最后最新一条
        fusion_record = next((r for r in recent_rows if r.assessment_type == "fusion"), None)
        structured_record = next((r for r in recent_rows if r.assessment_type == "structured"), None)
        latest = recent_rows[0]
        primary = fusion_record or structured_record or latest

        # 趋势对比：取上一条同类型记录
        prev_same_type = next(
            (r for r in recent_rows if r.assessment_type == primary.assessment_type and r.id != primary.id),
            None,
        )
        previous_score = prev_same_type.risk_score if prev_same_type else primary.risk_score

        if primary.risk_score > previous_score + 5:
            trend = "up"
        elif primary.risk_score < previous_score - 5:
            trend = "down"
        else:
            trend = "stable"

        advice = self._build_advice(primary.risk_level)

        modality_contributions: dict[str, float | None] = {
            "structured": None,
            "text": None,
            "physiological": None,
        }
        physiological_score = None

        for record in recent_rows:
            if modality_contributions["structured"] is None and record.structured_score is not None:
                modality_contributions["structured"] = round(record.structured_score, 2)
            if modality_contributions["text"] is None and record.text_score is not None:
                modality_contributions["text"] = round(record.text_score, 2)
            if modality_contributions["physiological"] is None and record.physiological_score is not None:
                modality_contributions["physiological"] = round(record.physiological_score, 2)
                physiological_score = round(record.physiological_score, 2)

        if modality_contributions["structured"] is None and primary.risk_score is not None:
            modality_contributions["structured"] = round(primary.risk_score, 2)

        risk_factors, protective_factors, review_flags = self._classify_report_factors(recent_rows)
        aggregated_factors = risk_factors[:]
        for factor in protective_factors:
            if len(aggregated_factors) >= 8:
                break
            aggregated_factors.append(factor)

        return {
            "risk_level": primary.risk_level,
            "risk_score": round(primary.risk_score, 2),
            "severity": self._level_to_severity(primary.risk_level),
            "trend": trend,
            "main_factors": aggregated_factors,
            "risk_factors": risk_factors,
            "protective_factors": protective_factors,
            "review_flags": review_flags,
            "review_triggers": [flag["feature"] for flag in review_flags],
            "review_required": bool(review_flags),
            "crisis_override": any(flag.get("type") == "crisis" for flag in review_flags),
            "advice": advice,
            "assessed_at": primary.created_at.isoformat(),
            "physiological_score": physiological_score,
            "modality_contributions": modality_contributions,
        }

    @staticmethod
    def _classify_report_factors(records: list[RiskAssessment]) -> tuple[list[dict], list[dict], list[dict]]:
        risk_factors: list[dict] = []
        protective_factors: list[dict] = []
        review_flags: list[dict] = []
        seen: set[tuple[str, str]] = set()

        def normalize_factor(raw: object) -> dict | None:
            if isinstance(raw, str):
                return {"feature": raw, "importance": 0.5, "direction": "increase"}
            if not isinstance(raw, dict):
                return None
            feature = str(raw.get("feature") or "").strip()
            if not feature:
                return None
            importance = raw.get("importance", 0.5)
            try:
                importance_value = max(0.0, min(1.0, float(importance)))
            except (TypeError, ValueError):
                importance_value = 0.5
            return {
                "feature": feature,
                "importance": importance_value,
                "direction": str(raw.get("direction") or "increase"),
            }

        def friendly_review_flag(feature: str, importance: float) -> dict | None:
            if feature == "crisis_override":
                return {"feature": "危机信号触发", "importance": max(importance, 0.9), "type": "crisis"}
            if feature.startswith("model_disagreement_"):
                points = feature.replace("model_disagreement_", "").replace("_points", "")
                return {"feature": f"模型评分分歧较大（差异约 {points} 分）", "importance": max(importance, 0.8), "type": "disagreement"}
            if feature.startswith("modality_conflict"):
                return {"feature": "多模态结果存在冲突", "importance": max(importance, 0.75), "type": "disagreement"}
            return None

        for record in records:
            for raw_factor in record.risk_factors or []:
                factor = normalize_factor(raw_factor)
                if not factor:
                    continue
                review_flag = friendly_review_flag(factor["feature"], factor["importance"])
                if review_flag:
                    key = ("review", review_flag["feature"])
                    if key not in seen:
                        seen.add(key)
                        review_flags.append(review_flag)
                    continue

                direction = factor["direction"]
                if direction in {"negative", "decrease", "降低风险"}:
                    factor["direction"] = "decrease"
                    key = ("protective", factor["feature"])
                    if key not in seen:
                        seen.add(key)
                        protective_factors.append(factor)
                else:
                    factor["direction"] = "increase"
                    key = ("risk", factor["feature"])
                    if key not in seen:
                        seen.add(key)
                        risk_factors.append(factor)

        risk_factors.sort(key=lambda item: float(item.get("importance", 0)), reverse=True)
        protective_factors.sort(key=lambda item: float(item.get("importance", 0)), reverse=True)
        review_flags.sort(key=lambda item: float(item.get("importance", 0)), reverse=True)
        return risk_factors[:8], protective_factors[:8], review_flags[:8]

    async def get_risk_trend(self, user_id: int, days: int) -> dict:
        since = self._since_datetime(days)
        stmt = (
            select(RiskAssessment)
            .where(
                RiskAssessment.user_id == user_id,
                RiskAssessment.created_at >= since,
                RiskAssessment.risk_score > 0,
            )
            .order_by(RiskAssessment.created_at.asc())
        )
        rows = (await self.db.execute(stmt)).scalars().all()

        grouped: dict[str, list[RiskAssessment]] = {}
        for row in rows:
            date_key = row.created_at.date().isoformat()
            grouped.setdefault(date_key, []).append(row)

        priority_order = {"fusion": 3, "structured": 2, "physiological": 1, "text": 0}
        points: list[dict] = []
        physiological_scores: list[dict] = []

        for date_key in sorted(grouped.keys()):
            day_rows = grouped[date_key]
            primary = max(
                day_rows,
                key=lambda r: (
                    priority_order.get(r.assessment_type or "", -1),
                    r.created_at,
                    r.risk_score,
                ),
            )

            structured_score = next((round(r.structured_score, 2) for r in reversed(day_rows) if r.structured_score is not None), None)
            text_score = next((round(r.text_score, 2) for r in reversed(day_rows) if r.text_score is not None), None)
            physiological_score = next((round(r.physiological_score, 2) for r in reversed(day_rows) if r.physiological_score is not None), None)

            points.append({
                "date": date_key,
                "risk_score": round(primary.risk_score, 2),
                "risk_level": primary.risk_level,
                "assessment_type": primary.assessment_type,
                "structured_score": structured_score,
                "text_score": text_score,
                "physiological_score": physiological_score,
                "record_count": len(day_rows),
            })

            if physiological_score is not None:
                physiological_scores.append({"date": date_key, "score": physiological_score})

        direction = "stable"
        if len(points) >= 2:
            window = min(3, len(points))
            early_avg = sum(float(p["risk_score"]) for p in points[:window]) / window
            late_avg = sum(float(p["risk_score"]) for p in points[-window:]) / window
            delta = late_avg - early_avg
            if delta >= 5:
                direction = "up"
            elif delta <= -5:
                direction = "down"

        return {
            "days": max(0, int(days)),
            "direction": direction,
            "points": points,
            "physiological_scores": physiological_scores,
        }

    async def export_risk(self, user_id: int, days: int, fmt: str) -> dict:
        since = self._since_datetime(days)
        stmt = (
            select(RiskAssessment)
            .where(RiskAssessment.user_id == user_id, RiskAssessment.created_at >= since)
            .order_by(RiskAssessment.created_at.asc())
        )
        rows = (await self.db.execute(stmt)).scalars().all()

        raw_items = [
            {
                "id": row.id,
                "risk_score": round(row.risk_score, 2),
                "risk_level": row.risk_level,
                "severity": self._level_to_severity(row.risk_level),
                "assessment_type": row.assessment_type,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]

        normalized_fmt = (fmt or "csv").strip().lower()
        if normalized_fmt == "json":
            return {"format": "json", "items": raw_items}

        if normalized_fmt == "pdf":
            pdf_bytes = await self._generate_pdf_report_async(user_id, raw_items)
            return {
                "format": "pdf",
                "filename": f"risk_report_{user_id}_{days}d.pdf",
                "content": pdf_bytes,
            }

        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["id", "risk_score", "risk_level", "severity", "assessment_type", "created_at"],
        )
        writer.writeheader()
        writer.writerows(raw_items)

        return {
            "format": "csv",
            "filename": f"risk_export_{user_id}_{days}d.csv",
            "content": output.getvalue(),
        }

    def _generate_pdf_report(self, user_id: int, items: list[dict]) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm, leftMargin=15 * mm, rightMargin=15 * mm)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], fontSize=18, spaceAfter=12)
        heading_style = ParagraphStyle("ReportHeading", parent=styles["Heading2"], fontSize=14, spaceAfter=8)
        body_style = ParagraphStyle("ReportBody", parent=styles["Normal"], fontSize=10, leading=14)

        elements = []
        elements.append(Paragraph("Risk Assessment Report", title_style))
        elements.append(Paragraph(f"User ID: {user_id}  |  Report Period: {len(items)} records", body_style))
        elements.append(Spacer(1, 10 * mm))

        if items:
            table_data = [["ID", "Risk Score", "Level", "Severity", "Type", "Date"]]
            for item in items:
                table_data.append([
                    str(item["id"]),
                    str(item["risk_score"]),
                    str(item["risk_level"]),
                    item["severity"],
                    item["assessment_type"],
                    item["created_at"][:10],
                ])
            table = Table(table_data, colWidths=[30, 60, 40, 60, 80, 80])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#409EFF")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F7FA")]),
            ]))
            elements.append(table)
        else:
            elements.append(Paragraph("No risk assessment records found in this period.", body_style))

        elements.append(Spacer(1, 10 * mm))
        if items:
            latest = items[-1]
            elements.append(Paragraph("Latest Assessment Summary", heading_style))
            elements.append(Paragraph(f"Risk Score: {latest['risk_score']}  |  Level: {latest['risk_level']}  |  Severity: {latest['severity']}", body_style))
            advice = self._build_advice(latest["risk_level"])
            elements.append(Paragraph("Recommendations:", heading_style))
            for a in advice:
                elements.append(Paragraph(f"  - {a}", body_style))

        doc.build(elements)
        return buffer.getvalue()

    async def _generate_pdf_report_async(self, user_id: int, items: list[dict]) -> bytes:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_pdf_executor, self._generate_pdf_report, user_id, items)

    async def _check_warning_trigger(self, user_id: int, current_risk: RiskAssessment) -> WarningNotification | None:
        stmt: Select = (
            select(RiskAssessment)
            .where(RiskAssessment.user_id == user_id, RiskAssessment.id < current_risk.id)
            .order_by(RiskAssessment.created_at.desc())
            .limit(1)
        )
        previous = (await self.db.execute(stmt)).scalar_one_or_none()

        previous_level = previous.risk_level if previous else 0
        should_warn = current_risk.risk_level >= 2
        if current_risk.risk_level >= 2:
            if current_risk.risk_level > previous_level:
                reason = f"风险等级从{previous_level}级上升到{current_risk.risk_level}级，已达到中风险及以上"
            else:
                reason = f"当前风险等级为{current_risk.risk_level}级，已达到中风险及以上，需要咨询师关注"
        else:
            reason = ""

        logger.info(
            "risk.judgement user_id=%s current_level=%s previous_level=%s should_warn=%s reason=%s",
            user_id,
            current_risk.risk_level,
            previous_level,
            should_warn,
            reason or "-",
        )

        if not should_warn:
            return None

        setting_stmt = select(WarningSetting).where(WarningSetting.user_id == user_id)
        setting = (await self.db.execute(setting_stmt)).scalar_one_or_none()
        threshold = setting.threshold_level if setting else 2
        if current_risk.risk_level < threshold:
            return None

        duplicate_stmt = select(WarningNotification).where(
            WarningNotification.risk_assessment_id == current_risk.id,
        )
        existing_warning = (await self.db.execute(duplicate_stmt)).scalar_one_or_none()
        if existing_warning is not None:
            return existing_warning

        warning = WarningNotification(
            user_id=user_id,
            risk_assessment_id=current_risk.id,
            previous_level=previous_level,
            current_level=current_risk.risk_level,
            trigger_reason=reason,
        )
        self.db.add(warning)
        await self.db.flush()

        bind_stmt = (
            select(UserCounselorBinding)
            .where(
                UserCounselorBinding.user_id == user_id,
                UserCounselorBinding.status == BindingStatus.ACTIVE,
                UserCounselorBinding.counselor_id != user_id,
            )
            .order_by(UserCounselorBinding.bound_at.desc())
            .limit(1)
        )
        binding = (await self.db.execute(bind_stmt)).scalars().first()
        if binding:
            warning.counselor_id = binding.counselor_id

        return warning

    async def trigger_warning_for_risk(self, risk: RiskAssessment) -> WarningNotification | None:
        return await self._check_warning_trigger(user_id=risk.user_id, current_risk=risk)

    async def generate_intervention_for_risk(self, risk: RiskAssessment) -> None:
        """Generate or update an active intervention plan for medium-and-above risk assessments."""
        if risk.risk_level < 2:
            return
        await self._auto_generate_intervention(user_id=risk.user_id, risk_level=risk.risk_level)

    async def _auto_generate_intervention(self, user_id: int, risk_level: int) -> None:
        stmt = (
            select(InterventionPlan)
            .where(
                InterventionPlan.user_id == user_id,
                InterventionPlan.status == "active",
            )
            .order_by(InterventionPlan.id.desc())
            .limit(1)
        )
        existing_plan = (await self.db.execute(stmt)).scalars().first()

        if existing_plan:
            if risk_level > existing_plan.risk_level:
                # M17 修复：先创建新计划，确认成功后再取消旧计划，避免无模板时用户失去所有干预
                new_plan = await self._create_plan_from_template(user_id, risk_level)
                if new_plan is not None:
                    existing_plan.status = "cancelled"
            return

        await self._create_plan_from_template(user_id, risk_level)

    async def _create_plan_from_template(self, user_id: int, risk_level: int) -> InterventionPlan | None:
        stmt = (
            select(InterventionTemplate)
            .where(InterventionTemplate.status == "active")
            .order_by(InterventionTemplate.id)
        )
        templates = (await self.db.execute(stmt)).scalars().all()

        template = None
        for candidate in templates:
            levels = candidate.applicable_levels or []
            if risk_level in levels:
                template = candidate
                break

        if template is None:
            template = templates[0] if templates else None
            if template is None:
                return

        normalized_tasks = self._validate_and_normalize_template_tasks(template.task_list, template.template_name)

        bind_stmt = (
            select(UserCounselorBinding)
            .where(
                UserCounselorBinding.user_id == user_id,
                UserCounselorBinding.status == BindingStatus.ACTIVE,
            )
            .order_by(UserCounselorBinding.bound_at.desc())
            .limit(1)
        )
        binding = (await self.db.execute(bind_stmt)).scalars().first()

        plan = InterventionPlan(
            user_id=user_id,
            counselor_id=binding.counselor_id if binding else None,
            plan_name=template.template_name,
            risk_level=risk_level,
            status="active",
            start_date=date.today(),
            end_date=date.today() + timedelta(weeks=template.estimated_weeks or 4),
        )
        self.db.add(plan)
        await self.db.flush()

        for i, task_def in enumerate(normalized_tasks):
            task = InterventionTask(
                plan_id=plan.id,
                task_name=task_def["task_name"],
                task_type=task_def["task_type"],
                description=task_def.get("description", ""),
                schedule=task_def.get("schedule", "daily"),
                duration_minutes=task_def.get("duration_minutes", 15),
                sort_order=i,
            )
            self.db.add(task)

        return plan

    @staticmethod
    def _validate_and_normalize_template_tasks(task_list: object, template_name: str) -> list[dict]:
        if not isinstance(task_list, list):
            raise ValueError(f"干预模板 {template_name} 的任务列表格式错误")
        if not task_list:
            raise ValueError(f"干预模板 {template_name} 的任务列表不能为空")

        normalized: list[dict] = []
        for idx, task_def in enumerate(task_list, start=1):
            if not isinstance(task_def, dict):
                raise ValueError(f"干预模板 {template_name} 的第 {idx} 个任务格式错误")

            task_name = str(task_def.get("task_name", "")).strip()
            task_type = str(task_def.get("task_type", "")).strip()
            if not task_name or not task_type:
                raise ValueError(f"干预模板 {template_name} 的第 {idx} 个任务缺少必要字段")

            duration_raw = task_def.get("duration_minutes", 15)
            try:
                duration_minutes = int(duration_raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"干预模板 {template_name} 的第 {idx} 个任务时长非法") from exc
            if duration_minutes <= 0:
                raise ValueError(f"干预模板 {template_name} 的第 {idx} 个任务时长必须大于0")

            normalized.append(
                {
                    "task_name": task_name,
                    "task_type": task_type,
                    "description": str(task_def.get("description", "") or "").strip(),
                    "schedule": str(task_def.get("schedule", "daily") or "daily").strip() or "daily",
                    "duration_minutes": duration_minutes,
                }
            )

        return normalized

    @staticmethod
    def _since_datetime(days: int) -> datetime:
        days_safe = max(0, int(days))
        return datetime.now(timezone.utc) - timedelta(days=days_safe)

    @staticmethod
    def _score_to_severity(score: float) -> str:
        if score <= 4:
            return "none"
        if score <= 9:
            return "mild"
        if score <= 14:
            return "moderate"
        return "severe"

    @staticmethod
    def _level_to_severity(level: int) -> str:
        return RISK_LEVEL_LABELS.get(level, "unknown")

    @staticmethod
    def _build_advice(level: int) -> list[str]:
        if level <= 1:
            return ["保持规律作息", "持续记录情绪变化"]
        if level == 2:
            return ["建议每周进行2-3次放松训练", "适当增加社交与运动活动"]
        if level == 3:
            return ["建议尽快预约咨询师", "启动中风险干预计划并每日打卡"]
        return ["请立即联系咨询师或紧急联系人", "优先执行高风险干预与随访"]
