"""Phase 5 租户级审计查询 API 测试.

覆盖：
- GET /tenant-audit/logs          查询当前租户审计日志
- GET /tenant-audit/logs/{id}     管理员查询指定租户审计日志
"""

from __future__ import annotations

import pytest


class TestTenantAuditApi:
    """租户级审计查询 API 测试."""

    def test_list_logs_unauthorized(self, client):
        """TC-P5-072: 未授权查询审计日志返回 401/403/307."""
        response = client.get("/api/v1/tenant-audit/logs")
        assert response.status_code in (401, 403, 307)

    def test_list_logs_non_admin_forbidden(self, client, auth_headers, as_role):
        """TC-P5-073: 非管理员查询审计日志返回 403."""
        as_role("user", 1)
        response = client.get("/api/v1/tenant-audit/logs", headers=auth_headers)
        assert response.status_code in (403, 307)

    def test_list_logs_admin_success(self, client, auth_headers, as_role):
        """TC-P5-074: 管理员查询当前租户审计日志成功."""
        as_role("admin", 1)
        # 创建一个租户会生成一条审计日志
        client.post(
            "/api/v1/tenants",
            json={"name": "审计测试", "code": "audit_test"},
            headers=auth_headers,
        )

        response = client.get("/api/v1/tenant-audit/logs", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert "items" in data
        assert "total" in data
        assert "tenant_id" in data

    def test_list_logs_with_pagination(self, client, auth_headers, as_role):
        """TC-P5-075: 审计日志分页."""
        as_role("admin", 1)
        response = client.get(
            "/api/v1/tenant-audit/logs?page=1&page_size=5",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["page"] == 1
        assert data["page_size"] == 5

    def test_list_logs_action_type_filter(self, client, auth_headers, as_role):
        """TC-P5-076: 按动作类型过滤审计日志."""
        as_role("admin", 1)
        # 创建租户（生成 tenant.create 日志）
        client.post(
            "/api/v1/tenants",
            json={"name": "过滤测试", "code": "filter_test"},
            headers=auth_headers,
        )

        response = client.get(
            "/api/v1/tenant-audit/logs?action_type=tenant.create",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        for item in data["items"]:
            assert item["action_type"] == "tenant.create"

    def test_list_logs_by_tenant_id_unauthorized(self, client):
        """TC-P5-077: 未授权查询指定租户审计日志返回 401/403/307."""
        response = client.get("/api/v1/tenant-audit/logs/1")
        assert response.status_code in (401, 403, 307)

    def test_list_logs_by_tenant_id_not_found(self, client, auth_headers, as_role):
        """TC-P5-078: 查询不存在租户的审计日志返回 404."""
        as_role("admin", 1)
        response = client.get(
            "/api/v1/tenant-audit/logs/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_list_logs_by_tenant_id_admin_success(self, client, auth_headers, as_role):
        """TC-P5-079: 管理员查询指定租户审计日志成功."""
        as_role("admin", 1)
        # 先创建租户
        create_resp = client.post(
            "/api/v1/tenants",
            json={"name": "指定租户", "code": "specific_tenant"},
            headers=auth_headers,
        )
        tenant_id = create_resp.json()["data"]["id"]

        # 查询该租户审计日志
        response = client.get(
            f"/api/v1/tenant-audit/logs/{tenant_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["tenant_id"] == tenant_id
        assert "tenant_name" in data
        assert "tenant_code" in data

    def test_list_logs_by_tenant_id_with_pagination(self, client, auth_headers, as_role):
        """TC-P5-080: 指定租户审计日志分页."""
        as_role("admin", 1)
        # 先创建租户
        create_resp = client.post(
            "/api/v1/tenants",
            json={"name": "分页租户", "code": "paginated_tenant"},
            headers=auth_headers,
        )
        tenant_id = create_resp.json()["data"]["id"]

        response = client.get(
            f"/api/v1/tenant-audit/logs/{tenant_id}?page=1&page_size=10",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["page"] == 1
        assert data["page_size"] == 10
