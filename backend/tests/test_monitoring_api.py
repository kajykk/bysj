from __future__ import annotations

from fastapi.testclient import TestClient


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
            response = client.get(
                f"/api/v1/monitoring/model-success-rate?granularity={gran}"
            )
            assert response.status_code in (200, 401, 403)

    def test_drift_alerts_filter_params(self, client: TestClient) -> None:
        """验证漂移告警过滤参数被接受"""
        response = client.get(
            "/api/v1/monitoring/drift-alerts?severity=HIGH&resolved=false"
        )
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


class TestFrontendMetricsEndpoint:
    """P3-2: 前端 Web Vitals 上报端点测试"""

    def test_valid_payload_returns_204(self, client: TestClient) -> None:
        """完整 Web Vitals 负载应返回 204"""
        payload = {
            "fcp": 1800.5,
            "lcp": 3200.0,
            "inp": 120,
            "cls": 0.05,
            "ttfb": 150,
            "pageLoadTime": 2800,
            "domReadyTime": 1200,
            "resourceCount": 50,
            "resourceSize": 500000,
            "url": "http://localhost:5173/user/dashboard",
            "timestamp": 1719609600000,
            "userAgent": "Mozilla/5.0",
        }
        response = client.post(
            "/api/v1/monitoring/frontend-metrics",
            json=payload,
        )
        assert response.status_code == 204

    def test_minimal_payload_returns_204(self, client: TestClient) -> None:
        """仅必填字段的负载应返回 204"""
        payload = {
            "url": "http://localhost:5173/",
            "timestamp": 1719609600000,
            "userAgent": "Mozilla/5.0",
        }
        response = client.post(
            "/api/v1/monitoring/frontend-metrics",
            json=payload,
        )
        assert response.status_code == 204

    def test_no_auth_required(self, client: TestClient) -> None:
        """端点应无需鉴权 (Web Vitals 需从匿名用户采集)"""
        payload = {
            "url": "http://localhost:5173/login",
            "timestamp": 1719609600000,
            "userAgent": "Mozilla/5.0",
        }
        response = client.post(
            "/api/v1/monitoring/frontend-metrics",
            json=payload,
            # 不携带任何 auth header
        )
        assert response.status_code == 204

    def test_missing_required_url_returns_400(self, client: TestClient) -> None:
        """缺少必填 url 字段应返回 400"""
        payload = {
            "timestamp": 1719609600000,
            "userAgent": "Mozilla/5.0",
        }
        response = client.post(
            "/api/v1/monitoring/frontend-metrics",
            json=payload,
        )
        assert response.status_code == 400

    def test_missing_required_user_agent_returns_400(self, client: TestClient) -> None:
        """缺少必填 userAgent 字段应返回 400"""
        payload = {
            "url": "http://localhost:5173/",
            "timestamp": 1719609600000,
        }
        response = client.post(
            "/api/v1/monitoring/frontend-metrics",
            json=payload,
        )
        assert response.status_code == 400

    def test_invalid_json_returns_400(self, client: TestClient) -> None:
        """无效 JSON 应返回 400"""
        response = client.post(
            "/api/v1/monitoring/frontend-metrics",
            data="not-json{",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

    def test_empty_body_returns_204(self, client: TestClient) -> None:
        """空 body 应优雅返回 204 (sendBeacon 可能发送空负载)"""
        response = client.post(
            "/api/v1/monitoring/frontend-metrics",
            content=b"",
        )
        assert response.status_code == 204

    def test_invalid_metrics_value_returns_400(self, client: TestClient) -> None:
        """指标值超出合理范围应返回 400"""
        payload = {
            "fcp": -100,  # 负值不合法
            "url": "http://localhost:5173/",
            "timestamp": 1719609600000,
            "userAgent": "Mozilla/5.0",
        }
        response = client.post(
            "/api/v1/monitoring/frontend-metrics",
            json=payload,
        )
        assert response.status_code == 400

    def test_non_dict_payload_returns_400(self, client: TestClient) -> None:
        """非对象 JSON 应返回 400"""
        response = client.post(
            "/api/v1/monitoring/frontend-metrics",
            json=[1, 2, 3],
        )
        assert response.status_code == 400

    def test_extra_fields_ignored(self, client: TestClient) -> None:
        """额外字段应被忽略 (extra=ignore)"""
        payload = {
            "url": "http://localhost:5173/",
            "timestamp": 1719609600000,
            "userAgent": "Mozilla/5.0",
            "unknownField": "should be ignored",
            "anotherExtra": 42,
        }
        response = client.post(
            "/api/v1/monitoring/frontend-metrics",
            json=payload,
        )
        assert response.status_code == 204
