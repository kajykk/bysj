"""add_orm_constraints_p1d8

Revision ID: g8c3d4e5f6a7
Revises: f7b2c3d4e5f6
Create Date: 2026-06-20 13:00:00.000000

P1-D-8: 添加 ORM 约束 (CheckConstraint)

P0 级别:
- users.role: 枚举约束 (user/admin/counselor) - 防止权限提升
- users.status: 枚举约束 (active/deleted)
- alert_silences: ends_at > starts_at 时间顺序约束
- physiological_records: sleep_hours/heart_rate/systolic_bp/diastolic_bp 范围约束
- review_tasks: risk_level (0-10) / risk_score (0-100) 范围约束
- canary_records: traffic_percent (1-100) 范围约束

P1 级别:
- review_tasks: status/priority 枚举约束
- canary_records: status 枚举约束
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "g8c3d4e5f6a7"
down_revision: Union[str, None] = "f7b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # P1-D-8 P0: users.role 枚举约束 - 防止权限提升
    op.create_check_constraint(
        "ck_users_role_values",
        "users",
        "role IN ('user', 'admin', 'counselor')",
    )
    # P1-D-8 P0: users.status 枚举约束
    op.create_check_constraint(
        "ck_users_status_values",
        "users",
        "status IN ('active', 'inactive', 'deleted')",
    )

    # P1-D-8 P0: alert_silences 时间顺序约束
    op.create_check_constraint(
        "ck_alert_silences_time_order",
        "alert_silences",
        "ends_at > starts_at",
    )

    # P1-D-8 P0: physiological_records 生理指标范围约束
    op.create_check_constraint(
        "ck_physiological_records_sleep_hours",
        "physiological_records",
        "sleep_hours IS NULL OR (sleep_hours >= 0 AND sleep_hours <= 24)",
    )
    op.create_check_constraint(
        "ck_physiological_records_sleep_quality",
        "physiological_records",
        "sleep_quality IS NULL OR (sleep_quality >= 0 AND sleep_quality <= 10)",
    )
    op.create_check_constraint(
        "ck_physiological_records_exercise_minutes",
        "physiological_records",
        "exercise_minutes IS NULL OR exercise_minutes >= 0",
    )
    op.create_check_constraint(
        "ck_physiological_records_heart_rate",
        "physiological_records",
        "heart_rate IS NULL OR (heart_rate >= 30 AND heart_rate <= 250)",
    )
    op.create_check_constraint(
        "ck_physiological_records_systolic_bp",
        "physiological_records",
        "systolic_bp IS NULL OR (systolic_bp >= 50 AND systolic_bp <= 300)",
    )
    op.create_check_constraint(
        "ck_physiological_records_diastolic_bp",
        "physiological_records",
        "diastolic_bp IS NULL OR (diastolic_bp >= 30 AND diastolic_bp <= 200)",
    )
    op.create_check_constraint(
        "ck_physiological_records_steps",
        "physiological_records",
        "steps IS NULL OR steps >= 0",
    )

    # P1-D-8 P0: review_tasks 评分范围约束
    op.create_check_constraint(
        "ck_review_tasks_risk_level",
        "review_tasks",
        "risk_level >= 0 AND risk_level <= 10",
    )
    op.create_check_constraint(
        "ck_review_tasks_risk_score",
        "review_tasks",
        "risk_score >= 0 AND risk_score <= 100",
    )

    # P1-D-8 P1: review_tasks 枚举约束
    op.create_check_constraint(
        "ck_review_tasks_status_values",
        "review_tasks",
        "status IN ('pending', 'in_review', 'resolved', 'escalated', 'archived')",
    )
    op.create_check_constraint(
        "ck_review_tasks_priority_values",
        "review_tasks",
        "priority IN ('normal_review', 'high_risk_review', 'crisis_review')",
    )

    # P1-D-8 P0: canary_records 流量百分比范围约束
    op.create_check_constraint(
        "ck_canary_records_traffic_percent",
        "canary_records",
        "traffic_percent >= 1 AND traffic_percent <= 100",
    )
    # P1-D-8 P1: canary_records 枚举约束
    op.create_check_constraint(
        "ck_canary_records_status_values",
        "canary_records",
        "status IN ('pending', 'running', 'paused', 'rolled_back', 'completed')",
    )


def downgrade() -> None:
    constraints = [
        ("ck_canary_records_status_values", "canary_records"),
        ("ck_canary_records_traffic_percent", "canary_records"),
        ("ck_review_tasks_priority_values", "review_tasks"),
        ("ck_review_tasks_status_values", "review_tasks"),
        ("ck_review_tasks_risk_score", "review_tasks"),
        ("ck_review_tasks_risk_level", "review_tasks"),
        ("ck_physiological_records_steps", "physiological_records"),
        ("ck_physiological_records_diastolic_bp", "physiological_records"),
        ("ck_physiological_records_systolic_bp", "physiological_records"),
        ("ck_physiological_records_heart_rate", "physiological_records"),
        ("ck_physiological_records_exercise_minutes", "physiological_records"),
        ("ck_physiological_records_sleep_quality", "physiological_records"),
        ("ck_physiological_records_sleep_hours", "physiological_records"),
        ("ck_alert_silences_time_order", "alert_silences"),
        ("ck_users_status_values", "users"),
        ("ck_users_role_values", "users"),
    ]
    for name, table in constraints:
        op.drop_constraint(name, table, type_="check")
