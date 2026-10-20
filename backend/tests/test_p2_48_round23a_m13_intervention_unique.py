"""ROUND_23a（M13）：干预计划并发唯一性 —— 数据库约束是唯一解。

判据（提示词 A3，先定死再写实现）：
1. 真并发：N 协程各自**独立 session** 同时评估同一用户（模拟文本/生理两路
   的独立 AsyncSessionLocal）⇒ `status='active'` 计划**恰好 1 条**，
   且不允许任何异常逃逸（except SAIntegrityError 兜底必须接住）；
2. 约束存在性：直接 INSERT 第二条 active ⇒ IntegrityError
   （证明约束真在测试库里生效，而非应用层假绿）；
3. 迁移中止：存量重复 active ⇒ 检测函数报冲突清单 + upgrade 抛错
   且**不建索引**（不静默修数）。

背景：ISS-014 的 with_for_update() 只能锁已存在的行；空表时两个独立事务
（app/services/risk_service.py 的 _trigger_warning_and_intervention，
文本/生理两路各自 AsyncSessionLocal + 自行 commit）都查不到 active ⇒
都插入 ⇒ 两条 active。唯一性只能由
uq_intervention_plans_active_per_user（model __table_args__ 与迁移
r2a3b4c5d6e7 双声明）保证。
"""

from __future__ import annotations

import asyncio
import importlib.util
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.models.intervention import InterventionPlan, InterventionTemplate
from app.models.user import User
from app.services.risk_service import RiskService
from tests.conftest import TestingSessionLocal

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "r2a3b4c5d6e7_add_intervention_active_unique.py"
)

# 自 seed 专用用户 id（避开 conftest 的 1/2/3；db_session 的 seed 不提交，
# 独立 session 的并发协程看不到未提交行，故本文件自己 seed + commit）。
M13_USER_ID = 424242


def _load_migration():
    """按文件路径加载迁移模块（与 alembic 运行时的 exec_module 同形）。"""
    spec = importlib.util.spec_from_file_location("m13_migration_under_test", MIGRATION_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def _seed_user_and_template() -> int:
    """独立 session 提交用户 + 模板（并发协程可见）。"""
    from app.core.pii_crypto import compute_blind_index
    from app.core.security import get_password_hash

    async with TestingSessionLocal() as db:
        existing = (
            await db.execute(select(User).where(User.id == M13_USER_ID))
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                User(
                    id=M13_USER_ID,
                    username="m13_conc_user",
                    email="m13@test.com",
                    email_hash=compute_blind_index("m13@test.com", "email"),
                    password_hash=get_password_hash("testpass123"),
                    role="user",
                    status="active",
                )
            )
        db.add(
            InterventionTemplate(
                template_name="M13 并发测试模板",
                applicable_levels=[2, 3, 4],
                task_list=[
                    {"task_name": "情绪日记", "task_type": "diary", "duration_minutes": 15},
                ],
                estimated_weeks=4,
                status="active",
            )
        )
        await db.commit()
    return M13_USER_ID


async def _cleanup(user_id: int) -> None:
    """清理本文件 seed 的行（FK 反序）。db_session 的数据由其 teardown 负责。"""
    async with TestingSessionLocal() as db:
        await db.execute(
            text(
                "DELETE FROM intervention_tasks WHERE plan_id IN "
                "(SELECT id FROM intervention_plans WHERE user_id = :uid)"
            ),
            {"uid": user_id},
        )
        await db.execute(
            text("DELETE FROM intervention_plans WHERE user_id = :uid"),
            {"uid": user_id},
        )
        await db.execute(
            text("DELETE FROM intervention_templates WHERE template_name = :n"),
            {"n": "M13 并发测试模板"},
        )
        await db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})
        await db.commit()


