"""Tests for UserDataService."""

from __future__ import annotations

import pytest
from datetime import datetime, UTC, timedelta

from app.services.user_data_service import UserDataService
from app.models.assessment import DataDraft, StructuredAssessment, TextEntry, PhysiologicalRecord


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
        service = UserDataService(db_session)
        record_id = await service.record_physiological(1, {
            "source": "manual",
            "sleep_hours": 7.5,
            "heart_rate": 72,
        })
        assert record_id > 0

    @pytest.mark.asyncio
    async def test_record_physiological_with_invalid_fields(self, db_session, seeded_user_id):
        """TC-COV-UDS-005: Record physiological data filters invalid fields."""
        service = UserDataService(db_session)
        record_id = await service.record_physiological(1, {
            "source": "manual",
            "sleep_hours": 7.5,
            "invalid_field": "should_be_ignored",
        })
        assert record_id > 0

    @pytest.mark.asyncio
    async def test_record_physiological_default_data_payload(self, db_session, seeded_user_id):
        """TC-COV-UDS-005b: Record physiological data with default data_payload."""
        service = UserDataService(db_session)
        record_id = await service.record_physiological(1, {
            "source": "manual",
        })
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
    async def test_get_history_physiological_with_data(self, db_session, seeded_user_id):
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
