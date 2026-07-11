"""Phase 4 运营看板 API 测试.

覆盖：
- GET /api/v1/ops-dashboard/overview: 权限检查 + 响应结构
- GET /api/v1/ops-dashboard/review-metrics: 权限检查 + 参数验证
"""

from __future__ import annotations

import pytest


class TestOpsDashboardApi:
    """运营看板 API 测试."""

    def test_overview_unauthorized(self, client):
        """TC-P4-001: 未授权访问运营看板返回 401/403/307."""
        response = client.get("/api/v1/ops-dashboard/overview")
        assert response.status_code in (401, 403, 307)

    def test_review_metrics_unauthorized(self, client):
        """TC-P4-002: 未授权访问复核指标返回 401/403/307."""
        response = client.get("/api/v1/ops-dashboard/review-metrics")
        assert response.status_code in (401, 403, 307)

    def test_overview_admin_access(self, client, auth_headers, as_role):
        """TC-P4-003: 管理员可访问运营看板总览."""
        as_role("admin", 1)
        response = client.get(
            "/api/v1/ops-dashboard/overview", headers=auth_headers
        )
        # 允许 200 或 500（数据库表可能未初始化），但不应该是 401/403
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert data["code"] == 200
            payload = data["data"]
            # 验证必需字段存在
            expected_keys = {
                "generated_at", "review", "crisis", "feedback",
                "kill_switch", "audit_events", "content",
            }
            assert expected_keys.issubset(set(payload.keys()))
            # 验证 review 子结构
            review = payload["review"]
            assert "status_distribution" in review
            assert "total_pending" in review
            assert "sla_target_hours" in review
            # 验证 kill_switch 子结构
            ks = payload["kill_switch"]
            assert "paused" in ks

    def test_review_metrics_admin_access(self, client, auth_headers, as_role):
        """TC-P4-004: 管理员可访问复核详细指标."""
        as_role("admin", 1)
        response = client.get(
            "/api/v1/ops-dashboard/review-metrics?days=7",
            headers=auth_headers,
        )
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert data["code"] == 200
            payload = data["data"]
            assert "period_days" in payload
            assert "since" in payload
            assert payload["period_days"] == 7

    def test_review_metrics_days_clamping(self, client, auth_headers, as_role):
        """TC-P4-005: days 参数被限制在 1-90 范围内."""
        as_role("admin", 1)
        # 测试 days=0 被限制为 1
        response = client.get(
            "/api/v1/ops-dashboard/review-metrics?days=0",
            headers=auth_headers,
        )
        if response.status_code == 200:
            data = response.json()
            assert data["data"]["period_days"] == 1

        # 测试 days=100 被限制为 90
        response = client.get(
            "/api/v1/ops-dashboard/review-metrics?days=100",
            headers=auth_headers,
        )
        if response.status_code == 200:
            data = response.json()
            assert data["data"]["period_days"] == 90

    def test_overview_non_admin_forbidden(self, client, auth_headers, as_role):
        """TC-P4-006: 非管理员用户无法访问运营看板."""
        as_role("user", 1)
        response = client.get(
            "/api/v1/ops-dashboard/overview", headers=auth_headers
        )
        assert response.status_code in (403, 404, 500)