class TestM13ConcurrentUniqueness:
    """并发唯一性：约束在测试库真生效 + 服务层兜底接住冲突。"""

    @pytest.mark.asyncio
    async def test_concurrent_assessments_yield_single_active_plan(self):
        """判据 1：N 协程独立 session 同时评估 ⇒ active 恰好 1 条。

        risk 仅作参数载体（SimpleNamespace 只提供 user_id/risk_level），
        被测路径是真实的：真 session、真 SQLite 库、真唯一索引、真服务代码。
        """
        user_id = await _seed_user_and_template()
        try:
            async def assess(risk_level: int) -> InterventionPlan | None:
                # 每个协程独立 session —— 与生产 _trigger_warning_and_intervention
                # 的 AsyncSessionLocal 同形（各自事务、各自 commit）。
                async with TestingSessionLocal() as db:
                    service = RiskService(db)
                    risk = SimpleNamespace(user_id=user_id, risk_level=risk_level, id=0)
                    plan = await service.generate_intervention_for_risk(risk)
                    await db.commit()
                    return plan

            results = await asyncio.gather(
                assess(2), assess(3), assess(2), assess(3),
                return_exceptions=True,
            )
            for r in results:
                assert not isinstance(r, Exception), (
                    f"并发评估不应有异常逃逸（except SAIntegrityError 兜底失效？）: {r!r}"
                )

            async with TestingSessionLocal() as db:
                active = (
                    await db.execute(
                        select(InterventionPlan).where(
                            InterventionPlan.user_id == user_id,
                            InterventionPlan.status == "active",
                        )
                    )
                ).scalars().all()
            assert len(active) == 1, (
                f"并发评估后 active 计划 {len(active)} 条（应为 1）: "
                f"{[p.id for p in active]}"
            )
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_second_writer_recovers_from_unique_conflict(self):
        """确定性交错：强制走 except SAIntegrityError 兜底路径。

        上面的 gather 用例在 SQLite 完全串行化时，后续协程会直接看到
        active 而**不经过兜底分支**——绿，但兜底未被验证（假绿）。
        本用例手工编排交错：
          A: add+flush 后**持锁 sleep 不提交**（B 的 select 读不到它）；
          B: select→None→create→flush（等 A 的写锁）→A commit→B 撞唯一索引
             →except 回查→返回 A 的计划。
        B 不抛异常且全库 active 恰 1 条 ⇒ 兜底路径真在工作。
        （generate_intervention_for_risk 的设计返回类型就是 None——await 后
        丢弃结果，不断言返回值；判定依据是「无异常 + active 恰 1 条 +
        全库总 plan 数恰 1」：若兜底没工作 B 会抛 SAIntegrityError；
        若约束没生效 B 的 create 会成功插入第二条 active。）
        """
        user_id = await _seed_user_and_template()
        try:
            risk = SimpleNamespace(user_id=user_id, risk_level=2, id=0)

            async def writer_a() -> None:
                async with TestingSessionLocal() as db:
                    db.add(
                        InterventionPlan(
                            user_id=user_id,
                            plan_name="M13 A 先插入",
                            risk_level=2,
                            status="active",
                            start_date=date.today(),
                        )
                    )
                    await db.flush()
                    # 持写锁（未提交）：保证 B 的 select 读不到这条 active
                    await asyncio.sleep(0.1)
                    await db.commit()

            async def writer_b() -> InterventionPlan | None:
                async with TestingSessionLocal() as db:
                    service = RiskService(db)
                    plan = await service.generate_intervention_for_risk(risk)
                    await db.commit()
                    return plan

            # generate_intervention_for_risk 设计上返回 None（不等同于失败）：
            # 不捕获异常即是兜底生效的第一重证据（T2 变异会在此炸红）。
            results = await asyncio.gather(writer_a(), writer_b())

            async with TestingSessionLocal() as db:
                active = (
                    await db.execute(
                        select(InterventionPlan).where(
                            InterventionPlan.user_id == user_id,
                            InterventionPlan.status == "active",
                        )
                    )
                ).scalars().all()
                all_plans = (
                    await db.execute(
                        select(InterventionPlan).where(
                            InterventionPlan.user_id == user_id
                        )
                    )
                ).scalars().all()
            assert len(active) == 1, f"active 应恰 1 条: {[p.id for p in active]}"
            # 全库总 plan 数=1 ⇒ B 的 create 插入被 savepoint 回滚，
            # 没有留下第二条任何状态的行（T1 删约束变异会在此变 2）。
            assert len(all_plans) == 1, (
                f"全库 plan 应恰 1 条（A 的），实际 {len(all_plans)}: "
                f"{[(p.id, p.plan_name, p.status) for p in all_plans]}"
            )
            assert all_plans[0].plan_name == "M13 A 先插入"
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_level_elevation_replaces_plan_under_unique_constraint(
        self, db_session, seeded_user_id
    ):
        """升级路径与唯一约束的交互（M17 × M13）。

        风险等级升高时取消旧 active + 插入新 active——两步若不在同一
        savepoint 内，插入会撞"自己刚要让位"的旧 active（回归实测抓到过）。
        断言：新计划建成（新 id）、旧计划 cancelled、全库 active 恰 1 条。
        """
        db_session.add(
            InterventionPlan(
                user_id=seeded_user_id,
                plan_name="M13 升级前",
                risk_level=2,
                status="active",
                start_date=date.today(),
            )
        )
        db_session.add(
            InterventionTemplate(
                template_name="M13 升级模板",
                applicable_levels=[3, 4],
                task_list=[{"task_name": "升级任务", "task_type": "exercise", "duration_minutes": 30}],
                estimated_weeks=4,
                status="active",
            )
        )
        await db_session.flush()
        service = RiskService(db_session)
        new_plan = await service._auto_generate_intervention(
            user_id=seeded_user_id, risk_level=3
        )
        assert new_plan is not None
        assert new_plan.risk_level == 3

        plans = (
            await db_session.execute(
                select(InterventionPlan).where(
                    InterventionPlan.user_id == seeded_user_id
                )
            )
        ).scalars().all()
        by_name = {p.plan_name: p for p in plans}
        assert by_name["M13 升级前"].status == "cancelled"
        assert by_name["M13 升级前"].id != new_plan.id
        active = [p for p in plans if p.status == "active"]
        assert len(active) == 1 and active[0].id == new_plan.id

    @pytest.mark.asyncio
    async def test_level_elevation_without_template_keeps_old_plan(
        self, db_session, seeded_user_id
    ):
        """M17 语义不失：升级但无匹配模板 ⇒ 旧 active 原样保留（不被取消）。"""
        db_session.add(
            InterventionPlan(
                user_id=seeded_user_id,
                plan_name="M13 无模板升级",
                risk_level=2,
                status="active",
                start_date=date.today(),
            )
        )
        await db_session.flush()
        service = RiskService(db_session)
        plan = await service._auto_generate_intervention(
            user_id=seeded_user_id, risk_level=3
        )
        assert plan is not None
        assert plan.plan_name == "M13 无模板升级"
        assert plan.status == "active"

    @pytest.mark.asyncio
    async def test_second_active_plan_violates_unique_index(self, db_session, seeded_user_id):
        """判据 2：直接 INSERT 第二条 active ⇒ IntegrityError。

        绕过服务层直接插，证明约束是数据库级的 —— 应用层怎么改都绕不过。
        """
        db_session.add(
            InterventionPlan(
                user_id=seeded_user_id,
                plan_name="M13 第一条",
                risk_level=2,
                status="active",
                start_date=date.today(),
            )
        )
        await db_session.flush()

        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                db_session.add(
                    InterventionPlan(
                        user_id=seeded_user_id,
                        plan_name="M13 第二条",
                        risk_level=2,
                        status="active",
                        start_date=date.today(),
                    )
                )
                await db_session.flush()

    @pytest.mark.asyncio
    async def test_non_active_statuses_do_not_conflict(self, db_session, seeded_user_id):
        """部分索引语义：cancelled/completed 历史计划可并存多条。

        反向证明约束只作用于 active —— 若是全局唯一索引，这条会红。
        """
        for i, status in enumerate(["cancelled", "completed", "cancelled"]):
            db_session.add(
                InterventionPlan(
                    user_id=seeded_user_id,
                    plan_name=f"M13 历史 {i}",
                    risk_level=2,
                    status=status,
                    start_date=date.today(),
                )
            )
            await db_session.flush()


