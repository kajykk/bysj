"""Tests for UserDataService."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.models.assessment import PhysiologicalRecord, StructuredAssessment, TextEntry
from app.models.risk import RiskAssessment
from app.services.user_data_service import UserDataService


class TestUserDataService:
    """Test user data service."""

    @pytest.mark.asyncio
    async def test_upsert_draft_new(self, db_session, seeded_user_id):
        """TC-COV-UDS-001: Create new draft."""
        service = UserDataService(db_session)
        draft_id = await service.upsert_draft(1, "structured", {"sleep_hours": 7.0})
        assert draft_id > 0

    @pytest.mark.asyncio
    async def test_upsert_draft_update(self, db_session, seeded_user_id):
        """TC-COV-UDS-002: Update existing draft."""
        service = UserDataService(db_session)
        await service.upsert_draft(1, "structured", {"sleep_hours": 7.0})
        draft_id = await service.upsert_draft(1, "structured", {"sleep_hours": 8.0})
        assert draft_id > 0
        # Verify update
        draft = await service.get_draft(1, "structured")
        assert draft.data_payload["sleep_hours"] == 8.0

    @pytest.mark.asyncio
    async def test_get_draft_none(self, db_session, seeded_user_id):
        """TC-COV-UDS-003: Get draft when none exists."""
        service = UserDataService(db_session)
        result = await service.get_draft(1, "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_draft_exists(self, db_session, seeded_user_id):
        """TC-COV-UDS-003b: Get existing draft."""
        service = UserDataService(db_session)
        await service.upsert_draft(1, "test_type", {"key": "value"})
        result = await service.get_draft(1, "test_type")
        assert result is not None
        assert result.data_payload["key"] == "value"

    @pytest.mark.asyncio
    async def test_record_physiological(self, db_session, seeded_user_id):
        """TC-COV-UDS-004: Record physiological data."""
        # Mock predict_physiological 避免依赖实际模型 artifact 文件
        with patch("app.services.user_data_service.model_engine") as mock_engine:
            mock_engine.predict_physiological = AsyncMock(
                return_value={
                    "risk_score": 30,
                    "risk_level": 2,
                    "model_used": ["physiological"],
                }
            )
            service = UserDataService(db_session)
            record_id = await service.record_physiological(
                1,
                {
                    "source": "manual",
                    "sleep_hours": 7.5,
                    "heart_rate": 72,
                },
            )
            assert record_id > 0

    @pytest.mark.asyncio
    async def test_record_physiological_with_invalid_fields(
        self, db_session, seeded_user_id
    ):
        """TC-COV-UDS-005: Record physiological data filters invalid fields."""
        with patch("app.services.user_data_service.model_engine") as mock_engine:
            mock_engine.predict_physiological = AsyncMock(
                return_value={
                    "risk_score": 30,
                    "risk_level": 2,
                    "model_used": ["physiological"],
                }
            )
            service = UserDataService(db_session)
            record_id = await service.record_physiological(
                1,
                {
                    "source": "manual",
                    "sleep_hours": 7.5,
                    "invalid_field": "should_be_ignored",
                },
            )
            assert record_id > 0

    @pytest.mark.asyncio
    async def test_record_physiological_default_data_payload(
        self, db_session, seeded_user_id
    ):
        """TC-COV-UDS-005b: Record physiological data with default data_payload."""
        service = UserDataService(db_session)
        record_id = await service.record_physiological(
            1,
            {
                "source": "manual",
            },
        )
        assert record_id > 0

    @pytest.mark.asyncio
    async def test_get_history_invalid_type(self, db_session, seeded_user_id):
        """TC-COV-UDS-006: Get history with invalid type raises error."""
        service = UserDataService(db_session)
        with pytest.raises(ValueError, match="不支持的数据类型"):
            await service.get_history(1, "invalid_type", 1, 10)

    @pytest.mark.asyncio
    async def test_get_history_invalid_date_range(self, db_session, seeded_user_id):
        """TC-COV-UDS-007: Get history with invalid date range raises error."""
        service = UserDataService(db_session)
        start = datetime(2024, 1, 15, tzinfo=UTC)
        end = datetime(2024, 1, 1, tzinfo=UTC)
        with pytest.raises(ValueError, match="开始时间不能晚于结束时间"):
            await service.get_history(1, "structured", 1, 10, start, end)

    @pytest.mark.asyncio
    async def test_get_history_structured_empty(self, db_session, seeded_user_id):
        """TC-COV-UDS-008: Get structured history when empty."""
        service = UserDataService(db_session)
        result = await service.get_history(1, "structured", 1, 10)
        assert result["items"] == []
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_get_history_text_empty(self, db_session, seeded_user_id):
        """TC-COV-UDS-009: Get text history when empty."""
        service = UserDataService(db_session)
        result = await service.get_history(1, "text", 1, 10)
        assert result["items"] == []
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_get_history_physiological_empty(self, db_session, seeded_user_id):
        """TC-COV-UDS-010: Get physiological history when empty."""
        service = UserDataService(db_session)
        result = await service.get_history(1, "physiological", 1, 10)
        assert result["items"] == []
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_get_history_physio_alias(self, db_session, seeded_user_id):
        """TC-COV-UDS-010b: Get physiological history using 'physio' alias."""
        service = UserDataService(db_session)
        result = await service.get_history(1, "physio", 1, 10)
        assert result["items"] == []
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_get_history_record_alias(self, db_session, seeded_user_id):
        """TC-COV-UDS-010c: Get physiological history using 'record' alias."""
        service = UserDataService(db_session)
        result = await service.get_history(1, "record", 1, 10)
        assert result["items"] == []
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_get_history_structured_with_data(self, db_session, seeded_user_id):
        """TC-COV-UDS-011: Get structured history with data."""
        service = UserDataService(db_session)
        # Create assessment
        assessment = StructuredAssessment(
            user_id=1,
            assessment_type="comprehensive",
            score=50.0,
            severity="moderate",
            data_payload={"test": "data"},
        )
        db_session.add(assessment)
        await db_session.commit()

        result = await service.get_history(1, "structured", 1, 10)
        assert result["total"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["type"] == "structured"
        assert result["items"][0]["data"]["score"] == 50.0

    @pytest.mark.asyncio
    async def test_get_history_text_with_data(self, db_session, seeded_user_id):
        """TC-COV-UDS-012: Get text history with data."""
        service = UserDataService(db_session)
        # Create text entry
        entry = TextEntry(
            user_id=1,
            entry_type="journal",
            content="Test content",
            emotion_tags=["happy"],
            mood_score=7,
            sentiment_score=0.8,
            sentiment_label="positive",
        )
        db_session.add(entry)
        await db_session.commit()

        result = await service.get_history(1, "text", 1, 10)
        assert result["total"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["type"] == "text"
        assert result["items"][0]["data"]["content"] == "Test content"

    @pytest.mark.asyncio
    async def test_get_history_physiological_with_data(
        self, db_session, seeded_user_id
    ):
        """TC-COV-UDS-013: Get physiological history with data."""
        service = UserDataService(db_session)
        # Create physiological record
        record = PhysiologicalRecord(
            user_id=1,
            source="manual",
            sleep_hours=7.5,
            heart_rate=72,
            steps=10000,
            data_payload={"device": "watch"},
        )
        db_session.add(record)
        await db_session.commit()

        result = await service.get_history(1, "physiological", 1, 10)
        assert result["total"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["type"] == "physiological"
        assert result["items"][0]["data"]["sleep_hours"] == 7.5

    @pytest.mark.asyncio
    async def test_get_history_with_date_filter(self, db_session, seeded_user_id):
        """TC-COV-UDS-014: Get history with date filter."""
        service = UserDataService(db_session)
        # Create assessment
        assessment = StructuredAssessment(
            user_id=1,
            assessment_type="comprehensive",
            score=50.0,
            severity="moderate",
            data_payload={"test": "data"},
        )
        db_session.add(assessment)
        await db_session.commit()

        start = datetime.now(UTC) - timedelta(days=1)
        end = datetime.now(UTC) + timedelta(days=1)
        result = await service.get_history(1, "structured", 1, 10, start, end)
        assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_get_history_pagination(self, db_session, seeded_user_id):
        """TC-COV-UDS-015: Get history with pagination."""
        service = UserDataService(db_session)
        # Create multiple assessments
        for i in range(5):
            assessment = StructuredAssessment(
                user_id=1,
                assessment_type="comprehensive",
                score=float(i * 10),
                severity="moderate",
                data_payload={"index": i},
            )
            db_session.add(assessment)
        await db_session.commit()

        result = await service.get_history(1, "structured", 1, 2)
        assert result["total"] == 5
        assert len(result["items"]) == 2
        assert result["page"] == 1
        assert result["page_size"] == 2

    @pytest.mark.asyncio
    async def test_save_assessment_result_text_branch(self, db_session, seeded_user_id):
        """TC-COV-UDS-016: 覆盖 _save_assessment_result text 评估分支。"""
        service = UserDataService(db_session)
        result = {
            "sentiment_score": 0.5,
            "risk_score": 50.0,
            "risk_level": 2,
            "model_used": ["text_model"],
            "risk_factors": ["stress"],
        }
        await service._save_assessment_result(result, 1, "text", {"text": "some text"})
        await db_session.commit()

        from sqlalchemy import select

        risk = (
            (
                await db_session.execute(
                    select(RiskAssessment).where(
                        RiskAssessment.assessment_type == "text"
                    )
                )
            )
            .scalars()
            .first()
        )
        assert risk is not None
        assert risk.text_score == 50.0

    @pytest.mark.asyncio
    async def test_save_assessment_result_text_no_sentiment(
        self, db_session, seeded_user_id
    ):
        """TC-COV-UDS-017: 覆盖 text 评估无 sentiment_score 时使用 risk_score 兜底。"""
        service = UserDataService(db_session)
        result = {
            "risk_score": 40.0,
            "risk_level": 1,
            "model_used": ["text_model"],
            "risk_factors": ["crisis"],
        }
        await service._save_assessment_result(result, 1, "text", {"text": "content"})
        await db_session.commit()

        from sqlalchemy import select

        risk = (
            (
                await db_session.execute(
                    select(RiskAssessment).where(
                        RiskAssessment.assessment_type == "text"
                    )
                )
            )
            .scalars()
            .first()
        )
        assert risk is not None
        assert risk.text_score == 40.0

    @pytest.mark.asyncio
    async def test_save_assessment_result_structured_branch(
        self, db_session, seeded_user_id
    ):
        """TC-COV-UDS-018: 覆盖 _save_assessment_result structured（else）分支及 models_used 字符串形式。"""
        service = UserDataService(db_session)
        result = {
            "risk_score": 60.0,
            "risk_level": 2,
            "model_used": "single_string_model",  # 字符串形式，覆盖 isinstance 分支
            "risk_factors": [{"feature": "stress", "importance": 0.8}],
        }
        await service._save_assessment_result(result, 1, "structured")
        await db_session.commit()

        from sqlalchemy import select

        risk = (
            (
                await db_session.execute(
                    select(RiskAssessment).where(
                        RiskAssessment.assessment_type == "structured"
                    )
                )
            )
            .scalars()
            .first()
        )
        assert risk is not None
        assert risk.models_used == ["single_string_model"]

    @pytest.mark.asyncio
    async def test_save_assessment_result_negative_score(
        self, db_session, seeded_user_id
    ):
        """TC-COV-UDS-019: 覆盖 risk_score 为负数时跳过保存。"""
        service = UserDataService(db_session)
        result = {
            "risk_score": -5.0,
            "risk_level": 0,
            "model_used": [],
        }
        await service._save_assessment_result(result, 1, "structured")
        await db_session.commit()

        from sqlalchemy import select

        all_risks = (
            (
                await db_session.execute(
                    select(RiskAssessment).where(
                        RiskAssessment.assessment_type == "structured"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(all_risks) == 0

    def test_generate_physio_factors_sleep_low(self):
        """TC-COV-UDS-020: 覆盖 sleep_hours < 6 时生成睡眠不足因素。"""
        result = {"data_quality": "good"}
        payload = {"physiological": {"sleep_hours": 4.0}}
        factors = UserDataService._generate_physio_factors(result, payload)
        assert any(
            f["feature"] == "睡眠时长" and f["direction"] == "睡眠不足" for f in factors
        )

    def test_generate_physio_factors_sleep_high(self):
        """TC-COV-UDS-021: 覆盖 sleep_hours > 10 时生成睡眠过长因素。"""
        result = {"data_quality": "good"}
        payload = {"physiological": {"sleep_hours": 11.0}}
        factors = UserDataService._generate_physio_factors(result, payload)
        assert any(f["direction"] == "睡眠过长" for f in factors)

    def test_generate_physio_factors_invalid_sleep(self):
        """TC-COV-UDS-022: 覆盖 sleep_hours 非法值时静默跳过。"""
        result = {"data_quality": "good"}
        payload = {"physiological": {"sleep_hours": "invalid"}}
        factors = UserDataService._generate_physio_factors(result, payload)
        assert not any(f["feature"] == "睡眠时长" for f in factors)

    def test_generate_physio_factors_heart_rate_high(self):
        """TC-COV-UDS-023: 覆盖 heart_rate >= 90 时生成偏高因素。"""
        result = {"data_quality": "good"}
        payload = {"physiological": {"heart_rate": 95}}
        factors = UserDataService._generate_physio_factors(result, payload)
        assert any(f["feature"] == "心率" and f["direction"] == "偏高" for f in factors)

    def test_generate_physio_factors_invalid_heart_rate(self):
        """TC-COV-UDS-024: 覆盖 heart_rate 非法值时静默跳过。"""
        result = {"data_quality": "good"}
        payload = {"physiological": {"heart_rate": "invalid"}}
        factors = UserDataService._generate_physio_factors(result, payload)
        assert not any(f["feature"] == "心率" for f in factors)

    def test_generate_physio_factors_steps_low(self):
        """TC-COV-UDS-025: 覆盖 steps < 3000 时生成活动过少因素。"""
        result = {"data_quality": "good"}
        payload = {"physiological": {"steps": 2000}}
        factors = UserDataService._generate_physio_factors(result, payload)
        assert any(
            f["feature"] == "步数" and f["direction"] == "活动过少" for f in factors
        )

    def test_generate_physio_factors_invalid_steps(self):
        """TC-COV-UDS-026: 覆盖 steps 非法值时静默跳过。"""
        result = {"data_quality": "good"}
        payload = {"physiological": {"steps": "invalid"}}
        factors = UserDataService._generate_physio_factors(result, payload)
        assert not any(f["feature"] == "步数" for f in factors)

    def test_generate_physio_factors_exercise_low(self):
        """TC-COV-UDS-027: 覆盖 exercise_minutes < 15 时生成运动不足因素。"""
        result = {"data_quality": "good"}
        payload = {"physiological": {"exercise_minutes": 10}}
        factors = UserDataService._generate_physio_factors(result, payload)
        assert any(
            f["feature"] == "运动时长" and f["direction"] == "运动不足" for f in factors
        )

    def test_generate_physio_factors_invalid_exercise(self):
        """TC-COV-UDS-028: 覆盖 exercise_minutes 非法值时静默跳过。"""
        result = {"data_quality": "good"}
        payload = {"physiological": {"exercise_minutes": "invalid"}}
        factors = UserDataService._generate_physio_factors(result, payload)
        assert not any(f["feature"] == "运动时长" for f in factors)

    def test_generate_physio_factors_poor_data_quality(self):
        """TC-COV-UDS-029: 覆盖 data_quality=poor 且无其他因素时生成数据质量因素。"""
        result = {"data_quality": "poor"}
        payload = {"physiological": {}}
        factors = UserDataService._generate_physio_factors(result, payload)
        assert any(f["feature"] == "数据质量" for f in factors)

    def test_generate_physio_factors_from_result_physiological_data(self):
        """TC-COV-UDS-030: 覆盖从 result.physiological_data 读取数据。"""
        result = {
            "data_quality": "good",
            "physiological_data": {"sleep_hours": 4.0},
        }
        factors = UserDataService._generate_physio_factors(result, None)
        assert any(f["feature"] == "睡眠时长" for f in factors)

    @pytest.mark.asyncio
    async def test_analyze_text(self, db_session, seeded_user_id):
        """TC-COV-UDS-031: 覆盖 analyze_text 完整流程。"""
        with patch("app.services.user_data_service.model_engine") as mock_engine:
            mock_engine.predict_text = AsyncMock(
                return_value={
                    "sentiment_score": 0.5,
                    "sentiment_label": "positive",
                    "risk_level": 2,
                }
            )
            service = UserDataService(db_session)
            result = await service.analyze_text(
                1, "journal", "今天心情不错", ["happy"], 7
            )
            assert "entry_id" in result
            assert result["sentiment_label"] == "positive"
            assert result["sentiment_score"] == 0.5

    @pytest.mark.asyncio
    async def test_analyze_text_default_risk_level(self, db_session, seeded_user_id):
        """TC-COV-UDS-032: 覆盖 analyze_text 无 risk_level 时调用 score_to_level。"""
        with patch("app.services.user_data_service.model_engine") as mock_engine:
            mock_engine.predict_text = AsyncMock(
                return_value={
                    "sentiment_score": 0.3,
                    "sentiment_label": "neutral",
                }
            )
            mock_engine.score_to_level = lambda score, kind: 1
            service = UserDataService(db_session)
            result = await service.analyze_text(1, "journal", "一般心情", [], 5)
            assert "entry_id" in result

    @pytest.mark.asyncio
    async def test_get_history_text_with_date_filter(self, db_session, seeded_user_id):
        """TC-COV-UDS-033: 覆盖 text 历史查询的日期过滤分支。"""
        service = UserDataService(db_session)
        entry = TextEntry(
            user_id=1,
            entry_type="journal",
            content="test",
            emotion_tags=[],
            mood_score=5,
        )
        db_session.add(entry)
        await db_session.commit()

        start = datetime.now(UTC) - timedelta(days=1)
        end = datetime.now(UTC) + timedelta(days=1)
        result = await service.get_history(1, "text", 1, 10, start, end)
        assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_get_history_physiological_with_date_filter(
        self, db_session, seeded_user_id
    ):
        """TC-COV-UDS-034: 覆盖 physiological 历史查询的日期过滤分支。"""
        service = UserDataService(db_session)
        record = PhysiologicalRecord(
            user_id=1,
            source="manual",
            sleep_hours=7.0,
            heart_rate=72,
        )
        db_session.add(record)
        await db_session.commit()

        start = datetime.now(UTC) - timedelta(days=1)
        end = datetime.now(UTC) + timedelta(days=1)
        result = await service.get_history(1, "physiological", 1, 10, start, end)
        assert result["total"] == 1
