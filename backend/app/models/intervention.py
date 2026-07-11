from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class InterventionPlan(Base):
    __tablename__ = "intervention_plans"

    __table_args__ = (
        CheckConstraint("risk_level >= 0 AND risk_level <= 10", name="ck_intervention_plans_risk_level"),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_intervention_plans_progress"),
        # P1-D-5 修复：复合索引 - 用户活跃干预计划查询
        Index("ix_intervention_plans_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # P1-D-2 修复：外键添加 ondelete="SET NULL"，咨询师账号删除时保留干预计划
    counselor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    plan_name: Mapped[str] = mapped_column(String(100), nullable=False)
    risk_level: Mapped[int] = mapped_column(Integer, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    # P1-D-4 修复：status 高频过滤，created_at 高频 order_by（干预计划列表排序）
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class InterventionTask(Base):
    __tablename__ = "intervention_tasks"

    __table_args__ = (
        CheckConstraint("duration_minutes IS NULL OR duration_minutes >= 1", name="ck_intervention_tasks_duration_minutes"),
        CheckConstraint("sort_order >= 0", name="ck_intervention_tasks_sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("intervention_plans.id", ondelete="CASCADE"), index=True)
    task_name: Mapped[str] = mapped_column(String(200), nullable=False)
    task_type: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    schedule: Mapped[str | None] = mapped_column(String(50), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TaskExecution(Base):
    __tablename__ = "task_executions"

    __table_args__ = (
        CheckConstraint("feedback_score IS NULL OR (feedback_score >= 1 AND feedback_score <= 5)", name="ck_task_executions_feedback_score"),
        UniqueConstraint("task_id", "user_id", "scheduled_date", name="uq_task_execution_task_user_date"),
        Index("ix_task_executions_composite", "task_id", "user_id", "scheduled_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("intervention_tasks.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    feedback_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class InterventionTemplate(Base):
    __tablename__ = "intervention_templates"

    __table_args__ = (
        CheckConstraint("estimated_weeks IS NULL OR (estimated_weeks >= 1 AND estimated_weeks <= 52)", name="ck_intervention_templates_estimated_weeks"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_name: Mapped[str] = mapped_column(String(100), nullable=False)
    applicable_levels: Mapped[list] = mapped_column(JSON, default=lambda: [0, 1, 2, 3, 4])
    applicable_groups: Mapped[str | None] = mapped_column(String(100), nullable=True)
    task_list: Mapped[list] = mapped_column(JSON, nullable=False)
    estimated_weeks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # P1-D-4 修复：status 高频过滤（模板列表按状态筛选）
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    # P1-D-2 修复：外键添加 ondelete="SET NULL"，创建者删除时保留模板
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
