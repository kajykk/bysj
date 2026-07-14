from __future__ import annotations

import asyncio
import logging
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.monitoring import MonitoringEventType, MonitoringLog

logger = logging.getLogger(__name__)


@dataclass
class LatencyHistogram:
    """Simple histogram for latency distribution."""

    buckets: list[float] = field(
        default_factory=lambda: [10, 50, 100, 200, 500, 1000, 2000, 5000]
    )
    counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    total_count: int = 0
    sum_ms: float = 0.0

    def observe(self, latency_ms: float) -> None:
        self.total_count += 1
        self.sum_ms += latency_ms
        for bucket in self.buckets:
            if latency_ms <= bucket:
                self.counts[f"le_{bucket}"] += 1
        self.counts["le_inf"] += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "buckets": {k: v for k, v in self.counts.items()},
            "total_count": self.total_count,
            "sum_ms": round(self.sum_ms, 2),
            "avg_ms": round(self.sum_ms / max(1, self.total_count), 2),
        }


@dataclass
class Counter:
    """Simple counter metric."""

    value: int = 0

    def increment(self, delta: int = 1) -> None:
        self.value += delta

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value}


class ObservabilityCollector:
    """Collects and batches observability metrics for async flush to database.

    Features:
    - Inference latency histogram
    - Model success / fallback counters
    - Input anomaly detection and counting
    - Async batch flush every 30s

    RES-P1-004 文档化说明 (死缓冲区):
        生产环境实际运行中, ``start()`` / ``stop()`` / ``_flush_loop`` 均未被调用
        (main.py 启动的是 ``ObservabilityExporter``, 不是本类). ``flush_to_db()``
        直接从 ``_pending_logs`` 取数据, 绕过 ``_flushed_buffer``. 而
        ``consume_flushed_logs()`` 虽然接口保留, 但生产代码中无任何消费者调用,
        仅有测试用例覆盖. 故 ``_flushed_buffer`` (上限 ``observability_max_buffer_size``)
        在当前生产配置下属于死缓冲区, 仅在测试场景中触发 ``_flush`` 路径时写入.
        保留接口供未来接入消费者 (如导出到外部 TSDB), 上限已从 10000 降至 1000
        以避免内存浪费.
    """

    _FLUSH_INTERVAL_SECONDS = 30
    _BATCH_SIZE = 100

    def __init__(self) -> None:
        self._latency_histogram = LatencyHistogram()
        self._success_counter = Counter()
        self._fallback_counter = Counter()
        self._anomaly_counter = Counter()
        # M-L 修复：缓冲区大小从 settings 读取，支持通过环境变量调整
        self._pending_logs: deque[MonitoringLog] = deque(
            maxlen=settings.observability_pending_logs_maxlen
        )
        # M-Svc-19 修复：改用 threading.Lock，使同步的 record_* 方法也能持锁保护 deque 操作。
        # 原 asyncio.Lock 仅支持 async with，同步方法无法使用，导致 record_* 中的
        # deque.append 与 _flush 的 list()/clear() 之间存在竞态。
        # async 方法（_flush/consume_flushed_logs/flush_to_db）锁内均无 await，改用同步锁安全。
        self._lock = threading.Lock()
        self._flush_task: asyncio.Task[None] | None = None
        self._running = False
        # M-23 修复：使用累积式缓冲区替代单次覆盖，避免外部消费者未及时读取时丢失 logs
        self._flushed_buffer: list[MonitoringLog] = []
        self._max_buffer_size = settings.observability_max_buffer_size

    async def start(self) -> None:
        """Start the periodic flush task."""
        if self._running:
            return
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("ObservabilityCollector started")

    async def stop(self) -> None:
        """Stop the periodic flush task and flush remaining logs."""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        # Final flush
        await self._flush()
        logger.info("ObservabilityCollector stopped")

    async def _flush_loop(self) -> None:
        """Background loop that flushes metrics periodically."""
        while self._running:
            try:
                await asyncio.sleep(self._FLUSH_INTERVAL_SECONDS)
                await self._flush()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("ObservabilityCollector flush loop error")

    async def _flush(self) -> None:
        """Flush pending logs to buffer for external consumption."""
        # M-Svc-19 修复：改用同步 with（threading.Lock），锁内无 await，安全
        with self._lock:
            if not self._pending_logs:
                return
            logs_to_flush = list(self._pending_logs)
            self._pending_logs.clear()
            # M-23 修复：累积到缓冲区而非覆盖，避免外部消费者未及时读取时丢失
            self._flushed_buffer.extend(logs_to_flush)
            # 防止缓冲区无界增长：超过上限时丢弃最旧的
            if len(self._flushed_buffer) > self._max_buffer_size:
                overflow = len(self._flushed_buffer) - self._max_buffer_size
                self._flushed_buffer = self._flushed_buffer[overflow:]

        logger.debug("Flushing %d observability logs to buffer", len(logs_to_flush))

    async def consume_flushed_logs(self) -> list[MonitoringLog]:
        """M-23 修复：供外部消费者取出并清空已 flush 的 logs.

        .. warning::
            RES-P1-004: 当前生产代码中无任何消费者调用此方法, 仅测试用例覆盖.
            ``flush_to_db()`` 直接从 ``_pending_logs`` 取数据, 绕过
            ``_flushed_buffer``. 故 ``_flushed_buffer`` 在生产中属于死缓冲区,
            保留本接口供未来接入外部消费者 (如 TSDB 导出器).

        Returns:
            所有已 flush 但尚未被消费的 MonitoringLog 列表。
            调用后缓冲区会被清空，避免重复消费。
        """
        # H-Svc-10 修复：在 _lock 内消费，避免与 _flush 并发时读到中间状态
        # M-Svc-19 修复：改用同步 with（threading.Lock）
        with self._lock:
            if not self._flushed_buffer:
                return []
            logs = self._flushed_buffer
            self._flushed_buffer = []
            return logs

    def record_inference_latency(
        self,
        latency_ms: float,
        model_version: str | None = None,
        user_id: int | None = None,
    ) -> None:
        """Record inference latency."""
        # M-Svc-19 修复：持锁保护 histogram/counter/deque 的复合操作，避免与 _flush 竞态
        with self._lock:
            self._latency_histogram.observe(latency_ms)
            log = MonitoringLog(
                event_type=MonitoringEventType.INFERENCE,
                model_version=model_version,
                user_id=user_id,
                latency_ms=latency_ms,
                response_summary={"histogram": self._latency_histogram.to_dict()},
            )
            self._pending_logs.append(log)

    def record_inference(
        self,
        model_version: str | None = None,
        latency_ms: float | None = None,
        fallback_reason: str | None = None,
        user_id: int | None = None,
    ) -> None:
        """Backward-compatible combined inference metric recorder."""
        # M-Svc-19 修复：持锁保护 counter/deque 的复合操作
        with self._lock:
            if latency_ms is not None:
                self._latency_histogram.observe(latency_ms)
            if fallback_reason:
                self._fallback_counter.increment()
                event_type = MonitoringEventType.FALLBACK
            else:
                self._success_counter.increment()
                event_type = MonitoringEventType.INFERENCE
            self._pending_logs.append(
                MonitoringLog(
                    event_type=event_type,
                    model_version=model_version,
                    user_id=user_id,
                    latency_ms=latency_ms,
                    fallback_reason=fallback_reason,
                    response_summary={
                        "status": "fallback" if fallback_reason else "success"
                    },
                )
            )

    def record_model_success(
        self,
        model_version: str | None = None,
        user_id: int | None = None,
        response_summary: dict | None = None,
    ) -> None:
        """Record a successful model prediction."""
        # M-Svc-19 修复：持锁保护 counter/deque 的复合操作
        with self._lock:
            self._success_counter.increment()
            log = MonitoringLog(
                event_type=MonitoringEventType.INFERENCE,
                model_version=model_version,
                user_id=user_id,
                response_summary=response_summary
                or {"status": "success", "counter": self._success_counter.to_dict()},
            )
            self._pending_logs.append(log)

    def record_fallback(
        self,
        reason: str,
        model_version: str | None = None,
        user_id: int | None = None,
        request_payload: dict | None = None,
    ) -> None:
        """Record a fallback event."""
        # M-Svc-19 修复：持锁保护 counter/deque 的复合操作
        with self._lock:
            self._fallback_counter.increment()
            log = MonitoringLog(
                event_type=MonitoringEventType.FALLBACK,
                model_version=model_version,
                user_id=user_id,
                fallback_reason=reason,
                request_payload=request_payload,
                response_summary={"fallback_counter": self._fallback_counter.to_dict()},
            )
            self._pending_logs.append(log)

    def record_input_anomaly(
        self,
        anomaly_type: str,
        details: dict | None = None,
        user_id: int | None = None,
        request_payload: dict | None = None,
    ) -> None:
        """Record an input anomaly detection."""
        # M-Svc-19 修复：持锁保护 counter/deque 的复合操作
        with self._lock:
            self._anomaly_counter.increment()
            log = MonitoringLog(
                event_type=MonitoringEventType.INPUT_ANOMALY,
                user_id=user_id,
                request_payload=request_payload,
                response_summary={
                    "anomaly_type": anomaly_type,
                    "details": details,
                    "anomaly_counter": self._anomaly_counter.to_dict(),
                },
            )
            self._pending_logs.append(log)

    def get_metrics_snapshot(self) -> dict[str, Any]:
        """Get current metrics snapshot."""
        return {
            "inference_latency": self._latency_histogram.to_dict(),
            "model_success": self._success_counter.to_dict(),
            "fallback": self._fallback_counter.to_dict(),
            "input_anomaly": self._anomaly_counter.to_dict(),
            "pending_logs": len(self._pending_logs),
        }

    async def flush_to_db(self, db_session: AsyncSession) -> int:
        """Flush pending logs to database using provided session.

        Returns:
            Number of logs flushed.
        """
        # M-Svc-19 修复：改用同步 with（threading.Lock），锁内无 await，安全
        with self._lock:
            if not self._pending_logs:
                return 0
            logs_to_flush = list(self._pending_logs)
            self._pending_logs.clear()

        # PERF-P3-004: 使用 add_all 批量添加替代逐个 add,
        # 减少 Python 层循环开销 (SQLAlchemy 内部优化批量 insert)
        db_session.add_all(logs_to_flush)
        # M-12 修复：service 层不内部 commit，避免污染调用方事务。
        # 改用 flush() 将更改刷入 DB（同一事务内可见），由调用方（API 层）统一管理事务提交。
        await db_session.flush()
        logger.info("Flushed %d observability logs to database", len(logs_to_flush))
        return len(logs_to_flush)

    def get_pending_logs(self) -> list[MonitoringLog]:
        """Get a copy of pending logs (for testing)."""
        return list(self._pending_logs)


# Global collector instance
observability_collector = ObservabilityCollector()
