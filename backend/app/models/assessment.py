from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DataDraft(Base):
    __tablename__ = "data_drafts"

    __table_args__ = (
        UniqueConstraint("user_id", "draft_type", name="uq_user_draft_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # P1-D-4 修复：draft_type 高频过滤（草稿按类型查询）
    draft_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    data_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class StructuredAssessment(Base):
    __tablename__ = "structured_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    assessment_type: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    data_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class TextEntry(Base):
    __tablename__ = "text_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    entry_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    emotion_tags: Mapped[list] = mapped_column(JSON, default=lambda: list())
    mood_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_label: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class PhysiologicalRecord(Base):
    __tablename__ = "physiological_records"

    __table_args__ = (
        # P1-D-8: 生理指标范围约束 - 防止异常值落库 (医疗数据完整性)
        CheckConstraint("sleep_hours IS NULL OR (sleep_hours >= 0 AND sleep_hours <= 24)", name="ck_physiological_records_sleep_hours"),
        CheckConstraint("sleep_quality IS NULL OR (sleep_quality >= 0 AND sleep_quality <= 10)", name="ck_physiological_records_sleep_quality"),
        CheckConstraint("exercise_minutes IS NULL OR exercise_minutes >= 0", name="ck_physiological_records_exercise_minutes"),
        CheckConstraint("heart_rate IS NULL OR (heart_rate >= 30 AND heart_rate <= 250)", name="ck_physiological_records_heart_rate"),
        CheckConstraint("systolic_bp IS NULL OR (systolic_bp >= 50 AND systolic_bp <= 300)", name="ck_physiological_records_systolic_bp"),
        CheckConstraint("diastolic_bp IS NULL OR (diastolic_bp >= 30 AND diastolic_bp <= 200)", name="ck_physiological_records_diastolic_bp"),
        CheckConstraint("steps IS NULL OR steps >= 0", name="ck_physiological_records_steps"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(50), default="manual", nullable=False)
    sleep_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    sleep_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exercise_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heart_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    systolic_bp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diastolic_bp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
