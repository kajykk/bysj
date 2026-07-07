from fastapi.testclient import TestClient


def test_admin_can_query_operation_logs(
    client: TestClient, as_role, seed_admin_data: None
) -> None:
    as_role("admin", 3)

    client.post(
        "/api/v1/admin/thresholds",
        json={
            "level": 4,
            "level_name": "high",
            "min_score": 70,
            "max_score": 79,
            "color": "#f90",
            "action_required": "follow-up",
        },
    )

    res = client.get("/api/v1/admin/operation-logs?page=1&page_size=20")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["total"] >= 1
    assert len(data["items"]) >= 1
