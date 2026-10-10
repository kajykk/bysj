"""上线前脏数据检查: canary_records 是否存在重复 RUNNING.

背景:
    迁移 n2b3c4d5e6f7_add_canary_single_running_unique_index 要加「同一
    route_prefix 至多一条 RUNNING」的部分唯一索引。重复 RUNNING 会让
    create_index(unique) 直接失败（或迫使迁移先改数据），因此**上线前必须
    先跑本脚本**。

用法:
    cd backend && python scripts/check_canary_duplicate_running.py

退出码:
    0 = 无重复（可安全执行迁移）
    1 = 存在重复（迁移会把多余行置为 rolled_back，需人工确认后再上线）
    2 = 执行失败（连接/表不存在等）

注意:
    本脚本只读，不做任何写入。迁移的清理策略是「置为 rolled_back 并写明
    rollback_reason」而非删除，保留灰度审计证据。
"""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, ".")

from sqlalchemy import text  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402


async def main() -> int:
    print("=" * 70)
    print("canary_records 重复 RUNNING 脏数据检查")
    print("=" * 70)

    try:
        async with AsyncSessionLocal() as db:
            # 在 Python 侧分组，避免 GROUP_CONCAT（SQLite/MySQL）与
            # string_agg（PostgreSQL）的方言差异，脚本跨库可用。
            rows = (
                await db.execute(
                    text(
                        "SELECT id, version, route_prefix, started_at "
                        "FROM canary_records WHERE status = 'running' "
                        "ORDER BY started_at DESC NULLS LAST, id DESC"
                    )
                )
            ).all()
    except Exception as exc:  # noqa: BLE001 - 脚本入口需给出明确退出码
        print(f"[X] 检查失败: {exc}", file=sys.stderr)
        return 2

    # 作用域键与迁移 n2b3c4d5e6f7 的索引表达式保持一致
    grouped: dict[str, list[tuple[int, str | None]]] = {}
    for row_id, version, route_prefix, _started_at in rows:
        key = route_prefix or ""
        grouped.setdefault(key, []).append((int(row_id), version))

    duplicates = {k: v for k, v in grouped.items() if len(v) > 1}

    if not duplicates:
        print("[OK] 无重复 RUNNING 金丝雀, 可安全执行迁移 n2b3c4d5e6f7")
        return 0

    print(f"[!] 发现 {len(duplicates)} 个作用域存在重复 RUNNING:\n")
    for scope_key, items in duplicates.items():
        shown = scope_key or "(NULL = 全局金丝雀)"
        print(f"  - route_prefix={shown}: {len(items)} 条 RUNNING")
        print(f"    ids={[i for i, _ in items]}")
        print(f"    versions={[v for _, v in items]}")

    print(
        "\n迁移会把每个作用域中 started_at 最旧的多余行置为 "
        "status='rolled_back'（保留行与审计字段）。"
    )
    print("请人工确认后再执行 alembic upgrade head。")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
