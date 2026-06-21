"""add_oplog_composite_indexes_v1_36

Revision ID: a7b8c9d0e1f2
Revises: 6e25d8827741
Create Date: 2026-06-03 18:00:00.000000

v1.36: 为 operation_logs 表增加 2 个复合索引
- idx_oplog_action_created: (action_type, created_at)
  用于按 action_type 在时间范围内高效查询 (告警通道/AM 同步/dedup_lock 统计)
- idx_oplog_target_action: (target_type, target_id, action_type)
  用于特定对象的审计追踪
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "6e25d8827741"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "idx_oplog_action_created",
        "operation_logs",
        ["action_type", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_oplog_target_action",
        "operation_logs",
        ["target_type", "target_id", "action_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_oplog_target_action", table_name="operation_logs")
    op.drop_index("idx_oplog_action_created", table_name="operation_logs")
