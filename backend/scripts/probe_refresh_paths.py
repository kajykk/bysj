"""探针 3：refresh / 全新 get / 显式 select 的完整 execution_options 对比。

目的：找执行层可用的区分标记 —— refresh 的对象已在 identity map（已过上游
租户校验），全新 get 是未校验加载，二者都产生「按主键取受保护表」的 SELECT。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-ci-only-2026-not-for-production")
os.environ.setdefault("PII_ENCRYPTION_KEY", "test-pii-key-for-unit-tests-only-not-for-production")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./probe_refresh2.db")

import asyncio

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.review import ReviewTask

CALLS: list[tuple[str, dict]] = []


def _listener(conn, clauseelement, multiparams, params, execution_options):
    sql = str(clauseelement.compile(dialect=conn.dialect))
    CALLS.append((sql, dict(execution_options or {})))


async def main() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    event.listen(engine.sync_engine, "before_execute", _listener)
    Session = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with Session() as s1:
        task = ReviewTask(user_id=1, risk_level=3, risk_score=75.0, status="pending", priority="normal_review")
        s1.add(task)
        await s1.flush()
        await s1.commit()
        tid = task.id

        print("=== 1. refresh ===")
        CALLS.clear()
        await s1.refresh(task)
        for sql, eo in CALLS:
            print("SQL:", " ".join(sql.split())[:120])
            print("EO_KEYS:", sorted(eo.keys()))

    # 新 session：identity map 为空，get 必须真的发 SQL
    async with Session() as s2:
        print("=== 2. 全新 session.get ===")
        CALLS.clear()
        await s2.get(ReviewTask, tid)
        for sql, eo in CALLS:
            print("SQL:", " ".join(sql.split())[:120])
            print("EO_KEYS:", sorted(eo.keys()))

        print("=== 3. 显式 select ===")
        CALLS.clear()
        await s2.execute(select(ReviewTask).where(ReviewTask.id == tid))
        for sql, eo in CALLS:
            print("SQL:", " ".join(sql.split())[:120])
            print("EO_KEYS:", sorted(eo.keys()))


asyncio.run(main())
