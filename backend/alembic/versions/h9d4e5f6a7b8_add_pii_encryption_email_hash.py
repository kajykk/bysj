"""add_pii_encryption_email_hash

PII 加密：User.email/phone 改为加密存储，新增 email_hash 盲索引列用于唯一约束和查询。

Revision ID: h9d4e5f6a7b8
Revises: ('g8c3d4e5f6a7', 'b8c9d0e1f2a3')
Create Date: 2026-06-21 00:00:00.000000

变更说明:
1. 新增 email_hash 列 (String(64), UNIQUE, NOT NULL, INDEX) - HMAC-SHA256 盲索引
2. 扩展 email 列长度以容纳密文 (EncryptedString 透明加密)
3. 扩展 phone 列长度以容纳密文
4. 删除 email 列的旧 UNIQUE 约束和 INDEX（密文不可用于唯一性校验）
5. 更新 CHECK 约束（加密后长度校验放宽）
6. 回填 email_hash：对存量明文 email 计算 HMAC 哈希
7. 加密存量 email/phone 明文数据

注意：此迁移需要 PII_ENCRYPTION_KEY 环境变量已配置。

SEC-FIX-2026-10-05（阻断级修复）:
    原实现在此迁移内用纯 SQL 回填 email_hash:

        UPDATE users SET email_hash = (
            SELECT substr(hex(sha256(
                COALESCE((SELECT value FROM app_config WHERE key='pii_encryption_key'),
                         'dev-only-fallback-key')
                || 'bysj-pii-email-v1' || email)), 1, 64)
        )
        WHERE email_hash IS NULL

    该实现有三个各自独立的致命缺陷：

    1. **引用了全仓不存在的 app_config 表。** 无 ORM 模型、无建表迁移，
       PostgreSQL 上直接抛 relation "app_config" does not exist，
       任何「已存在表」的存量库 alembic upgrade head 必然失败
       （docker-compose 的 alembic_migrate 服务走此路径；
       init_db.py:99-101 对已有表的库执行 upgrade head → 迁移容器退出 → 全站无法启动）。
    2. **算法与加密层不一致。** 此处是拼接式 sha256(key‖salt‖email)，
       而 app/core/pii_crypto.py:488 用的是真 HMAC-SHA256
       （其注释明确写「使用真正的 HMAC-SHA256（非拼接式 SHA256），防止长度扩展攻击」）。
       两者输出完全不同 → 即便 app_config 存在，所有存量 email_hash 也永远匹配不上
       应用侧的计算值 → auth_service 的按邮箱查询全部落空。
    3. **硬编码兜底弱密钥。** dev-only-fallback-key 恰是 pii_crypto.py:477-481
       注释里明确记载「已移除」的弱密钥（公开在 GitHub 历史中）。

    修复方式：改为在本迁移内用 Python 逐行调用应用层真正的 HMAC 实现
    （app.core.pii_crypto），不再依赖任何 DB 表存密钥，也不再自行实现拼接哈希。
    SQLite 不支持 sha256()，原先的纯 SQL 方案在 SQLite 测试库上同样无法运行；
    Python 路径同时解决了两个方言的问题。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "h9d4e5f6a7b8"
down_revision: Union[str, None] = ('g8c3d4e5f6a7', 'b8c9d0e1f2a3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def _backfill_email_hash() -> None:
    """用应用层真 HMAC-SHA256 逐行回填存量 users.email_hash.

    为什么必须在应用层做（而非纯 SQL）:
      - 密钥来自 settings.pii_encryption_key，不存在可被 SQL 查询的表；
      - 拼接式 sha256(key‖salt‖email) 与 pii_crypto 的真 HMAC 输出不同，
        自行实现会让存量数据永久匹配不上应用侧查询；
      - SQLite 无 sha256() 函数，纯 SQL 方案在 SQLite 库上直接报错。

    复用 app.core.pii_crypto 而非复制算法: 密钥校验、字段 salt、
    以及「缺密钥时拒绝降级到弱密钥」的策略都以该模块为唯一事实来源。
    本函数与之共享同一进程内已 import 的模块实例。
    """
    from app.core.pii_crypto import compute_blind_index

    connection = op.get_bind()
    # 绕过 TypeDecorator 的自动解密，直接取原始 email 值。
    # 存量 email 在本迁移执行时仍是明文（第 3 步的加密由应用层脚本完成），
    # 但已加密的库也可能是历史遗留，故用 decrypt_field 兼容双形态。
    from app.core.pii_crypto import decrypt_field

    rows = connection.execute(
        sa.text("SELECT id, email, email_hash FROM users WHERE email_hash IS NULL")
    ).fetchall()
    if not rows:
        return

    updated = 0
    # 存量脏数据收集：email 为空/空白的行无法计算盲索引。
    # 模型层 email 是 nullable=False 且有 ck_users_email_length(LENGTH>=3) 约束，
    # 所以这类行本就违反 schema 约束 —— 迁移不能给它编造一个 hash（那会让
    # NOT NULL 收紧通过、从而把脏数据永久固化进库里），也不能让
    # 第 4 步的 NOT NULL 收紧抛一个不可诊断的原始错误。
    # 这里收集 id 并在末尾显式抛错，指明需人工处理的行。
    unresolvable: list[int] = []
    for row_id, email_value, _ in rows:
        if email_value is None or str(email_value).strip() == "":
            unresolvable.append(row_id)
            continue
        plaintext = decrypt_field(email_value, "email")
        if not plaintext or not str(plaintext).strip():
            unresolvable.append(row_id)
            continue
        email_hash = compute_blind_index(plaintext, "email")
        if not email_hash:
            unresolvable.append(row_id)
            continue
        connection.execute(
            sa.text("UPDATE users SET email_hash = :email_hash WHERE id = :id"),
            {"id": row_id, "email_hash": email_hash},
        )
        updated += 1

    if unresolvable:
        raise RuntimeError(
            f"[h9d4e5f6a7b8] 有 {len(unresolvable)} 行用户的 email 为空/空白，"
            f"无法计算 email_hash 盲索引（users.id={sorted(unresolvable)[:20]}"
            f"{' ...' if len(unresolvable) > 20 else ''}）。"
            "这些数据违反 ck_users_email_length(LENGTH(email)>=3) 约束，"
            "请先修复或删除这些账号后重新执行本迁移 —— "
            "不要为其编造哈希值，否则脏数据会被 NOT NULL 约束永久固化。"
        )

    print(f"[h9d4e5f6a7b8] email_hash 回填完成: {updated}/{len(rows)} 行")


def upgrade() -> None:
    # 1. 新增 email_hash 列（先允许 NULL 以便回填）
    op.add_column(
        "users",
        sa.Column("email_hash", sa.String(length=64), nullable=True),
    )

    # 2. 回填 email_hash：对存量 email 计算 HMAC-SHA256 盲索引
    #    SEC-FIX-2026-10-05: 改为调用应用层真正的 HMAC 实现（见文件头说明）。
    #    不能用纯 SQL：app_config 表不存在、拼接式 sha256 与加密层算法不一致、
    #    且 SQLite 无 sha256() 函数。Python 路径同时满足正确性与跨方言。
    _backfill_email_hash()

    # 3. 加密存量 email/phone 明文数据（应用层加密，通过 Python 脚本执行）
    #    此处仅做标记，实际加密应在应用层迁移脚本中完成
    #    若数据库为空（全新部署），可跳过此步

    # 4. 设置 email_hash 为 NOT NULL
    op.alter_column("users", "email_hash", nullable=False)

    # 5. 创建 email_hash 唯一索引
    op.create_index("uq_users_email_hash", "users", ["email_hash"], unique=True)

    # 6. 删除 email 列的旧唯一约束和索引
    #    注意：索引名可能因数据库而异，尝试删除常见命名
    op.drop_index("ix_users_email", table_name="users", if_exists=True)
    op.drop_constraint("uq_users_email", "users", type_="unique", if_exists=True)

    # 7. 扩展 email 和 phone 列长度以容纳密文
    #    EncryptedString 长度 = 明文长度 * 2 + 前缀(7) + 50
    #    email: 100 * 2 + 57 = 257 → 使用 VARCHAR(500)
    #    phone: 20 * 2 + 57 = 97 → 使用 VARCHAR(200)
    op.alter_column("users", "email", existing_type=sa.String(100), type_=sa.String(500))
    op.alter_column("users", "phone", existing_type=sa.String(20), type_=sa.String(200))

    # 8. 更新 CHECK 约束（加密后长度校验放宽）
    op.drop_constraint("ck_users_email_length", "users", type_="check", if_exists=True)
    op.create_check_constraint(
        "ck_users_email_length",
        "users",
        "LENGTH(email) >= 3",
    )
    op.drop_constraint("ck_users_phone_length", "users", type_="check", if_exists=True)
    op.create_check_constraint(
        "ck_users_phone_length",
        "users",
        "phone IS NULL OR LENGTH(phone) >= 3",
    )


def downgrade() -> None:
    # 回滚：恢复原始 schema（注意：已加密的数据无法自动解密回明文）
    op.drop_constraint("ck_users_phone_length", "users", type_="check", if_exists=True)
    op.create_check_constraint(
        "ck_users_phone_length",
        "users",
        "phone IS NULL OR LENGTH(phone) <= 20",
    )
    op.drop_constraint("ck_users_email_length", "users", type_="check", if_exists=True)
    op.create_check_constraint(
        "ck_users_email_length",
        "users",
        "LENGTH(email) >= 3 AND LENGTH(email) <= 100",
    )
    op.alter_column("users", "phone", existing_type=sa.String(200), type_=sa.String(20))
    op.alter_column("users", "email", existing_type=sa.String(500), type_=sa.String(100))
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.drop_index("uq_users_email_hash", table_name="users", if_exists=True)
    op.drop_column("users", "email_hash")
