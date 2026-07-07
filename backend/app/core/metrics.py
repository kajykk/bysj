"""轻量级 Prometheus 指标收集模块 (v1.32)

设计原则:
- 零外部依赖, 不需要 prometheus_client
- 兼容 Prometheus exposition format (text/plain version 0.0.4)
- 线程安全 (使用 threading.Lock)
- 优雅降级: 模块加载失败不影响主应用
- 高性能: 使用 dict 存储, O(1) 增量

支持的指标类型:
- Counter: 累计计数, 例如 http_requests_total
- Histogram: 分布统计, 例如 http_request_duration_seconds
- Gauge: 瞬时值, 例如 websocket_connections_active
- Info: 静态信息, 例如 app_info
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

from app.core.config import RELEASE_VERSION

# M-7 修复：track_model_inference 的 except 块使用 logger 但模块未定义，会抛 NameError
logger = logging.getLogger(__name__)

# 线程安全锁
_lock = threading.Lock()

# 指标注册表
_REGISTRY: dict[str, dict[str, Any]] = {}


class Counter:
    """单调递增计数器"""

    def __init__(
        self, name: str, documentation: str, labelnames: tuple[str, ...] = ()
    ) -> None:
        self.name = name
        self.documentation = documentation
        self.labelnames = labelnames
        self._values: dict[tuple[str, ...], float] = {}
        with _lock:
            _REGISTRY.setdefault(
                name,
                {
                    "type": "counter",
                    "doc": documentation,
                    "labelnames": labelnames,
                    "instance": self,
                },
            )

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        # M-Core-6 修复：Counter 语义上只应单调递增，禁止负值破坏 Prometheus 指标语义
        if amount < 0:
            raise ValueError("Counter can only be incremented by non-negative values")
        if set(labels.keys()) != set(self.labelnames):
            raise ValueError(
                f"Label mismatch: expected {self.labelnames}, got {list(labels.keys())}"
            )
        key = tuple(labels[label_name] for label_name in self.labelnames)
        with _lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def collect(self) -> list[tuple[dict, float]]:
        with _lock:
            return [
                ({k: v for k, v in zip(self.labelnames, key)}, value)
                for key, value in self._values.items()
            ]


class Gauge:
    """可增可减的仪表"""

    def __init__(
        self, name: str, documentation: str, labelnames: tuple[str, ...] = ()
    ) -> None:
        self.name = name
        self.documentation = documentation
        self.labelnames = labelnames
        self._values: dict[tuple[str, ...], float] = {}
        with _lock:
            _REGISTRY.setdefault(
                name,
                {
                    "type": "gauge",
                    "doc": documentation,
                    "labelnames": labelnames,
                    "instance": self,
                },
            )

    def set(self, value: float, **labels: str) -> None:
        if set(labels.keys()) != set(self.labelnames):
            raise ValueError(
                f"Label mismatch: expected {self.labelnames}, got {list(labels.keys())}"
            )
        key = tuple(labels[label_name] for label_name in self.labelnames)
        with _lock:
            self._values[key] = value

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        # M-7 修复：Gauge.inc/dec 缺少 label 校验，与 Counter.inc/Gauge.set 不一致，
        # 传入错误 label 会静默创建错误 key，导致指标丢失或污染。
        if set(labels.keys()) != set(self.labelnames):
            raise ValueError(
                f"Label mismatch: expected {self.labelnames}, got {list(labels.keys())}"
            )
        key = tuple(labels[label_name] for label_name in self.labelnames)
        with _lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def dec(self, amount: float = 1.0, **labels: str) -> None:
        # M-7 修复：Gauge.dec 同样缺少 label 校验
        if set(labels.keys()) != set(self.labelnames):
            raise ValueError(
                f"Label mismatch: expected {self.labelnames}, got {list(labels.keys())}"
            )
        key = tuple(labels[label_name] for label_name in self.labelnames)
        with _lock:
            self._values[key] = self._values.get(key, 0.0) - amount

    def collect(self) -> list[tuple[dict, float]]:
        with _lock:
            return [
                ({k: v for k, v in zip(self.labelnames, key)}, value)
                for key, value in self._values.items()
            ]


class Histogram:
    """直方图, 统计请求耗时等分布

    默认 buckets 适配 HTTP 请求 (秒):
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, +Inf
    """

    DEFAULT_BUCKETS = (
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        float("inf"),
    )

    def __init__(
        self,
        name: str,
        documentation: str,
        labelnames: tuple[str, ...] = (),
        buckets: tuple[float, ...] | None = None,
    ) -> None:
        self.name = name
        self.documentation = documentation
        self.labelnames = labelnames
        self.buckets = buckets or self.DEFAULT_BUCKETS
        # {label_key: {bucket: count, "+Inf": count, "_sum": x, "_count": n}}
        self._values: dict[tuple[str, ...], dict[str, float]] = {}
        with _lock:
            _REGISTRY.setdefault(
                name,
                {
                    "type": "histogram",
                    "doc": documentation,
                    "labelnames": labelnames,
                    "instance": self,
                },
            )

    def observe(self, value: float, **labels: str) -> None:
        if set(labels.keys()) != set(self.labelnames):
            raise ValueError(
                f"Label mismatch: expected {self.labelnames}, got {list(labels.keys())}"
            )
        key = tuple(labels[label_name] for label_name in self.labelnames)
        with _lock:
            entry = self._values.setdefault(
                key, {**{b: 0.0 for b in self.buckets}, "_sum": 0.0, "_count": 0.0}
            )
            for b in self.buckets:
                if value <= b:
                    entry[b] += 1
            entry["_sum"] += value
            entry["_count"] += 1

    def collect(self) -> list[tuple[dict, float]]:
        with _lock:
            return [
                ({k: v for k, v in zip(self.labelnames, key)}, entry)
                for key, entry in self._values.items()
            ]


class Info:
    """静态信息 (标签形式)"""

    def __init__(self, name: str, documentation: str) -> None:
        self.name = name
        self.documentation = documentation
        self._labels: dict[str, str] = {}
        with _lock:
            _REGISTRY.setdefault(
                name,
                {
                    "type": "info",
                    "doc": documentation,
                    "labelnames": (),
                    "instance": self,
                },
            )

    def info(self, **labels: str) -> None:
        with _lock:
            self._labels.update(labels)

    def collect(self) -> list[tuple[dict, float]]:
        with _lock:
            return [({}, self._labels.copy())]  # type: ignore[return-value]


# 预定义核心指标 (v1.32)
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests processed, labeled by method, path, status.",
    labelnames=("method", "path", "status"),
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds.",
    labelnames=("method", "path"),
)

model_inference_total = Counter(
    "model_inference_total",
    "Total model inference calls.",
    labelnames=("model_name", "status"),
)

model_inference_duration_seconds = Histogram(
    "model_inference_duration_seconds",
    "Model inference duration in seconds.",
    labelnames=("model_name",),
)

websocket_connections_active = Gauge(
    "websocket_connections_active",
    "Current number of active WebSocket connections.",
)

websocket_messages_total = Counter(
    "websocket_messages_total",
    "Total WebSocket messages processed.",
    labelnames=("direction", "type"),
)

db_pool_size = Gauge(
    "db_pool_size",
    "Current SQLAlchemy connection pool size.",
)

app_info = Info("app", "Application information.")
app_info.info(version=RELEASE_VERSION, name="depression-warning-system")


# v1.39 Grafana Alert Rules 专用指标
# 8 个 Gauge + 1 Counter, 全部命名规范: observability_*
# 数据源: 复用 v1.36 _compute_* 函数, 60s 周期更新
observability_channel_success_rate = Gauge(
    "observability_channel_success_rate",
    "Overall channel success rate (0-1), computed every 60s by ObservabilityExporter.",
    labelnames=("channel",),
)
observability_am_sync_success_rate = Gauge(
    "observability_am_sync_success_rate",
    "AlertManager sync success rate (0-1), computed every 60s by ObservabilityExporter.",
)
observability_lock_acquire_rate = Gauge(
    "observability_lock_acquire_rate",
    "Lock acquire success rate (0-1), computed every 60s by ObservabilityExporter.",
)
observability_lock_fallback_rate = Gauge(
    "observability_lock_fallback_rate",
    "Lock fallback rate (0-1), computed every 60s by ObservabilityExporter.",
)
observability_lock_error_rate = Gauge(
    "observability_lock_error_rate",
    "Lock error rate (0-1), computed every 60s by ObservabilityExporter.",
)
observability_lock_acquire_total = Gauge(
    "observability_lock_acquire_total",
    "Total lock acquire attempts (counter), used for R7 0-flow protection. Computed every 60s.",
)
observability_escalation_rate = Gauge(
    "observability_escalation_rate",
    "Alert escalation rate (0-1), computed every 60s by ObservabilityExporter.",
)
observability_alert_total = Counter(
    "observability_alert_total",
    "Total alerts fired per severity, incremented by ObservabilityExporter on each trend collection.",
    labelnames=("severity",),
)

# R-C: 事件驱动实时指标 (由 EventBus 处理器实时更新, 与 60s 轮询互补)
# 端到端延迟 < 5s (vs 轮询 60s)
event_alerts_fired_total = Counter(
    "event_alerts_fired_total",
    "Total alert.fired events processed by EventBus (real-time, R-C).",
)
event_alerts_resolved_total = Counter(
    "event_alerts_resolved_total",
    "Total alert.resolved events processed by EventBus (real-time, R-C).",
)
event_alerts_escalated_total = Counter(
    "event_alerts_escalated_total",
    "Total alert.escalated events processed by EventBus (real-time, R-C).",
)
event_warnings_created_total = Counter(
    "event_warnings_created_total",
    "Total warning.created events processed by EventBus (real-time, R-C).",
)
event_reviews_submitted_total = Counter(
    "event_reviews_submitted_total",
    "Total review.submitted events processed by EventBus (real-time, R-C).",
)
event_bus_dropped_total = Counter(
    "event_bus_dropped_total",
    "Total events dropped due to EventBus queue full (R-C).",
)


# v1.40 STAB-P1-014~018 修复: 告警阈值相关指标暴露
# 关联 app/core/alert_rules.py 中 AR-101~205 规则

# STAB-P1-015: DB 连接池使用率 (0-1), 由 /metrics 端点采集时更新
db_pool_utilization = Gauge(
    "db_pool_utilization",
    "DB connection pool utilization ratio (0-1), updated on /metrics scrape. AR-103 threshold=0.8",
)

# STAB-P1-015: DB 熔断器失败计数与状态 (从 db_breaker 采集)
db_circuit_failure_count = Gauge(
    "db_circuit_failure_count",
    "DB circuit breaker current failure count. AR-201 threshold=5 (closed→open)",
)
db_circuit_state = Gauge(
    "db_circuit_state",
    "DB circuit breaker state (0=closed, 1=half_open, 2=open). AR-201 触发条件",
)

# STAB-P1-016: Redis 熔断状态 (本系统 Redis 仅有降级无熔断, 此指标供未来扩展)
# 0=closed (正常), 1=half_open (降级), 2=open (不可用)
redis_circuit_state = Gauge(
    "redis_circuit_state",
    "Redis circuit/degradation state (0=closed, 1=half_open, 2=open). AR-202 threshold > 0",
)

# STAB-P1-002: ML 推理熔断器失败计数与状态 (从 ml_breaker 采集)
ml_circuit_failure_count = Gauge(
    "ml_circuit_failure_count",
    "ML inference circuit breaker current failure count. Threshold=5 (closed→open)",
)
ml_circuit_state = Gauge(
    "ml_circuit_state",
    "ML inference circuit breaker state (0=closed, 1=half_open, 2=open)",
)

# STAB-P1-004: SMTP 邮件熔断器失败计数与状态 (从 smtp_breaker 采集)
smtp_circuit_failure_count = Gauge(
    "smtp_circuit_failure_count",
    "SMTP email circuit breaker current failure count. Threshold=5 (closed→open)",
)
smtp_circuit_state = Gauge(
    "smtp_circuit_state",
    "SMTP email circuit breaker state (0=closed, 1=half_open, 2=open)",
)

# STAB-P1-005: Celery broker 熔断器失败计数与状态 (从 celery_breaker 采集)
celery_circuit_failure_count = Gauge(
    "celery_circuit_failure_count",
    "Celery broker circuit breaker current failure count. Threshold=5 (closed→open)",
)
celery_circuit_state = Gauge(
    "celery_circuit_state",
    "Celery broker circuit breaker state (0=closed, 1=half_open, 2=open)",
)

# STAB-P1-017: 模型 fallback 率 (0-1), 由 /metrics 端点从 ModelEngine.get_metrics_snapshot() 采集
model_fallback_rate = Gauge(
    "model_fallback_rate",
    "Model fallback rate (0-1) from ModelEngine.get_metrics_snapshot. AR-203 threshold=0.3",
)

# STAB-P1-018: Celery 任务失败计数 (按 task 名分标签), 由 celery_app on_task_failure 递增
celery_task_failures_total = Counter(
    "celery_task_failures_total",
    "Total Celery task failures, labeled by task name. AR-204 threshold=10 in 5min",
    labelnames=("task_name",),
)

# STAB-P1-018: Celery worker 心跳 (0=无心跳, 1=正常), 由 celery worker 启动时设置
celery_worker_heartbeat = Gauge(
    "celery_worker_heartbeat",
    "Celery worker heartbeat status (1=alive, 0=dead). AR-205 threshold=0 for 2min",
)

# STAB-P1-008: MTTR (Mean Time To Repair) 自动统计指标
# 由 /metrics 端点调用 mttr_service.compute_mttr() 更新
# 数据源: OperationLog 中 alert_fired / alert_resolved 按 fingerprint 配对
alert_mttr_seconds = Gauge(
    "alert_mttr_seconds",
    "Mean Time To Repair (seconds) for resolved alerts in last 24h. AR-206 threshold=300s",
    labelnames=("severity",),
)
alert_resolved_total = Gauge(
    "alert_resolved_total",
    "Total resolved alerts (paired fired+resolved) in last 24h window.",
)
alert_unresolved_count = Gauge(
    "alert_unresolved_count",
    "Current unresolved alerts (fired but no resolved in 24h). AR-207 threshold>0 for 1h",
)


# SEC-P1-005: 异常访问检测指标
# 数据源: tasks/anomaly_detection.py 周期扫描 OperationLog
# 关联 alert_rules.py AR-303~AR-306 (anomaly_type 标签区分)
# anomaly_access_detected_total: 检测到的异常访问累计计数 (按 anomaly_type 分标签)
#   - high_frequency (AR-303): 同一用户 N 分钟内操作数超阈值
#   - off_hours (AR-304): 22:00~06:00 UTC 非工作时间管理员/咨询师操作
#   - cross_region (AR-305): 同一用户 N 小时内不同 IP 数量超阈值
#   - lateral (AR-306): 同一用户 N 分钟内不同 target_type 数量超阈值
anomaly_access_detected_total = Counter(
    "anomaly_access_detected_total",
    "Total anomaly access detected, labeled by anomaly_type. AR-303~AR-306 trigger when > 0",
    labelnames=("type",),
)

# anomaly_access_last_detected_at: 最近一次异常检测扫描时间戳 (Unix 秒)
# 由 detect_anomaly_access_task 每次扫描后更新 (无论是否发现异常)
# 用于监控扫描任务是否正常运行 (Grafana 可设告警: 5 分钟内未更新则任务异常)
anomaly_access_last_detected_at = Gauge(
    "anomaly_access_last_detected_at",
    "Last anomaly access detection scan timestamp (Unix seconds). Updated every scan.",
)


# R-005 修复: fire-and-forget 任务可观测性指标
# 数据源: app/core/fire_forget_metrics.py 在调度 + done_callback 中递增
# 覆盖 5 类 fire-and-forget 任务:
#   - assessment_save: 评估结果保存 (model_predict/_common.py)
#   - review_task_create: 复核任务创建 (model_predict/predict.py)
#   - warning_intervention: 告警+干预触发 (risk_service.py)
#   - validation_job: 模型验证任务 (validation.py)
#   - pdf_generation: PDF 报告生成 (reports.py)
# status 标签: scheduled / succeeded / failed / cancelled
# 配合 alert_rules.py 可扩展 AR-208 规则 (失败率 > 阈值告警)
fire_forget_tasks_total = Counter(
    "fire_forget_tasks_total",
    "Total fire-and-forget tasks, labeled by task_type and status "
    "(scheduled/succeeded/failed/cancelled). R-005 observability.",
    labelnames=("task_type", "status"),
)

fire_forget_task_duration_seconds = Histogram(
    "fire_forget_task_duration_seconds",
    "Fire-and-forget task duration in seconds, labeled by task_type. R-005 observability.",
    labelnames=("task_type",),
)

# R-006 修复: 启动组件失败计数 (用于 AR-209 告警)
# 标签:
#   component: 组件名 (init_db / seed_database / ensure_pii_key /
#              model_preload / sentry / observability_exporter /
#              health_monitor / ws_pubsub / canary_fallback)
#   fatal: "true" (致命，lifespan 中止) / "false" (非致命，降级运行)
startup_component_failures_total = Counter(
    "startup_component_failures_total",
    "Total startup component failures, labeled by component name and fatality. "
    "R-006 observability.",
    labelnames=("component", "fatal"),
)


def _format_labels(labels: dict[str, str]) -> str:
    """格式化为 {key="value",...}"""
    if not labels:
        return ""
    items = []
    for k, v in labels.items():
        escaped = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        items.append(f'{k}="{escaped}"')
    return "{" + ",".join(items) + "}"


def render_exposition() -> str:
    """渲染所有指标为 Prometheus exposition format.

    输出示例:
    # HELP http_requests_total Total HTTP requests...
    # TYPE http_requests_total counter
    http_requests_total{method="GET",path="/health",status="200"} 42
    """
    lines: list[str] = []
    with _lock:
        registry_snapshot = dict(_REGISTRY)

    for name, meta in registry_snapshot.items():
        lines.append(f"# HELP {name} {meta['doc']}")
        lines.append(f"# TYPE {name} {meta['type']}")
        instance = meta["instance"]
        for entry in instance.collect():
            if meta["type"] == "info":
                labels, info_labels = entry
                if not info_labels:
                    continue
                label_str = _format_labels(info_labels)
                lines.append(f"{name}_info{label_str} 1")
            elif meta["type"] == "histogram":
                labels, bucket_data = entry
                label_str = _format_labels(labels)
                for b in instance.buckets:
                    bucket_label = {
                        **labels,
                        "le": str(b) if b != float("inf") else "+Inf",
                    }
                    lines.append(
                        f"{name}_bucket{_format_labels(bucket_label)} {int(bucket_data[b])}"
                    )
                sum_label = {**labels}
                lines.append(
                    f"{name}_sum{_format_labels(sum_label)} {bucket_data['_sum']:.6f}"
                )
                count_label = {**labels}
                lines.append(
                    f"{name}_count{_format_labels(count_label)} {int(bucket_data['_count'])}"
                )
            else:
                labels, value = entry
                label_str = _format_labels(labels)
                lines.append(f"{name}{label_str} {value}")
    return "\n".join(lines) + "\n"


class Timer:
    """上下文管理器, 用于记录耗时"""

    def __init__(self, histogram: Histogram, **labels: str) -> None:
        self.histogram = histogram
        self.labels = labels
        self.start: float = 0.0

    def __enter__(self) -> "Timer":
        self.start = time.perf_counter()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        duration = time.perf_counter() - self.start
        self.histogram.observe(duration, **self.labels)


@contextmanager
def track_model_inference(model_name: str) -> Iterator[None]:
    """跟踪模型推理的计数器和直方图 (v1.32).

    自动记录:
    - model_inference_total{model_name, status} (success/error)
    - model_inference_duration_seconds{model_name}

    Usage:
        with track_model_inference("structured"):
            result = model.predict(...)
    """
    start = time.perf_counter()
    status = "success"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        duration = time.perf_counter() - start
        try:
            model_inference_total.inc(model_name=model_name, status=status)
            model_inference_duration_seconds.observe(duration, model_name=model_name)
        except Exception as exc:
            # 指标失败不影响主流程，但记录日志便于排查
            logger.debug("model_inference metrics inc failed: %s", exc)


def reset_registry() -> None:
    """清空所有指标 (仅用于测试)"""
    with _lock:
        for meta in _REGISTRY.values():
            inst = meta["instance"]
            if hasattr(inst, "_values"):
                inst._values.clear()
