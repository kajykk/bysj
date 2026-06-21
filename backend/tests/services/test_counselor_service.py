"""Tests for CounselorService."""

from __future__ import annotations

import pytest

from app.services.counselor_service import CounselorService


class TestCounselorService:
    """Test counselor service."""

    @pytest.mark.asyncio
    async def test_list_warnings_empty(self, db_session, seeded_user_id):
        """TC-COV-COUN-001: List warnings for counselor with no warnings."""
        service = CounselorService(db_session)
        result = await service.list_warnings(2, 1, 10, False)
        assert result["items"] == []
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_handle_warning_not_found(self, db_session, seeded_user_id):
        """TC-COV-COUN-002: Handle non-existent warning returns False."""
        service = CounselorService(db_session)
        result = await service.handle_warning(2, 9999, "handle", None)
        assert result is False

    @pytest.mark.asyncio
    async def test_list_my_users_empty(self, db_session, seeded_user_id):
        """TC-COV-COUN-003: List users for counselor with no bindings."""
        service = CounselorService(db_session)
        result = await service.list_my_users(2, 1, 10)
        assert result["items"] == []
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_create_consultation_record_no_binding(self, db_session, seeded_user_id):
        """TC-COV-COUN-004: Create record without binding raises error."""
        service = CounselorService(db_session)
        with pytest.raises(ValueError, match="当前用户未绑定到该咨询师"):
            await service.create_consultation_record(2, 1, {})

    @pytest.mark.asyncio
    async def test_update_consultation_record_not_found(self, db_session, seeded_user_id):
        """TC-COV-COUN-005: Update non-existent record returns False."""
        service = CounselorService(db_session)
        result = await service.update_consultation_record(2, 1, 9999, {})
        assert result is False

    @pytest.mark.asyncio
    async def test_get_user_detail_no_binding(self, db_session, seeded_user_id):
        """TC-COV-COUN-006: Get user detail without binding returns None."""
        service = CounselorService(db_session)
        result = await service.get_user_detail(2, 1)
        assert result is None

    @pytest.mark.asyncio
    async def test_list_consultation_records_empty(self, db_session, seeded_user_id):
        """TC-COV-COUN-007: List consultation records when none exist."""
        service = CounselorService(db_session)
        result = await service.list_consultation_records(2, 1, 1, 10)
        assert result["items"] == []
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_create_group(self, db_session, seeded_user_id):
        """TC-COV-COUN-008: Create client group."""
        service = CounselorService(db_session)
        group_id = await service.create_group(2, "Test Group", "Description", "blue")
        assert group_id > 0

    @pytest.mark.asyncio
    async def test_list_groups_empty(self, db_session, seeded_user_id):
        """TC-COV-COUN-009: List groups when none exist."""
        service = CounselorService(db_session)
        result = await service.list_groups(2, 1, 10)
        assert result["items"] == []
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_add_group_member_group_not_found(self, db_session, seeded_user_id):
        """TC-COV-COUN-010: Add member to non-existent group returns False."""
        service = CounselorService(db_session)
        result = await service.add_group_member(2, 9999, 1)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_or_create_bind_code(self, db_session, seeded_user_id):
        """TC-COV-COUN-011: Get or create bind code."""
        service = CounselorService(db_session)
        code = await service.get_or_create_bind_code(2)
        assert len(code) > 0

    @pytest.mark.asyncio
    async def test_bind_by_code_invalid(self, db_session, seeded_user_id):
        """TC-COV-COUN-012: Bind with invalid code raises error."""
        service = CounselorService(db_session)
        with pytest.raises(ValueError, match="绑定码无效或已过期"):
            await service.bind_by_code(1, "INVALID")

    @pytest.mark.asyncio
    async def test_get_user_binding_none(self, db_session, seeded_user_id):
        """TC-COV-COUN-013: Get user binding when none exists."""
        service = CounselorService(db_session)
        result = await service.get_user_binding(1)
        assert result is None

    @pytest.mark.asyncio
    async def test_unbind_no_binding(self, db_session, seeded_user_id):
        """TC-COV-COUN-014: Unbind when no active binding returns False."""
        service = CounselorService(db_session)
        result = await service.unbind(1)
        assert result is False
