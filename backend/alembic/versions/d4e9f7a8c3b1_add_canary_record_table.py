"""add_canary_record_table

Revision ID: d4e9f7a8c3b1
Revises: c3d8e5f6a9b2
Create Date: 2026-04-28 12:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4e9f7a8c3b1"
down_revision: Union[str, None] = "c3d8e5f6a9b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "canary_records",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False, comment="灰度版本号"),
        sa.Column("traffic_percent", sa.Integer(), nullable=False, default=1, comment="流量百分比 (1-100)"),
        sa.Column("status", sa.String(length=20), nullable=False, default="pending", comment="状态: pending, running, paused, rolled_back, completed"),
        sa.Column("auto_rollback_thresholds", sa.JSON(), nullable=True, comment="自动回滚阈值配置"),
        sa.Column("triggered_by", sa.Integer(), nullable=True, comment="触发用户ID"),
        sa.Column("started_at", sa.DateTime(), nullable=True, comment="灰度开始时间"),
        sa.Column("ended_at", sa.DateTime(), nullable=True, comment="灰度结束时间"),
        sa.Column("rollback_reason", sa.Text(), nullable=True, comment="回退原因"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False, comment="记录创建时间"),
        sa.ForeignKeyConstraint(["triggered_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_canary_records_status_started_at", "canary_records", ["status", "started_at"], unique=False)
    op.create_index("ix_canary_records_version_created_at", "canary_records", ["version", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_canary_records_version_created_at", table_name="canary_records")
    op.drop_index("ix_canary_records_status_started_at", table_name="canary_records")
    op.drop_table("canary_records")
