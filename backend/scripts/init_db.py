"""数据库初始化脚本 (全新部署 / 旧库升级).

行为 (H-AUDIT-01 修复):
- 全新空库: Base.metadata.create_all() 创建全部表 + alembic stamp head 标记迁移基线
- 已存在数据的库: 执行 alembic upgrade head 应用所有未应用迁移,
  避免 stamp head 把未应用的迁移静默标记为已应用导致 schema 漂移

用法:
    python scripts/init_db.py
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text

# 确保可以导入 app 模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def ensure_default_tenant(sync_conn) -> None:
    """幂等引导默认租户 (DEFAULT_TENANT_ID=1).

    多租户字段 (users.tenant_id 等) 外键指向 tenants.id。
    旧库升级 / 全新建库后都必须存在默认租户行, 否则注册/任何插入
    都违反外键约束 → 409 INTEGRITY_ERROR "数据冲突"。
    """
    from app.core.contracts import (
        DEFAULT_TENANT_ID,
        TENANT_STATUS_ACTIVE,
    )
    from app.models.tenant import Tenant

    existing = sync_conn.execute(
        text("SELECT id FROM tenants WHERE id = :tid"),
        {"tid": DEFAULT_TENANT_ID},
    ).first()
    if existing:
        return
    sync_conn.execute(
        Tenant.__table__.insert().values(
            id=DEFAULT_TENANT_ID,
            name="默认租户",
            code="default",
            status=TENANT_STATUS_ACTIVE,
        )
    )
    print(f"[OK] 引导默认租户 id={DEFAULT_TENANT_ID} (code=default)")


async def db_has_tables() -> bool:
    """检查数据库中是否已有任何表 (区分全新库与旧库)."""
    from app.core.database import engine

    async with engine.connect() as conn:
        if engine.dialect.name == "postgresql":
            row = await conn.execute(
                text(
                    "SELECT to_regclass('public.alembic_version') IS NOT NULL "
                    "OR EXISTS (SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public')"
                )
            )
        else:
            row = await conn.execute(
                text(
                    "SELECT COUNT(*) > 0 FROM sqlite_master "
                    "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'"
                )
            )
        return bool(row.scalar())


def run_alembic(args: list[str]) -> None:
    """运行 alembic 子命令, 失败时退出."""
    result = subprocess.run(
        ["alembic", *args],
        capture_output=True,
        text=True,
        cwd=BACKEND_ROOT,
    )
    if result.returncode == 0:
        print(f"[OK] alembic {' '.join(args)}: {result.stdout.strip()}")
    else:
        print(f"[ERROR] alembic {' '.join(args)} 失败: {result.stderr}", file=sys.stderr)
        sys.exit(result.returncode)


async def init_database() -> None:
    """初始化数据库 (新库建表+标记, 旧库升级)."""
    from app.models import Base  # noqa: F401
    from app.core.database import engine

    if await db_has_tables():
        print("[INFO] 检测到已存在的数据库, 执行 alembic upgrade head 应用未应用迁移...")
        run_alembic(["upgrade", "head"])
        async with engine.begin() as conn:
            await conn.run_sync(ensure_default_tenant)
    else:
        # 全新空库: 从 SQLAlchemy 模型创建全部表
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("[OK] 所有表已从 SQLAlchemy 模型创建")

        # 标记所有迁移为已应用 (仅对刚创建的全新 schema 正确)
        run_alembic(["stamp", "head"])

        # 引导默认租户, 否则 users.tenant_id 外键违反导致注册 409
        async with engine.begin() as conn:
            await conn.run_sync(ensure_default_tenant)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_database())
