"""Tests for canary API endpoints."""

from __future__ import annotations

import pytest


class TestCanaryApi:
    """Test canary API endpoints."""

    def test_list_canaries_unauthorized(self, client):
        """TC-COV-API-033: List canaries without auth returns 401."""
        response = client.get("/api/v1/canary/deployments")
        assert response.status_code in (401, 403)

    def test_get_canary_not_found(self, client, auth_headers, as_role):
        """TC-COV-API-034: Get non-existent canary returns 404 (admin) or 403 (non-admin)."""
        as_role("admin")
        response = client.get("/api/v1/canary/deployments/99999", headers=auth_headers)
        assert response.status_code in (403, 404)

    def test_create_canary_unauthorized(self, client):
        """TC-COV-API-035: Create canary without auth returns 401."""
        response = client.post("/api/v1/canary/deployments", json={})
        assert response.status_code in (401, 403)

    def test_update_traffic_unauthorized(self, client):
        """TC-COV-API-036: Update traffic without auth returns 401."""
        response = client.patch("/api/v1/canary/deployments/1/traffic", json={})
        assert response.status_code in (401, 403)

    def test_pause_canary_unauthorized(self, client):
        """TC-COV-API-037: Pause canary without auth returns 401."""
        response = client.post("/api/v1/canary/deployments/1/pause")
        assert response.status_code in (401, 403)

    def test_resume_canary_unauthorized(self, client):
        """TC-COV-API-038: Resume canary without auth returns 401."""
        response = client.post("/api/v1/canary/deployments/1/resume")
        assert response.status_code in (401, 403)

    def test_rollback_canary_unauthorized(self, client):
        """TC-COV-API-039: Rollback canary without auth returns 401."""
        response = client.post("/api/v1/canary/deployments/1/rollback", json={})
        assert response.status_code in (401, 403)

    def test_get_canary_unauthorized(self, client):
        """TC-COV-API-040: Get canary without auth returns 401."""
        response = client.get("/api/v1/canary/deployments/1")
        assert response.status_code in (401, 403)
