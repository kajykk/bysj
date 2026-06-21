"""Performance tests for API latency.

TC-PERF-001 ~ TC-PERF-003: API response time benchmarks.
"""

from __future__ import annotations

import time

import pytest


class TestApiLatency:
    """Test API latency benchmarks."""

    @pytest.mark.performance
    def test_health_check_latency(self, client):
        """TC-PERF-001: Health check should respond within 200ms."""
        start = time.time()
        response = client.get("/api/v1/health")
        elapsed = (time.time() - start) * 1000

        assert response.status_code == 200
        assert elapsed < 200, f"Health check took {elapsed:.2f}ms"

    @pytest.mark.performance
    def test_list_templates_latency(self, client, auth_headers):
        """TC-PERF-002: List templates should respond within 500ms."""
        start = time.time()
        response = client.get("/api/v1/reports/templates", headers=auth_headers)
        elapsed = (time.time() - start) * 1000

        assert response.status_code == 200
        assert elapsed < 500, f"List templates took {elapsed:.2f}ms"

    @pytest.mark.performance
    def test_fusion_engine_latency(self):
        """TC-PERF-003: Fusion engine should complete within 100ms."""
        from app.ml.fusion_engine import FusionEngine

        engine = FusionEngine()
        start = time.time()
        result = engine.fuse({"structured": 80, "text": 60, "physiological": 70})
        elapsed = (time.time() - start) * 1000

        assert result["risk_score"] > 0
        assert elapsed < 100, f"Fusion took {elapsed:.2f}ms"
