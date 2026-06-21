"""add_p1d_indexes_and_constraints

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-20 12:00:00.000000

P1-D-4/P1-D-5: 添加高频查询字段索引和复合索引
- 单列索引: 24 个高频查询字段（status/created_at/is_read/is_handled 等）
- 复合索引: 11 个多字段组合查询索引
- 目标: 提升 API 列表查询、过滤、排序性能

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============================================================
    # P1-D-4: 单列索引 - 高频查询字段
    # ============================================================

    # user_counselor_bindings: status 高频过滤, bound_at 高频 order_by
    op.create_index("ix_user_counselor_bindings_status", "user_counselor_bindings", ["status"], unique=False)
    op.create_index("ix_user_counselor_bindings_bound_at", "user_counselor_bindings", ["bound_at"], unique=False)

    # education_contents: category/content_type/status 高频过滤, created_at/sort_order/view_count 高频 order_by
    op.create_index("ix_education_contents_content_type", "education_contents", ["content_type"], unique=False)
    op.create_index("ix_education_contents_category", "education_contents", ["category"], unique=False)
    op.create_index("ix_education_contents_sort_order", "education_contents", ["sort_order"], unique=False)
    op.create_index("ix_education_contents_view_count", "education_contents", ["view_count"], unique=False)
    op.create_index("ix_education_contents_status", "education_contents", ["status"], unique=False)
    op.create_index("ix_education_contents_created_at", "education_contents", ["created_at"], unique=False)

    # operation_logs: operator_id/operator_role 高频过滤
    op.create_index("ix_operation_logs_operator_id", "operation_logs", ["operator_id"], unique=False)
    op.create_index("ix_operation_logs_operator_role", "operation_logs", ["operator_role"], unique=False)

    # model_feedbacks: created_at 高频 order_by
    op.create_index("ix_model_feedbacks_created_at", "model_feedbacks", ["created_at"], unique=False)

    # user_favorites: created_at 高频 order_by
    op.create_index("ix_user_favorites_created_at", "user_favorites", ["created_at"], unique=False)

    # alert_archives: status 高频过滤
    op.create_index("ix_alert_archives_status", "alert_archives", ["status"], unique=False)

    # intervention_plans: status 高频过滤, created_at 高频 order_by
    op.create_index("ix_intervention_plans_status", "intervention_plans", ["status"], unique=False)
    op.create_index("ix_intervention_plans_created_at", "intervention_plans", ["created_at"], unique=False)

    # intervention_templates: status 高频过滤
    op.create_index("ix_intervention_templates_status", "intervention_templates", ["status"], unique=False)

    # warning_notifications: is_read/is_handled 高频过滤, risk_assessment_id 外键查询
    op.create_index("ix_warning_notifications_is_read", "warning_notifications", ["is_read"], unique=False)
    op.create_index("ix_warning_notifications_is_handled", "warning_notifications", ["is_handled"], unique=False)
    op.create_index("ix_warning_notifications_risk_assessment_id", "warning_notifications", ["risk_assessment_id"], unique=False)

    # crisis_events: status 高频过滤, created_at 高频范围查询（复合索引无法覆盖单独 created_at）
    op.create_index("ix_crisis_events_status", "crisis_events", ["status"], unique=False)
    op.create_index("ix_crisis_events_created_at", "crisis_events", ["created_at"], unique=False)

    # data_drafts: draft_type 高频过滤
    op.create_index("ix_data_drafts_draft_type", "data_drafts", ["draft_type"], unique=False)

    # refresh_token_sessions: revoked_at 高频过滤
    op.create_index("ix_refresh_token_sessions_revoked_at", "refresh_token_sessions", ["revoked_at"], unique=False)

    # drift_alerts: resolved_at 高频过滤
    op.create_index("ix_drift_alerts_resolved_at", "drift_alerts", ["resolved_at"], unique=False)

    # ============================================================
    # P1-D-5: 复合索引 - 多字段组合查询
    # ============================================================

    # risk_assessments: 用户风险评估历史按时间查询
    op.create_index("ix_risk_assessments_user_created", "risk_assessments", ["user_id", "created_at"], unique=False)

    # warning_notifications: 用户未读告警列表、咨询师未处理告警列表
    op.create_index("ix_warning_notifications_user_is_read", "warning_notifications", ["user_id", "is_read"], unique=False)
    op.create_index("ix_warning_notifications_counselor_is_handled", "warning_notifications", ["counselor_id", "is_handled"], unique=False)

    # intervention_plans: 用户活跃干预计划查询
    op.create_index("ix_intervention_plans_user_status", "intervention_plans", ["user_id", "status"], unique=False)

    # consultation_appointments: 咨询师/用户预约按日期查询
    op.create_index("ix_consultation_appointments_counselor_date", "consultation_appointments", ["counselor_id", "appointment_date"], unique=False)
    op.create_index("ix_consultation_appointments_user_date", "consultation_appointments", ["user_id", "appointment_date"], unique=False)

    # review_tasks: 咨询师待处理复核任务查询
    op.create_index("ix_review_tasks_assigned_status", "review_tasks", ["assigned_to", "status"], unique=False)

    # crisis_events: 用户危机事件按状态查询
    op.create_index("ix_crisis_events_user_status", "crisis_events", ["user_id", "status"], unique=False)

    # monitoring_logs: 用户监控日志按时间查询
    op.create_index("ix_monitoring_logs_user_created", "monitoring_logs", ["user_id", "created_at"], unique=False)

    # operation_logs: 操作员审计日志按时间查询
    op.create_index("ix_operation_logs_operator_created", "operation_logs", ["operator_id", "created_at"], unique=False)

    # model_feedbacks: 用户模型反馈按时间查询
    op.create_index("ix_model_feedbacks_user_created", "model_feedbacks", ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    # P1-D-5: 复合索引
    op.drop_index("ix_model_feedbacks_user_created", table_name="model_feedbacks")
    op.drop_index("ix_operation_logs_operator_created", table_name="operation_logs")
    op.drop_index("ix_monitoring_logs_user_created", table_name="monitoring_logs")
    op.drop_index("ix_crisis_events_user_status", table_name="crisis_events")
    op.drop_index("ix_review_tasks_assigned_status", table_name="review_tasks")
    op.drop_index("ix_consultation_appointments_user_date", table_name="consultation_appointments")
    op.drop_index("ix_consultation_appointments_counselor_date", table_name="consultation_appointments")
    op.drop_index("ix_intervention_plans_user_status", table_name="intervention_plans")
    op.drop_index("ix_warning_notifications_counselor_is_handled", table_name="warning_notifications")
    op.drop_index("ix_warning_notifications_user_is_read", table_name="warning_notifications")
    op.drop_index("ix_risk_assessments_user_created", table_name="risk_assessments")

    # P1-D-4: 单列索引
    op.drop_index("ix_drift_alerts_resolved_at", table_name="drift_alerts")
    op.drop_index("ix_refresh_token_sessions_revoked_at", table_name="refresh_token_sessions")
    op.drop_index("ix_data_drafts_draft_type", table_name="data_drafts")
    op.drop_index("ix_crisis_events_created_at", table_name="crisis_events")
    op.drop_index("ix_crisis_events_status", table_name="crisis_events")
    op.drop_index("ix_warning_notifications_risk_assessment_id", table_name="warning_notifications")
    op.drop_index("ix_warning_notifications_is_handled", table_name="warning_notifications")
    op.drop_index("ix_warning_notifications_is_read", table_name="warning_notifications")
    op.drop_index("ix_intervention_templates_status", table_name="intervention_templates")
    op.drop_index("ix_intervention_plans_created_at", table_name="intervention_plans")
    op.drop_index("ix_intervention_plans_status", table_name="intervention_plans")
    op.drop_index("ix_alert_archives_status", table_name="alert_archives")
    op.drop_index("ix_user_favorites_created_at", table_name="user_favorites")
    op.drop_index("ix_model_feedbacks_created_at", table_name="model_feedbacks")
    op.drop_index("ix_operation_logs_operator_role", table_name="operation_logs")
    op.drop_index("ix_operation_logs_operator_id", table_name="operation_logs")
    op.drop_index("ix_education_contents_created_at", table_name="education_contents")
    op.drop_index("ix_education_contents_status", table_name="education_contents")
    op.drop_index("ix_education_contents_view_count", table_name="education_contents")
    op.drop_index("ix_education_contents_sort_order", table_name="education_contents")
    op.drop_index("ix_education_contents_category", table_name="education_contents")
    op.drop_index("ix_education_contents_content_type", table_name="education_contents")
    op.drop_index("ix_user_counselor_bindings_bound_at", table_name="user_counselor_bindings")
    op.drop_index("ix_user_counselor_bindings_status", table_name="user_counselor_bindings")
