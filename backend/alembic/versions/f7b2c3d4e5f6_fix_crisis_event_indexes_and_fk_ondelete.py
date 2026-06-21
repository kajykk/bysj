"""fix_crisis_event_indexes_and_fk_ondelete

Revision ID: f7b2c3d4e5f6
Revises: a7b8c9d0e1f2
Create Date: 2026-06-20 12:00:00.000000

P1-D-1: 修复 CrisisEvent 模型与迁移不一致
- crisis_events.crisis_score: Integer -> Float (与迁移 a1b2c3d4e5f6 保持一致)
- crisis_events 复合索引已在迁移 a1b2c3d4e5f6 中创建, 此迁移仅同步模型声明

P1-D-2: 为 14 个外键添加 ondelete="SET NULL" 策略
- admin.py: operation_logs.operator_id, system_configs.updated_by,
  meditation_logs.content_id, model_feedbacks.counselor_id,
  model_feedbacks.assessment_id, alert_silences.created_by
- counselor.py: consultation_appointments.counselor_id,
  consultation_records.appointment_id, consultation_records.warning_id,
  consultation_records.counselor_id
- intervention.py: intervention_plans.counselor_id,
  intervention_templates.created_by
- risk.py: warning_notifications.risk_assessment_id,
  warning_notifications.counselor_id
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f7b2c3d4e5f6"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # P1-D-1: crisis_events.crisis_score Integer -> Float
    # (create_all() 创建的数据库为 Integer, 迁移创建的为 Float, 统一为 Float)
    with op.batch_alter_table("crisis_events", schema=None) as batch_op:
        batch_op.alter_column(
            "crisis_score",
            existing_type=sa.Integer(),
            type_=sa.Float(),
            existing_nullable=True,
        )

    # P1-D-2: 为外键添加 ondelete="SET NULL"
    # 使用 batch_alter_table 兼容 SQLite (需重建表) 和 PostgreSQL (直接 ALTER)

    # operation_logs.operator_id -> users.id
    with op.batch_alter_table("operation_logs", schema=None) as batch_op:
        batch_op.drop_constraint("operation_logs_operator_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "operation_logs_operator_id_fkey",
            "operation_logs",
            "users",
            ["operator_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # system_configs.updated_by -> users.id
    with op.batch_alter_table("system_configs", schema=None) as batch_op:
        batch_op.drop_constraint("system_configs_updated_by_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "system_configs_updated_by_fkey",
            "system_configs",
            "users",
            ["updated_by"],
            ["id"],
            ondelete="SET NULL",
        )

    # meditation_logs.content_id -> education_contents.id
    with op.batch_alter_table("meditation_logs", schema=None) as batch_op:
        batch_op.drop_constraint("meditation_logs_content_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "meditation_logs_content_id_fkey",
            "meditation_logs",
            "education_contents",
            ["content_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # model_feedbacks.counselor_id -> users.id
    with op.batch_alter_table("model_feedbacks", schema=None) as batch_op:
        batch_op.drop_constraint("model_feedbacks_counselor_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "model_feedbacks_counselor_id_fkey",
            "model_feedbacks",
            "users",
            ["counselor_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # model_feedbacks.assessment_id -> risk_assessments.id
    with op.batch_alter_table("model_feedbacks", schema=None) as batch_op:
        batch_op.drop_constraint("model_feedbacks_assessment_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "model_feedbacks_assessment_id_fkey",
            "model_feedbacks",
            "risk_assessments",
            ["assessment_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # alert_silences.created_by -> users.id
    with op.batch_alter_table("alert_silences", schema=None) as batch_op:
        batch_op.drop_constraint("alert_silences_created_by_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "alert_silences_created_by_fkey",
            "alert_silences",
            "users",
            ["created_by"],
            ["id"],
            ondelete="SET NULL",
        )

    # consultation_appointments.counselor_id -> users.id
    with op.batch_alter_table("consultation_appointments", schema=None) as batch_op:
        batch_op.drop_constraint(
            "consultation_appointments_counselor_id_fkey", type_="foreignkey"
        )
        batch_op.create_foreign_key(
            "consultation_appointments_counselor_id_fkey",
            "consultation_appointments",
            "users",
            ["counselor_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # consultation_records.appointment_id -> consultation_appointments.id
    with op.batch_alter_table("consultation_records", schema=None) as batch_op:
        batch_op.drop_constraint(
            "consultation_records_appointment_id_fkey", type_="foreignkey"
        )
        batch_op.create_foreign_key(
            "consultation_records_appointment_id_fkey",
            "consultation_records",
            "consultation_appointments",
            ["appointment_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # consultation_records.warning_id -> warning_notifications.id
    with op.batch_alter_table("consultation_records", schema=None) as batch_op:
        batch_op.drop_constraint(
            "consultation_records_warning_id_fkey", type_="foreignkey"
        )
        batch_op.create_foreign_key(
            "consultation_records_warning_id_fkey",
            "consultation_records",
            "warning_notifications",
            ["warning_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # consultation_records.counselor_id -> users.id
    with op.batch_alter_table("consultation_records", schema=None) as batch_op:
        batch_op.drop_constraint(
            "consultation_records_counselor_id_fkey", type_="foreignkey"
        )
        batch_op.create_foreign_key(
            "consultation_records_counselor_id_fkey",
            "consultation_records",
            "users",
            ["counselor_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # intervention_plans.counselor_id -> users.id
    with op.batch_alter_table("intervention_plans", schema=None) as batch_op:
        batch_op.drop_constraint(
            "intervention_plans_counselor_id_fkey", type_="foreignkey"
        )
        batch_op.create_foreign_key(
            "intervention_plans_counselor_id_fkey",
            "intervention_plans",
            "users",
            ["counselor_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # intervention_templates.created_by -> users.id
    with op.batch_alter_table("intervention_templates", schema=None) as batch_op:
        batch_op.drop_constraint(
            "intervention_templates_created_by_fkey", type_="foreignkey"
        )
        batch_op.create_foreign_key(
            "intervention_templates_created_by_fkey",
            "intervention_templates",
            "users",
            ["created_by"],
            ["id"],
            ondelete="SET NULL",
        )

    # warning_notifications.risk_assessment_id -> risk_assessments.id
    with op.batch_alter_table("warning_notifications", schema=None) as batch_op:
        batch_op.drop_constraint(
            "warning_notifications_risk_assessment_id_fkey", type_="foreignkey"
        )
        batch_op.create_foreign_key(
            "warning_notifications_risk_assessment_id_fkey",
            "warning_notifications",
            "risk_assessments",
            ["risk_assessment_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # warning_notifications.counselor_id -> users.id
    with op.batch_alter_table("warning_notifications", schema=None) as batch_op:
        batch_op.drop_constraint(
            "warning_notifications_counselor_id_fkey", type_="foreignkey"
        )
        batch_op.create_foreign_key(
            "warning_notifications_counselor_id_fkey",
            "warning_notifications",
            "users",
            ["counselor_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    # 回退 crisis_score 类型
    with op.batch_alter_table("crisis_events", schema=None) as batch_op:
        batch_op.alter_column(
            "crisis_score",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=True,
        )

    # 回退外键 ondelete (移除 ondelete 策略)
    fk_pairs = [
        ("warning_notifications", "warning_notifications_counselor_id_fkey",
         "warning_notifications", "users", ["counselor_id"], ["id"]),
        ("warning_notifications", "warning_notifications_risk_assessment_id_fkey",
         "warning_notifications", "risk_assessments", ["risk_assessment_id"], ["id"]),
        ("intervention_templates", "intervention_templates_created_by_fkey",
         "intervention_templates", "users", ["created_by"], ["id"]),
        ("intervention_plans", "intervention_plans_counselor_id_fkey",
         "intervention_plans", "users", ["counselor_id"], ["id"]),
        ("consultation_records", "consultation_records_counselor_id_fkey",
         "consultation_records", "users", ["counselor_id"], ["id"]),
        ("consultation_records", "consultation_records_warning_id_fkey",
         "consultation_records", "warning_notifications", ["warning_id"], ["id"]),
        ("consultation_records", "consultation_records_appointment_id_fkey",
         "consultation_records", "consultation_appointments", ["appointment_id"], ["id"]),
        ("consultation_appointments", "consultation_appointments_counselor_id_fkey",
         "consultation_appointments", "users", ["counselor_id"], ["id"]),
        ("alert_silences", "alert_silences_created_by_fkey",
         "alert_silences", "users", ["created_by"], ["id"]),
        ("model_feedbacks", "model_feedbacks_assessment_id_fkey",
         "model_feedbacks", "risk_assessments", ["assessment_id"], ["id"]),
        ("model_feedbacks", "model_feedbacks_counselor_id_fkey",
         "model_feedbacks", "users", ["counselor_id"], ["id"]),
        ("meditation_logs", "meditation_logs_content_id_fkey",
         "meditation_logs", "education_contents", ["content_id"], ["id"]),
        ("system_configs", "system_configs_updated_by_fkey",
         "system_configs", "users", ["updated_by"], ["id"]),
        ("operation_logs", "operation_logs_operator_id_fkey",
         "operation_logs", "users", ["operator_id"], ["id"]),
    ]

    for table, constraint_name, source, referent, local, remote in fk_pairs:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(constraint_name, type_="foreignkey")
            batch_op.create_foreign_key(
                constraint_name,
                source,
                referent,
                local,
                remote,
            )
