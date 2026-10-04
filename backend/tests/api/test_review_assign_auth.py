"""AUDIT-2026-10-01 (P1-1) 回归：POST /reviews/{review_id}/assign 的归属校验.

**修复前**：该端点只校验 ``review.handle`` 权限，无任何归属校验 —— 任何持有该权限
的角色都能凭一个 ``review_id`` 把任意复核任务据为己有（``assigned_to`` → 自己、
``status`` → ``in_review``），从而使后续 ``get_review`` / ``resolve_review`` /
``escalate_review`` 的 owner 校验全部失效。

**修复后语义**：

- counselor：只能「领取」已绑定给自己的学生的任务（``user_counselor_bindings``），
  未绑定 → 403；尝试代他人分配 → 403。
- admin / super_admin：可把任务分配给任意咨询师（body ``assignee_id``），
  不传则接管给自己。
"""

from __future__ import annotations

import secrets

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.states import BindingStatus
from app.models.review import ReviewTask
from app.models.user import User, UserCounselorBinding
from app.schemas.review import ReviewPriority, ReviewTaskCreate
from app.services.review_service import ReviewService

# conftest.seeded_user_id 预置: 1=user(学生) 2=counselor 3=admin
STUDENT_ID = 1
ADMIN_ID = 3
COUNSELOR_BOUND = 2
COUNSELOR_UNBOUND = 99  # 无绑定关系；未绑定路径不会写入 DB，无需真实用户


async def _seed_pending_task(db_session, user_id: int = STUDENT_ID) -> int:
    """创建一个 pending 复核任务，返回其 id."""
    service = ReviewService(db_session)
    task = await service.create_review_task(
        ReviewTaskCreate(
            user_id=user_id,
            risk_level=3,
            risk_score=75.0,
            review_triggers=["SINGLE_MODEL_HIGH"],
            priority=ReviewPriority.HIGH_RISK_REVIEW,
        )
    )
    return task.id


async def _bind_counselor(
    db_session,
    counselor_id: int,
    student_id: int = STUDENT_ID,
    status: str = BindingStatus.ACTIVE,
) -> None:
    """建立一条咨询师-学生绑定记录."""
    db_session.add(
        UserCounselorBinding(
            user_id=student_id,
            counselor_id=counselor_id,
            bind_code=secrets.token_hex(3).upper(),
            status=status,
        )
    )
    await db_session.commit()


async def _reload(db_session, task_id: int) -> ReviewTask:
    # 端点用的是另一个 session（override 的 get_db）；expire_all 保证读到 DB 现值，
    # 而不是 identity map 里创建时那个陈旧对象。
    db_session.expire_all()
    return (
        await db_session.execute(select(ReviewTask).where(ReviewTask.id == task_id))
    ).scalar_one()


