"""数据库初始化脚本 (全新部署).

用于 alembic 迁移链不完整时的首次部署:
1. Base.metadata.create_all() 从 SQLAlchemy 模型创建全部表
2. alembic stamp head 标记所有迁移为已应用 (不执行迁移, 仅写版本号)

后续迁移 (新增的) 将正常执行 alembic upgrade head.

用法:
    python scripts/init_db.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# 确保可以导入 app 模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def init_database() -> None:
    """创建所有表并标记 alembic 版本."""
    # 1. 导入所有模型 (触发 Base.metadata 注册)
    from app.models import Base  # noqa: F401
    from app.core.database import engine

    # 2. 创建所有表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[OK] 所有表已从 SQLAlchemy 模型创建")

    # 3. 关闭引擎
    await engine.dispose()

    # 4. 调用 alembic stamp head (子进程)
    import subprocess

    result = subprocess.run(
        ["alembic", "stamp", "head"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
    )
    if result.returncode == 0:
        print(f"[OK] alembic stamp head: {result.stdout.strip()}")
    else:
        print(f"[ERROR] alembic stamp head 失败: {result.stderr}", file=sys.stderr)
        sys.exit(result.returncode)


if __name__ == "__main__":
    asyncio.run(init_database())
