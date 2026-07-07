from __future__ import annotations

from fastapi.testclient import TestClient


class TestReviewAPI:
    """Tests for Review API endpoints."""

    def test_list_reviews_admin(self, client: TestClient, as_role):
        """TC-API-REVIEW-HP-003: 管理员可查看全部复核任务"""
        as_role("admin", 1)
        response = client.get("/api/v1/reviews")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "items" in data["data"]

    def test_list_reviews_counselor(self, client: TestClient, as_role):
        """TC-API-REVIEW-HP-001: 咨询师可查看分配的复核任务"""
        as_role("counselor", 2)
        response = client.get("/api/v1/reviews")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "items" in data["data"]

    def test_list_reviews_user_forbidden(self, client: TestClient, as_role):
        """TC-API-REVIEW-SP-001: 普通用户不可查看复核任务"""
        as_role("user", 3)
        response = client.get("/api/v1/reviews")
        assert response.status_code == 403

    def test_list_reviews_unauthorized(self, client: TestClient):
        """TC-API-REVIEW-SP-003: 未登录用户返回 401/403"""
        # 由于测试环境覆盖了 get_current_user，无法测试真正的 401
        # 这里测试无权限访问
        response = client.get("/api/v1/reviews")
        # 在测试环境中，默认角色是 user，会返回 403
        assert response.status_code in [401, 403]

    def test_review_stats_admin(self, client: TestClient, as_role):
        """管理员可查看复核统计"""
        as_role("admin", 1)
        response = client.get("/api/v1/reviews/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "total" in data["data"]

    def test_crisis_events_admin(self, client: TestClient, as_role):
        """TC-CRISIS-HP-004: 管理员可查询危机事件"""
        as_role("admin", 1)
        response = client.get("/api/v1/reviews/crisis-events")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "items" in data["data"]

    def test_crisis_events_user_forbidden(self, client: TestClient, as_role):
        """TC-CRISIS-SP-001: 普通用户不可查询危机事件"""
        as_role("user", 3)
        response = client.get("/api/v1/reviews/crisis-events")
        assert response.status_code == 403
