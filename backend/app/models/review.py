from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class ReviewTask(Base):
    __tablename__ = "review_tasks"

    __table_args__ = (
        # P1-D-8: 评分范围约束 - 与 RiskAssessment 保持一致
        CheckConstraint("risk_level >= 0 AND risk_level <= 10", name="ck_review_tasks_risk_level"),
        CheckConstraint("risk_score >= 0 AND risk_score <= 100", name="ck_review_tasks_risk_score"),
        # P1-D-8: 枚举约束 - status 只允许合法值
        CheckConstraint("status IN ('pending', 'in_review', 'resolved', 'escalated', 'archived')", name="ck_review_tasks_status_values"),
        # P1-D-8: 枚举约束 - priority 只允许合法值
        CheckConstraint("priority IN ('normal_review', 'high_risk_review', 'crisis_review')", name="ck_review_tasks_priority_values"),
        # P1-D-5 修复：复合索引 - 咨询师待处理复核任务查询
        Index("ix_review_tasks_assigned_status", "assigned_to", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    risk_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("risk_assessments.id", ondelete="SET NULL"),
        nullable=True,
    )
    risk_level: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    review_triggers: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default="[]",
    )
    crisis_override: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
    )
    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="normal_review",
        index=True,
    )
    assigned_to: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    resolved_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="review_tasks",
    )
    assigned_counselor: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[assigned_to],
    )
    resolver: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[resolved_by],
    )


class CrisisEvent(Base):
    __tablename__ = "crisis_events"
    __table_args__ = (
        # P1-D-1 修复：声明迁移中已创建的复合索引，避免 autogenerate 误删
        Index("ix_crisis_events_status_created_at", "status", "created_at"),
        Index("ix_crisis_events_trigger_source_created_at", "trigger_source", "created_at"),
        # P1-D-5 修复：复合索引 - 用户危机事件按状态查询
        Index("ix_crisis_events_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    report_id: Mapped[int | None] = mapped_column(
        ForeignKey("risk_assessments.id", ondelete="SET NULL"),
        nullable=True,
    )
    trigger_source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    crisis_keywords: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default="[]",
    )
    # P1-D-1 修复：crisis_score 类型与迁移保持一致（Float），原 Integer 与迁移不一致
    crisis_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("review_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="detected",
        index=True,
    )
    handled_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    handled_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    # P1-D-4 修复：created_at 高频范围查询（危机事件导出按时间范围过滤）
    # 注意：复合索引 (status, created_at) 和 (trigger_source, created_at) 无法覆盖单独 created_at 查询
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        index=True,
    )
    handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[user_id],
    )
    review_task: Mapped["ReviewTask | None"] = relationship(
        "ReviewTask",
        foreign_keys=[review_task_id],
    )
    handler: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[handled_by],
    )
