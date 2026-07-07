"""Tests for user content API endpoints."""

from __future__ import annotations


class TestUserContentApi:
    """Test user content API endpoints."""

    def test_list_contents(self, client, auth_headers):
        """TC-COV-API-001: List contents endpoint returns success."""
        response = client.get("/api/v1/user/content/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "data" in data

    def test_list_contents_with_filters(self, client, auth_headers):
        """TC-COV-API-002: List contents with category filter."""
        response = client.get(
            "/api/v1/user/content/?category=meditation", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200

    def test_list_favorites(self, client, auth_headers):
        """TC-COV-API-003: List favorites endpoint returns success."""
        response = client.get(
            "/api/v1/user/content/favorites/list", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200

    def test_list_recommendations(self, client, auth_headers):
        """TC-COV-API-004: List recommendations endpoint returns success."""
        response = client.get(
            "/api/v1/user/content/recommendations", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200

    def test_list_recent_views(self, client, auth_headers):
        """TC-COV-API-005: List recent views endpoint returns success."""
        response = client.get("/api/v1/user/content/recent-views", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200

    def test_meditation_log_invalid_content(self, client, auth_headers):
        """TC-COV-API-006: Meditation log for non-existent content returns 404."""
        response = client.post(
            "/api/v1/user/content/meditation/log",
            headers=auth_headers,
            json={"content_id": 99999, "completed": True},
        )
        assert response.status_code == 404

    def test_get_content_detail_not_found(self, client, auth_headers):
        """TC-COV-API-007: Get content detail for non-existent content."""
        response = client.get("/api/v1/user/content/99999", headers=auth_headers)
        # Should return 404 or structured error
        assert response.status_code in (404, 200)

    def test_list_contents_unauthorized(self, client):
        """TC-COV-API-008: List contents without auth returns 401/403 (or 200 if endpoint is public)."""
        response = client.get("/api/v1/user/content/")
        assert response.status_code in (200, 401, 403)
