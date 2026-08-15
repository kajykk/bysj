"""add_super_admin_role

平台管理员角色 (super_admin) 入列 users.role 枚举约束.

背景: 2026-08 全量审核拍板项 — 平台级管理员独立角色.
约束 ck_users_role_values 由 b1a7c0d9f4e8 创建, 现需放宽为
role IN ('user', 'admin', 'counselor', 'super_admin').

采用 batch_alter_table 以同时兼容 PostgreSQL (ALTER TABLE DROP CONSTRAINT)
与 SQLite (表重建), 与项目 dev/prod 双数据库场景对齐.

Revision ID: l3c5d7e9f0a1
Revises: k2a7b8c9d0e1
Create Date: 2026-08-15 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
from app.core.contracts import (
    USER_ROLE_ADMIN,
    USER_ROLE_COUNSELOR,
    USER_ROLE_SUPER_ADMIN,
    USER_ROLE_USER,
)

# revision identifiers, used by Alembic.
revision: str = "l3c5d7e9f0a1"
down_revision: Union[str, None] = "k2a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 与 app/models/user.py 的 ck_users_role_values 定义保持同源
    role_values = (
        f"role IN ('{USER_ROLE_USER}', '{USER_ROLE_ADMIN}', "
        f"'{USER_ROLE_COUNSELOR}', '{USER_ROLE_SUPER_ADMIN}')"
    )
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("ck_users_role_values", type_="check")
        batch_op.create_check_constraint("ck_users_role_values", role_values)


def downgrade() -> None:
    role_values = (
        f"role IN ('{USER_ROLE_USER}', '{USER_ROLE_ADMIN}', '{USER_ROLE_COUNSELOR}')"
    )
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("ck_users_role_values", type_="check")
        batch_op.create_check_constraint("ck_users_role_values", role_values)
