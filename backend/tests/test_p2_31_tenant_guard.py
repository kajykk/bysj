"""P2-31 租户隔离机制化闸门（CODE_REVIEW_2026-10-11.md #31）。

被修的根因（报告根因段实锤）：``review_tasks`` / ``crisis_events`` 无
tenant_id 列，租户隔离靠**逐函数手写** JOIN + 必填 tenant_id —— 而作者会在
同类方法里整段忘记（``review_service.py`` 全文 tenant 仅出现 1 次，
:375-389 却配有长注释解释为何必须 JOIN）。手写在认知上不可解决，故本轮把
隔离下沉到**执行层**：任何 SELECT 触及受保护表而没有 ``users.tenant_id``
锚点时，引擎 ``before_execute`` 直接抛 ``TenantConstraintMissingError``
（fail-closed）。机制本体见 ``app/core/tenant_guard.py``。

本文件四道闸门，缺一不可：
1. **机制闸门**（TestGuardMechanism）：裸查询 / text() / 子查询 / CTE /
   全新 session.get 全部现红；helper 构造 / 已登记豁免 / ORM 刷新放行；
   INSERT/UPDATE/DELETE 不拦（范围控制，见模块 docstring 第 3 条）。
2. **行为闸门**（TestServiceBehaviorUnderGuard）：服务层跨租户读写仍按
   范式三（读 None / 写 ValueError），豁免路径（创建任务、记录事件、
   FOR UPDATE）端到端可用。
3. **反向闸门**（TestReverseGates）：证明「绕过机制会红」——
   抽掉服务的 tenant_id 必填参数 → TypeError；把服务的 JOIN 构造换成
   手写裸查询 → 执行层现红。只验证「机制在位时全绿」是假绿，不收。
4. **豁免管制闸门**（TestExemptionRegistry / TestMechanizedAuditGate）：
   源码里的豁免理由必须已登记、已登记必须有使用点；静态扫描 app/ 零漏网。
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from app.core.pii_crypto import compute_blind_index
from app.core.security import get_password_hash
from app.core.tenant_guard import (
    EXEMPTION_REGISTRY,
    TenantConstraintMissingError,
    TenantExemptionUnregisteredError,
    scan_unscoped_protected_queries,
)
from app.core.tenant_query import user_tenant_scoped_query
from app.models.review import CrisisEvent, ReviewTask
from app.models.user import User
from app.schemas.review import (
    CrisisEventCreate,
    CrisisEventFilter,
    ReviewPriority,
    ReviewTaskCreate,
    ReviewTaskFilter,
)
from app.services.review_service import CrisisEventService, ReviewService

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def run(coro):
    """同步跑完协程（仅供同步 fixture 使用；异步测试请直接 await）。"""
    import asyncio

    return asyncio.run(coro)


@pytest.fixture
def two_tenants(db_session):
    """两个租户、四个用户：tenant1 = user1/counselor2/admin3，tenant2 = user100。

    刻意不用 seeded_user_id：seed 用户 1/2/3 的 tenant_id 为 NULL，JOIN 推导
    租户时会被整体排除（见 MEMORY.md 租户隔离范式）。
    """
    pwd = get_password_hash("testpass123")

    def _mk(uid: int, username: str, role: str, tenant: int) -> User:
        email = f"{username}@test.com"
        return User(
            id=uid,
            username=username,
            email=email,
            email_hash=compute_blind_index(email, "email"),
            password_hash=pwd,
            role=role,
            status="active",
            tenant_id=tenant,
        )

    async def _seed():
        db_session.add_all(
            [
                _mk(1, "t1_student", "user", 1),
                _mk(2, "t1_counselor", "counselor", 1),
                _mk(3, "t1_admin", "admin", 1),
                _mk(100, "t2_student", "user", 2),
            ]
        )
        await db_session.flush()

    run(_seed())


async def _make_review_task(service: ReviewService, user_id: int = 1) -> int:
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


async def _make_crisis_event(service: CrisisEventService, user_id: int = 1) -> int:
    event = await service.record_crisis_event(
        CrisisEventCreate(
            user_id=user_id,
            trigger_source="text",
            crisis_keywords=["自伤"],
            crisis_score=0.9,
            input_summary=f"tenant-scope-summary-{user_id}",
        )
    )
    return event.id


# =========================================================================
# 闸门 1：机制本体
# =========================================================================


class TestGuardMechanism:
    """执行层闸门的行为矩阵（用 conftest 引擎，闸门已随其安装）。"""

    async def test_guard_installed_on_test_engine(self, db_session):
        """元断言：测试引擎真的装了闸门 —— 否则本文件所有反向闸门失去对象。"""
        sync_engine = db_session.bind.sync_engine
        assert getattr(sync_engine, "_tenant_guard_installed", False) is True

    async def test_bare_select_review_task_raises(self, db_session):
        """裸 select(ReviewTask) → TenantConstraintMissingError（A-01/A-02 形态）。"""
        with pytest.raises(TenantConstraintMissingError, match="租户锚点"):
            await db_session.execute(select(ReviewTask).where(ReviewTask.id == 1))

    async def test_bare_select_crisis_event_raises(self, db_session):
        with pytest.raises(TenantConstraintMissingError, match="租户锚点"):
            await db_session.execute(select(CrisisEvent).where(CrisisEvent.id == 1))

    async def test_bare_text_sql_raises(self, db_session):
        """text() 裸 SQL 同样过闸（ORM 之外还有 Core 构造路径）。"""
        with pytest.raises(TenantConstraintMissingError):
            await db_session.execute(text("SELECT id FROM crisis_events LIMIT 1"))

    async def test_count_over_bare_subquery_raises(self, db_session):
        """count 包裸子查询也现红 —— 外层看不出问题不等于内层干净。"""
        inner = select(CrisisEvent.id)
        with pytest.raises(TenantConstraintMissingError):
            await db_session.execute(select(func.count()).select_from(inner.subquery()))

    async def test_cte_without_anchor_raises(self, db_session):
        """WITH ... SELECT 形态同样纳入检查。"""
        cte = select(CrisisEvent.id).cte("crisis_cte")
        stmt = select(cte.c.id)
        with pytest.raises(TenantConstraintMissingError):
            await db_session.execute(stmt)

    async def test_helper_query_passes_and_scopes(self, db_session, two_tenants):
        """SSOT helper 构造的查询放行，且真的按租户收窄。"""
        service = CrisisEventService(db_session)
        await _make_crisis_event(service, user_id=1)
        await _make_crisis_event(service, user_id=100)

        stmt = user_tenant_scoped_query(CrisisEvent, 1)
        rows = (await db_session.execute(stmt)).scalars().all()
        assert [r.user_id for r in rows] == [1]

    async def test_registered_exemption_passes(self, db_session):
        """已登记理由的豁免放行（语句级显式声明）。"""
        stmt = (
            select(CrisisEvent.id)
            .execution_options(tenant_exempt="test_row_verification")
        )
        rows = (await db_session.execute(stmt)).scalars().all()
        assert rows == []

    async def test_unregistered_exemption_raises(self, db_session):
        """未登记理由 → TenantExemptionUnregisteredError（豁免本身受管制）。

        哨兵值刻意用连字符（登记键全是 snake_case）：TestExemptionRegistry 的
        源码扫描按 ``tenant_exempt="<snake_case>"`` 形态识别真实豁免点，
        连字符哨兵不会混进那张网 —— 负样本探针不该污染正向闸门。
        """
        stmt = (
            select(CrisisEvent.id)
            .execution_options(tenant_exempt="this-reason-is-not-registered")
        )
        with pytest.raises(TenantExemptionUnregisteredError, match="未登记"):
            await db_session.execute(stmt)

    async def test_insert_not_blocked(self, db_session, two_tenants):
        """写路径不拦（范围控制：租户约束由服务层必填 tenant_id 负责）。"""
        service = CrisisEventService(db_session)
        event_id = await _make_crisis_event(service, user_id=1)
        assert event_id > 0

    async def test_update_delete_not_blocked(self, db_session, two_tenants):
        """Core UPDATE/DELETE 不过闸（同样是有范围控制的放行）。"""
        from sqlalchemy import update

        service = CrisisEventService(db_session)
        event_id = await _make_crisis_event(service, user_id=1)
        await db_session.execute(
            update(CrisisEvent).where(CrisisEvent.id == event_id).values(status="reviewed")
        )
        await db_session.commit()

    async def test_stream_fires_guard(self, db_session):
        """stream() 路径同样过闸（crisis_export 走 stream，不能有盲区）。"""
        with pytest.raises(TenantConstraintMissingError):
            result = await db_session.stream(select(CrisisEvent))
            async for _ in result:
                pass

    async def test_orm_refresh_allowed_fresh_get_blocked(self, db_session, two_tenants):
        """refresh（已加载实例）放行；全新 session.get（identity map 未命中）拦截。

        二者都产生「按主键取受保护表」的 SELECT，区别只在对象是否已经过上游
        租户校验 —— 区分依据见 _is_orm_refresh_of_loaded_instance 的实测记录。
        """
        service = ReviewService(db_session)
        task_id = await _make_review_task(service, user_id=1)
        task = await service.get_review_by_id(task_id, tenant_id=1)
        assert task is not None

        # refresh：对象在 identity map，先前加载已过闸 → 放行
        await db_session.refresh(task)

        # 全新 get：先踢出 identity map，制造"未校验加载"
        db_session.expunge_all()
        with pytest.raises(TenantConstraintMissingError):
            await db_session.get(ReviewTask, task_id)


# =========================================================================
# 闸门 2：服务层行为（范式三）
# =========================================================================


class TestServiceBehaviorUnderGuard:
    """机制在位时，服务层租户隔离行为不回退。"""

    async def test_get_review_by_id_cross_tenant_returns_none(self, db_session, two_tenants):
        service = ReviewService(db_session)
        task_id = await _make_review_task(service, user_id=1)
        assert await service.get_review_by_id(task_id, tenant_id=2) is None

    async def test_get_review_by_id_same_tenant_returns_task(self, db_session, two_tenants):
        service = ReviewService(db_session)
        task_id = await _make_review_task(service, user_id=1)
        task = await service.get_review_by_id(task_id, tenant_id=1)
        assert task is not None and task.id == task_id

    async def test_get_reviews_scoped(self, db_session, two_tenants):
        service = ReviewService(db_session)
        await _make_review_task(service, user_id=1)
        await _make_review_task(service, user_id=100)

        r1 = await service.get_reviews(ReviewTaskFilter(), tenant_id=1)
        assert r1.total == 1 and r1.items[0].user_id == 1
        r2 = await service.get_reviews(ReviewTaskFilter(), tenant_id=2)
        assert r2.total == 1 and r2.items[0].user_id == 100

    async def test_get_review_stats_scoped(self, db_session, two_tenants):
        service = ReviewService(db_session)
        await _make_review_task(service, user_id=1)
        await _make_review_task(service, user_id=100)

        stats1 = await service.get_review_stats(days=30, tenant_id=1)
        assert stats1.total == 1
        stats2 = await service.get_review_stats(days=30, tenant_id=2)
        assert stats2.total == 1

    async def test_get_crisis_events_scoped(self, db_session, two_tenants):
        service = CrisisEventService(db_session)
        await _make_crisis_event(service, user_id=1)
        await _make_crisis_event(service, user_id=100)

        r1 = await service.get_crisis_events(CrisisEventFilter(), tenant_id=1)
        assert r1["total"] == 1
        assert r1["items"][0]["input_summary"] == "tenant-scope-summary-1"
        r2 = await service.get_crisis_events(CrisisEventFilter(), tenant_id=2)
        assert r2["total"] == 1
        assert r2["items"][0]["input_summary"] == "tenant-scope-summary-100"

    async def test_get_stats_scoped(self, db_session, two_tenants):
        service = CrisisEventService(db_session)
        await _make_crisis_event(service, user_id=1)
        await _make_crisis_event(service, user_id=100)
        await _make_crisis_event(service, user_id=100)

        s1 = await service.get_stats(tenant_id=1)
        assert s1["total"] == 1 and s1["detected"] == 1
        s2 = await service.get_stats(tenant_id=2)
        assert s2["total"] == 2

    async def test_write_paths_cross_tenant_raise(self, db_session, two_tenants):
        """写路径跨租户一律 ValueError（响亮失败，不返回 None 让调用方误判）。"""
        review = ReviewService(db_session)
        crisis = CrisisEventService(db_session)
        task_id = await _make_review_task(review, user_id=1)
        event_id = await _make_crisis_event(crisis, user_id=1)

        with pytest.raises(ValueError):
            await review.assign_review(task_id, 2, tenant_id=2)
        with pytest.raises(ValueError):
            await review.resolve_review(task_id, 2, "note", tenant_id=2)
        with pytest.raises(ValueError):
            await review.escalate_review(task_id, 2, "reason", tenant_id=2)
        with pytest.raises(ValueError):
            await crisis.handle_crisis_event(
                event_id, 2, "notify_counselor", tenant_id=2, operator_role="admin"
            )
        with pytest.raises(ValueError):
            await crisis.escalate_crisis_event(
                event_id, 2, "reason", tenant_id=2, operator_role="admin"
            )
        with pytest.raises(ValueError):
            await crisis.close_crisis_event(
                event_id, 2, tenant_id=2, operator_role="admin"
            )

    async def test_same_tenant_write_paths_work(self, db_session, two_tenants):
        """同租户写路径端到端可用（覆盖 FOR UPDATE 豁免 + refresh 放行）。"""
        review = ReviewService(db_session)
        crisis = CrisisEventService(db_session)
        task_id = await _make_review_task(review, user_id=1)
        event_id = await _make_crisis_event(crisis, user_id=1)

        assigned = await review.assign_review(task_id, 2, tenant_id=1)
        assert assigned.status == "in_review" and assigned.assigned_to == 2

        resolved = await review.resolve_review(
            task_id, 2, "done", is_admin=True, tenant_id=1
        )
        assert resolved.status == "resolved"

        handled = await crisis.handle_crisis_event(
            event_id, 2, "notify_counselor", tenant_id=1, operator_role="counselor"
        )
        assert handled.status == "reviewed"


# =========================================================================
# 闸门 3：反向闸门（绕过机制即红）
# =========================================================================

# (服务类, 方法名, 必填的 tenant_id 参数名)
_TENANT_SENSITIVE_METHODS = [
    (ReviewService, "get_reviews"),
    (ReviewService, "get_review_by_id"),
    (ReviewService, "assign_review"),
    (ReviewService, "resolve_review"),
    (ReviewService, "escalate_review"),
    (ReviewService, "get_review_stats"),
    (CrisisEventService, "get_crisis_events"),
    (CrisisEventService, "get_stats"),
    (CrisisEventService, "handle_crisis_event"),
    (CrisisEventService, "escalate_crisis_event"),
    (CrisisEventService, "close_crisis_event"),
]


class TestReverseGates:
    """证明「绕过机制会红」——只验机制在位时全绿是假绿，不收。"""

    @pytest.mark.parametrize("cls,method", [(c, m) for c, m in _TENANT_SENSITIVE_METHODS])
    def test_tenant_id_is_required_keyword(self, cls, method):
        """tenant_id 必填且无默认值：漏传 TypeError，而非静默全量返回。"""
        sig = inspect.signature(getattr(cls, method))
        assert "tenant_id" in sig.parameters, f"{cls.__name__}.{method} 缺少 tenant_id 参数"
        assert sig.parameters["tenant_id"].default is inspect.Parameter.empty, (
            f"{cls.__name__}.{method} 的 tenant_id 有默认值 —— "
            "给 None 配默认值等于把「忘记传」变成静默全量返回"
        )

    async def test_missing_tenant_id_call_raises_typeerror(self, db_session, two_tenants):
        """真实调用漏传 tenant_id → TypeError（不只是签名断言）。"""
        review = ReviewService(db_session)
        crisis = CrisisEventService(db_session)
        with pytest.raises(TypeError):
            await review.get_review_by_id(1)
        with pytest.raises(TypeError):
            await crisis.get_crisis_events(CrisisEventFilter())

    async def test_stripping_join_from_service_raises(self, db_session, two_tenants, monkeypatch):
        """**核心反向闸门**：把服务的 JOIN 构造换成手写裸查询 → 执行层现红。

        模拟的正是报告根因段的失效模式：作者新写/改写一个查询方法，手写
        ``select(Model).where(...)`` 而忘了 JOIN users。若执行层闸门被抽掉，
        本测试不会抛 TenantConstraintMissingError（数据直接返回）→ 红。
        """
        service = ReviewService(db_session)
        task_id = await _make_review_task(service, user_id=1)

        def _bare_select(model, tenant_id):  # 模拟「手写裸查询」
            return select(model)

        monkeypatch.setattr(
            "app.services.review_service.user_tenant_scoped_query", _bare_select
        )
        with pytest.raises(TenantConstraintMissingError):
            await service.get_review_by_id(task_id, tenant_id=1)

    async def test_by_pk_get_blocked(self, db_session, two_tenants):
        """A-01 原形态：凭一个 id 按主键裸取 → 现红（identity map 未命中时）。"""
        service = ReviewService(db_session)
        task_id = await _make_review_task(service, user_id=1)
        db_session.expunge_all()
        with pytest.raises(TenantConstraintMissingError):
            await db_session.get(ReviewTask, task_id)

    async def test_crisis_service_stripping_join_raises(self, db_session, two_tenants, monkeypatch):
        """危机事件服务同理（CrisisEvent 是敏感度最高的表）。"""
        service = CrisisEventService(db_session)
        event_id = await _make_crisis_event(service, user_id=1)

        def _bare_select(model, tenant_id):
            return select(model)

        monkeypatch.setattr(
            "app.services.review_service.user_tenant_scoped_query", _bare_select
        )
        with pytest.raises(TenantConstraintMissingError):
            await service._get_crisis_event_scoped(event_id, 1)


# =========================================================================
# 闸门 4：豁免管制 + 静态审计
# =========================================================================


class TestExemptionRegistry:
    """豁免登记表的双向把守：防新增不登记，防登记后变 stale。"""

    @staticmethod
    def _iter_sources():
        for root in (APP_DIR, Path(__file__).resolve().parents[1] / "tests"):
            for path in sorted(root.rglob("*.py")):
                if "__pycache__" in path.parts:
                    continue
                try:
                    yield path, path.read_text(encoding="utf-8")
                except OSError:
                    continue

    def test_source_exemptions_all_registered(self):
        """源码里每个 tenant_exempt= 理由必须已登记。"""
        pattern = re.compile(r"""tenant_exempt\s*=\s*["']([a-z_]+)["']""")
        used: set[str] = set()
        for _, src in self._iter_sources():
            used.update(pattern.findall(src))
        unregistered = used - set(EXEMPTION_REGISTRY)
        assert not unregistered, (
            f"以下豁免理由未登记在 EXEMPTION_REGISTRY：{sorted(unregistered)}。"
            "新增豁免必须登记并写明依据——豁免本身受管制。"
        )

    def test_registered_reasons_all_used(self):
        """已登记理由必须有真实使用点（防登记表退化成历史档案馆）。"""
        pattern = re.compile(r"""tenant_exempt\s*=\s*["']([a-z_]+)["']""")
        used: set[str] = set()
        for _, src in self._iter_sources():
            used.update(pattern.findall(src))
        stale = set(EXEMPTION_REGISTRY) - used
        assert not stale, (
            f"以下豁免理由已无使用点，请从 EXEMPTION_REGISTRY 移除：{sorted(stale)}"
        )

    def test_registry_entries_have_justification(self):
        """每条登记必须带书面依据（非空且超过一句话的长度下限）。"""
        for reason, justification in EXEMPTION_REGISTRY.items():
            assert justification and len(justification) >= 20, (
                f"豁免理由 {reason} 缺少书面依据"
            )


class TestMechanizedAuditGate:
    """全仓审计的常驻形态：静态扫描 app/ 零漏网（脚本化审计见
    scripts/audit_tenant_queries.py，与本测试共用同一扫描函数）。"""

    def test_no_unscoped_protected_queries(self):
        offenders = scan_unscoped_protected_queries(APP_DIR)
        assert not offenders, (
            "以下位置对受保护表（ReviewTask/CrisisEvent）做了无租户约束的查询：\n"
            + "\n".join(
                f"  {o['file']}:{o['line']} [{o['model']}] {o['segment']}" for o in offenders
            )
            + "\n请改用 app.core.tenant_query.user_tenant_scoped_query，"
            "或确认是有意的跨租户路径后加 .execution_options(tenant_exempt=\"<登记理由>\")。"
        )
