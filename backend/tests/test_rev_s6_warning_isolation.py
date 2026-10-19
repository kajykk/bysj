"""REV-2026-10-20 S6 回归：坏干预模板不得吞掉预警与评估。

改前三条链路都把 "trigger_warning → generate_intervention → commit" 放在
同一事务里。管理员把一个模板配成 ``task_list: []`` 后，
``_validate_and_normalize_template_tasks`` 在运行时读取模板时抛 ``ValueError``：

- fire-and-forget 路径：已 flush 的 ``WarningNotification`` 与
  ``RiskAssessment`` 一起回滚 ⇒ 中高风险学生"无预警、无记录"；
- ``save_assessment_result`` / ``UserDataService``：端点直接 500 ⇒
  用户刚写的日记正文与评估一并丢失。

本文件用**独立 SQLite 引擎 + 真实 commit** 构造端到端场景：mock 掉
commit 语义（conftest 的 commit→flush）会掩盖"先提交预警再生成干预"这一
修复点的真正含义，所以这里不用共享的 db_session fixture。
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.pii_crypto import compute_blind_index
from app.core.security import get_password_hash
from app.models import Base
from app.models.intervention import InterventionPlan, InterventionTemplate
from app.models.risk import RiskAssessment, WarningNotification
from app.models.user import User


@pytest.fixture
async def real_session_factory(tmp_path, monkeypatch):
    """独立 SQLite 文件 + 真实 commit 的 session factory。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 's6.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    # 让"函数内部 import AsyncSessionLocal"与"模块级绑定"两条路径都指向真实工厂
    import app.api.v1.model_predict._common as predict_common
    import app.core.database as db_module

    monkeypatch.setattr(db_module, "AsyncSessionLocal", factory)
    monkeypatch.setattr(predict_common, "AsyncSessionLocal", factory)

    yield factory

    await engine.dispose()


async def _seed_bad_template_context(factory) -> int:
    """建用户 + 唯一一个 active 但 task_list 为空的模板，返回 risk_id。"""
    email = "s6@test.com"
    async with factory() as db:
        db.add(
            User(
                id=701,
                username="s6_student",
                email=email,
                email_hash=compute_blind_index(email, "email"),
                password_hash=get_password_hash("testpass123"),
                role="user",
                status="active",
                tenant_id=1,
            )
        )
        db.add(
            InterventionTemplate(
                template_name="S6 坏模板",
                applicable_levels=[2, 3, 4],
                task_list=[],
                status="active",
            )
        )
        await db.flush()
        risk = RiskAssessment(
            user_id=701,
            risk_score=80.0,
            risk_level=3,
            assessment_type="fusion",
            is_latest=True,
        )
        db.add(risk)
        await db.commit()
        return risk.id


async def test_fire_and_forget_keeps_warning_when_intervention_fails(
    real_session_factory,
    monkeypatch,
):
    from app.services.risk_service import _trigger_warning_and_intervention

    risk_id = await _seed_bad_template_context(real_session_factory)

    # REV-2026-10-20：加**方言无关**的顺序断言。
    #
    # 背景：本用例原只断言「预警行最终还在」。但它跑在**独立 SQLite 引擎**上，
    # 而预警的 INSERT 是在 ``begin_nested()``（SAVEPOINT）里 flush 的 ——
    # SQLAlchemy 退出 savepoint 时发 ``RELEASE SAVEPOINT``，在 SQLite（pysqlite
    # legacy 模式不显式 BEGIN）下这等同 COMMIT ⇒ 预警**已经被落库**，后续那次
    # rollback 撤不掉它。于是「把预警的独立 commit 删掉」这个变异在本用例上
    # **照样绿**（实测：session 调用序从 ['commit','rollback'] 变成 ['rollback']，
    # 预警数仍是 1）—— 假绿。
    #
    # 而生产是 PostgreSQL：``RELEASE SAVEPOINT`` **不**提交外层事务，删掉预警的
    # 独立 commit 就会真的丢预警。⇒ 本用例在 SQLite 上**测不出**它声称的不变式。
    #
    # 修法：断言「预警提交**早于**干预生成」这个**机制**，与方言无关。
    order: list[str] = []

    from app.services.risk_service import RiskService

    orig_gen = RiskService.generate_intervention_for_risk

    async def _gen(self, risk):  # noqa: ANN001, ANN202
        order.append("intervention")
        return await orig_gen(self, risk)

    orig_commit = AsyncSession.commit

    async def _commit(self, *a, **k):  # noqa: ANN001, ANN002, ANN003
        order.append("commit")
        return await orig_commit(self, *a, **k)

    monkeypatch.setattr(RiskService, "generate_intervention_for_risk", _gen)
    monkeypatch.setattr(AsyncSession, "commit", _commit)

    # 改前：ValueError 从这里冒出去（调用方只有 done-callback 日志）
    await _trigger_warning_and_intervention(701, risk_id, 3)

    assert "commit" in order, f"预警未发生独立提交：{order}"
    assert "intervention" in order, f"干预生成未被观测：{order}"
    assert order.index("commit") < order.index("intervention"), (
        f"预警提交必须早于干预生成（否则干预失败会连带回滚预警），实际顺序 {order}"
    )

    async with real_session_factory() as db:
        warnings = (
            await db.execute(
                select(WarningNotification).where(
                    WarningNotification.risk_assessment_id == risk_id
                )
            )
        ).scalars().all()
        plans = (
            await db.execute(
                select(InterventionPlan).where(InterventionPlan.user_id == 701)
            )
        ).scalars().all()

    assert len(warnings) == 1, "预警必须独立提交，不能被坏模板回滚"
    assert plans == [], "坏模板不应产生干预计划"


async def test_save_assessment_result_keeps_assessment_when_intervention_fails(
    real_session_factory,
):
    from app.api.v1.model_predict._common import save_assessment_result

    await _seed_bad_template_context(real_session_factory)

    # 无 db 入参 ⇒ 内部自建 session 并 commit（fire-and-forget 场景）
    await save_assessment_result(
        {"risk_score": 80.0, "risk_level": 3},
        701,
        "structured",
    )

    async with real_session_factory() as db:
        rows = (
            await db.execute(
                select(RiskAssessment).where(RiskAssessment.user_id == 701)
            )
        ).scalars().all()

    # 原有 1 条 seeded + 新增 1 条
    assert len(rows) == 2, "评估结果必须落库（改前随 ValueError 一起回滚/不提交）"


async def test_user_data_service_keeps_entry_when_intervention_fails(
    real_session_factory,
):
    from app.services.user_data_service import UserDataService

    await _seed_bad_template_context(real_session_factory)

    async with real_session_factory() as db:
        service = UserDataService(db)
        # 改前：ValueError 冒泡到端点 → 500，用户刚写的正文一并丢失
        await service._save_assessment_result(
            {"risk_score": 70.0, "risk_level": 2},
            701,
            "text",
        )
        await db.commit()

    async with real_session_factory() as db:
        rows = (
            await db.execute(
                select(RiskAssessment).where(RiskAssessment.user_id == 701)
            )
        ).scalars().all()

    assert len(rows) == 2