class TestCounselorClaimGuard:
    """咨询师「领取」路径的归属校验。"""

    async def test_unbound_counselor_cannot_claim(
        self, client: TestClient, as_role, db_session, seeded_user_id
    ) -> None:
        """未绑定该学生的咨询师 → 403，且任务状态未被改动（没被夺取）。"""
        task_id = await _seed_pending_task(db_session)
        await _bind_counselor(db_session, COUNSELOR_BOUND)  # 绑定的是另一位咨询师

        as_role("counselor", COUNSELOR_UNBOUND)
        resp = client.post(f"/api/v1/reviews/{task_id}/assign")

        assert resp.status_code == 403
        task = await _reload(db_session, task_id)
        assert task.assigned_to is None
        assert task.status == "pending"

    async def test_inactive_binding_cannot_claim(
        self, client: TestClient, as_role, db_session, seeded_user_id
    ) -> None:
        """绑定已失效（status != active）→ 403。"""
        task_id = await _seed_pending_task(db_session)
        await _bind_counselor(db_session, COUNSELOR_BOUND, status=BindingStatus.INACTIVE)

        as_role("counselor", COUNSELOR_BOUND)
        resp = client.post(f"/api/v1/reviews/{task_id}/assign")

        assert resp.status_code == 403
        assert (await _reload(db_session, task_id)).assigned_to is None

    async def test_bound_counselor_can_claim(
        self, client: TestClient, as_role, db_session, seeded_user_id
    ) -> None:
        """已绑定该学生的咨询师 → 200，任务归属自己且进入 in_review。"""
        task_id = await _seed_pending_task(db_session)
        await _bind_counselor(db_session, COUNSELOR_BOUND)

        as_role("counselor", COUNSELOR_BOUND)
        resp = client.post(f"/api/v1/reviews/{task_id}/assign")

        assert resp.status_code == 200
        task = await _reload(db_session, task_id)
        assert task.assigned_to == COUNSELOR_BOUND
        assert task.status == "in_review"

    async def test_counselor_cannot_assign_to_another(
        self, client: TestClient, as_role, db_session, seeded_user_id
    ) -> None:
        """咨询师显式指定他人为受理人 → 403（不允许代他人分配）。"""
        task_id = await _seed_pending_task(db_session)
        await _bind_counselor(db_session, COUNSELOR_BOUND)

        as_role("counselor", COUNSELOR_BOUND)
        resp = client.post(
            f"/api/v1/reviews/{task_id}/assign", json={"assignee_id": 42}
        )

        assert resp.status_code == 403
        assert (await _reload(db_session, task_id)).assigned_to is None


class TestGuardNecessity:
    """元测试：证明 403 确由绑定守卫产生，去掉守卫即复现改前的越权。"""

    async def test_removing_guard_reproduces_pre_fix_escalation(
        self, client: TestClient, as_role, db_session, seeded_user_id, monkeypatch
    ) -> None:
        """把守卫替换成 no-op 后，未绑定咨询师同样能夺取任务（= 改前行为）。

        本用例的价值不在"验证现有实现"，而在于给出**改前/改后对照证据**：
        同一个请求，守卫存在时是 403 且任务纹丝不动；守卫消失时是 200 且
        ``assigned_to`` 变成调用者 —— 说明 P1-1 的越权确实源于缺失该校验。
        """
        from app.api.v1 import review as review_module

        async def _noop(db: object, counselor_id: int, student_id: int) -> None:
            return None

        monkeypatch.setattr(review_module, "_ensure_counselor_bound_to_student", _noop)

        task_id = await _seed_pending_task(db_session)

        as_role("counselor", COUNSELOR_UNBOUND)
        resp = client.post(f"/api/v1/reviews/{task_id}/assign")

        assert resp.status_code == 200
        task = await _reload(db_session, task_id)
        assert task.assigned_to == COUNSELOR_UNBOUND
        assert task.status == "in_review"


class TestAdminAssignPath:
    """管理员分配路径（不受绑定关系约束）。"""

    async def test_admin_can_claim_without_assignee(
        self, client: TestClient, as_role, db_session, seeded_user_id
    ) -> None:
        """管理员不带 body → 接管给自己（原行为保持）。"""
        task_id = await _seed_pending_task(db_session)

        as_role("admin", ADMIN_ID)
        resp = client.post(f"/api/v1/reviews/{task_id}/assign")

        assert resp.status_code == 200
        assert (await _reload(db_session, task_id)).assigned_to == ADMIN_ID

    async def test_admin_can_assign_to_specific_counselor(
        self, client: TestClient, as_role, db_session, seeded_user_id
    ) -> None:
        """管理员用 assignee_id 指定分配给某咨询师 → 200，归属该咨询师。"""
        task_id = await _seed_pending_task(db_session)

        as_role("admin", ADMIN_ID)
        resp = client.post(
            f"/api/v1/reviews/{task_id}/assign",
            json={"assignee_id": COUNSELOR_BOUND},
        )

        assert resp.status_code == 200
        assert (await _reload(db_session, task_id)).assigned_to == COUNSELOR_BOUND

    async def test_super_admin_can_assign(
        self, client: TestClient, as_role, db_session, seeded_user_id
    ) -> None:
        """平台管理员（super_admin）同样可分配。"""
        task_id = await _seed_pending_task(db_session)

        as_role("super_admin", ADMIN_ID)
        resp = client.post(
            f"/api/v1/reviews/{task_id}/assign",
            json={"assignee_id": COUNSELOR_BOUND},
        )

        assert resp.status_code == 200
        assert (await _reload(db_session, task_id)).assigned_to == COUNSELOR_BOUND


