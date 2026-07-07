from fastapi.testclient import TestClient


def test_generate_request_id_when_missing(client: TestClient, as_role) -> None:
    as_role("admin", 3)
    res = client.post(
        "/api/v1/admin/thresholds",
        json={
            "level": 3,
            "level_name": "high",
            "min_score": 70,
            "max_score": 89,
            "color": "#f80",
            "action_required": "follow_up",
        },
    )
    assert res.status_code == 200
    assert "x-request-id" in res.headers
    assert len(res.headers["x-request-id"]) >= 32


def test_echo_request_id_when_provided(client: TestClient, as_role) -> None:
    as_role("counselor", 2)
    list_res = client.get("/api/v1/counselor/warnings")
    warning_id = (
        list_res.json()["data"]["items"][0]["id"]
        if list_res.status_code == 200 and list_res.json()["data"]["items"]
        else 1
    )

    req_id = "req-abc-123"
    res = client.put(
        f"/api/v1/counselor/warnings/{warning_id}/handle",
        json={"action": "follow_up", "note": "ok"},
        headers={"x-request-id": req_id},
    )
    assert res.headers.get("x-request-id") == req_id
