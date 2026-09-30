"""RES-P1-014: email 盲索引归一化迁移脚本 (scripts/normalize_email_blind_index.py) 测试.

重点验证两件事:
1. 能检出"归一化后撞 users.email_hash UNIQUE 约束"的存量账号组, 且跳过它们
   (自动合并/删除账号是业务决策, 脚本不得代劳)
2. 对无冲突的行, 生成的 email_hash 与 compute_blind_index 一致 (迁移可收敛)
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import bindparam, select, text

from app.core.pii_crypto import _hmac_blind_index, compute_blind_index
from app.models.user import User

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "normalize_email_blind_index.py"
)


def _load_script_module():
    """按文件路径加载迁移脚本模块 (scripts/ 不是包, 无法直接 import)."""
    spec = importlib.util.spec_from_file_location(
        "normalize_email_blind_index", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # 必须先注册进 sys.modules: 模块内的 dataclass 在解析注解时会查找自身模块,
    # 未注册则 dataclasses 抛 AttributeError: 'NoneType' object has no attribute '__dict__'
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script_module():
    return _load_script_module()


async def _create_user(db_session, username: str, email: str) -> User:
    user = User(
        username=username,
        email=email,
        email_hash=_hmac_blind_index(email, "email"),  # 模拟迁移前的未归一化值
        password_hash="x",
        role="user",
        status="active",
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _rows_and_hashes(db_session, user_ids: list[int]):
    """读取原始密文 (绕过 TypeDecorator) 与当前 email_hash."""
    # expanding bindparam: IN 子句的列表绑定 (直接写 IN :ids 在 sqlite 下是语法错误)
    sql = text("SELECT id, email FROM users WHERE id IN :ids").bindparams(
        bindparam("ids", expanding=True)
    )
    result = await db_session.execute(sql, {"ids": user_ids})
    rows = [(r[0], r[1]) for r in result.fetchall()]
    result2 = await db_session.execute(
        select(User.id, User.email_hash).where(User.id.in_(user_ids))
    )
    current = {r[0]: r[1] for r in result2.fetchall()}
    return rows, current


@pytest.mark.asyncio
async def test_detects_unique_conflict_group(db_session, script_module) -> None:
    """大小写变体的两个账号 → 检出冲突组并跳过, 不生成更新."""
    u1 = await _create_user(db_session, "conflict_a", "Conflict@Example.com")
    u2 = await _create_user(db_session, "conflict_b", "conflict@example.com")
    await db_session.commit()

    rows, current = await _rows_and_hashes(db_session, [u1.id, u2.id])
    updates, stats = script_module.build_plan(rows, current)

    assert stats.conflict_groups, "未检出 UNIQUE 冲突"
    assert sorted(stats.conflict_groups[0]) == sorted([u1.id, u2.id])
    assert stats.conflict_rows == 2
    assert updates == [], "冲突行不得进入更新计划"


@pytest.mark.asyncio
async def test_generates_normalized_hash_for_single_row(db_session, script_module) -> None:
    """无冲突的未迁移行 → 生成与 compute_blind_index 一致的归一化 hash."""
    user = await _create_user(db_session, "single_mixed", "Single@Example.com")
    await db_session.commit()

    rows, current = await _rows_and_hashes(db_session, [user.id])
    updates, stats = script_module.build_plan(rows, current)

    assert stats.to_update == 1
    assert not stats.conflict_groups
    assert updates[0]["id"] == user.id
    # 更新值必须等于写入侧使用的归一化值, 否则迁移无法收敛
    assert updates[0]["email_hash"] == compute_blind_index("Single@Example.com", "email")


@pytest.mark.asyncio
async def test_already_migrated_row_not_updated(db_session, script_module) -> None:
    """已归一化的行 → 无需更新 (迁移可重复执行)."""
    email = "already@example.com"
    user = User(
        username="already_migrated",
        email=email,
        email_hash=compute_blind_index(email, "email"),
        password_hash="x",
        role="user",
        status="active",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()

    rows, current = await _rows_and_hashes(db_session, [user.id])
    updates, stats = script_module.build_plan(rows, current)

    assert stats.to_update == 0
    assert updates == []
