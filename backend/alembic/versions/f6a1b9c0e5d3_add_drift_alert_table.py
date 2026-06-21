"""add_drift_alert_table

Revision ID: f6a1b9c0e5d3
Revises: e5f0a8b9d4c2
Create Date: 2026-04-28 12:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f6a1b9c0e5d3"
down_revision: Union[str, None] = "e5f0a8b9d4c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "drift_alerts",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("model_version", sa.String(length=50), nullable=True, comment="模型版本号"),
        sa.Column("feature_name", sa.String(length=100), nullable=True, comment="发生漂移的特征名"),
        sa.Column("drift_type", sa.String(length=30), nullable=False, comment="漂移类型: feature_drift, prediction_drift, performance_drift"),
        sa.Column("severity", sa.String(length=20), nullable=False, default="MEDIUM", comment="严重程度: LOW, MEDIUM, HIGH, CRITICAL"),
        sa.Column("metric_value", sa.Float(), nullable=True, comment="漂移指标值"),
        sa.Column("threshold", sa.Float(), nullable=True, comment="阈值"),
        sa.Column("details", sa.JSON(), nullable=True, comment="详细数据"),
        sa.Column("resolved_at", sa.DateTime(), nullable=True, comment="告警解决时间"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False, comment="记录创建时间"),
    )
    op.create_index("ix_drift_alerts_severity_created_at", "drift_alerts", ["severity", "created_at"], unique=False)
    op.create_index("ix_drift_alerts_model_version_created_at", "drift_alerts", ["model_version", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_drift_alerts_model_version_created_at", table_name="drift_alerts")
    op.drop_index("ix_drift_alerts_severity_created_at", table_name="drift_alerts")
    op.drop_table("drift_alerts")
