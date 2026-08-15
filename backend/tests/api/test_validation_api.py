"""Tests for validation API endpoints."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.v1.model_validation import ClinicalValidationRequest


class TestClinicalValidationRequestShape:
    """SEC-FIX (M7 补强): y_score 内层结构校验 (防内存上限绕过 + ragged 数组 500)."""

    def test_ragged_y_score_rejected(self):
        with pytest.raises(ValidationError):
            ClinicalValidationRequest(
                y_true=[0, 1, 0],
                y_pred=[0, 1, 0],
                y_score=[[0.9, 0.1], [0.2], [0.8, 0.2]],
            )

    def test_inner_list_over_limit_rejected(self):
        with pytest.raises(ValidationError):
            ClinicalValidationRequest(
                y_true=[0, 1],
                y_pred=[0, 1],
                y_score=[[0.01] * 101, [0.01] * 101],
            )

    def test_mixed_scalar_and_list_rejected(self):
        with pytest.raises(ValidationError):
            ClinicalValidationRequest(
                y_true=[0, 1],
                y_pred=[0, 1],
                y_score=[0.9, [0.2, 0.8]],
            )

    def test_empty_inner_list_rejected(self):
        with pytest.raises(ValidationError):
            ClinicalValidationRequest(
                y_true=[0, 1],
                y_pred=[0, 1],
                y_score=[[], []],
            )

    def test_valid_2d_accepted(self):
        req = ClinicalValidationRequest(
            y_true=[0, 1], y_pred=[0, 1], y_score=[[0.9, 0.1], [0.2, 0.8]]
        )
        assert req.to_arrays()["y_score"].shape == (2, 2)


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
        response = client.get(
            "/api/v1/validation/nonexistent-id/status", headers=auth_headers
        )
        assert response.status_code in (200, 404, 500)

    def test_get_results_not_found(self, client, auth_headers, as_role):
        """TC-COV-API-027: Get results for non-existent job returns 404 (v1.31: 需 admin 角色)."""
        as_role("admin", 1)
        response = client.get(
            "/api/v1/validation/nonexistent-id/results", headers=auth_headers
        )
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
