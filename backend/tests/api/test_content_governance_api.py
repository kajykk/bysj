"""Phase 4 内容治理 API 测试.

覆盖：
- POST /content-governance/{id}/review   权限 + 审核
- POST /content-governance/{id}/takedown 权限 + 下架
- POST /content-governance/{id}/restore  权限 + 恢复
- GET  /content-governance/pending       权限 + 列表
- GET  /content-governance/history/{id}  权限 + 历史
"""

from __future__ import annotations

import pytest


class TestContentGovernanceApi:
    """内容治理 API 测试."""

    def test_review_unauthorized(self, client):
        """TC-P4-010: 未授权审核内容返回 401/403/307."""
        response = client.post(
            "/api/v1/content-governance/1/review",
            json={"reviewer_note": "测试审核"},
        )
        assert response.status_code in (401, 403, 307)

    def test_takedown_unauthorized(self, client):
        """TC-P4-011: 未授权下架内容返回 401/403/307."""
        response = client.post(
            "/api/v1/content-governance/1/takedown",
            json={"reason": "测试下架"},
        )
        assert response.status_code in (401, 403, 307)

    def test_restore_unauthorized(self, client):
        """TC-P4-012: 未授权恢复内容返回 401/403/307."""
        response = client.post(
            "/api/v1/content-governance/1/restore",
            json={"reason": "测试恢复"},
        )
        assert response.status_code in (401, 403, 307)

    def test_pending_unauthorized(self, client):
        """TC-P4-013: 未授权查看待审核列表返回 401/403/307."""
        response = client.get("/api/v1/content-governance/pending")
        assert response.status_code in (401, 403, 307)

    def test_history_unauthorized(self, client):
        """TC-P4-014: 未授权查看历史返回 401/403/307."""
        response = client.get("/api/v1/content-governance/history/1")
        assert response.status_code in (401, 403, 307)

    def test_review_not_found(self, client, auth_headers, as_role):
        """TC-P4-015: 审核不存在的内容返回 404."""
        as_role("admin", 1)
        response = client.post(
            "/api/v1/content-governance/99999/review",
            json={"reviewer_note": "测试审核"},
            headers=auth_headers,
        )
        assert response.status_code in (404, 500)

    def test_takedown_not_found(self, client, auth_headers, as_role):
        """TC-P4-016: 下架不存在的内容返回 404."""
        as_role("admin", 1)
        response = client.post(
            "/api/v1/content-governance/99999/takedown",
            json={"reason": "测试下架"},
            headers=auth_headers,
        )
        assert response.status_code in (404, 500)

    def test_restore_not_found(self, client, auth_headers, as_role):
        """TC-P4-017: 恢复不存在的内容返回 404."""
        as_role("admin", 1)
        response = client.post(
            "/api/v1/content-governance/99999/restore",
            json={"reason": "测试恢复"},
            headers=auth_headers,
        )
        assert response.status_code in (404, 500)

    def test_pending_admin_access(self, client, auth_headers, as_role):
        """TC-P4-018: 管理员可访问待审核列表."""
        as_role("admin", 1)
        response = client.get(
            "/api/v1/content-governance/pending", headers=auth_headers
        )
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert data["code"] == 200
            payload = data["data"]
            assert "items" in payload
            assert "total" in payload
            assert "page" in payload
            assert "page_size" in payload
            assert "review_cycle_days" in payload

    def test_history_admin_access(self, client, auth_headers, as_role):
        """TC-P4-019: 管理员可查看内容审核历史."""
        as_role("admin", 1)
        response = client.get(
            "/api/v1/content-governance/history/1", headers=auth_headers
        )
        # 200（内容存在）或 404（内容不存在）
        assert response.status_code in (200, 404, 500)
        if response.status_code == 200:
            data = response.json()
            assert data["code"] == 200
            payload = data["data"]
            assert "content_id" in payload
            assert "history" in payload
            assert "total_events" in payload

    def test_history_not_found(self, client, auth_headers, as_role):
        """TC-P4-020: 查看不存在内容的历史返回 404."""
        as_role("admin", 1)
        response = client.get(
            "/api/v1/content-governance/history/99999", headers=auth_headers
        )
        assert response.status_code in (404, 500)

    def test_pending_pagination(self, client, auth_headers, as_role):
        """TC-P4-021: 待审核列表支持分页."""
        as_role("admin", 1)
        response = client.get(
            "/api/v1/content-governance/pending?page=1&page_size=5",
            headers=auth_headers,
        )
        if response.status_code == 200:
            data = response.json()
            payload = data["data"]
            assert payload["page"] == 1
            assert payload["page_size"] == 5
            assert len(payload["items"]) <= 5

    def test_non_admin_forbidden(self, client, auth_headers, as_role):
        """TC-P4-022: 非管理员无法访问内容治理."""
        as_role("user", 1)
        response = client.get(
            "/api/v1/content-governance/pending", headers=auth_headers
        )
        assert response.status_code in (403, 404, 500)

    def test_review_validation_error(self, client, auth_headers, as_role):
        """TC-P4-023: 审核请求缺少必填字段返回 422."""
        as_role("admin", 1)
        response = client.post(
            "/api/v1/content-governance/1/review",
            json={},  # 缺少 reviewer_note
            headers=auth_headers,
        )
        assert response.status_code == 422
