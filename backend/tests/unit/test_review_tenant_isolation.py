"""P0-FIX-2026-10-11: 复核任务与危机事件必须做租户隔离（服务层强制）。

背景（来自 2026-10-11 全量源码审查）：

``review_tasks`` 与 ``crisis_events`` 两张表**都没有 tenant_id 列**
（见 ``app/models/review.py``），租户归属只能沿 ``user_id`` JOIN ``users``
推导。修复前 ReviewService / CrisisEventService 的所有读写端点都是
裸 ``select(...)`` 按主键取记录，其后果：

* **读**：租户 A 的管理员凭任意 ``review_id`` 读到租户 B 学生的
  ``resolution_note``（咨询师手写记录，属敏感个人信息）。
* **写**：更严重——``crisis-events/{id}/close`` 能把**他校学生**的危机事件
  置为 ``resolved`` 终态。resolved 是终态不可再开启，等于让真实发生的
  危机被静默关闭。这是 P0 而非 P1 的原因。

本文件直接调用**真实**服务方法（不经过 ``tests/unit/test_review_service.py``
里的 tenant_id=1 适配层），显式传入不同 tenant_id，验证隔离真实生效。
"""

from __future__ import annotations

import pytest

from app.core.pii_crypto import compute_blind_index
from app.core.security import get_password_hash
from app.models.user import User
from app.schemas.review import (
    CrisisEventCreate,
    ReviewPriority,
    ReviewTaskCreate,
    ReviewTaskFilter,
)
from app.services.review_service import CrisisEventService, ReviewService

OTHER_TENANT_ID = 2


@pytest.fixture
async def other_tenant_student(db_session):
    """在租户 2 下造一个学生用户，返回其 id。"""
    pwd = get_password_hash("testpass123")
    user = User(
        id=9001,
        username="tenant2_student",
        email="t2@test.com",
        email_hash=compute_blind_index("t2@test.com", "email"),
        password_hash=pwd,
        role="user",
        status="active",
        tenant_id=OTHER_TENANT_ID,
    )
    db_session.add(user)
    await db_session.flush()
    return user.id


@pytest.fixture
def review_service(db_session, seeded_user_id):
    return ReviewService(db_session)


@pytest.fixture
def crisis_service(db_session, seeded_user_id):
    return CrisisEventService(db_session)


class TestReviewTaskTenantIsolation:
    """ReviewService 各端点的租户隔离。"""

    async def test_get_reviews_excludes_other_tenant(
        self, review_service, seeded_user_id, other_tenant_student
    ):
        await review_service.create_review_task(
            ReviewTaskCreate(user_id=seeded_user_id, risk_level=3, risk_score=70.0)
        )
        await review_service.create_review_task(
            ReviewTaskCreate(
                user_id=other_tenant_student, risk_level=4, risk_score=90.0
            )
        )

        mine = await review_service.get_reviews(ReviewTaskFilter(), tenant_id=1)
        assert all(i.user_id == seeded_user_id for i in mine.items)
        assert mine.total == 1, "租户 2 的复核任务泄漏进租户 1 的列表"

    async def test_get_review_by_id_returns_none_for_other_tenant(
        self, review_service, seeded_user_id, other_tenant_student
    ):
        task = await review_service.create_review_task(
            ReviewTaskCreate(
                user_id=other_tenant_student,
                risk_level=4,
                risk_score=90.0,
                priority=ReviewPriority.CRISIS_REVIEW,
            )
        )

        got = await review_service.get_review_by_id(task.id, tenant_id=1)
        assert got is None, "跨租户按 id 直读复核任务未被拦截"

        # 同租户可见（证明上一步不是「查不到」而是「被过滤」）
        own = await review_service.get_review_by_id(task.id, tenant_id=OTHER_TENANT_ID)
        assert own is not None

    async def test_assign_review_rejects_other_tenant(
        self, review_service, other_tenant_student
    ):
        task = await review_service.create_review_task(
            ReviewTaskCreate(user_id=other_tenant_student, risk_level=4, risk_score=95.0)
        )

        with pytest.raises(ValueError, match="not found"):
            await review_service.assign_review(task.id, 2, tenant_id=1)

        # 状态未被改动
        fresh = await review_service.get_review_by_id(
            task.id, tenant_id=OTHER_TENANT_ID
        )
        assert fresh.status == "pending"
        assert fresh.assigned_to is None

    async def test_resolve_review_rejects_other_tenant(
        self, review_service, other_tenant_student
    ):
        task = await review_service.create_review_task(
            ReviewTaskCreate(user_id=other_tenant_student, risk_level=4, risk_score=95.0)
        )

        with pytest.raises(ValueError, match="not found"):
            await review_service.resolve_review(task.id, 2, "越权处理", tenant_id=1)

        fresh = await review_service.get_review_by_id(
            task.id, tenant_id=OTHER_TENANT_ID
        )
        assert fresh.status == "pending", "跨租户 resolve 改写了任务状态"

    async def test_escalate_review_rejects_other_tenant(
        self, review_service, other_tenant_student
    ):
        task = await review_service.create_review_task(
            ReviewTaskCreate(user_id=other_tenant_student, risk_level=4, risk_score=95.0)
        )

        with pytest.raises(ValueError, match="not found"):
            await review_service.escalate_review(task.id, 2, "越权升级", tenant_id=1)

        fresh = await review_service.get_review_by_id(
            task.id, tenant_id=OTHER_TENANT_ID
        )
        assert fresh.status == "pending"

    async def test_admin_path_also_blocked_cross_tenant(
        self, review_service, other_tenant_student
    ):
        """is_admin=True 只豁免「同租户内的 owner 校验」，不豁免租户隔离。

        这是本条修复最容易被后续改动误伤的地方：若有人把
        ``if not is_admin`` 直接套在租户校验外层，管理员就能跨租户处理。
        """
        task = await review_service.create_review_task(
            ReviewTaskCreate(user_id=other_tenant_student, risk_level=4, risk_score=95.0)
        )

        with pytest.raises(ValueError, match="not found"):
            await review_service.resolve_review(
                task.id, 3, "admin 越权", is_admin=True, tenant_id=1
            )

    async def test_review_stats_excludes_other_tenant(
        self, review_service, seeded_user_id, other_tenant_student
    ):
        await review_service.create_review_task(
            ReviewTaskCreate(
                user_id=other_tenant_student,
                risk_level=4,
                risk_score=95.0,
                crisis_override=True,
            )
        )

        stats = await review_service.get_review_stats(tenant_id=1)
        assert stats.total == 0, "跨租户任务被计入统计（可反推他校危机规模）"
        assert stats.crisis_count == 0


