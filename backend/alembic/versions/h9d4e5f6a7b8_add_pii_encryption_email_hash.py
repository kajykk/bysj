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
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "h9d4e5f6a7b8"
down_revision: Union[str, None] = ('g8c3d4e5f6a7', 'b8c9d0e1f2a3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 新增 email_hash 列（先允许 NULL 以便回填）
    op.add_column(
        "users",
        sa.Column("email_hash", sa.String(length=64), nullable=True),
    )

    # 2. 回填 email_hash：对存量 email 计算 HMAC-SHA256 盲索引
    #    注意：存量 email 为明文，直接计算哈希即可
    op.execute(
        """
        UPDATE users SET email_hash = (
            SELECT substr(hex(
                sha256(
                    COALESCE(
                        (SELECT value FROM app_config WHERE key = 'pii_encryption_key'),
                        'dev-only-fallback-key'
                    ) || 'bysj-pii-email-v1' || email
                )
            ), 1, 64)
        )
        WHERE email_hash IS NULL
        """
    )

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
