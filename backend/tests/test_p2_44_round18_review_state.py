"""ROUND_18 · T4/T5（审查报告 M7 / M8）：复核状态机的行锁、审计与受派人校验。

M7（``resolve_review``）：原实现是普通 SELECT，且是本服务里唯一不写审计的写操作。
两个并发请求都能通过 ``status in (pending, in_review)``，后提交者静默覆盖
``resolution_note / resolved_by``，第一份临床处置结论与处置人永久丢失，审计链里
也查不到这次处置。

M8（``assign_review``）：原实现直接 ``task.assigned_to = counselor_id``。管理员可把
危机复核分配给不存在的 id / 普通用户 / 他租户咨询师；任务随即变 ``in_review``，
而合法咨询师按租户 JOIN 看不到它 —— 危机复核被锁进无人可见的状态。

判据说明（关于"并发"）：仓库测试库是 SQLite，``FOR UPDATE`` 在 SQLite 上是 no-op，
两个事务互不阻塞，因此**无法**用双会话复现"后写覆盖"。这里改用两条互补判据：
1. 编译真实的加锁语句（PostgreSQL 方言），断言其带 ``FOR UPDATE``；
2. 用 spy 断言 ``resolve_review`` 确实走了这条语句（否则把 helper 留在文件里不用也能过）。
合起来钉住"取行带锁"；行锁本身的语义由 PostgreSQL 承担，单测不越权声称验证了它。
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.core.contracts import DEFAULT_TENANT_ID
from app.models.admin import OperationLog
from app.models.user import User
from app.schemas.review import ReviewTaskCreate
from app.services import review_service as review_module
from app.services.review_service import ReviewService, ReviewStateConflict


def _mk(uid: int, username: str, role: str, tenant: int | None, status: str = "active") -> User:
    from app.core.pii_crypto import compute_blind_index
    from app.core.security import get_password_hash

    email = f"{username}@test.com"
    return User(
        id=uid,
        username=username,
        email=email,
        email_hash=compute_blind_index(email, "email"),
        password_hash=get_password_hash("testpass123"),
        role=role,
        status=status,
        tenant_id=tenant,
    )


@pytest.fixture
async def people(db_session):
    """租户 1：学生 1 / 咨询师 2 / 管理员 3 / 普通用户 5 / 停用咨询师 6；租户 2：咨询师 4。"""
    db_session.add_all(
        [
            _mk(1, "r18_student", "user", 1),
            _mk(2, "r18_counselor", "counselor", 1),
            _mk(3, "r18_admin", "admin", 1),
            _mk(4, "r18_other_counselor", "counselor", 2),
            _mk(5, "r18_plain_user", "user", 1),
            _mk(6, "r18_disabled_counselor", "counselor", 1, status="inactive"),
        ]
    )
    await db_session.commit()
    return db_session


async def _new_task(service: ReviewService) -> int:
    task = await service.create_review_task(
        ReviewTaskCreate(user_id=1, risk_level=3, risk_score=80.0)
    )
    return task.id


# ── M7：行锁 ─────────────────────────────────────────────────────────


def test_locked_statement_compiles_with_for_update():
    """加锁语句在 PostgreSQL 方言下必须真的带 FOR UPDATE。"""
    stmt = review_module._locked_review_stmt(42)
    sql = str(
        stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).upper()
    assert "FOR UPDATE" in sql
    assert "REVIEW_TASKS" in sql


async def test_resolve_uses_the_locked_statement(people, monkeypatch):
    """resolve_review 必须走 ``_locked_review_stmt``（不是普通 SELECT / db.get）。"""
    service = ReviewService(people)
    task_id = await _new_task(service)

    seen: list[int] = []
    real = review_module._locked_review_stmt

    def _spy(review_id: int):
        seen.append(review_id)
        return real(review_id)

    monkeypatch.setattr(review_module, "_locked_review_stmt", _spy)

    await service.resolve_review(task_id, 2, "已电话随访", is_admin=True, tenant_id=1)

    assert seen == [task_id]


# ── M7：审计 ─────────────────────────────────────────────────────────


async def test_resolve_writes_audit_without_clinical_note_text(people):
    service = ReviewService(people)
    task_id = await _new_task(service)
    note = "建议每周复诊并复查 PHQ-9，家属陪同"

    await service.resolve_review(task_id, 2, note, is_admin=True, tenant_id=1)

    rows = (
        (
            await people.execute(
                select(OperationLog).where(OperationLog.action_type == "review.resolved")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.target_type == "review_task"
    assert row.target_id == task_id
    assert row.operator_id == 2
    assert row.tenant_id == DEFAULT_TENANT_ID

    detail = json.loads(row.detail)
    assert detail["previous_status"] == "pending"
    assert detail["resolved_by"] == 2
    assert detail["resolution_note_chars"] == len(note)
    # 处置备注属临床内容，不得复制进审计表
    assert note not in row.detail


async def test_second_resolve_is_rejected_and_writes_no_extra_audit(people):
    service = ReviewService(people)
    task_id = await _new_task(service)
    await service.resolve_review(task_id, 2, "首次处置", is_admin=True, tenant_id=1)

    with pytest.raises(
        ReviewStateConflict, match="Cannot resolve review with status resolved"
    ):
        await service.resolve_review(task_id, 2, "并发处置", is_admin=True, tenant_id=1)

    rows = (
        (
            await people.execute(
                select(OperationLog).where(OperationLog.action_type == "review.resolved")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1

    refreshed = await service.get_review_by_id(task_id, tenant_id=1)
    # 首次的处置结论没有被覆盖
    assert refreshed.resolution_note == "首次处置"
    assert refreshed.resolved_by == 2


async def test_resolve_rejects_cross_tenant(people):
    service = ReviewService(people)
    task_id = await _new_task(service)

    with pytest.raises(ValueError, match="not found"):
        await service.resolve_review(task_id, 2, "越权", is_admin=True, tenant_id=2)


# ── M8：受派人校验 ───────────────────────────────────────────────────


async def test_assign_accepts_same_tenant_counselor(people):
    """反向对照：合法受派人照常分配。"""
    service = ReviewService(people)
    task_id = await _new_task(service)

    task = await service.assign_review(task_id, 2, tenant_id=1)

    assert task.status == "in_review"
    assert task.assigned_to == 2


async def test_assign_rejects_missing_assignee(people):
    service = ReviewService(people)
    task_id = await _new_task(service)

    with pytest.raises(ValueError, match="不存在"):
        await service.assign_review(task_id, 9999, tenant_id=1)

    # 失败后任务仍是 pending，没有被锁成 in_review
    task = await service.get_review_by_id(task_id, tenant_id=1)
    assert task.status == "pending"
    assert task.assigned_to is None


async def test_assign_rejects_plain_user(people):
    service = ReviewService(people)
    task_id = await _new_task(service)

    with pytest.raises(ValueError, match="角色"):
        await service.assign_review(task_id, 5, tenant_id=1)


async def test_assign_rejects_cross_tenant_counselor(people):
    service = ReviewService(people)
    task_id = await _new_task(service)

    with pytest.raises(ValueError, match="不属于当前租户"):
        await service.assign_review(task_id, 4, tenant_id=1)


async def test_assign_rejects_disabled_counselor(people):
    service = ReviewService(people)
    task_id = await _new_task(service)

    with pytest.raises(ValueError, match="已停用"):
        await service.assign_review(task_id, 6, tenant_id=1)
