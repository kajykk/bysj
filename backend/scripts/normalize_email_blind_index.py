"""RES-P1-014: email 盲索引归一化迁移脚本

背景:
    compute_blind_index 原实现未做归一化, "Alice@x.com" 与 "alice@x.com"
    产生两个不同 email_hash。修复后写入侧统一为归一化值 (strip + casefold),
    但存量的 email_hash 仍是未归一化值 —— 读取侧已通过 blind_index_candidates
    双查兼容, 本脚本用于把存量数据收敛到归一化值, 使双查最终退化为单查。

风险 (必须先检出):
    归一化会让原本"不同"的两个邮箱映射到同一个 hash, 撞 users.email_hash 的
    UNIQUE 约束。因此本脚本**不会**自动合并或删除账号 —— 冲突组一律跳过并报告,
    由人工决定合并/改名。

使用:
    cd backend
    python scripts/normalize_email_blind_index.py                 # 预演 (dry-run)
    python scripts/normalize_email_blind_index.py --apply         # 实际执行
    python scripts/normalize_email_blind_index.py --apply --batch-size 200

退出码:
    0 = 无待更新项, 或全部更新成功
    1 = 前置检查失败 / 存在 UNIQUE 冲突 / 存在更新失败的行
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path

# 将 backend 目录加入 sys.path (脚本独立运行支持)
# 注意: 必须插入 str 而非 Path 对象 —— import 系统会静默跳过 sys.path 中的非字符串条目,
# 导致脚本独立运行时 ModuleNotFoundError: No module named 'app' (实测确认)。
BACKEND_DIR = str(Path(__file__).resolve().parents[1])
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.core.pii_crypto import (  # noqa: E402
    compute_blind_index,
    decrypt_field,
)


@dataclass
class MigrationStats:
    """迁移统计."""

    total: int = 0
    to_update: int = 0
    unchanged: int = 0
    updated: int = 0
    failed: int = 0
    conflict_rows: int = 0
    conflict_groups: list[list[int]] = field(default_factory=list)


def preflight_checks() -> list[str]:
    """执行前置检查, 返回错误列表 (空列表表示通过)."""
    errors: list[str] = []
    if not settings.pii_encryption_key:
        errors.append("PII_ENCRYPTION_KEY 未配置, 无法解密 email 明文")
    return errors


async def load_users(session) -> list[tuple[int, str]]:
    """读取 users 表的 (id, email 密文), 绕过 TypeDecorator 的自动解密."""
    result = await session.execute(text("SELECT id, email FROM users ORDER BY id"))
    return [(row_id, email) for row_id, email in result.fetchall()]


def build_plan(
    rows: list[tuple[int, str]],
    current_hash_by_id: dict[int, str],
) -> tuple[list[dict], MigrationStats]:
    """解密明文并生成更新计划; 检出归一化后的 hash 冲突.

    Args:
        rows: (id, email 密文) 列表
        current_hash_by_id: 库中现有的 (id, email_hash) 映射, 用于判断已迁移

    Returns:
        (updates, stats)。updates 元素形如 {"id": int, "email_hash": str}
    """
    stats = MigrationStats(total=len(rows))

    # 第一遍: 解密 + 计算归一化 hash
    normalized_by_id: dict[int, str] = {}
    for row_id, ciphertext in rows:
        if ciphertext is None or ciphertext == "":
            stats.unchanged += 1
            continue
        try:
            plaintext = decrypt_field(ciphertext, "email")
        except Exception as exc:
            # 不记录异常消息 (可能含部分明文 PII)
            print(f"  [FAIL] users.id={row_id} 解密失败: {exc.__class__.__name__}")
            stats.failed += 1
            continue
        if not plaintext:
            stats.unchanged += 1
            continue
        normalized_by_id[row_id] = compute_blind_index(plaintext, "email")

    # 第二遍: 按归一化 hash 分组, 检出撞 UNIQUE 的组
    groups: dict[str, list[int]] = {}
    for row_id, new_hash in normalized_by_id.items():
        groups.setdefault(new_hash, []).append(row_id)

    conflicted_ids: set[int] = set()
    for new_hash, ids in groups.items():
        if len(ids) > 1:
            stats.conflict_groups.append(ids)
            conflicted_ids.update(ids)

    # 第三遍: 生成更新计划 (已在库中的归一化值视为无需更新)
    updates: list[dict] = []
    for row_id, ciphertext in rows:
        if row_id not in normalized_by_id or row_id in conflicted_ids:
            continue
        new_hash = normalized_by_id[row_id]
        current_hash = current_hash_by_id.get(row_id)
        if current_hash == new_hash:
            stats.unchanged += 1
            continue
        updates.append({"id": row_id, "email_hash": new_hash})
        stats.to_update += 1

    stats.conflict_rows = len(conflicted_ids)
    return updates, stats


async def main(apply: bool, batch_size: int) -> int:
    errors = preflight_checks()
    if errors:
        for err in errors:
            print(f"[PREFLIGHT-FAIL] {err}")
        return 1

    print("=" * 70)
    print("email 盲索引归一化迁移 (RES-P1-014)")
    print(f"模式: {'APPLY (实际写入)' if apply else 'DRY-RUN (预演, 不写入)'}")
    print("=" * 70)

    async with AsyncSessionLocal() as session:
        rows = await load_users(session)
        result = await session.execute(text("SELECT id, email_hash FROM users ORDER BY id"))
        current_hash_by_id = {row_id: h for row_id, h in result.fetchall()}

        updates, stats = build_plan(rows, current_hash_by_id)

        print(f"\n扫描 users 行数: {stats.total}")
        print(f"  待更新 (归一化后 hash 变化): {stats.to_update}")
        print(f"  无需更新 (已归一化 / 空值): {stats.unchanged}")
        print(f"  解密失败: {stats.failed}")

        if stats.conflict_groups:
            print(
                f"\n[冲突] 检出 {len(stats.conflict_groups)} 组 UNIQUE 冲突, "
                f"涉及 {stats.conflict_rows} 个账号 —— 归一化后这些邮箱会映射到同一个 hash:"
            )
            for ids in stats.conflict_groups:
                print(f"  - users.id = {sorted(ids)}")
            print(
                "  这些行已跳过, 不会自动合并或删除。"
                "请先人工处理 (合并账号 / 修改其中一个邮箱) 后重跑本脚本。"
            )

        if not updates:
            print("\n无需更新的行, 迁移已收敛。")
            await engine.dispose()
            return 1 if (stats.failed or stats.conflict_groups) else 0

        if not apply:
            print(f"\n[DRY-RUN] 将更新 {len(updates)} 行 email_hash。")
            print("  确认无误后加 --apply 执行。")
            await engine.dispose()
            return 1 if (stats.failed or stats.conflict_groups) else 0

        update_sql = text("UPDATE users SET email_hash = :email_hash WHERE id = :id")
        for i in range(0, len(updates), batch_size):
            batch = updates[i : i + batch_size]
            try:
                for params in batch:
                    await session.execute(update_sql, params)
                await session.commit()
                stats.updated += len(batch)
                print(f"  [OK] 已提交第 {i // batch_size + 1} 批 ({len(batch)} 行)")
            except Exception as exc:
                await session.rollback()
                stats.failed += len(batch)
                stats.updated -= len(batch)
                print(f"  [FAIL] 第 {i // batch_size + 1} 批回滚: {exc.__class__.__name__}")

    await engine.dispose()

    print("\n" + "=" * 70)
    print(f"更新成功: {stats.updated} / 待更新: {len(updates)}")
    print(f"失败: {stats.failed} | UNIQUE 冲突组: {len(stats.conflict_groups)}")
    print("=" * 70)
    print(
        "提示: 迁移完成后 blind_index_candidates 对已迁移数据退化为单值, "
        "读取侧双查仍保留以兜底未迁移行。"
    )
    return 1 if (stats.failed or stats.conflict_groups) else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="email 盲索引归一化迁移 (RES-P1-014)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际执行更新 (默认仅 dry-run 预演)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="每批提交的行数 (默认 200)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(asyncio.run(main(apply=args.apply, batch_size=args.batch_size)))
