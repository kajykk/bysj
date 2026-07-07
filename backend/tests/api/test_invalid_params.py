from fastapi.testclient import TestClient


def test_postpone_missing_postpone_to_returns_400(
    client: TestClient, as_role, seed_intervention_for_user: int
) -> None:
    as_role("user", 1)
    task_id = seed_intervention_for_user
    res = client.put(
        f"/api/v1/user/intervention/tasks/{task_id}/postpone",
        json={"scheduled_date": "2026-04-08"},
    )
    assert res.status_code == 400


def test_postpone_invalid_date_returns_422(
    client: TestClient, as_role, seed_intervention_for_user: int
) -> None:
    as_role("user", 1)
    task_id = seed_intervention_for_user
    res = client.put(
        f"/api/v1/user/intervention/tasks/{task_id}/postpone",
        json={"scheduled_date": "bad-date", "postpone_to": "2026-04-08"},
    )
    assert res.status_code == 422


def test_risk_export_invalid_format_returns_422(client: TestClient, as_role) -> None:
    as_role("user", 1)
    res = client.get("/api/v1/user/risk/export?format=xml")
    assert res.status_code == 422


def test_admin_templates_invalid_pagination_returns_422(
    client: TestClient, as_role
) -> None:
    as_role("admin", 3)
    res = client.get("/api/v1/admin/templates?page=0&page_size=20")
    assert res.status_code == 422
