"""Tests for observability service."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from app.models.monitoring import MonitoringLog
from app.services.observability_service import (
    Counter,
    LatencyHistogram,
    ObservabilityCollector,
)


class TestLatencyHistogram:
    """Test LatencyHistogram."""

    def test_observe(self):
        """TC-COV-OBS-001: Observe latency."""
        h = LatencyHistogram()
        h.observe(50.0)
        assert h.total_count == 1
        assert h.sum_ms == 50.0
        assert h.counts["le_50"] == 1
        assert h.counts["le_inf"] == 1

    def test_observe_multiple(self):
        """TC-COV-OBS-002: Observe multiple latencies."""
        h = LatencyHistogram()
        h.observe(5.0)
        h.observe(50.0)
        h.observe(500.0)
        assert h.total_count == 3
        assert h.counts["le_10"] == 1
        assert h.counts["le_50"] == 2
        assert h.counts["le_500"] == 3

    def test_to_dict(self):
        """TC-COV-OBS-003: Histogram to dict."""
        h = LatencyHistogram()
        h.observe(100.0)
        d = h.to_dict()
        assert d["total_count"] == 1
        assert d["sum_ms"] == 100.0
        assert d["avg_ms"] == 100.0
        assert "buckets" in d


class TestCounter:
    """Test Counter."""

    def test_increment(self):
        """TC-COV-OBS-004: Increment counter."""
        c = Counter()
        c.increment()
        assert c.value == 1

    def test_increment_delta(self):
        """TC-COV-OBS-005: Increment by delta."""
        c = Counter()
        c.increment(5)
        assert c.value == 5

    def test_to_dict(self):
        """TC-COV-OBS-006: Counter to dict."""
        c = Counter()
        c.increment(3)
        assert c.to_dict() == {"value": 3}


class TestObservabilityCollector:
    """Test ObservabilityCollector."""

    def test_record_inference_latency(self):
        """TC-COV-OBS-007: Record inference latency."""
        collector = ObservabilityCollector()
        collector.record_inference_latency(100.0, model_version="v1", user_id=1)
        assert len(collector.get_pending_logs()) == 1
        snapshot = collector.get_metrics_snapshot()
        assert snapshot["pending_logs"] == 1
        assert snapshot["inference_latency"]["total_count"] == 1

    def test_record_inference_success(self):
        """TC-COV-OBS-008: Record successful inference."""
        collector = ObservabilityCollector()
        collector.record_inference(model_version="v1", latency_ms=50.0)
        snapshot = collector.get_metrics_snapshot()
        assert snapshot["model_success"]["value"] == 1
        assert snapshot["fallback"]["value"] == 0

    def test_record_inference_fallback(self):
        """TC-COV-OBS-009: Record fallback inference."""
        collector = ObservabilityCollector()
        collector.record_inference(model_version="v1", fallback_reason="timeout")
        snapshot = collector.get_metrics_snapshot()
        assert snapshot["fallback"]["value"] == 1
        assert snapshot["model_success"]["value"] == 0

    def test_record_model_success(self):
        """TC-COV-OBS-010: Record model success."""
        collector = ObservabilityCollector()
        collector.record_model_success(model_version="v1", user_id=1)
        snapshot = collector.get_metrics_snapshot()
        assert snapshot["model_success"]["value"] == 1

    def test_record_fallback(self):
        """TC-COV-OBS-011: Record fallback."""
        collector = ObservabilityCollector()
        collector.record_fallback("error", model_version="v1")
        snapshot = collector.get_metrics_snapshot()
        assert snapshot["fallback"]["value"] == 1

    def test_record_input_anomaly(self):
        """TC-COV-OBS-012: Record input anomaly."""
        collector = ObservabilityCollector()
        collector.record_input_anomaly("outlier", details={"field": "hr"})
        snapshot = collector.get_metrics_snapshot()
        assert snapshot["input_anomaly"]["value"] == 1

    def test_get_metrics_snapshot_empty(self):
        """TC-COV-OBS-013: Empty metrics snapshot."""
        collector = ObservabilityCollector()
        snapshot = collector.get_metrics_snapshot()
        assert snapshot["inference_latency"]["total_count"] == 0
        assert snapshot["model_success"]["value"] == 0
        assert snapshot["fallback"]["value"] == 0
        assert snapshot["input_anomaly"]["value"] == 0
        assert snapshot["pending_logs"] == 0

    @pytest.mark.asyncio
    async def test_flush_empty(self):
        """TC-COV-OBS-014: Flush with no logs."""
        collector = ObservabilityCollector()
        await collector._flush()
        assert collector.get_pending_logs() == []

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """TC-COV-OBS-015: Start and stop collector."""
        collector = ObservabilityCollector()
        await collector.start()
        assert collector._running is True
        await collector.stop()
        assert collector._running is False

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        """TC-COV-OBS-016: Start is idempotent."""
        collector = ObservabilityCollector()
        await collector.start()
        await collector.start()  # Should not raise
        await collector.stop()

    @pytest.mark.asyncio
    async def test_flush_with_logs(self):
        """TC-COV-OBS-017: _flush 将 pending 日志累积到 flushed_buffer。"""
        collector = ObservabilityCollector()
        collector.record_inference_latency(100.0, model_version="v1", user_id=1)
        collector.record_inference_latency(200.0, model_version="v1", user_id=1)
        assert len(collector.get_pending_logs()) == 2

        await collector._flush()
        # flush 后 pending 应为空
        assert len(collector.get_pending_logs()) == 0
        # flushed_buffer 应有 2 条
        consumed = await collector.consume_flushed_logs()
        assert len(consumed) == 2

    @pytest.mark.asyncio
    async def test_flush_buffer_overflow(self):
        """TC-COV-OBS-018: _flush 缓冲区超过上限时丢弃最旧日志。"""
        collector = ObservabilityCollector()
        collector._max_buffer_size = 3

        for i in range(5):
            collector.record_inference_latency(float(i))
        await collector._flush()

        consumed = await collector.consume_flushed_logs()
        assert len(consumed) == 3

    @pytest.mark.asyncio
    async def test_consume_flushed_logs_empty(self):
        """TC-COV-OBS-019: consume_flushed_logs 无日志时返回空列表。"""
        collector = ObservabilityCollector()
        result = await collector.consume_flushed_logs()
        assert result == []

    @pytest.mark.asyncio
    async def test_consume_clears_buffer(self):
        """TC-COV-OBS-020: consume_flushed_logs 调用后清空缓冲区，避免重复消费。"""
        collector = ObservabilityCollector()
        collector.record_inference_latency(50.0)
        await collector._flush()

        first = await collector.consume_flushed_logs()
        assert len(first) == 1
        second = await collector.consume_flushed_logs()
        assert second == []

    @pytest.mark.asyncio
    async def test_flush_loop_handles_exception(self):
        """TC-COV-OBS-021: _flush_loop 中 _flush 抛异常时捕获并继续循环。"""
        collector = ObservabilityCollector()
        collector._running = True
        collector._FLUSH_INTERVAL_SECONDS = 0.001

        call_count = {"n": 0}

        async def mock_flush():
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("test flush error")
            collector._running = False

        collector._flush = mock_flush
        await collector._flush_loop()
        assert call_count["n"] >= 1

    @pytest.mark.asyncio
    async def test_flush_to_db_empty(self, db_session):
        """TC-COV-OBS-022: flush_to_db 无 pending 日志时返回 0。"""
        collector = ObservabilityCollector()
        count = await collector.flush_to_db(db_session)
        assert count == 0

    @pytest.mark.asyncio
    async def test_flush_to_db_with_logs(self, db_session, seeded_user_id):
        """TC-COV-OBS-023: flush_to_db 将日志写入数据库并返回数量。"""
        collector = ObservabilityCollector()
        collector.record_inference_latency(100.0, model_version="v1", user_id=1)
        collector.record_inference_latency(200.0, model_version="v1", user_id=1)

        count = await collector.flush_to_db(db_session)
        assert count == 2
        await db_session.commit()

        result = await db_session.execute(select(MonitoringLog))
        logs = result.scalars().all()
        assert len(logs) >= 2

    @pytest.mark.asyncio
    async def test_flush_loop_handles_cancel(self):
        """TC-COV-OBS-024: _flush_loop 收到 CancelledError 时 break 退出循环（覆盖行 118）。

        直接创建 _flush_loop 任务并让任务进入 sleep 后再 cancel，
        确保 CancelledError 在 await asyncio.sleep(...) 处抛出，被 except 分支捕获并 break。
        不使用 start()/stop()，因为 stop() 先设 _running=False 会导致 while 条件不满足而正常退出。
        """
        collector = ObservabilityCollector()
        collector._FLUSH_INTERVAL_SECONDS = 0.001
        collector._running = True

        # 创建后台 flush_loop 任务
        task = asyncio.create_task(collector._flush_loop())
        # 让出控制权让任务进入 await asyncio.sleep(...)
        await asyncio.sleep(0.01)

        # 现在 cancel，CancelledError 将在 await asyncio.sleep(...) 处抛出
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


class TestObservabilityMaxBufferSize:
    """RES-P1-004 测试: ObservabilityCollector 缓冲区上限调整.

    验证 ``settings.observability_max_buffer_size`` 从 10000 降至 1000,
    避免死缓冲区占用过多内存.
    """

    def test_config_default_is_1000(self):
        """RES-P1-004-TC-001: observability_max_buffer_size 默认值应为 1000."""
        from app.core.config import Settings

        fields = Settings.model_fields
        assert "observability_max_buffer_size" in fields
        assert (
            fields["observability_max_buffer_size"].default == 1000
        ), "RES-P1-004: 默认值应从 10000 降至 1000, 避免死缓冲区内存浪费"

    def test_collector_reads_config_default(self):
        """RES-P1-004-TC-002: ObservabilityCollector._max_buffer_size 应读取配置默认值."""
        collector = ObservabilityCollector()
        from app.core.config import settings

        assert collector._max_buffer_size == settings.observability_max_buffer_size
        assert (
            collector._max_buffer_size == 1000
        ), f"_max_buffer_size 应为 1000, 实际: {collector._max_buffer_size}"

    @pytest.mark.asyncio
    async def test_buffer_overflow_at_1000(self):
        """RES-P1-004-TC-003: 上限 1000 时, 超过 1000 条日志应丢弃最旧的."""
        collector = ObservabilityCollector()
        assert collector._max_buffer_size == 1000

        # 写入 1500 条日志到 pending
        for i in range(1500):
            collector.record_inference_latency(float(i))
        await collector._flush()

        consumed = await collector.consume_flushed_logs()
        # 上限 1000, 应只保留最新的 1000 条
        assert (
            len(consumed) == 1000
        ), f"上限 1000 时应只保留 1000 条, 实际: {len(consumed)}"
        # 应丢弃最旧的 500 条 (索引 0-499), 保留 500-1499
        # 验证保留的是最新的: 第一条应是 index=500 的日志
        # (MonitoringLog.latency_ms 记录的是 record_inference_latency 的第一个参数)
        assert consumed[0].latency_ms == 500.0
        assert consumed[-1].latency_ms == 1499.0

    def test_dead_buffer_documented(self):
        """RES-P1-004-TC-004: consume_flushed_logs docstring 应文档化死缓冲区状态."""
        from app.services.observability_service import ObservabilityCollector

        doc = ObservabilityCollector.consume_flushed_logs.__doc__ or ""
        # docstring 应包含 RES-P1-004 标识和死缓冲区说明
        assert "RES-P1-004" in doc, "consume_flushed_logs docstring 应标注 RES-P1-004"
        assert (
            "死缓冲区" in doc or "无任何消费者" in doc
        ), "docstring 应说明当前无生产消费者, _flushed_buffer 属于死缓冲区"
