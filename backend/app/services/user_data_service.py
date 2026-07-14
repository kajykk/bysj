from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.model_engine import model_engine
from app.models.assessment import (
    DataDraft,
    PhysiologicalRecord,
    StructuredAssessment,
    TextEntry,
)
from app.models.risk import RiskAssessment
from app.services.risk_service import RiskService

logger = logging.getLogger(__name__)

# M18 修复：将 save_assessment_result 的核心逻辑下沉到 service 层，避免反向依赖 API 层
_PHYSIO_FEATURE_LABELS: dict[str, str] = {
    "sleep_hours": "睡眠时长",
    "sleep_quality": "睡眠质量",
    "heart_rate": "心率",
    "steps": "步数",
    "exercise_minutes": "运动时长",
    "systolic_bp": "收缩压",
    "diastolic_bp": "舒张压",
}


class UserDataService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _save_assessment_result(
        self,
        result: dict,
        user_id: int,
        assessment_type: str,
        payload: dict | None = None,
    ) -> None:
        """保存评估结果到数据库（内联实现，避免反向依赖 API 层）。

        M18 修复：将 save_assessment_result 核心逻辑下沉到 service 层。
        不自动 commit，由调用方管理事务（配合 M19 的事务一致性修复）。
        """
        structured_score: float | None = None
        text_score: float | None = None
        physio_score: float | None = None

        if assessment_type == "text":
            sentiment = result.get("sentiment_score")
            text_score = (
                round(sentiment * 100, 2)
                if sentiment is not None
                else result.get("risk_score")
            )
        elif assessment_type == "physiological":
            physio_score = (
                result.get("risk_score")
                if result.get("risk_score") is not None
                else None
            )

        models_used = result.get("model_used", [])
        if isinstance(models_used, str):
            models_used = [models_used]

        if assessment_type == "physiological":
            risk_factors = self._generate_physio_factors(result, payload)
        elif assessment_type == "text":
            risk_factors = (
                result.get("risk_factors", result.get("crisis_keywords", [])) or []
            )
        else:
            risk_factors = result.get("risk_factors") or []

        # C-04 修复：使用显式 None 检查，避免合法的 0 分被跳过保存
        raw_score = result.get("risk_score")
        risk_score_value = float(raw_score) if raw_score is not None else 0.0
        if risk_score_value < 0:
            logger.warning(
                "Skipped saving %s assessment for user %s (invalid risk_score=%s)",
                assessment_type,
                user_id,
                risk_score_value,
            )
            return

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
            risk_score=risk_score_value,
            risk_level=(
                result.get("risk_level") if result.get("risk_level") is not None else 0
            ),
            structured_score=structured_score,
            text_score=text_score,
            physiological_score=physio_score,
            models_used=models_used,
            risk_factors=risk_factors,
            assessment_type=assessment_type,
            is_latest=True,
        )
        self.db.add(risk)
        await self.db.flush()
        risk_service = RiskService(self.db)
        await risk_service.trigger_warning_for_risk(risk)
        await risk_service.generate_intervention_for_risk(risk)

    @staticmethod
    def _generate_physio_factors(
        result: dict, payload: dict | None = None
    ) -> list[dict]:
        """生成生理数据风险因素列表（从 model_predict.py 内联，避免反向依赖）。"""
        factors: list[dict] = []
        physio_data = (payload or {}).get("physiological", {}) or result.get(
            "physiological_data", {}
        )
        data_quality = result.get("data_quality", "partial")

        for key, label in _PHYSIO_FEATURE_LABELS.items():
            if key == "sleep_hours":
                sleep = physio_data.get("sleep_hours")
                if sleep is not None:
                    try:
                        s = float(sleep)
                        if s < 6:
                            factors.append(
                                {
                                    "feature": label,
                                    "importance": round((6 - s) / 6, 2),
                                    "direction": "睡眠不足",
                                }
                            )
                        elif s > 10:
                            factors.append(
                                {
                                    "feature": label,
                                    "importance": 0.5,
                                    "direction": "睡眠过长",
                                }
                            )
                    except (TypeError, ValueError):
                        pass
            elif key == "heart_rate":
                hr = physio_data.get("heart_rate")
                if hr is not None:
                    try:
                        h = float(hr)
                        if h >= 90:
                            factors.append(
                                {
                                    "feature": label,
                                    "importance": min(round((h - 80) / 30, 2), 1.0),
                                    "direction": "偏高",
                                }
                            )
                    except (TypeError, ValueError):
                        pass
            elif key == "steps":
                steps = physio_data.get("steps")
                if steps is not None:
                    try:
                        st = float(steps)
                        if st < 3000:
                            factors.append(
                                {
                                    "feature": label,
                                    "importance": min(
                                        round((3000 - st) / 3000, 2), 1.0
                                    ),
                                    "direction": "活动过少",
                                }
                            )
                    except (TypeError, ValueError):
                        pass
            elif key == "exercise_minutes":
                ex = physio_data.get("exercise_minutes")
                if ex is not None:
                    try:
                        e = float(ex)
                        if e < 15:
                            factors.append(
                                {
                                    "feature": label,
                                    "importance": min(round((15 - e) / 15, 2), 1.0),
                                    "direction": "运动不足",
                                }
                            )
                    except (TypeError, ValueError):
                        pass

        if not factors and data_quality == "poor":
            factors.append(
                {
                    "feature": "数据质量",
                    "importance": 0.5,
                    "direction": "生理数据不足，建议补充更多指标",
                }
            )

        factors.sort(key=lambda f: f["importance"], reverse=True)
        return factors[:5]

    async def upsert_draft(
        self, user_id: int, draft_type: str, data_payload: dict
    ) -> int:
        stmt = select(DataDraft).where(
            DataDraft.user_id == user_id, DataDraft.draft_type == draft_type
        )
        draft = (await self.db.execute(stmt)).scalar_one_or_none()
        if draft:
            draft.data_payload = data_payload
            # M-33 修复：DataDraft.updated_at 为 naive DateTime 列，需用 naive UTC 与其他列保持一致
            draft.updated_at = datetime.now(UTC).replace(tzinfo=None)
        else:
            draft = DataDraft(
                user_id=user_id, draft_type=draft_type, data_payload=data_payload
            )
            self.db.add(draft)
        await self.db.commit()
        await self.db.refresh(draft)
        return draft.id

    async def get_draft(self, user_id: int, draft_type: str) -> DataDraft | None:
        stmt = select(DataDraft).where(
            DataDraft.user_id == user_id, DataDraft.draft_type == draft_type
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def analyze_text(
        self,
        user_id: int,
        entry_type: str,
        content: str,
        emotion_tags: list[str],
        mood_score: int | None,
    ) -> dict:
        entry = TextEntry(
            user_id=user_id,
            entry_type=entry_type,
            content=content,
            emotion_tags=emotion_tags,
            mood_score=mood_score,
        )
        self.db.add(entry)
        await self.db.flush()

        result = await model_engine.predict_text(content)
        # M-Svc-11 修复：使用 .get() 防御 KeyError，避免模型返回结果缺少字段时崩溃
        entry.sentiment_score = result.get("sentiment_score")
        entry.sentiment_label = result.get("sentiment_label")

        risk_score = round(float(result.get("sentiment_score", 0)) * 100, 2)
        risk_result = {
            **result,
            "risk_score": risk_score,
            "risk_level": (
                result.get("risk_level")
                if result.get("risk_level") is not None
                else model_engine.score_to_level(risk_score, "text")
            ),
        }
        # M18 修复：内联 save_assessment_result 逻辑，避免 services 层反向依赖 API 层
        # M19 修复：将 commit 移到 save_assessment_result 之后，确保文本记录和风险评估在同一事务内提交
        await self._save_assessment_result(
            risk_result, user_id, "text", {"text": content}
        )
        await self.db.commit()

        return {
            "entry_id": entry.id,
            "sentiment_score": entry.sentiment_score,
            "sentiment_label": entry.sentiment_label,
        }

    async def record_physiological(self, user_id: int, payload: dict) -> int:
        allowed_fields = {
            "source",
            "sleep_hours",
            "sleep_quality",
            "exercise_minutes",
            "heart_rate",
            "systolic_bp",
            "diastolic_bp",
            "steps",
            "data_payload",
        }
        safe_payload = {k: v for k, v in payload.items() if k in allowed_fields}
        if "data_payload" not in safe_payload or safe_payload["data_payload"] is None:
            safe_payload["data_payload"] = {}
        record = PhysiologicalRecord(user_id=user_id, **safe_payload)
        self.db.add(record)
        # M19 修复：将 commit 移到 save_assessment_result 之后，确保生理记录和风险评估在同一事务内提交
        await self.db.flush()

        prediction_payload = {
            "sleep_hours": safe_payload.get("sleep_hours"),
            "sleep_quality": safe_payload.get("sleep_quality"),
            "exercise_minutes": safe_payload.get("exercise_minutes"),
            "heart_rate": safe_payload.get("heart_rate"),
            "systolic_bp": safe_payload.get("systolic_bp"),
            "diastolic_bp": safe_payload.get("diastolic_bp"),
            "steps": safe_payload.get("steps"),
        }
        prediction_payload = {
            k: v for k, v in prediction_payload.items() if v is not None
        }
        if prediction_payload:
            result = await model_engine.predict_physiological(prediction_payload)
            # M18 修复：内联 save_assessment_result 逻辑，避免 services 层反向依赖 API 层
            await self._save_assessment_result(
                result, user_id, "physiological", {"physiological": prediction_payload}
            )

        await self.db.commit()
        await self.db.refresh(record)
        return record.id

    async def get_history(
        self,
        user_id: int,
        data_type: str,
        page: int,
        page_size: int,
        start_dt: datetime | None = None,
        end_dt: datetime | None = None,
    ) -> dict:
        if start_dt and end_dt and start_dt > end_dt:
            raise ValueError("开始时间不能晚于结束时间")
        offset = (page - 1) * page_size
        normalized_type = (data_type or "").strip().lower()

        if normalized_type == "structured":
            stmt = (
                select(StructuredAssessment)
                .where(StructuredAssessment.user_id == user_id)
                .order_by(StructuredAssessment.created_at.desc())
            )
            count_stmt = (
                select(func.count())
                .select_from(StructuredAssessment)
                .where(StructuredAssessment.user_id == user_id)
            )
            if start_dt:
                stmt = stmt.where(StructuredAssessment.created_at >= start_dt)
                count_stmt = count_stmt.where(
                    StructuredAssessment.created_at >= start_dt
                )
            if end_dt:
                stmt = stmt.where(StructuredAssessment.created_at <= end_dt)
                count_stmt = count_stmt.where(StructuredAssessment.created_at <= end_dt)
            rows = (
                (await self.db.execute(stmt.offset(offset).limit(page_size)))
                .scalars()
                .all()
            )
            total = (await self.db.execute(count_stmt)).scalar_one()
            items = [
                {
                    "id": row.id,
                    "type": "structured",
                    "created_at": row.created_at,
                    "data": {
                        "assessment_type": row.assessment_type,
                        "score": row.score,
                        "severity": row.severity,
                        "data_payload": row.data_payload,
                    },
                }
                for row in rows
            ]
        elif normalized_type == "text":
            stmt = (
                select(TextEntry)
                .where(TextEntry.user_id == user_id)
                .order_by(TextEntry.created_at.desc())
            )
            count_stmt = (
                select(func.count())
                .select_from(TextEntry)
                .where(TextEntry.user_id == user_id)
            )
            if start_dt:
                stmt = stmt.where(TextEntry.created_at >= start_dt)
                count_stmt = count_stmt.where(TextEntry.created_at >= start_dt)
            if end_dt:
                stmt = stmt.where(TextEntry.created_at <= end_dt)
                count_stmt = count_stmt.where(TextEntry.created_at <= end_dt)
            rows = (
                (await self.db.execute(stmt.offset(offset).limit(page_size)))
                .scalars()
                .all()
            )
            total = (await self.db.execute(count_stmt)).scalar_one()
            items = [
                {
                    "id": row.id,
                    "type": "text",
                    "created_at": row.created_at,
                    "data": {
                        "entry_type": row.entry_type,
                        "content": row.content,
                        "mood_score": row.mood_score,
                        "sentiment_score": row.sentiment_score,
                        "sentiment_label": row.sentiment_label,
                    },
                }
                for row in rows
            ]
        elif normalized_type in {"physiological", "physio", "record"}:
            stmt = (
                select(PhysiologicalRecord)
                .where(PhysiologicalRecord.user_id == user_id)
                .order_by(PhysiologicalRecord.recorded_at.desc())
            )
            count_stmt = (
                select(func.count())
                .select_from(PhysiologicalRecord)
                .where(PhysiologicalRecord.user_id == user_id)
            )
            if start_dt:
                stmt = stmt.where(PhysiologicalRecord.recorded_at >= start_dt)
                count_stmt = count_stmt.where(
                    PhysiologicalRecord.recorded_at >= start_dt
                )
            if end_dt:
                stmt = stmt.where(PhysiologicalRecord.recorded_at <= end_dt)
                count_stmt = count_stmt.where(PhysiologicalRecord.recorded_at <= end_dt)
            rows = (
                (await self.db.execute(stmt.offset(offset).limit(page_size)))
                .scalars()
                .all()
            )
            total = (await self.db.execute(count_stmt)).scalar_one()
            items = [
                {
                    "id": row.id,
                    "type": "physiological",
                    "created_at": row.recorded_at,
                    "data": {
                        "source": row.source,
                        "sleep_hours": row.sleep_hours,
                        "sleep_quality": row.sleep_quality,
                        "exercise_minutes": row.exercise_minutes,
                        "heart_rate": row.heart_rate,
                        "steps": row.steps,
                        "data_payload": row.data_payload,
                    },
                }
                for row in rows
            ]
        else:
            raise ValueError(f"不支持的数据类型: {data_type}")

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