class TestCrisisEventTenantIsolation:
    """CrisisEventService 三个写端点的租户隔离（最高敏感级数据）。"""

    @staticmethod
    async def _make_event(crisis_service, user_id):
        return await crisis_service.record_crisis_event(
            CrisisEventCreate(
                user_id=user_id,
                trigger_source="text",
                crisis_keywords=["自杀"],
                crisis_score=0.95,
                input_summary="用户表达自杀意愿",
            )
        )

    async def test_handle_rejects_other_tenant(
        self, crisis_service, other_tenant_student
    ):
        event = await self._make_event(crisis_service, other_tenant_student)

        with pytest.raises(ValueError, match="not found"):
            await crisis_service.handle_crisis_event(
                event.id, 2, "notify_counselor", tenant_id=1
            )

        fresh = await crisis_service._get_crisis_event_scoped(
            event.id, OTHER_TENANT_ID
        )
        assert fresh.status == "detected", "跨租户改写了危机事件状态"

    async def test_escalate_rejects_other_tenant(
        self, crisis_service, other_tenant_student
    ):
        event = await self._make_event(crisis_service, other_tenant_student)

        with pytest.raises(ValueError, match="not found"):
            await crisis_service.escalate_crisis_event(
                event.id, 2, "越权升级", tenant_id=1
            )

        fresh = await crisis_service._get_crisis_event_scoped(
            event.id, OTHER_TENANT_ID
        )
        assert fresh.status == "detected"

    async def test_close_rejects_other_tenant(
        self, crisis_service, other_tenant_student
    ):
        """resolved 是终态 —— 跨租户关闭的后果最重。"""
        event = await self._make_event(crisis_service, other_tenant_student)

        with pytest.raises(ValueError, match="not found"):
            await crisis_service.close_crisis_event(event.id, 2, "越权关闭", tenant_id=1)

        fresh = await crisis_service._get_crisis_event_scoped(
            event.id, OTHER_TENANT_ID
        )
        assert fresh.status == "detected", "危机事件被跨租户静默关闭"
        assert fresh.handled_by is None


class TestTenantIdIsRequired:
    """``tenant_id`` 必须是必填参数 —— 漏传要编译期失败，而不是静默全量返回。"""

    async def test_get_review_by_id_requires_tenant_id(self, review_service):
        with pytest.raises(TypeError):
            await review_service.get_review_by_id(1)  # type: ignore[call-arg]

    async def test_get_reviews_requires_tenant_id(self, review_service):
        with pytest.raises(TypeError):
            await review_service.get_reviews(ReviewTaskFilter())  # type: ignore[call-arg]

    async def test_assign_review_requires_tenant_id(self, review_service):
        with pytest.raises(TypeError):
            await review_service.assign_review(1, 2)  # type: ignore[call-arg]

    async def test_handle_crisis_event_requires_tenant_id(self, crisis_service):
        with pytest.raises(TypeError):
            await crisis_service.handle_crisis_event(1, 2, "resolved")  # type: ignore[call-arg]

    async def test_close_crisis_event_requires_tenant_id(self, crisis_service):
        with pytest.raises(TypeError):
            await crisis_service.close_crisis_event(1, 2)  # type: ignore[call-arg]

    async def test_get_review_stats_requires_tenant_id(self, review_service):
        with pytest.raises(TypeError):
            await review_service.get_review_stats()  # type: ignore[call-arg]
