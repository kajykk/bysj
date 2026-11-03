"""数据库初始化脚本 (全新部署 / 旧库升级).

行为 (H-AUDIT-01 修复):
- 全新空库: Base.metadata.create_all() 创建全部表 + alembic stamp head 标记迁移基线
- 已存在数据的库: 执行 alembic upgrade head 应用所有未应用迁移,
  避免 stamp head 把未应用的迁移静默标记为已应用导致 schema 漂移

迁移后追加「期望索引存在性自检」(只读):
- 逐个检查 EXPECTED_INDEXES 是否存在于目标库, 缺失时打印告警与补建 SQL;
- 默认**不执行任何 DDL**。只有显式传 ``--repair-drift`` 才对标记为可自动
  补建的索引执行 ``CREATE ... INDEX IF NOT EXISTS``（目前仅
  ``uq_canary_records_single_running``）。
- ``--repair-drift`` 执行前提: 先确认 canary_records 无重复 RUNNING 行
  （``python scripts/check_canary_duplicate_running.py`` 退出码为 0）；
  否则唯一索引会建失败，或把脏数据留在库里。

用法:
    python scripts/init_db.py                  # 迁移 + 只读自检（默认）
    python scripts/init_db.py --repair-drift   # 额外幂等补建缺失的 canary 索引
"""
from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text

# 确保可以导入 app 模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BACKEND_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class ExpectedIndex:
    """迁移必须存在的索引及其补建 DDL。

    ``auto_repair`` 为真时才允许在 ``--repair-drift`` 下自动执行：
    自动补建必须保证幂等（``IF NOT EXISTS``）且不改写数据。
    """

    name: str
    table: str
    ddl: str
    auto_repair: bool = False


#: 期望索引清单。三项均由 ORM ``__table_args__`` 声明，全新库走
#: ``create_all`` 即自带；自检仍保留是为了兜住「历史库漏跑迁移」的漂移。
#: ``uq_canary_records_single_running`` 额外允许 ``--repair-drift`` 幂等补建，
#: 因为早期新建库（模型声明该索引之前）可能只有表没有索引。
EXPECTED_INDEXES: tuple[ExpectedIndex, ...] = (
    ExpectedIndex(
        name="uq_risk_assessments_latest",
        table="risk_assessments",
        ddl=(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_risk_assessments_latest "
            "ON risk_assessments (user_id) WHERE is_latest"
        ),
    ),
    ExpectedIndex(
        name="uq_warning_notifications_assessment",
        table="warning_notifications",
        ddl=(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_warning_notifications_assessment "
            "ON warning_notifications (risk_assessment_id) "
            "WHERE risk_assessment_id IS NOT NULL"
        ),
    ),
    ExpectedIndex(
        name="uq_canary_records_single_running",
        table="canary_records",
        ddl=(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_canary_records_single_running "
            "ON canary_records (COALESCE(route_prefix, '')) WHERE status = 'running'"
        ),
        auto_repair=True,
    ),
)


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


async def _fetch_existing_index_names(conn, *, dialect_name: str | None = None) -> set[str]:
    """读取目标库现有索引名（PG / SQLite 两种方言）。"""
    dialect = dialect_name
    if dialect is None:
        from app.core.database import engine

        dialect = engine.dialect.name
    if dialect == "postgresql":
        rows = await conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = current_schema()"
            )
        )
    else:
        rows = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'index'")
        )
    return {str(row[0]) for row in rows.fetchall() if row[0]}


def find_missing_indexes(existing_names: set[str]) -> list[ExpectedIndex]:
    """按期望清单比对现有索引名，返回缺失项（纯函数，便于单测）。"""
    return [idx for idx in EXPECTED_INDEXES if idx.name not in existing_names]


async def check_index_drift(
    *, repair_drift: bool = False, engine_obj=None
) -> list[ExpectedIndex]:
    """期望索引存在性自检；缺失时告警并列出补建 SQL。

    默认只读：``repair_drift=False`` 时**绝不执行 DDL**，避免迁移 job 在
    默认路径上自动改生产库结构。只有显式 ``--repair-drift`` 才对
    ``auto_repair=True`` 的索引执行幂等补建。

    Args:
        repair_drift: 是否执行幂等补建（默认 False）。
        engine_obj: 可选引擎注入（单测用），默认取 ``app.core.database.engine``。

    Returns:
        仍然缺失的索引列表（空列表 = 无漂移或已修复）。调用方不应把
        漂移当成迁移失败而退出，只需让日志/告警可见。
    """
    if engine_obj is None:
        from app.core.database import engine as engine_obj  # noqa: PLC0415

    async with engine_obj.begin() as conn:
        existing = await _fetch_existing_index_names(
            conn, dialect_name=engine_obj.dialect.name
        )
        missing = find_missing_indexes(existing)

        if not missing:
            print("[OK] 期望索引全部存在（schema 无漂移）")
            return []

        print(
            f"[WARN] 检测到 schema 漂移：{len(missing)} 个期望索引缺失",
            file=sys.stderr,
        )
        for idx in missing:
            print(f"  - {idx.name} (table={idx.table})", file=sys.stderr)
            print(f"    补建 SQL: {idx.ddl}", file=sys.stderr)

        if not repair_drift:
            print(
                "[INFO] 未启用 --repair-drift，不执行任何 DDL。"
                "人工确认后可用 `python scripts/init_db.py --repair-drift` "
                "幂等补建。",
                file=sys.stderr,
            )
            return missing

        print(
            "[PRECONDITION] 补建唯一索引前必须确认无重复数据；"
            "canary_records 请先运行 "
            "`python scripts/check_canary_duplicate_running.py` 且退出码为 0。",
            file=sys.stderr,
        )
        remaining: list[ExpectedIndex] = []
        for idx in missing:
            if not idx.auto_repair:
                print(
                    f"[SKIP] {idx.name}: 未配置自动补建，请人工评估后执行上面的 SQL",
                    file=sys.stderr,
                )
                remaining.append(idx)
                continue
            print(f"[REPAIR] 幂等补建 {idx.name} ...")
            await conn.execute(text(idx.ddl))
            print(f"[OK] {idx.name} 已补建")
        return remaining


async def init_database(*, repair_drift: bool = False) -> None:
    """初始化数据库 (新库建表+标记, 旧库升级, 迁移后索引自检)."""
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

    # 迁移后自检: 默认只读；补建 DDL 只在 --repair-drift 下执行。
    await check_index_drift(repair_drift=repair_drift)

    await engine.dispose()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="数据库初始化 / 迁移 + 期望索引漂移自检"
    )
    parser.add_argument(
        "--repair-drift",
        action="store_true",
        help=(
            "幂等补建缺失的可自动修复索引（当前仅 uq_canary_records_single_running）。"
            "默认关闭，避免迁移 job 自动改生产库结构。执行前必须先确认 "
            "canary_records 无重复 RUNNING 行（check_canary_duplicate_running.py 退出码 0）。"
        ),
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(init_database(repair_drift=args.repair_drift))
