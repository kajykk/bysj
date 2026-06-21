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

import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator


# 线程安全锁
_lock = threading.Lock()

# 指标注册表
_REGISTRY: dict[str, dict[str, Any]] = {}


class Counter:
    """单调递增计数器"""

    def __init__(self, name: str, documentation: str, labelnames: tuple[str, ...] = ()) -> None:
        self.name = name
        self.documentation = documentation
        self.labelnames = labelnames
        self._values: dict[tuple[str, ...], float] = {}
        with _lock:
            _REGISTRY.setdefault(name, {"type": "counter", "doc": documentation, "labelnames": labelnames, "instance": self})

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        if set(labels.keys()) != set(self.labelnames):
            raise ValueError(f"Label mismatch: expected {self.labelnames}, got {list(labels.keys())}")
        key = tuple(labels[l] for l in self.labelnames)
        with _lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def collect(self) -> list[tuple[dict, float]]:
        with _lock:
            return [({k: v for k, v in zip(self.labelnames, key)}, value) for key, value in self._values.items()]


class Gauge:
    """可增可减的仪表"""

    def __init__(self, name: str, documentation: str, labelnames: tuple[str, ...] = ()) -> None:
        self.name = name
        self.documentation = documentation
        self.labelnames = labelnames
        self._values: dict[tuple[str, ...], float] = {}
        with _lock:
            _REGISTRY.setdefault(name, {"type": "gauge", "doc": documentation, "labelnames": labelnames, "instance": self})

    def set(self, value: float, **labels: str) -> None:
        if set(labels.keys()) != set(self.labelnames):
            raise ValueError(f"Label mismatch: expected {self.labelnames}, got {list(labels.keys())}")
        key = tuple(labels[l] for l in self.labelnames)
        with _lock:
            self._values[key] = value

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        key = tuple(labels[l] for l in self.labelnames)
        with _lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def dec(self, amount: float = 1.0, **labels: str) -> None:
        key = tuple(labels[l] for l in self.labelnames)
        with _lock:
            self._values[key] = self._values.get(key, 0.0) - amount

    def collect(self) -> list[tuple[dict, float]]:
        with _lock:
            return [({k: v for k, v in zip(self.labelnames, key)}, value) for key, value in self._values.items()]


class Histogram:
    """直方图, 统计请求耗时等分布

    默认 buckets 适配 HTTP 请求 (秒):
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, +Inf
    """

    DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float("inf"))

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
            _REGISTRY.setdefault(name, {"type": "histogram", "doc": documentation, "labelnames": labelnames, "instance": self})

    def observe(self, value: float, **labels: str) -> None:
        if set(labels.keys()) != set(self.labelnames):
            raise ValueError(f"Label mismatch: expected {self.labelnames}, got {list(labels.keys())}")
        key = tuple(labels[l] for l in self.labelnames)
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
            return [({k: v for k, v in zip(self.labelnames, key)}, entry) for key, entry in self._values.items()]


class Info:
    """静态信息 (标签形式)"""

    def __init__(self, name: str, documentation: str) -> None:
        self.name = name
        self.documentation = documentation
        self._labels: dict[str, str] = {}
        with _lock:
            _REGISTRY.setdefault(name, {"type": "info", "doc": documentation, "labelnames": (), "instance": self})

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
app_info.info(version="v1.32-observability-complete", name="depression-warning-system")


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
                    bucket_label = {**labels, "le": str(b) if b != float("inf") else "+Inf"}
                    lines.append(f"{name}_bucket{_format_labels(bucket_label)} {int(bucket_data[b])}")
                sum_label = {**labels}
                lines.append(f"{name}_sum{_format_labels(sum_label)} {bucket_data['_sum']:.6f}")
                count_label = {**labels}
                lines.append(f"{name}_count{_format_labels(count_label)} {int(bucket_data['_count'])}")
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
