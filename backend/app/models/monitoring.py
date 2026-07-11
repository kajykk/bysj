from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MonitoringEventType(str, Enum):
    INFERENCE = "inference"
    FALLBACK = "fallback"
    INPUT_ANOMALY = "input_anomaly"
    DRIFT_ALERT = "drift_alert"
    MODEL_LOAD = "model_load"
    CANARY_SWITCH = "canary_switch"


class DriftSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class CanaryStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    ROLLED_BACK = "rolled_back"
    COMPLETED = "completed"


class MonitoringLog(Base):
    __tablename__ = "monitoring_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="事件类型: inference, fallback, input_anomaly, drift_alert, model_load, canary_switch"
    )
    model_version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="模型版本号"
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="关联用户ID"
    )
    request_payload: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="请求 payload 摘要(脱敏)"
    )
    response_summary: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="响应摘要"
    )
    fallback_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="回退原因(如触发回退则记录)"
    )
    latency_ms: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="请求延迟(毫秒)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        comment="记录创建时间"
    )

    __table_args__ = (
        Index("ix_monitoring_logs_event_type_created_at", "event_type", "created_at"),
        Index("ix_monitoring_logs_model_version_created_at", "model_version", "created_at"),
        # P1-D-5 修复：复合索引 - 用户监控日志按时间查询
        Index("ix_monitoring_logs_user_created", "user_id", "created_at"),
    )


class CanaryRecord(Base):
    __tablename__ = "canary_records"

    __table_args__ = (
        Index("ix_canary_records_status_started_at", "status", "started_at"),
        Index("ix_canary_records_version_created_at", "version", "created_at"),
        # P1-D-8: 流量百分比范围约束 - 0-100（rolled_back/completed 允许 0%）
        CheckConstraint("traffic_percent >= 0 AND traffic_percent <= 100", name="ck_canary_records_traffic_percent"),
        # P1-D-8: 枚举约束 - status 只允许合法值
        CheckConstraint("status IN ('pending', 'running', 'paused', 'rolled_back', 'completed')", name="ck_canary_records_status_values"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="灰度版本号"
    )
    traffic_percent: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="流量百分比 (1-100)"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=CanaryStatus.PENDING,
        comment="状态: pending, running, paused, rolled_back, completed"
    )
    auto_rollback_thresholds: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        default=lambda: {
            "max_fallback_rate": 0.05,
            "max_drift_alerts_per_hour": 10,
            "max_avg_latency_ms": 500,
        },
        comment="自动回滚阈值配置"
    )
    triggered_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="触发用户ID"
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="灰度开始时间"
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="灰度结束时间"
    )
    rollback_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="回退原因"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        comment="记录创建时间"
    )


class ValidationResult(Base):
    __tablename__ = "validation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sample_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="样本唯一标识"
    )
    model_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="模型版本号"
    )
    ground_truth: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="真实标签"
    )
    prediction: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="预测标签"
    )
    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="预测置信度"
    )
    is_correct: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        comment="是否正确 (1=正确, 0=错误, NULL=未评估)"
    )
    failure_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="失败原因 (如预测错误则记录)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        comment="记录创建时间"
    )

    __table_args__ = (
        Index("ix_validation_results_model_version_created_at", "model_version", "created_at"),
        Index("ix_validation_results_is_correct_created_at", "is_correct", "created_at"),
    )


class DriftAlert(Base):
    __tablename__ = "drift_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="模型版本号"
    )
    feature_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="发生漂移的特征名"
    )
    drift_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="漂移类型: feature_drift, prediction_drift, performance_drift"
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DriftSeverity.MEDIUM,
        comment="严重程度: LOW, MEDIUM, HIGH, CRITICAL"
    )
    metric_value: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="漂移指标值"
    )
    threshold: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="阈值"
    )
    details: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="详细数据"
    )
    # P1-D-4 修复：resolved_at 高频过滤（活跃告警 vs 已解决告警列表）
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
        comment="告警解决时间"
    )
    # C-03 修复：acknowledged_at 持久化 ACKNOWLEDGED 状态，避免服务重启后丢失
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="告警确认时间（ACKNOWLEDGED 状态持久化）"
    )
    # H-5 修复：closed_at 持久化 CLOSED 状态，避免服务重启后内存 history 丢失导致
    # CLOSED 告警被误判为 RESOLVED
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="告警关闭时间（CLOSED 状态持久化）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        comment="记录创建时间"
    )

    __table_args__ = (
        Index("ix_drift_alerts_severity_created_at", "severity", "created_at"),
        Index("ix_drift_alerts_model_version_created_at", "model_version", "created_at"),
    )
