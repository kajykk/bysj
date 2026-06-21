"""Tests for observability service."""

from __future__ import annotations

import asyncio

import pytest

from app.services.observability_service import (
    LatencyHistogram,
    Counter,
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
