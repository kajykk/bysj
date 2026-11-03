"""新库自带 canary「同一 route_prefix 至多一条 RUNNING」唯一索引的回归测试。

缺陷背景：该索引原先只写在迁移 ``n2b3c4d5e6f7``，SQLAlchemy 模型未声明，
全新库走 ``create_all + alembic stamp head`` 后天然缺索引 → ``init_db.py``
的漂移自检永远报警。本文件锁定：

(a) ``create_all`` 在 SQLite / PostgreSQL 方言下产出与迁移 DDL 等价的索引；
(b) 新库实际索引与 ``init_db.EXPECTED_INDEXES`` 一致（自检无漂移）；
(c) 约束真的生效：重复 RUNNING（含两条 ``route_prefix IS NULL``）被拒绝。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateIndex

from app.models import Base
from app.models.monitoring import CanaryRecord

BACKEND_ROOT = Path(__file__).resolve().parents[2]
INDEX_NAME = "uq_canary_records_single_running"

_INSERT_RUNNING = text(
    "INSERT INTO canary_records (version, traffic_percent, status, route_prefix) "
    "VALUES (:version, 1, 'running', :prefix)"
)


def _canary_index():
    return next(
        idx for idx in CanaryRecord.__table__.indexes if idx.name == INDEX_NAME
    )


def _load_init_db():
    spec = importlib.util.spec_from_file_location(
        "init_db_canary_index_under_test", BACKEND_ROOT / "scripts" / "init_db.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # dataclass 在 exec 期需要从 sys.modules 反查模块，先注册再执行。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fresh_memory_engine():
    return create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool, future=True
    )


def test_index_ddl_matches_migration_for_both_dialects():
    """(a1) 编译结果与迁移 n2b3c4d5e6f7 的 DDL 语义完全一致。"""
    index = _canary_index()
    assert index.unique is True
    # 表达式索引：NULL 归一为 ''，否则多条全局 RUNNING 不受约束。
    assert "coalesce" in str(index.expressions[0]).lower()
    # 部分索引：只约束 RUNNING，历史 paused/completed 不受影响。
    assert "status = 'running'" in str(index.dialect_options["postgresql"]["where"])
    assert "status = 'running'" in str(index.dialect_options["sqlite"]["where"])

    for dialect in (postgresql.dialect(), sqlite.dialect()):
        ddl = str(CreateIndex(index).compile(dialect=dialect))
        assert f"CREATE UNIQUE INDEX {INDEX_NAME}" in ddl
        assert "ON canary_records (coalesce(route_prefix, ''))" in ddl
        assert "WHERE status = 'running'" in ddl


@pytest.mark.asyncio
async def test_fresh_create_all_creates_index_without_drift():
    """(a2)(b) 全新库 create_all 后索引存在，且自检清单无缺失。"""
    engine = _fresh_memory_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        rows = (
            await conn.execute(
                text("SELECT name, sql FROM sqlite_master WHERE type = 'index'")
            )
        ).fetchall()

    names = {row[0] for row in rows}
    definition = {row[0]: row[1] for row in rows}[INDEX_NAME]
    await engine.dispose()

    assert INDEX_NAME in names
    lowered = (definition or "").lower()
    assert "unique index" in lowered
    assert "coalesce(route_prefix, '')" in lowered
    assert "where status = 'running'" in lowered

    init_db = _load_init_db()
    assert init_db.find_missing_indexes(names) == [], "新库不应天生漂移"


@pytest.mark.asyncio
async def test_duplicate_running_same_route_prefix_rejected():
    """(c1) 同一 route_prefix 的第二条 RUNNING 被唯一约束拒绝。"""
    engine = _fresh_memory_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(_INSERT_RUNNING, {"version": "v1", "prefix": "/api/v1/reports"})

    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(
                _INSERT_RUNNING, {"version": "v2", "prefix": "/api/v1/reports"}
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_duplicate_running_null_route_prefix_rejected():
    """(c2) 两条 route_prefix IS NULL（全局金丝雀）同样被拒绝。

    改前若直接对 route_prefix 建唯一索引，NULL 互不相等会漏掉这一类，
    故索引表达式必须是 COALESCE(route_prefix, '')。
    """
    engine = _fresh_memory_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(_INSERT_RUNNING, {"version": "g1", "prefix": None})

    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(_INSERT_RUNNING, {"version": "g2", "prefix": None})

    await engine.dispose()


@pytest.mark.asyncio
async def test_repair_drift_is_idempotent_when_index_exists():
    """(3) 索引已存在时 --repair-drift 是空操作（不再重复建）。"""
    init_db = _load_init_db()
    engine = _fresh_memory_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    remaining = await init_db.check_index_drift(repair_drift=True, engine_obj=engine)
    assert remaining == [], "索引已存在时补建路径不应有剩余缺失项"

    # 补建路径走完后约束仍生效，说明没有破坏已有索引。
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(_INSERT_RUNNING, {"version": "v1", "prefix": "/x"})
            await conn.execute(_INSERT_RUNNING, {"version": "v2", "prefix": "/x"})

    await engine.dispose()
