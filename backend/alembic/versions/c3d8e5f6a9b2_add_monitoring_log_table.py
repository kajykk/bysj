"""add_monitoring_log_table

Revision ID: c3d8e5f6a9b2
Revises: 5f2c9d3a1b7e
Create Date: 2026-04-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d8e5f6a9b2"
down_revision: Union[str, None] = "5f2c9d3a1b7e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "monitoring_logs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False, comment="事件类型: inference, fallback, input_anomaly, drift_alert, model_load, canary_switch"),
        sa.Column("model_version", sa.String(length=50), nullable=True, comment="模型版本号"),
        sa.Column("user_id", sa.Integer(), nullable=True, comment="关联用户ID"),
        sa.Column("request_payload", sa.JSON(), nullable=True, comment="请求 payload 摘要(脱敏)"),
        sa.Column("response_summary", sa.JSON(), nullable=True, comment="响应摘要"),
        sa.Column("fallback_reason", sa.Text(), nullable=True, comment="回退原因(如触发回退则记录)"),
        sa.Column("latency_ms", sa.Float(), nullable=True, comment="请求延迟(毫秒)"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False, comment="记录创建时间"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_monitoring_logs_event_type_created_at", "monitoring_logs", ["event_type", "created_at"], unique=False)
    op.create_index("ix_monitoring_logs_model_version_created_at", "monitoring_logs", ["model_version", "created_at"], unique=False)
    op.create_index("ix_monitoring_logs_user_id", "monitoring_logs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_monitoring_logs_model_version_created_at", table_name="monitoring_logs")
    op.drop_index("ix_monitoring_logs_event_type_created_at", table_name="monitoring_logs")
    op.drop_index("ix_monitoring_logs_user_id", table_name="monitoring_logs")
    op.drop_table("monitoring_logs")
