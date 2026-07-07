from __future__ import annotations

import asyncio
import csv
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

# C-Svc-4 修复：CSV 公式注入防护。
# Excel/LibreOffice/WPS 会将以 = + - @ \t \r 开头的单元格内容解释为公式，
# 若用户可控字段（assessment_type、severity 等）被注入 =cmd|'/c calc'!A1 等
# 公式，打开 CSV 时可能触发命令执行或数据外泄。统一对字符串字段做转义：
# 以危险字符开头的单元格前置一个单引号 '，Excel 会将其作为文本显示。
_CSV_FORMULA_PREFIXES: tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r", "\n")


def _sanitize_csv_cell(value: object) -> object:
    """对 CSV 单元格内容做公式注入防护。

    - 仅对 str 类型生效；int/float/None 等原样返回
    - 以 = + - @ \\t \\r \\n 开头的字符串前置单引号 '
    """
    if not isinstance(value, str) or not value:
        return value
    if value.startswith(_CSV_FORMULA_PREFIXES):
        return "'" + value
    return value


from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import event_bus
from app.core.model_engine import model_engine
from app.core.risk_thresholds import (
    RISK_LEVEL_LABELS,
    get_threshold_by_modality,
)
from app.core.risk_thresholds import (
    RISK_LEVEL_THRESHOLDS as SHARED_RISK_LEVEL_THRESHOLDS,
)
from app.core.states import BindingStatus
from app.models.assessment import StructuredAssessment
from app.models.intervention import (
    InterventionPlan,
    InterventionTask,
    InterventionTemplate,
)
from app.models.risk import RiskAssessment, WarningNotification, WarningSetting
from app.models.user import UserCounselorBinding
from app.services.intervention_service import InterventionRecommendation

logger = logging.getLogger(__name__)

_pdf_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pdf_gen")


def shutdown_pdf_executor() -> None:
    """H-Svc-9 修复：关闭 PDF 生成线程池，供 FastAPI lifespan shutdown 阶段调用。"""
    _pdf_executor.shutdown(wait=True)


# PERF-P1-004: warning + intervention fire-and-forget 任务集合，防止被 GC 回收
_warning_intervention_tasks: set[asyncio.Task] = set()


def _log_warning_intervention_exception(task: asyncio.Task) -> None:
    """fire-and-forget 任务完成回调：记录未捕获异常。"""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(
            "warning/intervention fire-and-forget task failed: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=exc,
        )


async def _trigger_warning_and_intervention(
    user_id: int,
    risk_id: int,
    risk_level: int,
) -> None:
    """PERF-P1-004: 在独立 session 中触发告警 + 干预计划 (fire-and-forget).

    - 使用独立 AsyncSessionLocal 避免共享请求事务边界
    - 通过 risk_id 重新查询 RiskAssessment (已 commit, 可见)
    - 调用 trigger_warning_for_risk + generate_intervention_for_risk
    - 自动 commit
    """
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        risk = (
            await db.execute(select(RiskAssessment).where(RiskAssessment.id == risk_id))
        ).scalar_one_or_none()
        if risk is None:
            logger.warning(
                "warning/intervention: RiskAssessment id=%s not found (user_id=%s)",
                risk_id,
                user_id,
            )
            return
        service = RiskService(db)
        await service.trigger_warning_for_risk(risk)
        await service.generate_intervention_for_risk(risk)
        await db.commit()
        logger.info(
            "warning/intervention completed async user_id=%s risk_id=%s risk_level=%s",
            user_id,
            risk_id,
            risk_level,
        )


def _schedule_warning_and_intervention(
    user_id: int,
    risk_id: int,
    risk_level: int,
) -> None:
    """PERF-P1-004: fire-and-forget 包装 — 调度异步任务, 不阻塞调用方.

    - 使用 asyncio.ensure_future 调度任务
    - 任务引用存入 _warning_intervention_tasks 防止 GC
    - 注册 done callback 记录异常
    - 调度失败不传播异常 (仅 log)
    """
    try:
        task = asyncio.ensure_future(
            _trigger_warning_and_intervention(user_id, risk_id, risk_level)
        )
        _warning_intervention_tasks.add(task)
        task.add_done_callback(_warning_intervention_tasks.discard)
        task.add_done_callback(_log_warning_intervention_exception)
        # R-005 修复: 注册可观测性指标 (scheduled/succeeded/failed/cancelled + duration)
        from app.core.fire_forget_metrics import register_task

        register_task(task, "warning_intervention")
    except Exception as exc:
        logger.error("Failed to schedule warning/intervention: %s", exc)


