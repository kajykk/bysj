from fastapi.testclient import TestClient


def test_counselor_group_create_invalid_422(client: TestClient, as_role) -> None:
    as_role("counselor", 2)
    res = client.post("/api/v1/counselor/groups", json={"group_name": ""})
    assert res.status_code == 422


def test_counselor_group_member_invalid_422(client: TestClient, as_role) -> None:
    as_role("counselor", 2)
    res = client.post("/api/v1/counselor/groups/1/members", json={"user_id": 0})
    assert res.status_code == 422


def test_counselor_consultation_invalid_422(client: TestClient, as_role) -> None:
    as_role("counselor", 2)
    res = client.post("/api/v1/counselor/users/1/consultations", json={"main_topics": ""})
    assert res.status_code == 422


def test_counselor_bind_code_refresh_requires_role(client: TestClient, as_role) -> None:
    as_role("user", 1)
    res = client.post("/api/v1/counselor/bind-code/refresh")
    assert res.status_code == 403


def test_admin_template_invalid_422(client: TestClient, as_role) -> None:
    as_role("admin", 3)
    res = client.post("/api/v1/admin/templates", json={"template_name": ""})
    assert res.status_code == 422


def test_admin_threshold_invalid_422(client: TestClient, as_role) -> None:
    as_role("admin", 3)
    res = client.post(
        "/api/v1/admin/thresholds",
        json={"level": 1, "level_name": "L1", "min_score": 20, "max_score": 40, "color": "#f00"},
    )
    assert res.status_code == 422


def test_admin_config_invalid_422(client: TestClient, as_role) -> None:
    as_role("admin", 3)
    res = client.post("/api/v1/admin/configs", json={"config_value": {}})
    assert res.status_code == 422


def test_admin_template_list_empty_page_returns_200(client: TestClient, as_role) -> None:
    as_role("admin", 3)
    res = client.get("/api/v1/admin/templates?page=999&page_size=20")
    assert res.status_code == 200
    body = res.json()
    assert "data" in body
    assert body["data"].get("items") is not None
