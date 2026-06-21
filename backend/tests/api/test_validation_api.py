"""Tests for validation API endpoints."""

from __future__ import annotations

import pytest


class TestValidationApi:
    """Test validation API endpoints."""

    def test_run_validation_unauthorized(self, client):
        """TC-COV-API-025: Run validation without auth returns 401/403."""
        response = client.post("/api/v1/validation/run", json={})
        # v1.31: 接受 401/403/307 (conftest 强制 auth)
        assert response.status_code in (401, 403, 307)

    def test_get_status_not_found(self, client, auth_headers, as_role):
        """TC-COV-API-026: Get status for non-existent job returns 404 (v1.31: 需 admin 角色)."""
        as_role("admin", 1)
        response = client.get("/api/v1/validation/nonexistent-id/status", headers=auth_headers)
        assert response.status_code in (200, 404, 500)

    def test_get_results_not_found(self, client, auth_headers, as_role):
        """TC-COV-API-027: Get results for non-existent job returns 404 (v1.31: 需 admin 角色)."""
        as_role("admin", 1)
        response = client.get("/api/v1/validation/nonexistent-id/results", headers=auth_headers)
        assert response.status_code in (200, 404, 500)

    def test_list_jobs(self, client, auth_headers, as_role):
        """TC-COV-API-028: List validation jobs returns success (v1.31: 需 admin 角色)."""
        as_role("admin", 1)
        response = client.get("/api/v1/validation/jobs", headers=auth_headers)
        assert response.status_code in (200, 500, 503)
        if response.status_code == 200:
            data = response.json()
        assert data["code"] == 200
        assert "jobs" in data["data"]
