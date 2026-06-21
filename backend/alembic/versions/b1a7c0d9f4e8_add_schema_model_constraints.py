"""add_schema_model_constraints

Revision ID: b1a7c0d9f4e8
Revises: 5f2c9d3a1b7e
Create Date: 2026-04-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1a7c0d9f4e8"
down_revision: Union[str, None] = "5f2c9d3a1b7e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_users_username_length",
        "users",
        "LENGTH(username) >= 3 AND LENGTH(username) <= 50",
    )
    op.create_check_constraint(
        "ck_users_email_length",
        "users",
        "LENGTH(email) >= 3 AND LENGTH(email) <= 100",
    )
    op.create_check_constraint(
        "ck_users_phone_length",
        "users",
        "phone IS NULL OR LENGTH(phone) <= 20",
    )
    op.create_check_constraint(
        "ck_users_password_hash_length",
        "users",
        "LENGTH(password_hash) <= 255",
    )
    op.create_check_constraint(
        "ck_users_role_length",
        "users",
        "LENGTH(role) <= 20",
    )
    op.create_check_constraint(
        "ck_users_status_length",
        "users",
        "LENGTH(status) <= 20",
    )
    op.create_check_constraint(
        "ck_users_avatar_url_length",
        "users",
        "avatar_url IS NULL OR LENGTH(avatar_url) <= 500",
    )

    op.create_check_constraint(
        "ck_user_profiles_age",
        "user_profiles",
        "age IS NULL OR (age >= 0 AND age <= 120)",
    )
    op.create_check_constraint(
        "ck_user_counselor_bindings_bind_code_length",
        "user_counselor_bindings",
        "LENGTH(bind_code) >= 4 AND LENGTH(bind_code) <= 10",
    )

    op.create_check_constraint(
        "ck_warning_notifications_current_level",
        "warning_notifications",
        "current_level >= 0 AND current_level <= 10",
    )
    op.create_check_constraint(
        "ck_warning_notifications_previous_level",
        "warning_notifications",
        "previous_level IS NULL OR (previous_level >= 0 AND previous_level <= 10)",
    )

    op.create_check_constraint(
        "ck_warning_thresholds_min_score",
        "warning_thresholds",
        "min_score >= 0 AND min_score <= 100",
    )
    op.create_check_constraint(
        "ck_warning_thresholds_max_score",
        "warning_thresholds",
        "max_score >= 0 AND max_score <= 100",
    )
    op.create_check_constraint(
        "ck_warning_thresholds_score_order",
        "warning_thresholds",
        "min_score <= max_score",
    )

    op.create_check_constraint(
        "ck_model_registry_accuracy",
        "model_registry",
        "accuracy IS NULL OR (accuracy >= 0 AND accuracy <= 1)",
    )
    op.create_check_constraint(
        "ck_model_registry_f1_score",
        "model_registry",
        "f1_score IS NULL OR (f1_score >= 0 AND f1_score <= 1)",
    )
    op.create_check_constraint(
        "ck_model_registry_latency_ms",
        "model_registry",
        "latency_ms IS NULL OR latency_ms >= 0",
    )

    op.create_check_constraint(
        "ck_education_contents_duration_minutes",
        "education_contents",
        "duration_minutes IS NULL OR duration_minutes >= 0",
    )
    op.create_check_constraint(
        "ck_education_contents_sort_order",
        "education_contents",
        "sort_order >= 0",
    )
    op.create_check_constraint(
        "ck_education_contents_view_count",
        "education_contents",
        "view_count >= 0",
    )

    op.create_check_constraint(
        "ck_intervention_plans_risk_level",
        "intervention_plans",
        "risk_level >= 0 AND risk_level <= 10",
    )
    op.create_check_constraint(
        "ck_intervention_plans_progress",
        "intervention_plans",
        "progress >= 0 AND progress <= 100",
    )
    op.create_check_constraint(
        "ck_intervention_tasks_duration_minutes",
        "intervention_tasks",
        "duration_minutes IS NULL OR duration_minutes >= 1",
    )
    op.create_check_constraint(
        "ck_intervention_tasks_sort_order",
        "intervention_tasks",
        "sort_order >= 0",
    )
    op.create_check_constraint(
        "ck_task_executions_feedback_score",
        "task_executions",
        "feedback_score IS NULL OR (feedback_score >= 1 AND feedback_score <= 5)",
    )
    op.create_check_constraint(
        "ck_intervention_templates_estimated_weeks",
        "intervention_templates",
        "estimated_weeks IS NULL OR (estimated_weeks >= 1 AND estimated_weeks <= 52)",
    )

    op.create_check_constraint(
        "ck_operation_logs_operator_role_length",
        "operation_logs",
        "operator_role IS NULL OR LENGTH(operator_role) <= 20",
    )
    op.create_check_constraint(
        "ck_operation_logs_action_type_length",
        "operation_logs",
        "action_type IS NOT NULL AND LENGTH(action_type) <= 50",
    )
    op.create_check_constraint(
        "ck_operation_logs_target_type_length",
        "operation_logs",
        "target_type IS NULL OR LENGTH(target_type) <= 50",
    )
    op.create_check_constraint(
        "ck_operation_logs_ip_address_length",
        "operation_logs",
        "ip_address IS NULL OR LENGTH(ip_address) <= 50",
    )

    op.alter_column(
        "data_drafts",
        "draft_type",
        existing_type=sa.String(length=20),
        type_=sa.String(length=50),
        existing_nullable=False,
    )
    op.alter_column(
        "structured_assessments",
        "assessment_type",
        existing_type=sa.String(length=20),
        type_=sa.String(length=50),
        existing_nullable=False,
    )
    op.alter_column(
        "physiological_records",
        "source",
        existing_type=sa.String(length=20),
        type_=sa.String(length=50),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "physiological_records",
        "source",
        existing_type=sa.String(length=50),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
    op.alter_column(
        "structured_assessments",
        "assessment_type",
        existing_type=sa.String(length=50),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
    op.alter_column(
        "data_drafts",
        "draft_type",
        existing_type=sa.String(length=50),
        type_=sa.String(length=20),
        existing_nullable=False,
    )

    for name, table in [
        ("ck_operation_logs_ip_address_length", "operation_logs"),
        ("ck_operation_logs_target_type_length", "operation_logs"),
        ("ck_operation_logs_action_type_length", "operation_logs"),
        ("ck_operation_logs_operator_role_length", "operation_logs"),
        ("ck_intervention_templates_estimated_weeks", "intervention_templates"),
        ("ck_task_executions_feedback_score", "task_executions"),
        ("ck_intervention_tasks_sort_order", "intervention_tasks"),
        ("ck_intervention_tasks_duration_minutes", "intervention_tasks"),
        ("ck_intervention_plans_progress", "intervention_plans"),
        ("ck_intervention_plans_risk_level", "intervention_plans"),
        ("ck_education_contents_view_count", "education_contents"),
        ("ck_education_contents_sort_order", "education_contents"),
        ("ck_education_contents_duration_minutes", "education_contents"),
        ("ck_model_registry_latency_ms", "model_registry"),
        ("ck_model_registry_f1_score", "model_registry"),
        ("ck_model_registry_accuracy", "model_registry"),
        ("ck_warning_thresholds_score_order", "warning_thresholds"),
        ("ck_warning_thresholds_max_score", "warning_thresholds"),
        ("ck_warning_thresholds_min_score", "warning_thresholds"),
        ("ck_warning_notifications_previous_level", "warning_notifications"),
        ("ck_warning_notifications_current_level", "warning_notifications"),
        ("ck_user_counselor_bindings_bind_code_length", "user_counselor_bindings"),
        ("ck_user_profiles_age", "user_profiles"),
        ("ck_users_avatar_url_length", "users"),
        ("ck_users_status_length", "users"),
        ("ck_users_role_length", "users"),
        ("ck_users_password_hash_length", "users"),
        ("ck_users_phone_length", "users"),
        ("ck_users_email_length", "users"),
        ("ck_users_username_length", "users"),
    ]:
        op.drop_constraint(name, table, type_="check")
