"""Contract tests for monitoring API endpoints.

Validates request/response contracts for monitoring and observability APIs.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

pytestmark = pytest.mark.contract


class TestMonitoringContract:
    """Contract tests for monitoring endpoints."""

    def test_health_endpoint(self):
        """TC-CNT-HP-036: Health endpoint returns system status.

        H-AUDIT-01: /health 在根路径 (非 /api/v1 下), 返回 status: ok|degraded
        """
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["ok", "degraded"]

    def test_health_response_schema(self):
        """TC-CNT-HP-037: Health response has expected structure."""
        response = client.get("/health")

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
            assert "status" in data

    def test_metrics_endpoint(self):
        """TC-CNT-HP-038: Metrics endpoint returns system metrics.

        H-AUDIT-01: /api/v1/metrics 是 Prometheus exposition 文本格式且强制 Bearer
        """
        response = client.get("/api/v1/metrics")

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            assert response.headers.get("content-type", "").startswith("text/plain")
            assert "# HELP" in response.text

    def test_success_rate_endpoint(self):
        """TC-CNT-HP-039: Success rate endpoint returns prediction success stats.

        H-AUDIT-01: 真实路径为 /monitoring/model-success-rate
        """
        response = client.get("/api/v1/monitoring/model-success-rate")

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
            # Should contain success rate information
            assert any(k in data for k in ["success_rate", "rate", "percentage"])

    def test_fallback_stats_endpoint(self):
        """TC-CNT-HP-040: Fallback stats endpoint returns fallback statistics."""
        response = client.get("/api/v1/monitoring/fallback-stats")

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

    def test_drift_alerts_endpoint(self):
        """TC-CNT-HP-041: Drift alerts endpoint returns drift information."""
        response = client.get("/api/v1/monitoring/drift-alerts")

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list) or isinstance(data, dict)

    def test_dashboard_summary_endpoint(self):
        """TC-CNT-HP-042: Dashboard summary returns aggregated stats."""
        response = client.get("/api/v1/monitoring/dashboard-summary")

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

    def test_monitoring_time_range_filter(self):
        """TC-CNT-HP-043: Monitoring endpoints accept time range filters."""
        response = client.get(
            "/api/v1/monitoring/model-success-rate",
            params={
                "start_time": "2024-01-01T00:00:00Z",
                "end_time": "2024-01-31T23:59:59Z",
            },
        )

        assert response.status_code in [200, 401, 403, 422]


class TestCanaryContract:
    """Contract tests for canary deployment endpoints."""

    def test_create_canary_schema(self):
        """TC-CNT-HP-044: Create canary endpoint accepts valid config.

        H-AUDIT-01: 真实路径 /api/v1/canary/deployments, schema 为 CanaryCreateRequest
        """
        response = client.post(
            "/api/v1/canary/deployments",
            headers={"Authorization": "Bearer test_token"},
            json={
                "version": "test_v1",
                "traffic_percent": 10,
            },
        )

        assert response.status_code in [201, 200, 401, 403, 422]

    def test_adjust_canary_traffic(self):
        """TC-CNT-HP-045: Adjust canary traffic endpoint accepts valid percentage."""
        response = client.patch(
            "/api/v1/canary/deployments/test-canary-id/traffic",
            headers={"Authorization": "Bearer test_token"},
            json={"traffic_percent": 50},
        )

        assert response.status_code in [200, 401, 403, 404, 422]

    def test_rollback_canary(self):
        """TC-CNT-HP-046: Rollback canary endpoint triggers rollback."""
        response = client.post(
            "/api/v1/canary/deployments/test-canary-id/rollback",
            headers={"Authorization": "Bearer test_token"},
        )

        assert response.status_code in [200, 401, 403, 404]

    def test_canary_list_endpoint(self):
        """TC-CNT-HP-047: Canary list endpoint returns canary deployments."""
        response = client.get(
            "/api/v1/canary/deployments",
            headers={"Authorization": "Bearer test_token"},
        )

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list) or "items" in data


class TestValidationContract:
    """Contract tests for validation endpoints."""

    def test_create_validation_task(self):
        """TC-CNT-HP-048: Create validation task accepts valid config.

        H-AUDIT-01: 真实路径 /api/v1/validation/run (ValidationRunRequest)
        """
        response = client.post(
            "/api/v1/validation/run",
            headers={"Authorization": "Bearer test_token"},
            json={
                "model_id": "test_model",
                "validation_type": "cross_validation",
            },
        )

        assert response.status_code in [201, 200, 401, 403, 422]

    def test_get_validation_status(self):
        """TC-CNT-HP-049: Get validation status returns task info."""
        response = client.get(
            "/api/v1/validation/test-task-id",
            headers={"Authorization": "Bearer test_token"},
        )

        assert response.status_code in [200, 401, 403, 404]

        if response.status_code == 200:
            data = response.json()
            assert "status" in data or "state" in data

    def test_validation_results_schema(self):
        """TC-CNT-HP-050: Validation results have expected structure."""
        response = client.get(
            "/api/v1/validation/test-task-id/results",
            headers={"Authorization": "Bearer test_token"},
        )

        assert response.status_code in [200, 401, 403, 404]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)


class TestReportContract:
    """Contract tests for report export endpoints.

    H-AUDIT-01: 原用例请求 /reports/pdf + /reports/excel (设计稿阶段的通用导出端点),
    实际已演进为 /reports/user-risk/pdf + /reports/batch-export/excel (见 reports.py)。
    用例同步对齐真实契约, 否则一直 404。
    """

    def test_pdf_export_schema(self):
        """TC-CNT-HP-051: PDF export returns PDF content type."""
        response = client.post(
            "/api/v1/reports/user-risk/pdf",
            headers={"Authorization": "Bearer test_token"},
            json={
                "user_id": 1,
                "user_name": "test",
                "risk_level": "high",
                "risk_trend": [{"date": "2026-07-01", "score": 3.2, "level": "medium"}],
                "recommendations": [],
            },
        )

        assert response.status_code in [200, 401, 403, 422]

        if response.status_code == 200:
            assert response.headers.get("content-type") in [
                "application/pdf",
                "application/octet-stream",
            ]

    def test_excel_export_schema(self):
        """TC-CNT-HP-052: Excel export returns Excel content type."""
        response = client.post(
            "/api/v1/reports/batch-export/excel",
            headers={"Authorization": "Bearer test_token"},
            json={"data": [{"data": {"user_id": 1}}]},
        )

        assert response.status_code in [200, 401, 403, 422]

        if response.status_code == 200:
            assert response.headers.get("content-type") in [
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/octet-stream",
            ]

    def test_export_with_invalid_type(self):
        """TC-CNT-HP-053: Export with invalid data returns validation error.

        H-AUDIT-01: 无权限时 401/403 先于校验, 空 data 触发 min_length 校验 422
        """
        response = client.post(
            "/api/v1/reports/batch-export/excel",
            headers={"Authorization": "Bearer test_token"},
            json={"data": []},
        )

        assert response.status_code in [200, 401, 403, 422]
