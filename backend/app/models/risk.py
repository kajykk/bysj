from datetime import datetime, time

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    func,
    text,
)
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
        # PERF-P2-002: 复合索引 - 通过 is_latest 快速查询每个用户的最新风险评估
        Index("ix_risk_assessments_user_is_latest", "user_id", "is_latest"),
        # SEC-FIX-2026-10-05: 部分唯一索引 —— is_latest 的数据库级约束。
        #
        # 缺陷: is_latest 的写入是「先全清再插新」的 check-then-act
        #       (risk_service_assessment.py:206-226 与
        #        api/v1/model_predict/_common.py:118-141), 且 _common 那条
        #        fire-and-forget 任务用的是**独立 session**。此前只有普通复合索引,
        #        并发下两个 session 各自 UPDATE+INSERT 会在 READ COMMITTED 下交错,
        #        同一 user_id 出现 2 条 is_latest=True。
        #
        # 后果: is_latest 是「最新评估」的唯一真相来源（j1f6a7b8c9d0 迁移注释
        #       明言用于替代 GROUP BY + max(created_at)）。出现 2 条后, 依赖
        #       WHERE is_latest=True 的查询（如 list_my_users）会返回**重复用户行**,
        #       咨询师工作台把同一学生列两次, 且 max(created_at) 语义被破坏。
        #
        # 为什么必须靠数据库: 应用层的检查无法覆盖两个独立 session 的并发,
        #       只有唯一索引能真正兜底。注意是 **部分** 索引（WHERE is_latest）,
        #       否则历史评估（is_latest=False）会因 user_id 重复而全部冲突。
        Index(
            "uq_risk_assessments_latest",
            "user_id",
            unique=True,
            sqlite_where=text("is_latest = 1"),
            postgresql_where=text("is_latest"),
        ),
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
    # PERF-P2-002: is_latest 标志位, 标记每个用户的最新风险评估, 避免 GROUP BY + max(created_at) 子查询
    is_latest: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


class WarningNotification(Base):
    __tablename__ = "warning_notifications"

    __table_args__ = (
        CheckConstraint("current_level >= 0 AND current_level <= 10", name="ck_warning_notifications_current_level"),
        CheckConstraint("previous_level IS NULL OR (previous_level >= 0 AND previous_level <= 10)", name="ck_warning_notifications_previous_level"),
        # P1-D-5 修复：复合索引 - 用户未读告警列表、咨询师未处理告警列表
        Index("ix_warning_notifications_user_is_read", "user_id", "is_read"),
        Index("ix_warning_notifications_counselor_is_handled", "counselor_id", "is_handled"),
        # SEC-FIX-2026-10-05: 部分唯一索引 —— 同一评估只允许一条预警通知。
        #
        # 缺陷: risk_service_warning.py:77-102 的告警去重是 check-then-act
        #       （先 SELECT 查重再 INSERT，靠捕获 SAIntegrityError 兜冲突），
        #       但该列此前只有 index=True 没有唯一性 → 那个 IntegrityError
        #       永远不会被触发，去重在并发下失效。
        #
        # 为什么用部分索引而非 unique=True: 该列 nullable（评估删除时
        #       SET NULL），历史上可能存在多条 NULL 关联的告警；部分索引
        #       只约束「有评估 id」的行，语义更精确且不会破坏既有数据。
        Index(
            "uq_warning_notifications_assessment",
            "risk_assessment_id",
            unique=True,
            sqlite_where=text("risk_assessment_id IS NOT NULL"),
            postgresql_where=text("risk_assessment_id IS NOT NULL"),
        ),
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