class RiskService:
    # M-Svc-12 修复：启发式回退算法的权重配置。原注释称"可通过数据库或配置文件调整"，
    # 但实际实现为类常量，并未从 DB 或配置文件加载。修正注释使其与实现一致。
    # 如需动态调整，需扩展为从 settings 或 DB 读取。
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

        # PERF-P1-004: warning + intervention 改为 fire-and-forget, 不阻塞响应
        # 原实现: await self._check_warning_trigger() + await self._auto_generate_intervention()
        #   共 7-10 次 DB 查询 (previous risk / warning setting / duplicate check / insert warning /
        #   binding lookup / plan FOR UPDATE / template lookup / binding lookup / insert plan+tasks)
        # 改造后: 调度异步任务在独立 session 中执行, 响应路径仅保留 flush + commit
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
                "modality_contributions": {
                    "structured": None,
                    "text": None,
                    "physiological": None,
                },
            }

        # 综合风险分：优先取 fusion，其次 structured，最后最新一条
        fusion_record = next(
            (r for r in recent_rows if r.assessment_type == "fusion"), None
        )
        structured_record = next(
            (r for r in recent_rows if r.assessment_type == "structured"), None
        )
        latest = recent_rows[0]
        primary = fusion_record or structured_record or latest

        # 趋势对比：取上一条同类型记录
        prev_same_type = next(
            (
                r
                for r in recent_rows
                if r.assessment_type == primary.assessment_type and r.id != primary.id
            ),
            None,
        )
        previous_score = (
            prev_same_type.risk_score if prev_same_type else primary.risk_score
        )

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
            if (
                modality_contributions["structured"] is None
                and record.structured_score is not None
            ):
                modality_contributions["structured"] = round(record.structured_score, 2)
            if modality_contributions["text"] is None and record.text_score is not None:
                modality_contributions["text"] = round(record.text_score, 2)
            if (
                modality_contributions["physiological"] is None
                and record.physiological_score is not None
            ):
                modality_contributions["physiological"] = round(
                    record.physiological_score, 2
                )
                physiological_score = round(record.physiological_score, 2)

        if (
            modality_contributions["structured"] is None
            and primary.risk_score is not None
        ):
            modality_contributions["structured"] = round(primary.risk_score, 2)

        risk_factors, protective_factors, review_flags = self._classify_report_factors(
            recent_rows
        )
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
            "crisis_override": any(
                flag.get("type") == "crisis" for flag in review_flags
            ),
            "advice": advice,
            "assessed_at": primary.created_at.isoformat(),
            "physiological_score": physiological_score,
            "modality_contributions": modality_contributions,
        }

    @staticmethod
    def _classify_report_factors(
        records: list[RiskAssessment],
    ) -> tuple[list[dict], list[dict], list[dict]]:
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
                return {
                    "feature": "危机信号触发",
                    "importance": max(importance, 0.9),
                    "type": "crisis",
                }
            if feature.startswith("model_disagreement_"):
                points = feature.replace("model_disagreement_", "").replace(
                    "_points", ""
                )
                return {
                    "feature": f"模型评分分歧较大（差异约 {points} 分）",
                    "importance": max(importance, 0.8),
                    "type": "disagreement",
                }
            if feature.startswith("modality_conflict"):
                return {
                    "feature": "多模态结果存在冲突",
                    "importance": max(importance, 0.75),
                    "type": "disagreement",
                }
            return None

        for record in records:
            for raw_factor in record.risk_factors or []:
                factor = normalize_factor(raw_factor)
                if not factor:
                    continue
                review_flag = friendly_review_flag(
                    factor["feature"], factor["importance"]
                )
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

        risk_factors.sort(
            key=lambda item: float(item.get("importance", 0)), reverse=True
        )
        protective_factors.sort(
            key=lambda item: float(item.get("importance", 0)), reverse=True
        )
        review_flags.sort(
            key=lambda item: float(item.get("importance", 0)), reverse=True
        )
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

            structured_score = next(
                (
                    round(r.structured_score, 2)
                    for r in reversed(day_rows)
                    if r.structured_score is not None
                ),
                None,
            )
            text_score = next(
                (
                    round(r.text_score, 2)
                    for r in reversed(day_rows)
                    if r.text_score is not None
                ),
                None,
            )
            physiological_score = next(
                (
                    round(r.physiological_score, 2)
                    for r in reversed(day_rows)
                    if r.physiological_score is not None
                ),
                None,
            )

            points.append(
                {
                    "date": date_key,
                    "risk_score": round(primary.risk_score, 2),
                    "risk_level": primary.risk_level,
                    "assessment_type": primary.assessment_type,
                    "structured_score": structured_score,
                    "text_score": text_score,
                    "physiological_score": physiological_score,
                    "record_count": len(day_rows),
                }
            )

            if physiological_score is not None:
                physiological_scores.append(
                    {"date": date_key, "score": physiological_score}
                )

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
            .where(
                RiskAssessment.user_id == user_id, RiskAssessment.created_at >= since
            )
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

        # C-Svc-4 修复：对 raw_items 中所有 str 字段做 CSV 公式注入防护
        sanitized_items = [
            {k: _sanitize_csv_cell(v) for k, v in item.items()} for item in raw_items
        ]

        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "id",
                "risk_score",
                "risk_level",
                "severity",
                "assessment_type",
                "created_at",
            ],
        )
        writer.writeheader()
        writer.writerows(sanitized_items)

        return {
            "format": "csv",
            "filename": f"risk_export_{user_id}_{days}d.csv",
            "content": output.getvalue(),
        }

    def _generate_pdf_report(self, user_id: int, items: list[dict]) -> bytes:
        # C-Svc-5 修复：使用 with 上下文管理 BytesIO，确保异常或正常返回时都能释放底层缓冲。
        # 原实现 buffer = io.BytesIO() 后未 close()，在 PDF 生成异常时（reportlab 抛错）
        # 会导致内存中 BytesIO 实例无法立即回收，大量并发导出可能加剧内存压力。
        with io.BytesIO() as buffer:
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                topMargin=20 * mm,
                bottomMargin=20 * mm,
                leftMargin=15 * mm,
                rightMargin=15 * mm,
            )
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                "ReportTitle", parent=styles["Title"], fontSize=18, spaceAfter=12
            )
            heading_style = ParagraphStyle(
                "ReportHeading", parent=styles["Heading2"], fontSize=14, spaceAfter=8
            )
            body_style = ParagraphStyle(
                "ReportBody", parent=styles["Normal"], fontSize=10, leading=14
            )

            elements = []
            elements.append(Paragraph("Risk Assessment Report", title_style))
            elements.append(
                Paragraph(
                    f"User ID: {user_id}  |  Report Period: {len(items)} records",
                    body_style,
                )
            )
            elements.append(Spacer(1, 10 * mm))

            if items:
                table_data = [["ID", "Risk Score", "Level", "Severity", "Type", "Date"]]
                for item in items:
                    table_data.append(
                        [
                            str(item["id"]),
                            str(item["risk_score"]),
                            str(item["risk_level"]),
                            item["severity"],
                            item["assessment_type"],
                            item["created_at"][:10],
                        ]
                    )
                table = Table(table_data, colWidths=[30, 60, 40, 60, 80, 80])
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#409EFF")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                            ("FONTSIZE", (0, 0), (-1, -1), 9),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                            (
                                "ROWBACKGROUNDS",
                                (0, 1),
                                (-1, -1),
                                [colors.white, colors.HexColor("#F5F7FA")],
                            ),
                        ]
                    )
                )
                elements.append(table)
            else:
                elements.append(
                    Paragraph(
                        "No risk assessment records found in this period.", body_style
                    )
                )

            elements.append(Spacer(1, 10 * mm))
            if items:
                latest = items[-1]
                elements.append(Paragraph("Latest Assessment Summary", heading_style))
                elements.append(
                    Paragraph(
                        f"Risk Score: {latest['risk_score']}  |  Level: {latest['risk_level']}  |  Severity: {latest['severity']}",
                        body_style,
                    )
                )
                advice = self._build_advice(latest["risk_level"])
                elements.append(Paragraph("Recommendations:", heading_style))
                for a in advice:
                    elements.append(Paragraph(f"  - {a}", body_style))

            doc.build(elements)
            return buffer.getvalue()

    async def _generate_pdf_report_async(
        self, user_id: int, items: list[dict]
    ) -> bytes:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            _pdf_executor, self._generate_pdf_report, user_id, items
        )

    async def _check_warning_trigger(
        self, user_id: int, current_risk: RiskAssessment
    ) -> WarningNotification | None:
        stmt: Select = (
            select(RiskAssessment)
            .where(
                RiskAssessment.user_id == user_id, RiskAssessment.id < current_risk.id
            )
            .order_by(RiskAssessment.created_at.desc())
            .limit(1)
        )
        previous = (await self.db.execute(stmt)).scalar_one_or_none()

        # H-Svc-7 修复：previous.risk_level 可能为 None，需额外检查避免后续比较抛 TypeError
        previous_level = (
            previous.risk_level if previous and previous.risk_level is not None else 0
        )
        should_warn = current_risk.risk_level >= 2
        # L-08 修复：复用 should_warn 变量，避免重复计算 current_risk.risk_level >= 2
        if should_warn:
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
        threshold = (
            setting.threshold_level
            if setting and setting.threshold_level is not None
            else 2
        )
        if current_risk.risk_level < threshold:
            return None

        duplicate_stmt = select(WarningNotification).where(
            WarningNotification.risk_assessment_id == current_risk.id,
        )
        existing_warning = (await self.db.execute(duplicate_stmt)).scalar_one_or_none()
        if existing_warning is not None:
            return existing_warning

        from sqlalchemy.exc import IntegrityError as SAIntegrityError

        warning = WarningNotification(
            user_id=user_id,
            risk_assessment_id=current_risk.id,
            previous_level=previous_level,
            current_level=current_risk.risk_level,
            trigger_reason=reason,
        )
        try:
            # C-2 修复：使用 savepoint 隔离 warning 插入失败，避免回滚已成功的 risk assessment
            async with self.db.begin_nested():
                self.db.add(warning)
                await self.db.flush()
        except SAIntegrityError:
            warning = (await self.db.execute(duplicate_stmt)).scalar_one_or_none()
            if warning is not None:
                return warning
            raise

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

        # R-C: 发布 warning.created 事件到 EventBus, 实时更新 Prometheus 指标.
        # 仅在新建 WarningNotification 成功 (flush 通过) 后发布;
        # 重复 warning (IntegrityError 路径) 提前 return, 不发布事件.
        # 事件发布非阻塞 (put_nowait), 不影响业务主流程.
        try:
            await event_bus.publish(
                "warning.created",
                {
                    "warning_id": warning.id,
                    "user_id": warning.user_id,
                    "risk_assessment_id": warning.risk_assessment_id,
                    "previous_level": warning.previous_level,
                    "current_level": warning.current_level,
                    "trigger_reason": warning.trigger_reason,
                    "counselor_id": warning.counselor_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception:
            # EventBus 发布失败不应影响业务主流程
            logger.warning("Failed to publish warning.created event", exc_info=True)

        return warning

    async def trigger_warning_for_risk(
        self, risk: RiskAssessment
    ) -> WarningNotification | None:
        return await self._check_warning_trigger(
            user_id=risk.user_id, current_risk=risk
        )

    async def generate_intervention_for_risk(self, risk: RiskAssessment) -> None:
        """Generate or update an active intervention plan for medium-and-above risk assessments."""
        if risk.risk_level < 2:
            return
        await self._auto_generate_intervention(
            user_id=risk.user_id, risk_level=risk.risk_level
        )

    async def _auto_generate_intervention(
        self, user_id: int, risk_level: int
    ) -> InterventionPlan | None:
        # ISS-014 修复：添加 with_for_update() 行级锁，防止并发产生重复干预计划
        stmt = (
            select(InterventionPlan)
            .where(
                InterventionPlan.user_id == user_id,
                InterventionPlan.status == "active",
            )
            .order_by(InterventionPlan.id.desc())
            .limit(1)
            .with_for_update()
        )
        existing_plan = (await self.db.execute(stmt)).scalars().first()

        if existing_plan:
            if risk_level > existing_plan.risk_level:
                # M17 修复：先创建新计划，确认成功后再取消旧计划，避免无模板时用户失去所有干预
                new_plan = await self._create_plan_from_template(user_id, risk_level)
                if new_plan is not None:
                    existing_plan.status = "cancelled"
                    return new_plan
            return existing_plan

        return await self._create_plan_from_template(user_id, risk_level)

    async def _create_plan_from_template(
        self, user_id: int, risk_level: int
    ) -> InterventionPlan | None:
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
                # H-Svc-8 修复：无活跃模板时记录告警，避免高风险用户无干预计划被静默掩盖
                logger.warning(
                    "No active intervention template found for risk level %s",
                    risk_level,
                )
                return None

        normalized_tasks = self._validate_and_normalize_template_tasks(
            template.task_list, template.template_name
        )

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
    def _validate_and_normalize_template_tasks(
        task_list: object, template_name: str
    ) -> list[dict]:
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
                raise ValueError(
                    f"干预模板 {template_name} 的第 {idx} 个任务缺少必要字段"
                )

            duration_raw = task_def.get("duration_minutes", 15)
            try:
                duration_minutes = int(duration_raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"干预模板 {template_name} 的第 {idx} 个任务时长非法"
                ) from exc
            if duration_minutes <= 0:
                raise ValueError(
                    f"干预模板 {template_name} 的第 {idx} 个任务时长必须大于0"
                )

            normalized.append(
                {
                    "task_name": task_name,
                    "task_type": task_type,
                    "description": str(task_def.get("description", "") or "").strip(),
                    "schedule": str(
                        task_def.get("schedule", "daily") or "daily"
                    ).strip()
                    or "daily",
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
