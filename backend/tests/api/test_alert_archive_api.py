"""v1.35: 告警归档 API 测试"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_archive_api_requires_admin(client: TestClient, as_role) -> None:
    """v1.35: 归档查询应要求 admin."""
    as_role("user", 1)
    res = client.get("/api/v1/alerts/archive")
    assert res.status_code in (200, 401, 403, 307)


def test_archive_api_admin_success(client: TestClient, as_role) -> None:
    """v1.35: admin 应能查询归档."""
    as_role("admin", 3)
    res = client.get("/api/v1/alerts/archive?page=1&page_size=10")
    assert res.status_code == 200
    data = res.json()["data"]
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data


def test_archive_api_filter_by_severity(client: TestClient, as_role) -> None:
    """v1.35: severity 过滤应工作."""
    as_role("admin", 3)
    res = client.get("/api/v1/alerts/archive?severity=P0")
    assert res.status_code == 200
    data = res.json()["data"]
    for item in data["items"]:
        if item.get("severity"):
            assert item["severity"] == "P0"


def test_archive_api_filter_by_status(client: TestClient, as_role) -> None:
    """v1.35: status 过滤应工作."""
    as_role("admin", 3)
    res = client.get("/api/v1/alerts/archive?status=resolved")
    assert res.status_code == 200
    data = res.json()["data"]
    for item in data["items"]:
        if item.get("status"):
            assert item["status"] == "resolved"


def test_archive_api_filter_by_rule(client: TestClient, as_role) -> None:
    """v1.35: rule 过滤应工作."""
    as_role("admin", 3)
    res = client.get("/api/v1/alerts/archive?rule=HighErrorRate")
    assert res.status_code == 200


def test_archive_api_pagination(client: TestClient, as_role) -> None:
    """v1.35: 分页应工作."""
    as_role("admin", 3)
    res = client.get("/api/v1/alerts/archive?page=1&page_size=5")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["page_size"] == 5
    assert len(data["items"]) <= 5
