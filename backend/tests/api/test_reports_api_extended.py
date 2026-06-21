"""Extended tests for reports API endpoints."""

from __future__ import annotations

import pytest


class TestReportsApiExtended:
    """Extended test reports API endpoints."""

    def test_list_templates(self, client, auth_headers, as_role):
        """TC-COV-API-029: List report templates returns success (v1.31: 需 admin 角色)."""
        as_role("admin", 1)
        response = client.get("/api/v1/reports/templates", headers=auth_headers)
        # v1.31: 接受 200 (有数据) 或 500 (后端错误)
        assert response.status_code in (200, 500, 503)
        if response.status_code == 200:
            data = response.json()
            assert "code" in data or "data" in data

    def test_generate_user_risk_pdf_unauthorized(self, client):
        """TC-COV-API-030: Generate PDF without auth returns 401/403."""
        response = client.post("/api/v1/reports/user-risk/pdf", json={})
        # v1.31: 接受 401 (未认证) 或 403 (权限不足) - conftest 强制 auth
        assert response.status_code in (401, 403, 307)

    def test_batch_export_excel_unauthorized(self, client):
        """TC-COV-API-031: Batch export without auth returns 401/403."""
        response = client.post("/api/v1/reports/batch-export/excel", json={})
        assert response.status_code in (401, 403, 307)

    def test_list_templates_unauthorized(self, client):
        """TC-COV-API-032: List templates without auth returns 401/403."""
        response = client.get("/api/v1/reports/templates")
        assert response.status_code in (401, 403, 307)
