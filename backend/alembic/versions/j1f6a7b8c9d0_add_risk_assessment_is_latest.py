"""add_risk_assessment_is_latest

PERF-P2-002: 为 risk_assessments 表添加 is_latest 列，标记每个用户的最新风险评估。
消除 list_my_users 中的 GROUP BY + max(created_at) 子查询，改为 WHERE is_latest = True 直接查询。

Revision ID: j1f6a7b8c9d0
Revises: i0e5f6a7b8c9
Create Date: 2026-07-13 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "j1f6a7b8c9d0"
down_revision: Union[str, None] = "i0e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PERF-P2-002: 新增 is_latest 列，默认 False
    op.add_column(
        "risk_assessments",
        sa.Column(
            "is_latest",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    # 回填: 为每个用户标记最新风险评估 (created_at 最大的那条)
    # 使用 id (主键) 替代 rowid, 确保 SQLite/PostgreSQL 兼容
    # 注意: 若同用户存在 created_at 相同的多条记录, 均标记为 is_latest=True
    #       应用层创建新记录时会先清除旧 is_latest, 不会产生数据不一致
    op.execute(
        """
        UPDATE risk_assessments
        SET is_latest = 1
        WHERE id IN (
            SELECT ra.id
            FROM risk_assessments ra
            INNER JOIN (
                SELECT user_id, MAX(created_at) AS max_created_at
                FROM risk_assessments
                GROUP BY user_id
            ) latest ON ra.user_id = latest.user_id
                     AND ra.created_at = latest.max_created_at
        )
        """
    )

    # 创建复合索引: (user_id, is_latest) — 加速 list_my_users 查询
    op.create_index(
        "ix_risk_assessments_user_is_latest",
        "risk_assessments",
        ["user_id", "is_latest"],
    )


def downgrade() -> None:
    op.drop_index("ix_risk_assessments_user_is_latest", table_name="risk_assessments")
    op.drop_column("risk_assessments", "is_latest")