class TestAssignEdgeCases:
    """边界与权限。"""

    async def test_unknown_review_returns_404(
        self, client: TestClient, as_role, db_session, seeded_user_id
    ) -> None:
        """不存在的 review_id → 404（不再是 400）。"""
        as_role("admin", ADMIN_ID)
        resp = client.post("/api/v1/reviews/999999/assign")
        assert resp.status_code == 404

    async def test_plain_user_forbidden(
        self, client: TestClient, as_role, db_session, seeded_user_id
    ) -> None:
        """普通用户没有 review.handle 权限 → 403。"""
        task_id = await _seed_pending_task(db_session)

        as_role("user", STUDENT_ID)
        resp = client.post(f"/api/v1/reviews/{task_id}/assign")

        assert resp.status_code == 403
        assert (await _reload(db_session, task_id)).assigned_to is None

    async def test_assignee_id_must_be_positive(
        self, client: TestClient, as_role, db_session, seeded_user_id
    ) -> None:
        """assignee_id 非正整数 → 422（schema 约束）。"""
        task_id = await _seed_pending_task(db_session)

        as_role("admin", ADMIN_ID)
        resp = client.post(
            f"/api/v1/reviews/{task_id}/assign", json={"assignee_id": 0}
        )

        assert resp.status_code == 422


class TestAssignableCounselorsEndpoint:
    """`GET /reviews/assignable-counselors`：管理员指定分配所需的候选名单数据源。"""

    async def test_admin_gets_only_active_counselors(
        self, client: TestClient, as_role, db_session, seeded_user_id
    ) -> None:
        """只返回 active 的 counselor —— 不含 user(1) / admin(3)。"""
        as_role("admin", ADMIN_ID)
        resp = client.get("/api/v1/reviews/assignable-counselors")

        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        ids = [i["id"] for i in items]
        assert COUNSELOR_BOUND in ids          # id=2 是 active counselor
        assert STUDENT_ID not in ids           # id=1 是 user
        assert ADMIN_ID not in ids             # id=3 是 admin
        assert set(items[0]) >= {"id", "username", "role", "nickname"}

    async def test_inactive_counselor_excluded(
        self, client: TestClient, as_role, db_session, seeded_user_id
    ) -> None:
        """停用的咨询师不出现在名单里（否则会把任务分给已停用账号）。"""
        user = (
            await db_session.execute(select(User).where(User.id == COUNSELOR_BOUND))
        ).scalar_one()
        user.status = "inactive"
        await db_session.commit()

        as_role("admin", ADMIN_ID)
        resp = client.get("/api/v1/reviews/assignable-counselors")

        assert resp.status_code == 200
        assert COUNSELOR_BOUND not in [i["id"] for i in resp.json()["data"]["items"]]

    async def test_counselor_forbidden(
        self, client: TestClient, as_role, db_session, seeded_user_id
    ) -> None:
        """咨询师无权查看（名单含其他咨询师的账号信息）。"""
        as_role("counselor", COUNSELOR_BOUND)
        resp = client.get("/api/v1/reviews/assignable-counselors")
        assert resp.status_code == 403

    async def test_plain_user_forbidden(
        self, client: TestClient, as_role, db_session, seeded_user_id
    ) -> None:
        """普通用户无权查看。"""
        as_role("user", STUDENT_ID)
        resp = client.get("/api/v1/reviews/assignable-counselors")
        assert resp.status_code == 403
