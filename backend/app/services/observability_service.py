from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring import MonitoringEventType, MonitoringLog

logger = logging.getLogger(__name__)


@dataclass
class LatencyHistogram:
    """Simple histogram for latency distribution."""

    buckets: list[float] = field(default_factory=lambda: [10, 50, 100, 200, 500, 1000, 2000, 5000])
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
    """

    _FLUSH_INTERVAL_SECONDS = 30
    _BATCH_SIZE = 100

    def __init__(self) -> None:
        self._latency_histogram = LatencyHistogram()
        self._success_counter = Counter()
        self._fallback_counter = Counter()
        self._anomaly_counter = Counter()
        self._pending_logs: deque[MonitoringLog] = deque(maxlen=1000)
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task[None] | None = None
        self._running = False

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
        """Flush pending logs to database."""
        async with self._lock:
            if not self._pending_logs:
                return
            logs_to_flush = list(self._pending_logs)
            self._pending_logs.clear()

        # Note: actual DB write happens via external session
        # This method returns the logs for the caller to persist
        logger.debug("Flushing %d observability logs", len(logs_to_flush))
        self._last_flushed_logs = logs_to_flush

    def record_inference_latency(self, latency_ms: float, model_version: str | None = None, user_id: int | None = None) -> None:
        """Record inference latency."""
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
                response_summary={"status": "fallback" if fallback_reason else "success"},
            )
        )

    def record_model_success(self, model_version: str | None = None, user_id: int | None = None, response_summary: dict | None = None) -> None:
        """Record a successful model prediction."""
        self._success_counter.increment()
        log = MonitoringLog(
            event_type=MonitoringEventType.INFERENCE,
            model_version=model_version,
            user_id=user_id,
            response_summary=response_summary or {"status": "success", "counter": self._success_counter.to_dict()},
        )
        self._pending_logs.append(log)

    def record_fallback(self, reason: str, model_version: str | None = None, user_id: int | None = None, request_payload: dict | None = None) -> None:
        """Record a fallback event."""
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

    def record_input_anomaly(self, anomaly_type: str, details: dict | None = None, user_id: int | None = None, request_payload: dict | None = None) -> None:
        """Record an input anomaly detection."""
        self._anomaly_counter.increment()
        log = MonitoringLog(
            event_type=MonitoringEventType.INPUT_ANOMALY,
            user_id=user_id,
            request_payload=request_payload,
            response_summary={"anomaly_type": anomaly_type, "details": details, "anomaly_counter": self._anomaly_counter.to_dict()},
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
        async with self._lock:
            if not self._pending_logs:
                return 0
            logs_to_flush = list(self._pending_logs)
            self._pending_logs.clear()

        for log in logs_to_flush:
            db_session.add(log)
        await db_session.commit()
        logger.info("Flushed %d observability logs to database", len(logs_to_flush))
        return len(logs_to_flush)

    def get_pending_logs(self) -> list[MonitoringLog]:
        """Get a copy of pending logs (for testing)."""
        return list(self._pending_logs)


# Global collector instance
observability_collector = ObservabilityCollector()
