"""Tests for CounselorService."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.pii_crypto import compute_blind_index
from app.core.states import BindingStatus
from app.models.counselor import (
    ClientGroupMember,
)
from app.models.risk import RiskAssessment, WarningNotification
from app.models.user import User, UserCounselorBinding
from app.services.counselor_service import CounselorService


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _make_binding(
    db_session,
    user_id: int,
    counselor_id: int,
    bind_code: str,
    status: str,
    bound_at: datetime | None = None,
) -> UserCounselorBinding:
    """创建一条绑定记录并刷新, 保证 server_default 字段可用."""
    binding = UserCounselorBinding(
        user_id=user_id,
        counselor_id=counselor_id,
        bind_code=bind_code,
        status=status,
        bound_at=bound_at if bound_at is not None else _now(),
    )
    db_session.add(binding)
    await db_session.commit()
    await db_session.refresh(binding)
    return binding


async def _make_user(
    db_session,
    user_id: int,
    role: str = "user",
    status: str = "active",
    username: str | None = None,
) -> User:
    # username CHECK 约束: 3 <= LENGTH(username) <= 50
    uname = username or f"user_{user_id}"
    user = User(
        id=user_id,
        username=uname,
        email=f"u{user_id}@test.com",
        email_hash=compute_blind_index(f"u{user_id}@test.com", "email"),
        password_hash="x",
        role=role,
        status=status,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def _make_warning(
    db_session,
    user_id: int,
    counselor_id: int,
    *,
    current_level: int = 3,
    previous_level: int | None = 2,
    trigger_reason: str = "risk up",
    is_handled: bool = False,
    handle_action: str | None = None,
) -> WarningNotification:
    warning = WarningNotification(
        user_id=user_id,
        counselor_id=counselor_id,
        current_level=current_level,
        previous_level=previous_level,
        trigger_reason=trigger_reason,
        is_handled=is_handled,
        handle_action=handle_action,
    )
    db_session.add(warning)
    await db_session.commit()
    await db_session.refresh(warning)
    return warning


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
    async def test_create_consultation_record_no_binding(
        self, db_session, seeded_user_id
    ):
        """TC-COV-COUN-004: Create record without binding raises error."""
        service = CounselorService(db_session)
        with pytest.raises(ValueError, match="当前用户未绑定到该咨询师"):
            await service.create_consultation_record(2, 1, {})

    @pytest.mark.asyncio
    async def test_update_consultation_record_not_found(
        self, db_session, seeded_user_id
    ):
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


# ===========================================================================
# Extended tests below — cover remaining lines to reach 75%+ coverage
# ===========================================================================


class TestListWarningsExtended:
    """list_warnings 扩展覆盖."""

    async def test_with_warnings(self, db_session, seeded_user_id):
        """TC-COV-COUN-101: 返回告警列表 + 字段映射 (覆盖 49-68)."""
        await _make_warning(db_session, 1, 2, current_level=3, trigger_reason="risk up")
        service = CounselorService(db_session)
        result = await service.list_warnings(2, 1, 10, False)
        assert result["total"] == 1
        item = result["items"][0]
        assert item["user_id"] == 1
        assert item["risk_level"] == "high"
        assert item["status"] == "pending"
        assert item["handled_at"] is None
        assert item["handled_by"] is None
        assert "title" in item and "content" in item

    async def test_only_unhandled_filter(self, db_session, seeded_user_id):
        """TC-COV-COUN-102: only_unhandled=True 过滤已处理告警 (覆盖 41-42)."""
        # 未处理
        await _make_warning(db_session, 1, 2, is_handled=False)
        # 已处理
        await _make_warning(db_session, 1, 2, is_handled=True, handle_action="handle")
        service = CounselorService(db_session)

        result_all = await service.list_warnings(2, 1, 10, False)
        assert result_all["total"] == 2

        result_unhandled = await service.list_warnings(2, 1, 10, True)
        assert result_unhandled["total"] == 1
        # 未处理告警的 status 应为 pending
        assert result_unhandled["items"][0]["status"] == "pending"

    async def test_pagination(self, db_session, seeded_user_id):
        """TC-COV-COUN-103: 分页返回正确切片."""
        for i in range(5):
            await _make_warning(db_session, 1, 2, trigger_reason=f"r{i}")
        service = CounselorService(db_session)

        page1 = await service.list_warnings(2, 1, 2, False)
        assert page1["total"] == 5
        assert len(page1["items"]) == 2

        page2 = await service.list_warnings(2, 2, 2, False)
        assert len(page2["items"]) == 2
        assert page2["page"] == 2

        page3 = await service.list_warnings(2, 3, 2, False)
        assert len(page3["items"]) == 1

    async def test_warning_belongs_to_other_counselor(self, db_session, seeded_user_id):
        """TC-COV-COUN-104: 仅返回属于当前咨询师的告警."""
        await _make_warning(db_session, 1, 2)
        await _make_warning(db_session, 1, 3)  # counselor_id=3 (admin)
        service = CounselorService(db_session)
        result = await service.list_warnings(2, 1, 10, False)
        assert result["total"] == 1


class TestHandleWarningExtended:
    """handle_warning 扩展覆盖 - 覆盖 80-113."""

    async def test_handle_action_happy_path(self, db_session, seeded_user_id):
        """TC-COV-COUN-201: handle 动作正常处理 (覆盖 96-113)."""
        warning = await _make_warning(db_session, 1, 2, is_handled=False)
        service = CounselorService(db_session)

        result = await service.handle_warning(
            2, warning.id, "handle", "note-h", ip_address="1.1.1.1", request_id="req-1"
        )
        assert result is True

        await db_session.refresh(warning)
        assert warning.is_handled is True
        assert warning.handle_action == "handle"
        assert warning.handle_note == "note-h"
        assert warning.handled_at is not None

    async def test_ignore_action_happy_path(self, db_session, seeded_user_id):
        """TC-COV-COUN-202: ignore 动作正常处理."""
        warning = await _make_warning(db_session, 1, 2, is_handled=False)
        service = CounselorService(db_session)
        result = await service.handle_warning(2, warning.id, "ignore", None)
        assert result is True
        await db_session.refresh(warning)
        assert warning.handle_action == "ignore"

    async def test_idempotent_same_action(self, db_session, seeded_user_id):
        """TC-COV-COUN-203: 同 action 重复处理返回 True (覆盖 82-91)."""
        warning = await _make_warning(db_session, 1, 2, is_handled=False)
        service = CounselorService(db_session)

        first = await service.handle_warning(2, warning.id, "handle", "n1")
        assert first is True

        second = await service.handle_warning(2, warning.id, "handle", "n2")
        assert second is True  # 幂等

    async def test_idempotent_different_action_returns_false(
        self, db_session, seeded_user_id
    ):
        """TC-COV-COUN-204: 不同 action 重复处理返回 False (覆盖 85-90)."""
        warning = await _make_warning(db_session, 1, 2, is_handled=False)
        service = CounselorService(db_session)

        first = await service.handle_warning(2, warning.id, "handle", "n1")
        assert first is True

        second = await service.handle_warning(2, warning.id, "ignore", "n2")
        assert second is False  # 幂等性破坏

    async def test_invalid_action_returns_false(self, db_session, seeded_user_id):
        """TC-COV-COUN-205: 非法 action 返回 False (覆盖 93-94)."""
        warning = await _make_warning(db_session, 1, 2, is_handled=False)
        service = CounselorService(db_session)
        result = await service.handle_warning(2, warning.id, "invalid", None)
        assert result is False

    async def test_warning_belongs_to_other_counselor(self, db_session, seeded_user_id):
        """TC-COV-COUN-206: 告警不属于当前咨询师返回 False (覆盖 80)."""
        warning = await _make_warning(db_session, 1, 3)  # counselor_id=3
        service = CounselorService(db_session)
        result = await service.handle_warning(2, warning.id, "handle", None)
        assert result is False


class TestListMyUsersExtended:
    """list_my_users 扩展覆盖 - 覆盖 124-198."""

    async def test_with_active_binding(self, db_session, seeded_user_id):
        """TC-COV-COUN-301: 有绑定用户时返回列表 (覆盖 152-198)."""
        await _make_binding(
            db_session, 1, 2, "B001", BindingStatus.ACTIVE, bound_at=_now()
        )
        # Add a risk assessment for the user
        db_session.add(
            RiskAssessment(
                user_id=1,
                risk_score=72,
                risk_level=3,
                structured_score=72,
                models_used=["m"],
                risk_factors=[],
                assessment_type="structured",
                is_latest=True,
            )
        )
        await db_session.commit()

        service = CounselorService(db_session)
        result = await service.list_my_users(2, 1, 10)
        assert result["total"] == 1
        item = result["items"][0]
        assert item["id"] == 1
        assert item["username"] == "seed_user"
        assert item["latest_risk_level"] == 3
        assert item["latest_risk_label"] == "high"
        assert item["risk_level"] == 3
        assert item["risk_score"] == 72

    async def test_with_risk_level_filter(self, db_session, seeded_user_id):
        """TC-COV-COUN-302: 按风险等级过滤 (覆盖 124-142)."""
        await _make_binding(
            db_session, 1, 2, "B001", BindingStatus.ACTIVE, bound_at=_now()
        )
        db_session.add(
            RiskAssessment(
                user_id=1,
                risk_score=72,
                risk_level=3,
                structured_score=72,
                models_used=["m"],
                risk_factors=[],
                assessment_type="structured",
                is_latest=True,
            )
        )
        await db_session.commit()

        service = CounselorService(db_session)

        # 匹配 risk_level=3
        matched = await service.list_my_users(2, 1, 10, risk_level=3)
        assert matched["total"] == 1
        assert matched["items"][0]["id"] == 1

        # 不匹配 risk_level=1
        unmatched = await service.list_my_users(2, 1, 10, risk_level=1)
        assert unmatched["total"] == 0
        assert unmatched["items"] == []

    async def test_excludes_inactive_bindings(self, db_session, seeded_user_id):
        """TC-COV-COUN-303: 仅返回 ACTIVE 绑定用户."""
        await _make_binding(
            db_session, 1, 2, "B001", BindingStatus.INACTIVE, bound_at=_now()
        )
        service = CounselorService(db_session)
        result = await service.list_my_users(2, 1, 10)
        assert result["total"] == 0

    async def test_pagination(self, db_session, seeded_user_id):
        """TC-COV-COUN-304: 分页正确."""
        # 创建额外用户 (id 4, 5)
        await _make_user(db_session, 4, role="user")
        await _make_user(db_session, 5, role="user")
        await _make_binding(
            db_session, 1, 2, "B001", BindingStatus.ACTIVE, bound_at=_now()
        )
        await _make_binding(
            db_session, 4, 2, "B002", BindingStatus.ACTIVE, bound_at=_now()
        )
        await _make_binding(
            db_session, 5, 2, "B003", BindingStatus.ACTIVE, bound_at=_now()
        )

        service = CounselorService(db_session)
        page1 = await service.list_my_users(2, 1, 2)
        assert page1["total"] == 3
        assert len(page1["items"]) == 2
        page2 = await service.list_my_users(2, 2, 2)
        assert len(page2["items"]) == 1


class TestCreateConsultationRecordExtended:
    """create_consultation_record 扩展覆盖 - 覆盖 210-240."""

    async def test_happy_path_without_warning(self, db_session, seeded_user_id):
        """TC-COV-COUN-401: 创建咨询记录 (无 warning_id, 覆盖 216-240)."""
        await _make_binding(
            db_session, 1, 2, "B001", BindingStatus.ACTIVE, bound_at=_now()
        )
        service = CounselorService(db_session)

        record_id = await service.create_consultation_record(
            2,
            1,
            {
                "main_topics": "topic1",
                "client_status": "stable",
                "interventions": "CBT",
                "next_plan": "follow-up",
                "notes": "ok",
            },
        )
        assert record_id > 0

    async def test_with_warning_id(self, db_session, seeded_user_id):
        """TC-COV-COUN-402: 关联 warning_id 创建咨询记录 (覆盖 211-214)."""
        await _make_binding(
            db_session, 1, 2, "B001", BindingStatus.ACTIVE, bound_at=_now()
        )
        warning = await _make_warning(db_session, 1, 2)
        service = CounselorService(db_session)

        record_id = await service.create_consultation_record(
            2, 1, {"warning_id": warning.id, "main_topics": "t"}
        )
        assert record_id > 0

    async def test_warning_not_found(self, db_session, seeded_user_id):
        """TC-COV-COUN-403: warning_id 不存在抛错 (覆盖 213-214)."""
        await _make_binding(
            db_session, 1, 2, "B001", BindingStatus.ACTIVE, bound_at=_now()
        )
        service = CounselorService(db_session)
        with pytest.raises(ValueError, match="预警不存在或不属于当前咨询师用户关系"):
            await service.create_consultation_record(2, 1, {"warning_id": 9999})

    async def test_warning_belongs_to_other_counselor(self, db_session, seeded_user_id):
        """TC-COV-COUN-404: warning 属于其他咨询师抛错 (覆盖 213)."""
        await _make_binding(
            db_session, 1, 2, "B001", BindingStatus.ACTIVE, bound_at=_now()
        )
        # warning 属于 counselor 3 (admin)
        warning = await _make_warning(db_session, 1, 3)
        service = CounselorService(db_session)
        with pytest.raises(ValueError, match="预警不存在或不属于当前咨询师用户关系"):
            await service.create_consultation_record(2, 1, {"warning_id": warning.id})

    async def test_warning_belongs_to_other_user(self, db_session, seeded_user_id):
        """TC-COV-COUN-405: warning 属于其他用户抛错 (覆盖 213)."""
        await _make_user(db_session, 4, role="user")
        await _make_binding(
            db_session, 4, 2, "B004", BindingStatus.ACTIVE, bound_at=_now()
        )
        await _make_binding(
            db_session, 1, 2, "B001", BindingStatus.ACTIVE, bound_at=_now()
        )
        # warning 属于 user 4, 但调用 create_consultation_record(counselor=2, user=1, ...)
        warning = await _make_warning(db_session, 4, 2)
        service = CounselorService(db_session)
        with pytest.raises(ValueError, match="预警不存在或不属于当前咨询师用户关系"):
            await service.create_consultation_record(2, 1, {"warning_id": warning.id})


class TestUpdateConsultationRecordExtended:
    """update_consultation_record 扩展覆盖 - 覆盖 246-267."""

    async def test_happy_path(self, db_session, seeded_user_id):
        """TC-COV-COUN-501: 更新咨询记录 (覆盖 253-267)."""
        await _make_binding(
            db_session, 1, 2, "B001", BindingStatus.ACTIVE, bound_at=_now()
        )
        service = CounselorService(db_session)
        record_id = await service.create_consultation_record(
            2, 1, {"main_topics": "t1"}
        )

        ok = await service.update_consultation_record(
            2,
            1,
            record_id,
            {
                "main_topics": "t2",
                "client_status": "stable",
                "interventions": "CBT",
                "next_plan": "fu",
                "notes": "n",
            },
        )
        assert ok is True

    async def test_update_warning_id_valid(self, db_session, seeded_user_id):
        """TC-COV-COUN-502: 更新 warning_id 到合法值 (覆盖 246-252)."""
        await _make_binding(
            db_session, 1, 2, "B001", BindingStatus.ACTIVE, bound_at=_now()
        )
        warning = await _make_warning(db_session, 1, 2)
        service = CounselorService(db_session)
        record_id = await service.create_consultation_record(2, 1, {"main_topics": "t"})

        ok = await service.update_consultation_record(
            2, 1, record_id, {"warning_id": warning.id}
        )
        assert ok is True

    async def test_update_warning_id_invalid(self, db_session, seeded_user_id):
        """TC-COV-COUN-503: 更新 warning_id 到不存在值抛错 (覆盖 249-251)."""
        await _make_binding(
            db_session, 1, 2, "B001", BindingStatus.ACTIVE, bound_at=_now()
        )
        service = CounselorService(db_session)
        record_id = await service.create_consultation_record(2, 1, {"main_topics": "t"})

        with pytest.raises(ValueError, match="预警不存在或不属于当前咨询师用户关系"):
            await service.update_consultation_record(
                2, 1, record_id, {"warning_id": 9999}
            )

    async def test_update_warning_id_to_none(self, db_session, seeded_user_id):
        """TC-COV-COUN-504: 将 warning_id 设为 None (覆盖 248 分支)."""
        await _make_binding(
            db_session, 1, 2, "B001", BindingStatus.ACTIVE, bound_at=_now()
        )
        warning = await _make_warning(db_session, 1, 2)
        service = CounselorService(db_session)
        record_id = await service.create_consultation_record(
            2, 1, {"warning_id": warning.id, "main_topics": "t"}
        )

        ok = await service.update_consultation_record(
            2, 1, record_id, {"warning_id": None}
        )
        assert ok is True

    async def test_update_record_wrong_counselor(self, db_session, seeded_user_id):
        """TC-COV-COUN-505: record 属于其他咨询师返回 False."""
        await _make_binding(
            db_session, 1, 2, "B001", BindingStatus.ACTIVE, bound_at=_now()
        )
        service = CounselorService(db_session)
        record_id = await service.create_consultation_record(2, 1, {"main_topics": "t"})
        # 用 counselor 3 调用 - 不匹配
        result = await service.update_consultation_record(3, 1, record_id, {})
        assert result is False

    async def test_update_record_wrong_user(self, db_session, seeded_user_id):
        """TC-COV-COUN-506: record 属于其他用户返回 False."""
        await _make_user(db_session, 4, role="user")
        await _make_binding(
            db_session, 1, 2, "B001", BindingStatus.ACTIVE, bound_at=_now()
        )
        await _make_binding(
            db_session, 4, 2, "B004", BindingStatus.ACTIVE, bound_at=_now()
        )
        service = CounselorService(db_session)
        record_id = await service.create_consultation_record(2, 1, {"main_topics": "t"})
        # 用 user 4 调用 - 不匹配
        result = await service.update_consultation_record(2, 4, record_id, {})
        assert result is False


class TestGetUserDetailExtended:
    """get_user_detail 扩展覆盖 - 覆盖 278-299."""

    async def test_happy_path_with_risk(self, db_session, seeded_user_id):
        """TC-COV-COUN-601: 返回用户详情 + 最新风险评估 (覆盖 278-299)."""
        await _make_binding(
            db_session, 1, 2, "B001", BindingStatus.ACTIVE, bound_at=_now()
        )
        db_session.add(
            RiskAssessment(
                user_id=1,
                risk_score=80,
                risk_level=4,
                structured_score=80,
                models_used=["m"],
                risk_factors=[],
                assessment_type="structured",
                is_latest=True,
            )
        )
        await db_session.commit()

        service = CounselorService(db_session)
        result = await service.get_user_detail(2, 1)
        assert result is not None
        assert result["id"] == 1
        assert result["username"] == "seed_user"
        assert result["latest_risk_level"] == 4
        assert result["latest_risk_label"] == "critical"
        assert result["risk_level"] == 4
        assert result["risk_score"] == 80

    async def test_no_risk_assessment(self, db_session, seeded_user_id):
        """TC-COV-COUN-602: 用户无风险评估返回 none."""
        await _make_binding(
            db_session, 1, 2, "B001", BindingStatus.ACTIVE, bound_at=_now()
        )
        service = CounselorService(db_session)
        result = await service.get_user_detail(2, 1)
        assert result is not None
        assert result["latest_risk_level"] is None
        assert result["latest_risk_label"] == "none"
        assert result["risk_level"] == 0


class TestListConsultationRecordsExtended:
    """list_consultation_records 扩展覆盖 - 覆盖 310-348."""

    async def test_with_records_and_warning(self, db_session, seeded_user_id):
        """TC-COV-COUN-701: 返回记录 + 关联 warning (覆盖 318-348)."""
        await _make_binding(
            db_session, 1, 2, "B001", BindingStatus.ACTIVE, bound_at=_now()
        )
        warning = await _make_warning(
            db_session, 1, 2, is_handled=True, handle_action="handle"
        )
        service = CounselorService(db_session)
        record_id = await service.create_consultation_record(
            2, 1, {"warning_id": warning.id, "main_topics": "t", "notes": "n"}
        )

        result = await service.list_consultation_records(2, 1, 1, 10)
        assert result["total"] == 1
        item = result["items"][0]
        assert item["id"] == record_id
        assert item["warning_id"] == warning.id
        assert item["warning_status"] == "handled"
        assert item["warning_risk_level"] == "high"
        assert item["main_topics"] == "t"

    async def test_pagination(self, db_session, seeded_user_id):
        """TC-COV-COUN-702: 分页正确."""
        await _make_binding(
            db_session, 1, 2, "B001", BindingStatus.ACTIVE, bound_at=_now()
        )
        service = CounselorService(db_session)
        for i in range(3):
            await service.create_consultation_record(2, 1, {"main_topics": f"t{i}"})

        page1 = await service.list_consultation_records(2, 1, 1, 2)
        assert page1["total"] == 3
        assert len(page1["items"]) == 2

        page2 = await service.list_consultation_records(2, 1, 2, 2)
        assert len(page2["items"]) == 1


class TestListGroupsExtended:
    """list_groups 扩展覆盖 - 覆盖 372-402."""

    async def test_with_groups_and_members(self, db_session, seeded_user_id):
        """TC-COV-COUN-801: 返回分组 + 成员计数 (覆盖 376-402)."""
        service = CounselorService(db_session)
        g1 = await service.create_group(2, "G1", "d1", "blue")
        g2 = await service.create_group(2, "G2", "d2", "red")

        # 添加绑定 + 成员
        await _make_binding(
            db_session, 1, 2, "B001", BindingStatus.ACTIVE, bound_at=_now()
        )
        await _make_user(db_session, 4, role="user")
        await _make_binding(
            db_session, 4, 2, "B004", BindingStatus.ACTIVE, bound_at=_now()
        )

        db_session.add(ClientGroupMember(group_id=g1, user_id=1))
        db_session.add(ClientGroupMember(group_id=g1, user_id=4))
        db_session.add(ClientGroupMember(group_id=g2, user_id=1))
        await db_session.commit()

        result = await service.list_groups(2, 1, 10)
        assert result["total"] == 2
        # 按 id desc 排序, g2 在前
        items = {it["id"]: it for it in result["items"]}
        assert items[g1]["user_count"] == 2
        assert items[g2]["user_count"] == 1

    async def test_pagination(self, db_session, seeded_user_id):
        """TC-COV-COUN-802: 分页正确."""
        service = CounselorService(db_session)
        for i in range(5):
            await service.create_group(2, f"G{i}", None, "blue")

        page1 = await service.list_groups(2, 1, 2)
        assert page1["total"] == 5
        assert len(page1["items"]) == 2

        page3 = await service.list_groups(2, 3, 2)
        assert len(page3["items"]) == 1


class TestAddGroupMemberExtended:
    """add_group_member 扩展覆盖 - 覆盖 411-447."""

    async def test_happy_path(self, db_session, seeded_user_id):
        """TC-COV-COUN-901: 正常添加成员 (覆盖 429-447)."""
        service = CounselorService(db_session)
        group_id = await service.create_group(2, "G1", "d", "blue")
        await _make_binding(
            db_session, 1, 2, "B001", BindingStatus.ACTIVE, bound_at=_now()
        )

        result = await service.add_group_member(2, group_id, 1)
        assert result is True

        # 验证成员已加入
        from sqlalchemy import select

        member = (
            await db_session.execute(
                select(ClientGroupMember).where(
                    ClientGroupMember.group_id == group_id,
                    ClientGroupMember.user_id == 1,
                )
            )
        ).scalar_one_or_none()
        assert member is not None

    async def test_group_belongs_to_other_counselor(self, db_session, seeded_user_id):
        """TC-COV-COUN-902: 分组不属于当前咨询师返回 False (覆盖 406-407)."""
        service = CounselorService(db_session)
        group_id = await service.create_group(2, "G1", "d", "blue")
        # 用 counselor 3 (admin) 调用
        result = await service.add_group_member(3, group_id, 1)
        assert result is False

    async def test_no_active_binding_returns_false(self, db_session, seeded_user_id):
        """TC-COV-COUN-903: 用户未与咨询师建立绑定返回 False (覆盖 411-419)."""
        service = CounselorService(db_session)
        group_id = await service.create_group(2, "G1", "d", "blue")
        # 无绑定关系
        result = await service.add_group_member(2, group_id, 1)
        assert result is False

    async def test_inactive_binding_returns_false(self, db_session, seeded_user_id):
        """TC-COV-COUN-904: 仅 INACTIVE 绑定返回 False."""
        service = CounselorService(db_session)
        group_id = await service.create_group(2, "G1", "d", "blue")
        await _make_binding(
            db_session, 1, 2, "B001", BindingStatus.INACTIVE, bound_at=_now()
        )
        result = await service.add_group_member(2, group_id, 1)
        assert result is False

    async def test_already_member_returns_true(self, db_session, seeded_user_id):
        """TC-COV-COUN-905: 已是成员返回 True (覆盖 425-427)."""
        service = CounselorService(db_session)
        group_id = await service.create_group(2, "G1", "d", "blue")
        await _make_binding(
            db_session, 1, 2, "B001", BindingStatus.ACTIVE, bound_at=_now()
        )

        first = await service.add_group_member(2, group_id, 1)
        assert first is True

        # 再次添加相同成员
        second = await service.add_group_member(2, group_id, 1)
        assert second is True


class TestGetOrCreateBindCodeExtended:
    """get_or_create_bind_code 扩展覆盖 - 覆盖 469-510."""

    async def test_idempotent_returns_existing_code(self, db_session, seeded_user_id):
        """TC-COV-COUN-1001: 已有 placeholder 时直接返回 (覆盖 469-470)."""
        service = CounselorService(db_session)
        code1 = await service.get_or_create_bind_code(2)
        code2 = await service.get_or_create_bind_code(2)
        assert code1 == code2

    async def test_creates_new_placeholder(self, db_session, seeded_user_id):
        """TC-COV-COUN-1002: 无 placeholder 时创建新绑定."""
        service = CounselorService(db_session)
        code = await service.get_or_create_bind_code(2)
        assert code is not None
        assert 4 <= len(code) <= 10

        # 验证 DB 中有占位绑定
        from sqlalchemy import select

        binding = (
            await db_session.execute(
                select(UserCounselorBinding).where(
                    UserCounselorBinding.counselor_id == 2,
                    UserCounselorBinding.user_id == 2,
                    UserCounselorBinding.status == BindingStatus.PLACEHOLDER,
                )
            )
        ).scalar_one_or_none()
        assert binding is not None
        assert binding.bind_code == code


class TestRefreshBindCode:
    """refresh_bind_code 全方法覆盖 - 覆盖 520-574."""

    async def test_with_existing_placeholder(self, db_session, seeded_user_id):
        """TC-COV-COUN-1101: 已有 placeholder 时刷新 code (覆盖 557-573)."""
        service = CounselorService(db_session)
        # 先创建 placeholder
        old_code = await service.get_or_create_bind_code(2)

        # 刷新
        new_code = await service.refresh_bind_code(2)

        assert new_code is not None
        assert new_code != old_code
        assert 4 <= len(new_code) <= 10

    async def test_without_existing_placeholder(self, db_session, seeded_user_id):
        """TC-COV-COUN-1102: 无 placeholder 时创建新绑定 (覆盖 534-556)."""
        service = CounselorService(db_session)
        # 直接调用 refresh (没有 pre-existing placeholder)
        new_code = await service.refresh_bind_code(2)
        assert new_code is not None
        assert 4 <= len(new_code) <= 10

        # 验证 DB 中有占位绑定
        from sqlalchemy import select

        binding = (
            await db_session.execute(
                select(UserCounselorBinding).where(
                    UserCounselorBinding.counselor_id == 2,
                    UserCounselorBinding.user_id == 2,
                    UserCounselorBinding.status == BindingStatus.PLACEHOLDER,
                )
            )
        ).scalar_one_or_none()
        assert binding is not None
        assert binding.bind_code == new_code

    async def test_refresh_twice_changes_code(self, db_session, seeded_user_id):
        """TC-COV-COUN-1103: 连续刷新 code 应不同."""
        service = CounselorService(db_session)
        code1 = await service.refresh_bind_code(2)
        code2 = await service.refresh_bind_code(2)
        assert code1 != code2


class TestBindByCodeExtended:
    """bind_by_code 扩展覆盖 - 覆盖 605-695."""

    async def test_happy_path_placeholder_to_active(self, db_session, seeded_user_id):
        """TC-COV-COUN-1201: 占位绑定转 ACTIVE 成功 (覆盖 605-695)."""
        service = CounselorService(db_session)
        code = await service.get_or_create_bind_code(2)

        result = await service.bind_by_code(1, code)
        assert result["counselor_id"] == 2
        assert result["status"] == "active"
        assert result["bind_code_status"] == "active"
        assert result["counselor_name"] == "counselor"
        assert "binding_id" in result
        assert "bound_at" in result

    async def test_reactivate_existing_inactive_binding(
        self, db_session, seeded_user_id
    ):
        """TC-COV-COUN-1202: 已存在历史绑定时激活它 (覆盖 635-650)."""
        # 创建历史 INACTIVE 绑定 (user 1, counselor 2)
        await _make_binding(
            db_session,
            1,
            2,
            "OLDB1",
            BindingStatus.INACTIVE,
            bound_at=_now(),
        )
        # 为 counselor 2 创建 placeholder
        service = CounselorService(db_session)
        code = await service.get_or_create_bind_code(2)

        result = await service.bind_by_code(1, code)
        assert result["counselor_id"] == 2
        assert result["status"] == "active"

    async def test_already_bound_same_counselor_raises(
        self, db_session, seeded_user_id
    ):
        """TC-COV-COUN-1203: 已绑定该咨询师抛错 (覆盖 622-624)."""
        # 创建 ACTIVE 绑定 user1 -> counselor2
        await _make_binding(
            db_session,
            1,
            2,
            "ACTIVE1",
            BindingStatus.ACTIVE,
            bound_at=_now(),
        )
        # 创建 placeholder for counselor 2
        service = CounselorService(db_session)
        code = await service.get_or_create_bind_code(2)

        with pytest.raises(ValueError, match="您已绑定该咨询师，无需重复绑定"):
            await service.bind_by_code(1, code)

    async def test_already_bound_other_counselor_raises(
        self, db_session, seeded_user_id
    ):
        """TC-COV-COUN-1204: 已绑定其他咨询师抛错 (覆盖 622-625)."""
        # 创建 ACTIVE 绑定 user1 -> counselor3 (admin, 作为占位)
        await _make_binding(
            db_session,
            1,
            3,
            "ACTIVE3",
            BindingStatus.ACTIVE,
            bound_at=_now(),
        )
        # 创建 placeholder for counselor 2
        service = CounselorService(db_session)
        code = await service.get_or_create_bind_code(2)

        with pytest.raises(ValueError, match="您已绑定其他咨询师"):
            await service.bind_by_code(1, code)

    async def test_counselor_inactive_raises(self, db_session, seeded_user_id):
        """TC-COV-COUN-1205: 咨询师停用抛错 (覆盖 627-629)."""
        # 创建一个 inactive counselor
        await _make_user(
            db_session, 4, role="counselor", status="inactive", username="ic_test"
        )
        # 为 counselor 4 创建 placeholder
        service = CounselorService(db_session)
        code = await service.get_or_create_bind_code(4)

        with pytest.raises(ValueError, match="绑定的咨询师不存在或已停用"):
            await service.bind_by_code(1, code)

    async def test_active_binding_reuses_code(self, db_session, seeded_user_id):
        """TC-COV-COUN-1206: ACTIVE 绑定可被复用绑定 (覆盖 659-670).

        场景: 占位绑定的 status 已是 ACTIVE (特殊路径), 走 else 分支.
        """
        # 直接创建一个 ACTIVE 占位绑定 (user_id=counselor_id, status=ACTIVE)
        await _make_binding(
            db_session,
            2,
            2,
            "REUSE1",
            BindingStatus.ACTIVE,
            bound_at=_now(),
        )
        service = CounselorService(db_session)
        # user 1 用此 code 绑定 - 应走 else 分支创建新 binding
        result = await service.bind_by_code(1, "REUSE1")
        assert result["counselor_id"] == 2
        assert result["status"] == "active"


class TestGetUserBindingExtended:
    """get_user_binding 扩展覆盖 - 覆盖 712-721."""

    async def test_happy_path(self, db_session, seeded_user_id):
        """TC-COV-COUN-1301: 返回用户当前绑定 (覆盖 712-721)."""
        await _make_binding(
            db_session,
            1,
            2,
            "B001",
            BindingStatus.ACTIVE,
            bound_at=_now(),
        )
        service = CounselorService(db_session)
        result = await service.get_user_binding(1)
        assert result is not None
        assert result["counselor_id"] == 2
        assert result["counselor_name"] == "counselor"
        assert result["status"] == "active"
        assert "bound_at" in result
        assert result["binding_id"] > 0

    async def test_excludes_self_placeholder(self, db_session, seeded_user_id):
        """TC-COV-COUN-1302: 排除 user_id == counselor_id 的占位绑定."""
        # placeholder for counselor 2 (user_id=2)
        await _make_binding(
            db_session,
            2,
            2,
            "PH01",
            BindingStatus.PLACEHOLDER,
            bound_at=_now(),
        )
        service = CounselorService(db_session)
        # 查 user 1 - 无 ACTIVE 绑定
        result = await service.get_user_binding(1)
        assert result is None


class TestUnbindExtended:
    """unbind 扩展覆盖 - 覆盖 738-751."""

    async def test_happy_path(self, db_session, seeded_user_id):
        """TC-COV-COUN-1401: 解绑成功 (覆盖 738-751)."""
        await _make_binding(
            db_session,
            1,
            2,
            "B001",
            BindingStatus.ACTIVE,
            bound_at=_now(),
        )
        service = CounselorService(db_session)
        result = await service.unbind(1)
        assert result is True

        # 验证状态已变更
        from sqlalchemy import select

        binding = (
            await db_session.execute(
                select(UserCounselorBinding).where(
                    UserCounselorBinding.user_id == 1,
                    UserCounselorBinding.counselor_id == 2,
                )
            )
        ).scalar_one_or_none()
        assert binding is not None
        assert binding.status == BindingStatus.INACTIVE
        assert binding.unbound_at is not None

    async def test_unbind_after_unbind_returns_false(self, db_session, seeded_user_id):
        """TC-COV-COUN-1402: 解绑后再解绑返回 False."""
        await _make_binding(
            db_session,
            1,
            2,
            "B001",
            BindingStatus.ACTIVE,
            bound_at=_now(),
        )
        service = CounselorService(db_session)

        first = await service.unbind(1)
        assert first is True

        second = await service.unbind(1)
        assert second is False
