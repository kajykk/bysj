from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.models.monitoring import MonitoringEventType


class TestMonitoringAPI:
    """T-BE-002: Monitoring API 路由单元测试"""

    def test_model_success_rate_endpoint_exists(self, client: TestClient) -> None:
        """验证模型成功率端点存在"""
        response = client.get("/api/v1/monitoring/model-success-rate?granularity=day")
        assert response.status_code in (200, 401, 403)

    def test_fallback_stats_endpoint_exists(self, client: TestClient) -> None:
        """验证回退统计端点存在"""
        response = client.get("/api/v1/monitoring/fallback-stats")
        assert response.status_code in (200, 401, 403)

    def test_drift_alerts_endpoint_exists(self, client: TestClient) -> None:
        """验证漂移告警端点存在"""
        response = client.get("/api/v1/monitoring/drift-alerts")
        assert response.status_code in (200, 401, 403)

    def test_dashboard_summary_endpoint_exists(self, client: TestClient) -> None:
        """验证仪表板摘要端点存在"""
        response = client.get("/api/v1/monitoring/dashboard-summary")
        assert response.status_code in (200, 401, 403)

    def test_request_details_endpoint_exists(self, client: TestClient) -> None:
        """验证请求详情端点存在"""
        response = client.get("/api/v1/monitoring/request-details")
        assert response.status_code in (200, 401, 403)

    def test_request_detail_by_id_endpoint_exists(self, client: TestClient) -> None:
        """验证单个请求详情端点存在"""
        response = client.get("/api/v1/monitoring/request-details/1")
        assert response.status_code in (200, 401, 403, 404)

    def test_model_success_rate_granularity_param(self, client: TestClient) -> None:
        """验证粒度参数被接受"""
        for gran in ["hour", "day", "week"]:
            response = client.get(f"/api/v1/monitoring/model-success-rate?granularity={gran}")
            assert response.status_code in (200, 401, 403)

    def test_drift_alerts_filter_params(self, client: TestClient) -> None:
        """验证漂移告警过滤参数被接受"""
        response = client.get("/api/v1/monitoring/drift-alerts?severity=HIGH&resolved=false")
        assert response.status_code in (200, 401, 403)

    def test_request_details_pagination_params(self, client: TestClient) -> None:
        """验证分页参数被接受"""
        response = client.get("/api/v1/monitoring/request-details?limit=10&offset=0")
        assert response.status_code in (200, 401, 403)

    def test_monitoring_router_prefix(self) -> None:
        """验证 monitoring router 前缀正确"""
        from app.api.v1.monitoring import router
        assert router.prefix == "/monitoring"

    def test_monitoring_router_tags(self) -> None:
        """验证 monitoring router 标签正确"""
        from app.api.v1.monitoring import router
        assert "monitoring" in router.tags
