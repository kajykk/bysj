"""add_review_and_crisis_tables

Revision ID: a1b2c3d4e5f6
Revises: f6a1b9c0e5d3
Create Date: 2026-05-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f6a1b9c0e5d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create review_tasks table
    op.create_table(
        "review_tasks",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("risk_report_id", sa.Integer(), sa.ForeignKey("risk_assessments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("risk_level", sa.Integer(), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("review_triggers", sa.Text(), nullable=True, default="[]"),
        sa.Column("crisis_override", sa.Boolean(), nullable=False, default=False),
        sa.Column("status", sa.String(length=20), nullable=False, default="pending", index=True),
        sa.Column("priority", sa.String(length=20), nullable=False, default="normal_review", index=True),
        sa.Column("assigned_to", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("resolved_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )

    # Create crisis_events table
    op.create_table(
        "crisis_events",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("risk_assessments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("trigger_source", sa.String(length=20), nullable=False),
        sa.Column("crisis_keywords", sa.Text(), nullable=True, default="[]"),
        sa.Column("crisis_score", sa.Float(), nullable=True),
        sa.Column("input_summary", sa.Text(), nullable=True),
        sa.Column("review_task_id", sa.Integer(), sa.ForeignKey("review_tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, default="detected"),
        sa.Column("handled_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("handled_action", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("handled_at", sa.DateTime(), nullable=True),
    )

    # Create additional indexes for crisis_events
    op.create_index("ix_crisis_events_status_created_at", "crisis_events", ["status", "created_at"], unique=False)
    op.create_index("ix_crisis_events_trigger_source_created_at", "crisis_events", ["trigger_source", "created_at"], unique=False)


def downgrade() -> None:
    # Drop crisis_events indexes and table
    op.drop_index("ix_crisis_events_trigger_source_created_at", table_name="crisis_events")
    op.drop_index("ix_crisis_events_status_created_at", table_name="crisis_events")
    op.drop_table("crisis_events")

    # Drop review_tasks table
    op.drop_table("review_tasks")
