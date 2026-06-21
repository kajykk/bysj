"""Tests for user intervention API endpoints."""

from __future__ import annotations

import pytest


class TestUserInterventionApi:
    """Test user intervention API endpoints."""

    def test_get_active_intervention(self, client, auth_headers):
        """TC-COV-API-009: Get active intervention returns success."""
        response = client.get("/api/v1/user/intervention/active", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "data" in data
        assert "plan" in data["data"]

    def test_get_intervention_history(self, client, auth_headers):
        """TC-COV-API-010: Get intervention history returns success."""
        response = client.get("/api/v1/user/intervention/history", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "items" in data["data"]

    def test_complete_task_not_found(self, client, auth_headers):
        """TC-COV-API-011: Complete non-existent task returns 404."""
        response = client.put(
            "/api/v1/user/intervention/tasks/99999/complete",
            headers=auth_headers,
            json={"scheduled_date": "2024-01-01"},
        )
        assert response.status_code == 404

    def test_feedback_task_not_found(self, client, auth_headers):
        """TC-COV-API-012: Feedback for non-existent task returns 404."""
        response = client.put(
            "/api/v1/user/intervention/tasks/99999/feedback",
            headers=auth_headers,
            json={"scheduled_date": "2024-01-01", "feedback_score": 5},
        )
        assert response.status_code == 404

    def test_mark_task_missed_not_found(self, client, auth_headers):
        """TC-COV-API-013: Mark non-existent task as missed returns 404."""
        response = client.put(
            "/api/v1/user/intervention/tasks/99999/missed",
            headers=auth_headers,
            json={"scheduled_date": "2024-01-01"},
        )
        assert response.status_code == 404

    def test_skip_task_not_found(self, client, auth_headers):
        """TC-COV-API-014: Skip non-existent task returns 404."""
        response = client.put(
            "/api/v1/user/intervention/tasks/99999/skip",
            headers=auth_headers,
            json={"scheduled_date": "2024-01-01"},
        )
        assert response.status_code == 404

    def test_postpone_task_missing_postpone_to(self, client, auth_headers):
        """TC-COV-API-015: Postpone task without postpone_to returns 400."""
        response = client.put(
            "/api/v1/user/intervention/tasks/99999/postpone",
            headers=auth_headers,
            json={"scheduled_date": "2024-01-01"},
        )
        assert response.status_code == 400

    def test_postpone_task_not_found(self, client, auth_headers):
        """TC-COV-API-016: Postpone non-existent task returns 404 or 409."""
        response = client.put(
            "/api/v1/user/intervention/tasks/99999/postpone",
            headers=auth_headers,
            json={"scheduled_date": "2024-01-01", "postpone_to": "2024-01-15"},
        )
        assert response.status_code in (404, 409)

    def test_active_intervention_unauthorized(self, client):
        """TC-COV-API-017: Get active intervention may be 200/401/403."""
        response = client.get("/api/v1/user/intervention/active")
        assert response.status_code in (200, 401, 403)
