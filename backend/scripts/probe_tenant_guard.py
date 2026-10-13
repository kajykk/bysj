"""P2-31 探针：验证 SQLAlchemy 2.0.49 下 before_execute 事件机制（不依赖 conftest）。

验证点：
1. AsyncEngine 上 before_execute 的签名（是否带 execution_options）；
2. 语句级 .execution_options(tenant_exempt=...) 能否传到事件；
3. JOIN User 推导租户的编译 SQL 形态（users.tenant_id 是否出现）；
4. ORM 实体 select / Core count / text() 是否都触发事件。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-ci-only-2026-not-for-production")
os.environ.setdefault("PII_ENCRYPTION_KEY", "test-pii-key-for-unit-tests-only-not-for-production")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./probe_tenant_guard.db")

import asyncio

from sqlalchemy import event, func, select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.review import CrisisEvent, ReviewTask
from app.models.user import User

CALLS: list[tuple[str, dict]] = []


def _make_listener():
    def _listener(conn, clauseelement, multiparams, params, execution_options):
        sql = str(clauseelement.compile(dialect=conn.dialect, compile_kwargs={"literal_binds": True}))
        CALLS.append((sql, dict(execution_options or {})))

    return _listener


async def main() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    # 试探 1：5 参签名（conn, clauseelement, multiparams, params, execution_options）
    try:
        event.listen(engine.sync_engine, "before_execute", _make_listener())
        print("SIG5_OK")
    except TypeError as exc:
        print(f"SIG5_FAIL: {exc}")

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    Session = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        from app.models.base import Base

        await conn.run_sync(Base.metadata.create_all)

    async with Session() as session:
        # A. ORM 实体 select + JOIN User 推导租户
        stmt = (
            select(ReviewTask)
            .join(User, User.id == ReviewTask.user_id)
            .where(User.tenant_id == 1)
        )
        await session.execute(stmt)

        # B. 裸 select（应被闸门判为缺约束）
        await session.execute(select(CrisisEvent).where(CrisisEvent.id == 1))

        # C. Core count + select_from(subquery)
        inner = select(ReviewTask).join(User, User.id == ReviewTask.user_id).where(User.tenant_id == 1)
        await session.execute(select(func.count()).select_from(inner.subquery()))

        # D. text() 裸 SQL
        await session.execute(text("SELECT id FROM review_tasks LIMIT 1"))

        # E. 语句级 execution_options 豁免标记
        await session.execute(
            select(CrisisEvent.status, func.count())
            .execution_options(tenant_exempt="platform_admin")
        )

        # F. INSERT（不应触发租户闸门判红——探针只看事件是否触发）
        from app.models.review import ReviewTask as RT

        session.add(RT(user_id=1, risk_level=1, risk_score=1.0, status="pending", priority="normal_review"))
        await session.flush()

    for i, (sql, eo) in enumerate(CALLS):
        print(f"--- CALL {i} ---")
        print("SQL:", sql.replace("\n", " ")[:220])
        print("EXEC_OPTS:", {k: v for k, v in eo.items() if k.startswith("tenant")})


asyncio.run(main())
