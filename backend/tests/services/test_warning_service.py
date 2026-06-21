"""Tests for WarningService."""

from __future__ import annotations

import pytest

from app.services.warning_service import WarningService
from app.models.risk import WarningNotification, WarningSetting


class TestWarningService:
    """Test warning service."""

    @pytest.mark.asyncio
    async def test_list_warnings_empty(self, db_session, seeded_user_id):
        """TC-COV-WRN-001: List warnings for user with no warnings."""
        service = WarningService(db_session)
        result = await service.list_warnings(1, 1, 10, None)
        assert result["items"] == []
        assert result["total"] == 0
        assert result["page"] == 1

    @pytest.mark.asyncio
    async def test_list_warnings_with_read_filter(self, db_session, seeded_user_id):
        """TC-COV-WRN-002: List warnings with read filter."""
        service = WarningService(db_session)
        result = await service.list_warnings(1, 1, 10, is_read=False)
        assert result["items"] == []

    @pytest.mark.asyncio
    async def test_mark_read_not_found(self, db_session, seeded_user_id):
        """TC-COV-WRN-003: Mark non-existent warning as read returns False."""
        service = WarningService(db_session)
        result = await service.mark_read(1, 9999)
        assert result is False

    @pytest.mark.asyncio
    async def test_mark_read_all_empty(self, db_session, seeded_user_id):
        """TC-COV-WRN-004: Mark all as read when no warnings."""
        service = WarningService(db_session)
        result = await service.mark_read_all(1)
        assert result == 0

    @pytest.mark.asyncio
    async def test_get_setting_default(self, db_session, seeded_user_id):
        """TC-COV-WRN-005: Get warning setting creates default if none exists."""
        service = WarningService(db_session)
        result = await service.get_setting(1)
        assert result.user_id == 1

    @pytest.mark.asyncio
    async def test_update_setting(self, db_session, seeded_user_id):
        """TC-COV-WRN-006: Update warning setting."""
        service = WarningService(db_session)
        result = await service.update_setting(1, {"notify_channels": ["email"], "threshold_level": 2})
        assert result.notify_channels == ["email"]
        assert result.threshold_level == 2

    @pytest.mark.asyncio
    async def test_update_setting_threshold_clamping(self, db_session, seeded_user_id):
        """TC-COV-WRN-007: Update setting clamps threshold to valid range."""
        service = WarningService(db_session)
        result = await service.update_setting(1, {"threshold_level": -1})
        assert result.threshold_level == 0
        result = await service.update_setting(1, {"threshold_level": 10})
        assert result.threshold_level == 4

    @pytest.mark.asyncio
    async def test_list_warnings_with_data(self, db_session, seeded_user_id):
        """TC-COV-WRN-008: List warnings with actual data."""
        service = WarningService(db_session)
        # Create a warning notification
        warning = WarningNotification(
            user_id=1,
            risk_assessment_id=1,
            previous_level=1,
            current_level=3,
            trigger_reason="风险等级上升",
            is_read=False,
            is_handled=False,
        )
        db_session.add(warning)
        await db_session.commit()

        result = await service.list_warnings(1, 1, 10, None)
        assert result["total"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["risk_level"] == "high"
        assert result["items"][0]["is_read"] is False

    @pytest.mark.asyncio
    async def test_list_warnings_read_filter(self, db_session, seeded_user_id):
        """TC-COV-WRN-009: List warnings with read/unread filter."""
        service = WarningService(db_session)
        # Create warnings
        warning1 = WarningNotification(
            user_id=1,
            risk_assessment_id=1,
            previous_level=1,
            current_level=2,
            trigger_reason="测试1",
            is_read=True,
            is_handled=False,
        )
        warning2 = WarningNotification(
            user_id=1,
            risk_assessment_id=1,
            previous_level=1,
            current_level=3,
            trigger_reason="测试2",
            is_read=False,
            is_handled=False,
        )
        db_session.add(warning1)
        db_session.add(warning2)
        await db_session.commit()

        result_read = await service.list_warnings(1, 1, 10, is_read=True)
        assert result_read["total"] == 1
        assert result_read["items"][0]["is_read"] is True

        result_unread = await service.list_warnings(1, 1, 10, is_read=False)
        assert result_unread["total"] == 1
        assert result_unread["items"][0]["is_read"] is False

    @pytest.mark.asyncio
    async def test_mark_read_success(self, db_session, seeded_user_id):
        """TC-COV-WRN-010: Mark warning as read successfully."""
        service = WarningService(db_session)
        warning = WarningNotification(
            user_id=1,
            risk_assessment_id=1,
            previous_level=1,
            current_level=2,
            trigger_reason="测试",
            is_read=False,
            is_handled=False,
        )
        db_session.add(warning)
        await db_session.commit()
        await db_session.refresh(warning)

        result = await service.mark_read(1, warning.id)
        assert result is True

        # Verify it's now read
        result_list = await service.list_warnings(1, 1, 10, is_read=True)
        assert result_list["total"] == 1

    @pytest.mark.asyncio
    async def test_mark_read_already_read(self, db_session, seeded_user_id):
        """TC-COV-WRN-011: Mark already read warning doesn't error."""
        service = WarningService(db_session)
        warning = WarningNotification(
            user_id=1,
            risk_assessment_id=1,
            previous_level=1,
            current_level=2,
            trigger_reason="测试",
            is_read=True,
            is_handled=False,
        )
        db_session.add(warning)
        await db_session.commit()
        await db_session.refresh(warning)

        result = await service.mark_read(1, warning.id)
        assert result is True

    @pytest.mark.asyncio
    async def test_mark_all_read(self, db_session, seeded_user_id):
        """TC-COV-WRN-012: Mark all warnings as read."""
        service = WarningService(db_session)
        # Create multiple unread warnings
        for i in range(3):
            warning = WarningNotification(
                user_id=1,
                risk_assessment_id=1,
                previous_level=1,
                current_level=2,
                trigger_reason=f"测试{i}",
                is_read=False,
                is_handled=False,
            )
            db_session.add(warning)
        await db_session.commit()

        result = await service.mark_read_all(1)
        assert result == 3

        # Verify all are read
        result_list = await service.list_warnings(1, 1, 10, is_read=False)
        assert result_list["total"] == 0

    @pytest.mark.asyncio
    async def test_update_setting_quiet_hours(self, db_session, seeded_user_id):
        """TC-COV-WRN-013: Update quiet hours setting."""
        from datetime import time
        service = WarningService(db_session)
        result = await service.update_setting(1, {
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "08:00",
        })
        assert result.quiet_hours_start == time(22, 0)
        assert result.quiet_hours_end == time(8, 0)

    @pytest.mark.asyncio
    async def test_update_setting_no_changes(self, db_session, seeded_user_id):
        """TC-COV-WRN-014: Update with empty payload doesn't error."""
        service = WarningService(db_session)
        result = await service.update_setting(1, {})
        assert result.user_id == 1

    @pytest.mark.asyncio
    async def test_warning_status_resolved(self, db_session, seeded_user_id):
        """TC-COV-WRN-015: Warning status shows resolved when handled."""
        service = WarningService(db_session)
        warning = WarningNotification(
            user_id=1,
            risk_assessment_id=1,
            previous_level=1,
            current_level=2,
            trigger_reason="测试",
            is_read=True,
            is_handled=True,
            handle_action="reviewed",
        )
        db_session.add(warning)
        await db_session.commit()

        result = await service.list_warnings(1, 1, 10, None)
        assert result["items"][0]["status"] == "handled"

    @pytest.mark.asyncio
    async def test_warning_status_pending(self, db_session, seeded_user_id):
        """TC-COV-WRN-016: Warning status shows pending when not handled."""
        service = WarningService(db_session)
        warning = WarningNotification(
            user_id=1,
            risk_assessment_id=1,
            previous_level=1,
            current_level=2,
            trigger_reason="测试",
            is_read=False,
            is_handled=False,
        )
        db_session.add(warning)
        await db_session.commit()

        result = await service.list_warnings(1, 1, 10, None)
        assert result["items"][0]["status"] == "pending"
