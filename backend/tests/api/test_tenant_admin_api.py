"""Phase 5 租户管理 API 测试.

覆盖：
- POST   /tenants              创建租户（权限 + 唯一性 + 验证）
- GET    /tenants              列出租户（权限 + 分页 + 过滤）
- GET    /tenants/{id}         获取详情（权限 + 404）
- PUT    /tenants/{id}         更新租户（权限 + 404 + 无字段）
- POST   /tenants/{id}/suspend 暂停租户（权限 + 409 + 404）
- POST   /tenants/{id}/activate 激活租户（权限 + 409 + 404）
- GET    /tenants/{id}/stats   租户统计（权限 + 404）
"""

from __future__ import annotations

import pytest


class TestTenantAdminApi:
    """租户管理 API 测试."""

    # ── 未授权测试 ──

    def test_create_tenant_unauthorized(self, client):
        """TC-P5-043: 未授权创建租户返回 401/403/307."""
        response = client.post(
            "/api/v1/tenants",
            json={"name": "测试租户", "code": "test_tenant"},
        )
        assert response.status_code in (401, 403, 307)

    def test_list_tenants_unauthorized(self, client):
        """TC-P5-044: 未授权列出租户返回 401/403/307."""
        response = client.get("/api/v1/tenants")
        assert response.status_code in (401, 403, 307)

    def test_get_tenant_unauthorized(self, client):
        """TC-P5-045: 未授权获取租户详情返回 401/403/307."""
        response = client.get("/api/v1/tenants/1")
        assert response.status_code in (401, 403, 307)

    def test_update_tenant_unauthorized(self, client):
        """TC-P5-046: 未授权更新租户返回 401/403/307."""
        response = client.put(
            "/api/v1/tenants/1",
            json={"name": "更新名称"},
        )
        assert response.status_code in (401, 403, 307)

    def test_suspend_tenant_unauthorized(self, client):
        """TC-P5-047: 未授权暂停租户返回 401/403/307."""
        response = client.post(
            "/api/v1/tenants/1/suspend",
            json={"reason": "测试暂停"},
        )
        assert response.status_code in (401, 403, 307)

    def test_activate_tenant_unauthorized(self, client):
        """TC-P5-048: 未授权激活租户返回 401/403/307."""
        response = client.post(
            "/api/v1/tenants/1/activate",
            json={"reason": "测试激活"},
        )
        assert response.status_code in (401, 403, 307)

    def test_tenant_stats_unauthorized(self, client):
        """TC-P5-049: 未授权查看租户统计返回 401/403/307."""
        response = client.get("/api/v1/tenants/1/stats")
        assert response.status_code in (401, 403, 307)

    # ── 非管理员测试 ──

    def test_create_tenant_non_admin_forbidden(self, client, auth_headers, as_role):
        """TC-P5-050: 非管理员创建租户返回 403."""
        as_role("user", 1)
        response = client.post(
            "/api/v1/tenants",
            json={"name": "测试租户", "code": "test_tenant"},
            headers=auth_headers,
        )
        assert response.status_code in (403, 307)

    def test_list_tenants_non_admin_forbidden(self, client, auth_headers, as_role):
        """TC-P5-051: 非管理员列出租户返回 403."""
        as_role("user", 1)
        response = client.get("/api/v1/tenants", headers=auth_headers)
        assert response.status_code in (403, 307)

    # ── 管理员测试 ──

    def test_create_tenant_admin_success(self, client, auth_headers, as_role):
        """TC-P5-052: 管理员创建租户成功."""
        as_role("admin", 1)
        response = client.post(
            "/api/v1/tenants",
            json={
                "name": "测试大学",
                "code": "test_univ",
                "config": {"brand_color": "#1a73e8"},
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "测试大学"
        assert data["code"] == "test_univ"
        assert data["status"] == "active"
        assert data["config"]["brand_color"] == "#1a73e8"

    def test_create_tenant_duplicate_code_conflict(self, client, auth_headers, as_role):
        """TC-P5-053: 重复租户编码返回 409."""
        as_role("admin", 1)
        # 第一次创建
        client.post(
            "/api/v1/tenants",
            json={"name": "大学A", "code": "dup_code"},
            headers=auth_headers,
        )
        # 第二次创建同 code
        response = client.post(
            "/api/v1/tenants",
            json={"name": "大学B", "code": "dup_code"},
            headers=auth_headers,
        )
        assert response.status_code == 409

    def test_create_tenant_invalid_code_format(self, client, auth_headers, as_role):
        """TC-P5-054: 无效租户编码格式返回 422."""
        as_role("admin", 1)
        response = client.post(
            "/api/v1/tenants",
            json={"name": "测试", "code": "Invalid Code!"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_create_tenant_missing_fields(self, client, auth_headers, as_role):
        """TC-P5-055: 缺少必填字段返回 422."""
        as_role("admin", 1)
        response = client.post(
            "/api/v1/tenants",
            json={"name": "测试"},  # 缺少 code
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_list_tenants_admin_success(self, client, auth_headers, as_role):
        """TC-P5-056: 管理员列出租户成功."""
        as_role("admin", 1)
        # 创建几个租户
        for i in range(3):
            client.post(
                "/api/v1/tenants",
                json={"name": f"租户{i}", "code": f"list_t_{i}"},
                headers=auth_headers,
            )

        response = client.get("/api/v1/tenants", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 3

    def test_list_tenants_with_pagination(self, client, auth_headers, as_role):
        """TC-P5-057: 租户列表分页."""
        as_role("admin", 1)
        response = client.get(
            "/api/v1/tenants?page=1&page_size=2",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["page"] == 1
        assert data["page_size"] == 2

    def test_list_tenants_status_filter(self, client, auth_headers, as_role):
        """TC-P5-058: 按状态过滤租户列表."""
        as_role("admin", 1)
        response = client.get(
            "/api/v1/tenants?status=active",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        for item in data["items"]:
            assert item["status"] == "active"

    def test_get_tenant_not_found(self, client, auth_headers, as_role):
        """TC-P5-059: 获取不存在的租户返回 404."""
        as_role("admin", 1)
        response = client.get(
            "/api/v1/tenants/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_get_tenant_admin_success(self, client, auth_headers, as_role):
        """TC-P5-060: 管理员获取租户详情成功."""
        as_role("admin", 1)
        # 先创建
        create_resp = client.post(
            "/api/v1/tenants",
            json={"name": "详情测试", "code": "detail_test"},
            headers=auth_headers,
        )
        tenant_id = create_resp.json()["data"]["id"]

        # 再查询
        response = client.get(
            f"/api/v1/tenants/{tenant_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "详情测试"
        assert data["code"] == "detail_test"

    def test_update_tenant_admin_success(self, client, auth_headers, as_role):
        """TC-P5-061: 管理员更新租户成功."""
        as_role("admin", 1)
        # 先创建
        create_resp = client.post(
            "/api/v1/tenants",
            json={"name": "更新前", "code": "update_test"},
            headers=auth_headers,
        )
        tenant_id = create_resp.json()["data"]["id"]

        # 更新
        response = client.put(
            f"/api/v1/tenants/{tenant_id}",
            json={"name": "更新后", "config": {"theme": "dark"}},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "更新后"
        assert data["config"]["theme"] == "dark"

    def test_update_tenant_not_found(self, client, auth_headers, as_role):
        """TC-P5-062: 更新不存在的租户返回 404."""
        as_role("admin", 1)
        response = client.put(
            "/api/v1/tenants/99999",
            json={"name": "不存在"},
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_update_tenant_no_fields(self, client, auth_headers, as_role):
        """TC-P5-063: 未提供更新字段返回 400."""
        as_role("admin", 1)
        # 先创建
        create_resp = client.post(
            "/api/v1/tenants",
            json={"name": "无更新", "code": "no_update"},
            headers=auth_headers,
        )
        tenant_id = create_resp.json()["data"]["id"]

        # 空更新
        response = client.put(
            f"/api/v1/tenants/{tenant_id}",
            json={},
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_suspend_tenant_admin_success(self, client, auth_headers, as_role):
        """TC-P5-064: 管理员暂停租户成功."""
        as_role("admin", 1)
        # 先创建
        create_resp = client.post(
            "/api/v1/tenants",
            json={"name": "暂停测试", "code": "suspend_test"},
            headers=auth_headers,
        )
        tenant_id = create_resp.json()["data"]["id"]

        # 暂停
        response = client.post(
            f"/api/v1/tenants/{tenant_id}/suspend",
            json={"reason": "测试暂停"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "suspended"
        assert data["reason"] == "测试暂停"

    def test_suspend_tenant_already_suspended(self, client, auth_headers, as_role):
        """TC-P5-065: 暂停已暂停的租户返回 409."""
        as_role("admin", 1)
        # 先创建
        create_resp = client.post(
            "/api/v1/tenants",
            json={"name": "重复暂停", "code": "double_suspend"},
            headers=auth_headers,
        )
        tenant_id = create_resp.json()["data"]["id"]

        # 第一次暂停
        client.post(
            f"/api/v1/tenants/{tenant_id}/suspend",
            json={"reason": "第一次暂停"},
            headers=auth_headers,
        )

        # 第二次暂停
        response = client.post(
            f"/api/v1/tenants/{tenant_id}/suspend",
            json={"reason": "第二次暂停"},
            headers=auth_headers,
        )
        assert response.status_code == 409

    def test_activate_tenant_admin_success(self, client, auth_headers, as_role):
        """TC-P5-066: 管理员激活租户成功."""
        as_role("admin", 1)
        # 先创建
        create_resp = client.post(
            "/api/v1/tenants",
            json={"name": "激活测试", "code": "activate_test"},
            headers=auth_headers,
        )
        tenant_id = create_resp.json()["data"]["id"]

        # 先暂停
        client.post(
            f"/api/v1/tenants/{tenant_id}/suspend",
            json={"reason": "暂停"},
            headers=auth_headers,
        )

        # 再激活
        response = client.post(
            f"/api/v1/tenants/{tenant_id}/activate",
            json={"reason": "恢复运营"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "active"

    def test_activate_tenant_already_active(self, client, auth_headers, as_role):
        """TC-P5-067: 激活已活跃的租户返回 409."""
        as_role("admin", 1)
        # 先创建（默认 active）
        create_resp = client.post(
            "/api/v1/tenants",
            json={"name": "已活跃", "code": "already_active"},
            headers=auth_headers,
        )
        tenant_id = create_resp.json()["data"]["id"]

        # 尝试激活
        response = client.post(
            f"/api/v1/tenants/{tenant_id}/activate",
            json={"reason": "重复激活"},
            headers=auth_headers,
        )
        assert response.status_code == 409

    def test_tenant_stats_admin_success(self, client, auth_headers, as_role):
        """TC-P5-068: 管理员查看租户统计成功."""
        as_role("admin", 1)
        # 先创建
        create_resp = client.post(
            "/api/v1/tenants",
            json={"name": "统计测试", "code": "stats_test"},
            headers=auth_headers,
        )
        tenant_id = create_resp.json()["data"]["id"]

        response = client.get(
            f"/api/v1/tenants/{tenant_id}/stats",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert "user_count" in data
        assert "audit_log_count_30d" in data

    def test_tenant_stats_not_found(self, client, auth_headers, as_role):
        """TC-P5-069: 查看不存在的租户统计返回 404."""
        as_role("admin", 1)
        response = client.get(
            "/api/v1/tenants/99999/stats",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_suspend_tenant_not_found(self, client, auth_headers, as_role):
        """TC-P5-070: 暂停不存在的租户返回 404."""
        as_role("admin", 1)
        response = client.post(
            "/api/v1/tenants/99999/suspend",
            json={"reason": "不存在"},
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_activate_tenant_not_found(self, client, auth_headers, as_role):
        """TC-P5-071: 激活不存在的租户返回 404."""
        as_role("admin", 1)
        response = client.post(
            "/api/v1/tenants/99999/activate",
            json={"reason": "不存在"},
            headers=auth_headers,
        )
        assert response.status_code == 404
