from datetime import datetime

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
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.contracts import DEFAULT_TENANT_ID
from app.models.base import Base


class ModelRegistry(Base):
    __tablename__ = "model_registry"

    __table_args__ = (
        CheckConstraint("accuracy IS NULL OR (accuracy >= 0 AND accuracy <= 1)", name="ck_model_registry_accuracy"),
        CheckConstraint("f1_score IS NULL OR (f1_score >= 0 AND f1_score <= 1)", name="ck_model_registry_f1_score"),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="ck_model_registry_latency_ms"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_type: Mapped[str] = mapped_column(String(30), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    version: Mapped[str] = mapped_column(String(20), default="1.0.0")
    status: Mapped[str] = mapped_column(String(20), default="active")
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    f1_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    loaded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class OperationLog(Base):
    __tablename__ = "operation_logs"

    __table_args__ = (
        CheckConstraint("operator_role IS NULL OR LENGTH(operator_role) <= 20", name="ck_operation_logs_operator_role_length"),
        CheckConstraint("action_type IS NOT NULL AND LENGTH(action_type) <= 50", name="ck_operation_logs_action_type_length"),
        CheckConstraint("target_type IS NULL OR LENGTH(target_type) <= 50", name="ck_operation_logs_target_type_length"),
        CheckConstraint("ip_address IS NULL OR LENGTH(ip_address) <= 50", name="ck_operation_logs_ip_address_length"),
        # v1.36: 复合索引 - 支持按 action_type + 时间范围高效查询
        # 用于: 告警通道/AM 同步/dedup_lock 统计等高频查询
        Index("idx_oplog_action_created", "action_type", "created_at"),
        # v1.36: 复合索引 - 支持按 target_type + target_id + action_type 查询
        # 用于: 特定对象的审计追踪 (如: target_type=alert_channel, target_id=channel_name)
        Index("idx_oplog_target_action", "target_type", "target_id", "action_type"),
        # P1-D-5 修复：复合索引 - 操作员审计日志按时间查询
        Index("ix_operation_logs_operator_created", "operator_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # P1-D-2 修复：外键添加 ondelete="SET NULL"，审计日志在用户删除时保留
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    # P1-D-4 修复：operator_role 高频过滤（管理员审计列表按角色筛选）
    operator_role: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Phase 5: 多租户字段 — 审计日志按租户隔离
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False, default=DEFAULT_TENANT_ID, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class SystemConfig(Base):
    __tablename__ = "system_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    config_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    config_value: Mapped[dict] = mapped_column(JSON, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # P1-D-2 修复：外键添加 ondelete="SET NULL"
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class UserFavorite(Base):
    __tablename__ = "user_favorites"

    __table_args__ = (
        UniqueConstraint("user_id", "content_id", name="uq_user_content_favorite"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("education_contents.id", ondelete="CASCADE"), nullable=False, index=True)
    # P1-D-4 修复：created_at 高频 order_by（收藏列表排序）
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class EducationContent(Base):
    __tablename__ = "education_contents"

    __table_args__ = (
        CheckConstraint("duration_minutes IS NULL OR duration_minutes >= 0", name="ck_education_contents_duration_minutes"),
        CheckConstraint("sort_order >= 0", name="ck_education_contents_sort_order"),
        CheckConstraint("view_count >= 0", name="ck_education_contents_view_count"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # P1-D-4 修复：category/content_type/status 高频过滤，created_at/sort_order/view_count 高频 order_by
    category: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    audio_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    difficulty: Mapped[str | None] = mapped_column(String(10), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class MeditationLog(Base):
    __tablename__ = "meditation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # P1-D-2 修复：外键添加 ondelete="SET NULL"，内容删除时保留冥想记录
    content_id: Mapped[int | None] = mapped_column(ForeignKey("education_contents.id", ondelete="SET NULL"), nullable=True)
    played_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ContentViewHistory(Base):
    __tablename__ = "content_view_histories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("education_contents.id", ondelete="CASCADE"), index=True)
    viewed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class ModelFeedback(Base):
    __tablename__ = "model_feedbacks"

    __table_args__ = (
        # P1-D-5 修复：复合索引 - 用户模型反馈按时间查询
        Index("ix_model_feedbacks_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # P1-D-2 修复：外键添加 ondelete="SET NULL"，咨询师删除时保留反馈
    counselor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # P1-D-2 修复：外键添加 ondelete="SET NULL"，评估删除时保留反馈
    assessment_id: Mapped[int | None] = mapped_column(ForeignKey("risk_assessments.id", ondelete="SET NULL"), nullable=True)
    agreed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # P1-D-4 修复：created_at 高频 order_by（反馈列表排序）
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class WarningThreshold(Base):
    __tablename__ = "warning_thresholds"

    __table_args__ = (
        CheckConstraint("min_score >= 0 AND min_score <= 100", name="ck_warning_thresholds_min_score"),
        CheckConstraint("max_score >= 0 AND max_score <= 100", name="ck_warning_thresholds_max_score"),
        CheckConstraint("min_score <= max_score", name="ck_warning_thresholds_score_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    level: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    level_name: Mapped[str] = mapped_column(String(20), nullable=False)
    min_score: Mapped[float] = mapped_column(Float, nullable=False)
    max_score: Mapped[float] = mapped_column(Float, nullable=False)
    color: Mapped[str] = mapped_column(String(20), nullable=False)
    action_required: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AlertSilence(Base):
    """v1.34: 告警静默规则.

    用于在维护期或已知问题期间静默特定告警.
    匹配器: matcher (JSON) 支持按 alertname/severity 等 label 匹配.
    """

    __tablename__ = "alert_silences"

    __table_args__ = (
        # P1-D-8: 时间顺序约束 - ends_at 必须晚于 starts_at
        CheckConstraint("ends_at > starts_at", name="ck_alert_silences_time_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    matcher: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    # P1-D-2 修复：外键添加 ondelete="SET NULL"，创建者删除时保留静默规则
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # M-5 修复：持久化 AlertManager 返回的 silenceID，删除时用于同步取消 AM 侧静默
    am_silence_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class AlertArchive(Base):
    """v1.35: 告警归档表.

    用于存储 90 天前的告警 (alert_fired / alert_resolved),
    释放 OperationLog 空间, 保留审计能力.
    只读表, 不参与告警通知.
    """

    __tablename__ = "alert_archives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    original_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    rule: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    # P1-D-4 修复：status 高频过滤（归档告警列表按状态筛选）
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    labels: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    annotations: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    fingerprint: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    original_created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    archived_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
