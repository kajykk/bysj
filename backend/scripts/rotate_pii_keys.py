"""P2-4: PII 加密密钥轮换脚本

将数据库中所有 PII 加密字段用当前 PII_ENCRYPTION_KEY 重新加密,
同步更新 email_hash 盲索引. 配合 .env 中设置 PII_PREVIOUS_KEYS 实现零停机轮换.

轮换流程:
1. 在 .env 中:
   - 将当前 PII_ENCRYPTION_KEY 的值加入 PII_PREVIOUS_KEYS (逗号分隔)
   - 设置新的 PII_ENCRYPTION_KEY
2. 重启应用 (decrypt_field 会自动回退到旧密钥解密旧密文)
3. 运行本脚本将所有旧密文迁移到新密钥
4. 验证后清除 PII_PREVIOUS_KEYS (可选)

使用:
    cd backend
    python scripts/rotate_pii_keys.py                          # 预演 (dry-run)
    python scripts/rotate_pii_keys.py --apply                 # 实际执行
    python scripts/rotate_pii_keys.py --apply --batch-size 200   # 自定义批大小

注意:
- 脚本可重复执行: 已用新密钥加密的行会自动跳过 (通过密文比较检测).
- 失败行不会阻断后续行处理, 失败统计在末尾汇总.
- email_hash 盲索引会与 email 字段同步更新, 维护 UNIQUE 约束一致性.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

# 将 backend 目录加入 sys.path (脚本独立运行支持)
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.core.pii_crypto import (  # noqa: E402
    ENCRYPTED_PREFIX,
    ENCRYPTED_PREFIX_V2,
    compute_blind_index,
    decrypt_field,
    encrypt_field,
    is_encrypted_with_current_key,
)


@dataclass
class FieldSpec:
    """PII 字段规格说明.

    Attributes:
        table: 数据库表名
        column: 加密列名
        field: pii_crypto 中的 field key (用于密钥派生和 salt 选择)
        has_blind_index: 是否关联盲索引列 (如 email_hash), 需要同步更新
    """
    table: str
    column: str
    field: str
    has_blind_index: bool = False


# 需要轮换的 PII 字段 (与 app/models/user.py 中定义保持一致)
# 顺序: 先处理无盲索引的字段, 再处理 email (因为 email_hash 唯一约束可能影响批次)
PII_FIELDS: list[FieldSpec] = [
    FieldSpec("users", "phone", "phone"),
    FieldSpec("emergency_contacts", "name", "emergency_name"),
    FieldSpec("emergency_contacts", "phone", "emergency_phone"),
    FieldSpec("users", "email", "email", has_blind_index=True),
]


@dataclass
class RotationStats:
    """轮换统计信息."""
    table: str
    column: str
    total: int = 0
    rotated: int = 0          # 实际重加密的行数
    skipped: int = 0          # 跳过 (NULL/明文/已是新密文)
    failed: int = 0           # 失败行数
    blind_index_updated: int = 0

    def merge(self, other: "RotationStats") -> "RotationStats":
        self.total += other.total
        self.rotated += other.rotated
        self.skipped += other.skipped
        self.failed += other.failed
        self.blind_index_updated += other.blind_index_updated
        return self


def preflight_checks() -> list[str]:
    """执行前置检查, 返回错误列表 (空列表表示通过)."""
    errors: list[str] = []
    if not settings.pii_encryption_key:
        errors.append("PII_ENCRYPTION_KEY 未配置 (新密钥)")
        return errors
    if not settings.pii_previous_keys:
        errors.append(
            "PII_PREVIOUS_KEYS 未配置 (旧密钥列表). "
            "请将旧密钥加入此列表后再轮换, 否则旧密文仍可解密但无法区分新旧密文."
        )
        return errors

    current_key = settings.pii_encryption_key.strip()
    previous_keys = [k.strip() for k in settings.pii_previous_keys.split(",") if k.strip()]
    if current_key in previous_keys:
        errors.append(
            "PII_ENCRYPTION_KEY 出现在 PII_PREVIOUS_KEYS 中. "
            "新密钥不应与旧密钥相同, 请确认 .env 配置."
        )
    if len(previous_keys) != len(set(previous_keys)):
        errors.append("PII_PREVIOUS_KEYS 包含重复密钥, 请去重后再运行.")
    return errors


async def rotate_field(
    session,
    spec: FieldSpec,
    batch_size: int,
    apply: bool,
) -> RotationStats:
    """轮换单个字段的所有密文.

    流程:
    1. SELECT 读取所有原始密文 (绕过 TypeDecorator 的自动解密)
    2. 对每行: decrypt_field (含旧密钥回退) -> encrypt_field (用当前密钥)
    3. 比较新旧密文: 相同则跳过 (已是新密文), 不同则加入更新队列
    4. apply=True 时分批 UPDATE 提交
    """
    stats = RotationStats(table=spec.table, column=spec.column)

    select_sql = text(f"SELECT id, {spec.column} FROM {spec.table}")
    result = await session.execute(select_sql)
    rows = result.fetchall()
    stats.total = len(rows)

    if not rows:
        return stats

    updates: list[dict] = []

    for row_id, ciphertext in rows:
        if ciphertext is None or ciphertext == "":
            stats.skipped += 1
            continue
        # SEC-P2-004: 支持 v1 (Fernet) 和 v2 (AES-256-GCM) 双前缀检测
        if not (ciphertext.startswith(ENCRYPTED_PREFIX)
                or ciphertext.startswith(ENCRYPTED_PREFIX_V2)):
            # 未加密的旧数据 - 跳过 (避免误加密非 PII 数据)
            stats.skipped += 1
            continue

        # P2-4: 用当前密钥尝试解密判断是否需要轮换
        # (Fernet 每次加密 IV 不同, 不能通过密文比较判断)
        if is_encrypted_with_current_key(ciphertext, spec.field):
            # 当前密钥能解密 → 已是最新状态, 跳过
            stats.skipped += 1
            continue

        # 当前密钥解不开, 用 decrypt_field 回退到旧密钥解密
        try:
            plaintext = decrypt_field(ciphertext, spec.field)
            new_ciphertext = encrypt_field(plaintext, spec.field)
        except Exception as exc:
            stats.failed += 1
            # SEC-P3-004: 失败日志仅记录 id 和异常类名, 不记录完整异常消息
            # (异常消息可能包含部分明文 PII 数据, 存在泄露风险)
            print(f"  [FAIL] {spec.table}.{spec.column} id={row_id}: "
                  f"{exc.__class__.__name__} (详情见应用日志)")
            continue

        update_payload: dict = {"id": row_id, "value": new_ciphertext}
        if spec.has_blind_index:
            # 重计算盲索引 (使用当前 PII_ENCRYPTION_KEY 派生的 HMAC)
            update_payload["email_hash"] = compute_blind_index(plaintext, spec.field)
        updates.append(update_payload)
        stats.rotated += 1

    if not apply:
        if stats.rotated > 0:
            extra = " (含 email_hash 盲索引同步更新)" if spec.has_blind_index else ""
            print(f"  [DRY-RUN] {spec.table}.{spec.column}: "
                  f"将重加密 {stats.rotated} 行{extra} "
                  f"(跳过 {stats.skipped}, 失败 {stats.failed})")
        else:
            print(f"  [DRY-RUN] {spec.table}.{spec.column}: 无需更新 "
                  f"(总 {stats.total}, 跳过 {stats.skipped}, 失败 {stats.failed})")
        return stats

    if not updates:
        print(f"  [APPLIED] {spec.table}.{spec.column}: 无需更新 "
              f"(总 {stats.total}, 跳过 {stats.skipped}, 失败 {stats.failed})")
        return stats

    # 构造 UPDATE 语句 (表名/列名为硬编码常量, 非用户输入, 无注入风险)
    set_clause = f"{spec.column} = :value"
    if spec.has_blind_index:
        set_clause += ", email_hash = :email_hash"
    update_sql = text(f"UPDATE {spec.table} SET {set_clause} WHERE id = :id")

    # 分批提交: 每批 batch_size 行, 单独事务, 失败时回滚当前批不影响后续
    for i in range(0, len(updates), batch_size):
        batch = updates[i:i + batch_size]
        batch_num = i // batch_size + 1
        try:
            for params in batch:
                await session.execute(update_sql, params)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            stats.failed += len(batch)
            stats.rotated -= len(batch)
            # SEC-P3-004: 批次失败日志仅记录行数和异常类名, 不记录完整异常消息
            print(f"  [BATCH-FAIL] {spec.table}.{spec.column} batch #{batch_num} "
                  f"({len(batch)} rows): {exc.__class__.__name__} (详情见应用日志)")
            continue
        if spec.has_blind_index:
            stats.blind_index_updated += len(batch)

    print(f"  [APPLIED] {spec.table}.{spec.column}: 重加密 {stats.rotated} 行 "
          f"(跳过 {stats.skipped}, 失败 {stats.failed}, "
          f"盲索引更新 {stats.blind_index_updated})")
    return stats


async def run(apply: bool, batch_size: int) -> int:
    print("=" * 72)
    print("PII 加密密钥轮换脚本 (P2-4)")
    print(f"模式: {'APPLY (实际执行)' if apply else 'DRY-RUN (预演)'}")
    print(f"批大小: {batch_size}")
    print(f"当前密钥长度: {len(settings.pii_encryption_key)} chars")
    prev_keys = [k.strip() for k in settings.pii_previous_keys.split(",") if k.strip()]
    print(f"旧密钥数量: {len(prev_keys)}")
    print("=" * 72)

    errors = preflight_checks()
    if errors:
        print("\n[X] 前置检查失败:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("\n前置检查通过")
    print("-" * 72)

    overall = RotationStats(table="(overall)", column="(all)")
    try:
        async with AsyncSessionLocal() as session:
            for spec in PII_FIELDS:
                print(f"\n-> 处理 {spec.table}.{spec.column} (field={spec.field})")
                stats = await rotate_field(session, spec, batch_size, apply)
                overall.merge(stats)
    finally:
        await engine.dispose()

    print("\n" + "-" * 72)
    print("汇总:")
    print(f"  总行数:                {overall.total}")
    print(f"  重加密成功:            {overall.rotated}")
    print(f"  跳过 (NULL/已是新密文): {overall.skipped}")
    print(f"  失败:                  {overall.failed}")
    print(f"  盲索引更新:            {overall.blind_index_updated}")
    print("-" * 72)

    if not apply and overall.rotated > 0:
        print("\n这是预演结果. 若确认无误, 运行: "
              "python scripts/rotate_pii_keys.py --apply")
    elif apply and overall.failed == 0 and overall.rotated > 0:
        print("\n[X] 轮换完成. 验证应用功能正常后, 可清除 PII_PREVIOUS_KEYS 配置.")
    elif apply and overall.failed == 0 and overall.rotated == 0:
        print("\n[OK] 无需轮换 (所有密文已是当前密钥加密).")
    elif apply and overall.failed > 0:
        print(f"\n[!] 有 {overall.failed} 行失败, 请检查日志后重试 "
              "(脚本可重复执行, 已成功的行会自动跳过).")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="PII 加密密钥轮换脚本")
    parser.add_argument("--apply", action="store_true",
                        help="实际执行 (默认 dry-run 预演)")
    parser.add_argument("--batch-size", type=int, default=100,
                        help="批处理大小 (默认 100, 每批提交一次事务)")
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size 必须 >= 1")
    return asyncio.run(run(apply=args.apply, batch_size=args.batch_size))


if __name__ == "__main__":
    sys.exit(main())
