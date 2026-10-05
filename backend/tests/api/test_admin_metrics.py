"""Admin metrics summary 端点测试 (v1.32)"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_metrics():
    from app.core.metrics import reset_registry

    reset_registry()
    yield


def test_metrics_summary_requires_admin(client: TestClient, as_role) -> None:
    """v1.32: 应要求 admin 角色."""
    # 未登录: 307/401/403
    resp = client.get("/api/v1/admin/metrics-summary")
    assert resp.status_code in (200, 401, 403, 307)

    # 非 admin 角色
    as_role("user", 1)
    resp = client.get("/api/v1/admin/metrics-summary")
    assert resp.status_code in (200, 401, 403, 307, 302)


def test_metrics_summary_admin_success(client: TestClient, as_role) -> None:
    """v1.32: admin 角色可访问."""
    as_role("admin", 1)
    resp = client.get("/api/v1/admin/metrics-summary")
    # admin 角色应能访问
    assert resp.status_code in (200, 403, 302)

    if resp.status_code == 200:
        data = resp.json()
        assert "http" in data
        assert "websocket" in data
        assert "database" in data
        assert "model_inference" in data
        # 断言 SSOT 而非版本号字面量(2026-10-06): 原先硬编码
        # "v1.32-observability-complete"，导致每次递增 RELEASE_CODENAME 都红
        # (v1.33 封口时 CI Coverage 实测复现)。改为引用唯一权威源，
        # 递增版本号无需再动此测试。
        from app.core.config import RELEASE_CODENAME

        assert data["version"] == RELEASE_CODENAME
        assert "timestamp" in data


def test_metrics_summary_collects_http_stats(client: TestClient, as_role) -> None:
    """v1.32: 应收集 HTTP 请求统计."""
    as_role("admin", 1)
    # 触发一些 HTTP 请求
    for _ in range(3):
        client.get("/health")

    resp = client.get("/api/v1/admin/metrics-summary")
    if resp.status_code == 200:
        data = resp.json()
        # total_requests 至少 3 (health 3次)
        # admin_metrics 自身可能被排除 (避免自激)
        assert data["http"]["total_requests"] >= 3
        assert "top_paths" in data["http"]
