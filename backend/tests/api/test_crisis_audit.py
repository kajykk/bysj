from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


class TestCrisisAuditAPI:
    """Tests for crisis audit log API endpoints."""

    def test_crisis_event_recorded_on_text_prediction(self, client: TestClient, as_role):
        """TC-CRISIS-HP-001: 检测到危机时自动记录危机事件"""
        as_role("user", 1)
        
        # 发送危机文本
        response = client.post(
            "/api/v1/model/predict/text",
            json={"text": "不想活了，想结束这一切。"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["crisis_detected"] is True

    def test_crisis_event_list_admin(self, client: TestClient, as_role):
        """TC-CRISIS-HP-004: 管理员可查询危机事件列表"""
        as_role("admin", 1)
        response = client.get("/api/v1/reviews/crisis-events")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "items" in data["data"]

    def test_crisis_event_list_user_forbidden(self, client: TestClient, as_role):
        """TC-CRISIS-SP-001: 普通用户不可查询危机事件"""
        as_role("user", 3)
        response = client.get("/api/v1/reviews/crisis-events")
        assert response.status_code == 403

    def test_crisis_event_stats_admin(self, client: TestClient, as_role):
        """管理员可查看危机事件统计"""
        as_role("admin", 1)
        response = client.get("/api/v1/reviews/crisis-events")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