class TestM13MigrationAbortsOnDuplicate:
    """判据 3：迁移检测到存量重复 active ⇒ 中止 + 冲突清单，不建索引、不静默修数。"""

    def test_find_duplicate_detects_conflicts_and_ids(self):
        """真库（同步 Engine，与 alembic 运行时同形）造两条 active ⇒ 报冲突。"""
        mig = _load_migration()
        eng = create_engine("sqlite:///:memory:")
        with eng.connect() as conn:
            conn.execute(
                text(
                    "CREATE TABLE intervention_plans ("
                    "id INTEGER PRIMARY KEY, user_id INTEGER, status TEXT)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO intervention_plans (id, user_id, status) VALUES "
                    "(11, 7, 'active'), (12, 7, 'active'), (13, 8, 'active'), "
                    "(14, 8, 'cancelled'), (15, 9, 'cancelled')"
                )
            )
            conflicts = mig.find_duplicate_active_plans(conn)
            assert conflicts == [(7, 2, [11, 12])], conflicts

    def test_find_duplicate_empty_when_clean(self):
        """无重复 active ⇒ 空清单（迁移才会继续建索引）。"""
        mig = _load_migration()
        eng = create_engine("sqlite:///:memory:")
        with eng.connect() as conn:
            conn.execute(
                text(
                    "CREATE TABLE intervention_plans ("
                    "id INTEGER PRIMARY KEY, user_id INTEGER, status TEXT)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO intervention_plans (id, user_id, status) VALUES "
                    "(11, 7, 'active'), (12, 8, 'cancelled'), (13, 8, 'completed')"
                )
            )
            assert mig.find_duplicate_active_plans(conn) == []

    def test_upgrade_aborts_on_conflicts_without_creating_index(self, monkeypatch):
        """存量重复 ⇒ upgrade 抛 RuntimeError 且 create_index 未被调用。"""
        mig = _load_migration()
        calls: list[tuple] = []
        monkeypatch.setattr(
            mig,
            "op",
            SimpleNamespace(
                get_bind=lambda: object(),
                create_index=lambda *a, **k: calls.append((a, k)),
            ),
        )
        monkeypatch.setattr(
            mig, "find_duplicate_active_plans", lambda bind: [(7, 2, [11, 12])]
        )
        with pytest.raises(RuntimeError, match="迁移中止"):
            mig.upgrade()
        assert calls == [], f"冲突场景不得建索引，实际调用: {calls}"

    def test_upgrade_creates_partial_unique_index_when_clean(self, monkeypatch):
        """无冲突 ⇒ upgrade 建部分唯一索引（钉 unique=True + WHERE 子句）。"""
        mig = _load_migration()
        calls: list[tuple] = []
        monkeypatch.setattr(
            mig,
            "op",
            SimpleNamespace(
                get_bind=lambda: object(),
                create_index=lambda *a, **k: calls.append((a, k)),
            ),
        )
        monkeypatch.setattr(mig, "find_duplicate_active_plans", lambda bind: [])
        mig.upgrade()
        assert len(calls) == 1, calls
        args, kwargs = calls[0]
        assert args[0] == "uq_intervention_plans_active_per_user"
        assert args[1] == "intervention_plans"
        assert list(args[2]) == ["user_id"]
        assert kwargs["unique"] is True
        # WHERE 子句必须存在（部分索引）——sqlite_where/postgresql_where 各方言一份
        assert "sqlite_where" in kwargs and "postgresql_where" in kwargs
