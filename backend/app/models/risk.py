from datetime import datetime, time

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, Time, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    __table_args__ = (
        CheckConstraint("risk_score >= 0 AND risk_score <= 100", name="ck_risk_assessments_risk_score"),
        CheckConstraint("risk_level >= 0 AND risk_level <= 10", name="ck_risk_assessments_risk_level"),
        CheckConstraint("structured_score IS NULL OR (structured_score >= 0 AND structured_score <= 100)", name="ck_risk_assessments_structured_score"),
        CheckConstraint("text_score IS NULL OR (text_score >= 0 AND text_score <= 100)", name="ck_risk_assessments_text_score"),
        CheckConstraint("physiological_score IS NULL OR (physiological_score >= 0 AND physiological_score <= 100)", name="ck_risk_assessments_physiological_score"),
        # P1-D-5 修复：复合索引 - 用户风险评估历史按时间倒序查询
        Index("ix_risk_assessments_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    structured_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    text_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    physiological_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    models_used: Mapped[list] = mapped_column(JSON, default=lambda: list())
    risk_factors: Mapped[list] = mapped_column(JSON, default=lambda: list())
    assessment_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class WarningNotification(Base):
    __tablename__ = "warning_notifications"

    __table_args__ = (
        CheckConstraint("current_level >= 0 AND current_level <= 10", name="ck_warning_notifications_current_level"),
        CheckConstraint("previous_level IS NULL OR (previous_level >= 0 AND previous_level <= 10)", name="ck_warning_notifications_previous_level"),
        # P1-D-5 修复：复合索引 - 用户未读告警列表、咨询师未处理告警列表
        Index("ix_warning_notifications_user_is_read", "user_id", "is_read"),
        Index("ix_warning_notifications_counselor_is_handled", "counselor_id", "is_handled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # P1-D-2 修复：外键添加 ondelete="SET NULL"，评估删除时保留告警通知
    risk_assessment_id: Mapped[int | None] = mapped_column(ForeignKey("risk_assessments.id", ondelete="SET NULL"), nullable=True, index=True)
    # P1-D-2 修复：外键添加 ondelete="SET NULL"，咨询师账号删除时保留告警通知
    counselor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    previous_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_level: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger_reason: Mapped[str] = mapped_column(Text, nullable=False)
    # P1-D-4 修复：is_read/is_handled 高频过滤（未读/未处理告警列表）
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_handled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    handle_action: Mapped[str | None] = mapped_column(String(30), nullable=True)
    handle_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class WarningSetting(Base):
    __tablename__ = "warning_settings"

    __table_args__ = (
        CheckConstraint("threshold_level >= 0 AND threshold_level <= 10", name="ck_warning_settings_threshold_level"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    notify_channels: Mapped[dict] = mapped_column(JSON, default=lambda: {"in_app": True})
    threshold_level: Mapped[int] = mapped_column(Integer, default=2)
    quiet_hours_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    quiet_hours_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
