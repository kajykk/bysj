from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select

from app.core.risk_thresholds import RISK_LEVEL_LABELS
from app.models.risk import RiskAssessment


class ReportMixin:
    """风险报告与趋势相关方法 Mixin。

    包含风险评估报告生成、风险因子分类、风险趋势 SQL window function 查询，
    以及多个 staticmethod 辅助函数 (`_since_datetime`、`_level_to_severity`、
    `_build_advice`)。这些 staticmethod 也被 ExportMixin 和 AssessmentMixin 通过
    self 访问 (依赖 Python MRO 在最终 RiskService 类中可用)。

    依赖主类 RiskService 提供 `self.db`。
    """

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
        """PERF-P2-004: 使用 SQL window function + 条件聚合替代 Python 内循环聚合.

        改造前: 拉取所有 rows → Python dict 按 date 分组 → Python max/priority 找 primary
                → Python next+reversed 找各模态 latest scores → Python len() 计数
        改造后: SQL ROW_NUMBER() OVER (PARTITION BY date) 计算每天 primary + latest scores,
                COUNT(*) OVER (PARTITION BY date) 获取每天记录数,
                外层 GROUP BY date + MAX(CASE WHEN rn=1) 聚合为每天 1 行,
                Python 仅处理聚合结果 (传输行数从 N 降至 ~days).
        """
        since = self._since_datetime(days)
        date_expr = func.date(RiskAssessment.created_at)

        # priority 表达式: fusion=3 > structured=2 > physiological=1 > text=0
        priority_expr = case(
            (RiskAssessment.assessment_type == "fusion", 3),
            (RiskAssessment.assessment_type == "structured", 2),
            (RiskAssessment.assessment_type == "physiological", 1),
            (RiskAssessment.assessment_type == "text", 0),
            else_=-1,
        )

        # NULL 排序辅助: 非 NULL=0 (排前), NULL=1 (排后), 配合 ROW_NUMBER 找 latest non-NULL
        def _nulls_last(column):
            return case((column.isnot(None), 0), else_=1)

        # 子查询: 每天所有记录 + 4 个 ROW_NUMBER 排名 + COUNT 窗口
        subq = (
            select(
                date_expr.label("date_key"),
                RiskAssessment.risk_score,
                RiskAssessment.risk_level,
                RiskAssessment.assessment_type,
                RiskAssessment.structured_score,
                RiskAssessment.text_score,
                RiskAssessment.physiological_score,
                func.row_number()
                .over(
                    partition_by=date_expr,
                    order_by=[
                        priority_expr.desc(),
                        RiskAssessment.created_at.desc(),
                        RiskAssessment.risk_score.desc(),
                    ],
                )
                .label("primary_rn"),
                func.row_number()
                .over(
                    partition_by=date_expr,
                    order_by=[
                        _nulls_last(RiskAssessment.structured_score),
                        RiskAssessment.created_at.desc(),
                    ],
                )
                .label("structured_rn"),
                func.row_number()
                .over(
                    partition_by=date_expr,
                    order_by=[
                        _nulls_last(RiskAssessment.text_score),
                        RiskAssessment.created_at.desc(),
                    ],
                )
                .label("text_rn"),
                func.row_number()
                .over(
                    partition_by=date_expr,
                    order_by=[
                        _nulls_last(RiskAssessment.physiological_score),
                        RiskAssessment.created_at.desc(),
                    ],
                )
                .label("physio_rn"),
                func.count().over(partition_by=date_expr).label("record_count"),
            )
            .where(
                RiskAssessment.user_id == user_id,
                RiskAssessment.created_at >= since,
                RiskAssessment.risk_score > 0,
            )
            .subquery()
        )

        # 外层: GROUP BY date + MAX(CASE WHEN rn=1) 聚合为每天 1 行
        agg_stmt = (
            select(
                subq.c.date_key,
                func.max(
                    case(
                        (subq.c.primary_rn == 1, subq.c.risk_score),
                        else_=None,
                    )
                ).label("primary_risk_score"),
                func.max(
                    case(
                        (subq.c.primary_rn == 1, subq.c.risk_level),
                        else_=None,
                    )
                ).label("primary_risk_level"),
                func.max(
                    case(
                        (subq.c.primary_rn == 1, subq.c.assessment_type),
                        else_=None,
                    )
                ).label("primary_assessment_type"),
                func.max(
                    case(
                        (subq.c.structured_rn == 1, subq.c.structured_score),
                        else_=None,
                    )
                ).label("latest_structured_score"),
                func.max(
                    case(
                        (subq.c.text_rn == 1, subq.c.text_score),
                        else_=None,
                    )
                ).label("latest_text_score"),
                func.max(
                    case(
                        (subq.c.physio_rn == 1, subq.c.physiological_score),
                        else_=None,
                    )
                ).label("latest_physio_score"),
                func.max(subq.c.record_count).label("record_count"),
            )
            .group_by(subq.c.date_key)
            .order_by(subq.c.date_key.asc())
        )
        rows = (await self.db.execute(agg_stmt)).all()

        points: list[dict] = []
        physiological_scores: list[dict] = []

        for row in rows:
            # date_key: SQLite func.date() 返回字符串 'YYYY-MM-DD', PostgreSQL 返回 date 对象
            date_key = row.date_key
            date_str = date_key if isinstance(date_key, str) else date_key.isoformat()

            structured_score = (
                round(row.latest_structured_score, 2)
                if row.latest_structured_score is not None
                else None
            )
            text_score = (
                round(row.latest_text_score, 2)
                if row.latest_text_score is not None
                else None
            )
            physiological_score = (
                round(row.latest_physio_score, 2)
                if row.latest_physio_score is not None
                else None
            )

            points.append(
                {
                    "date": date_str,
                    "risk_score": round(row.primary_risk_score, 2),
                    "risk_level": row.primary_risk_level,
                    "assessment_type": row.primary_assessment_type,
                    "structured_score": structured_score,
                    "text_score": text_score,
                    "physiological_score": physiological_score,
                    "record_count": row.record_count,
                }
            )

            if physiological_score is not None:
                physiological_scores.append(
                    {"date": date_str, "score": physiological_score}
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

    @staticmethod
    def _since_datetime(days: int) -> datetime:
        days_safe = max(0, int(days))
        return datetime.now(timezone.utc) - timedelta(days=days_safe)

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
