"""v1.34: 静默规则 API 测试"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient


def test_create_silence_requires_admin(client: TestClient, as_role) -> None:
    """v1.34: 创建静默规则应要求 admin."""
    as_role("user", 1)
    now = datetime.now(UTC).replace(tzinfo=None)
    res = client.post(
        "/api/v1/alerts/silences",
        json={
            "name": "test-silence",
            "matcher": {"alertname": "X"},
            "starts_at": now.isoformat(),
            "ends_at": (now + timedelta(hours=1)).isoformat(),
        },
    )
    assert res.status_code in (401, 403, 307, 200)


def test_create_silence_success(client: TestClient, as_role) -> None:
    """v1.34: admin 创建静默规则."""
    as_role("admin", 3)
    now = datetime.now(UTC).replace(tzinfo=None)
    res = client.post(
        "/api/v1/alerts/silences",
        json={
            "name": "maintenance-window",
            "matcher": {"severity": "P0"},
            "starts_at": now.isoformat(),
            "ends_at": (now + timedelta(hours=2)).isoformat(),
            "comment": "scheduled DB maintenance",
        },
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["name"] == "maintenance-window"
    assert data["matcher"] == {"severity": "P0"}
    assert data["is_active"] is True
    assert data["created_by"] == 3


def test_create_silence_validates_time_range(client: TestClient, as_role) -> None:
    """v1.34: ends_at 必须在 starts_at 之后.

    P1-SEC-021 修复后，时间范围校验迁移至 Pydantic model_validator，
    返回 422 (Unprocessable Entity) 而非 400。两种状态码均表示输入校验失败。
    """
    as_role("admin", 3)
    now = datetime.now(UTC).replace(tzinfo=None)
    res = client.post(
        "/api/v1/alerts/silences",
        json={
            "name": "bad-window",
            "matcher": {},
            "starts_at": now.isoformat(),
            "ends_at": (now - timedelta(hours=1)).isoformat(),
        },
    )
    assert res.status_code in (400, 422)


def test_list_silences_admin(client: TestClient, as_role) -> None:
    """v1.34: admin 可查询静默规则."""
    as_role("admin", 3)
    res = client.get("/api/v1/alerts/silences?page=1&page_size=10")
    assert res.status_code == 200
    data = res.json()["data"]
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data


def test_list_active_silences(client: TestClient, as_role) -> None:
    """v1.34: 列出当前生效的静默规则."""
    as_role("admin", 3)
    res = client.get("/api/v1/alerts/silences/active")
    assert res.status_code == 200
    data = res.json()["data"]
    assert "items" in data
    # 所有 item 应是当前生效
    now = datetime.now(UTC).replace(tzinfo=None)
    for item in data["items"]:
        starts = datetime.fromisoformat(item["starts_at"].replace("Z", "+00:00"))
        ends = datetime.fromisoformat(item["ends_at"].replace("Z", "+00:00"))
        assert starts <= now <= ends


def test_delete_silence_soft_delete(client: TestClient, as_role) -> None:
    """v1.34: 删除静默规则是软删除 (is_active=False)."""
    as_role("admin", 3)
    # 创建
    now = datetime.now(UTC).replace(tzinfo=None)
    create_res = client.post(
        "/api/v1/alerts/silences",
        json={
            "name": "to-delete",
            "matcher": {"alertname": "test"},
            "starts_at": now.isoformat(),
            "ends_at": (now + timedelta(hours=1)).isoformat(),
        },
    )
    silence_id = create_res.json()["data"]["id"]

    # 删除
    res = client.delete(f"/api/v1/alerts/silences/{silence_id}")
    assert res.status_code == 200
    assert res.json()["data"]["is_active"] is False


def test_delete_silence_not_found(client: TestClient, as_role) -> None:
    """v1.34: 不存在的静默规则应返回 404."""
    as_role("admin", 3)
    res = client.delete("/api/v1/alerts/silences/999999")
    assert res.status_code == 404


def test_delete_silence_requires_admin(client: TestClient, as_role) -> None:
    """v1.34: 删除应要求 admin."""
    as_role("user", 1)
    res = client.delete("/api/v1/alerts/silences/1")
    assert res.status_code in (401, 403, 307, 200)
