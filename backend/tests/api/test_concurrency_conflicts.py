from datetime import date

from fastapi.testclient import TestClient


def test_task_state_conflict_on_double_complete(client: TestClient, as_role, seed_intervention_for_user: int) -> None:
    as_role("user", 1)
    task_id = seed_intervention_for_user

    first = client.put(
        f"/api/v1/user/intervention/tasks/{task_id}/complete",
        json={"scheduled_date": date.today().isoformat()},
    )
    assert first.status_code == 200

    second = client.put(
        f"/api/v1/user/intervention/tasks/{task_id}/complete",
        json={"scheduled_date": date.today().isoformat()},
    )
    assert second.status_code == 409


def test_warning_handle_conflict_by_other_counselor(client: TestClient, as_role, seed_counselor_data: None) -> None:
    as_role("counselor", 2)
    list_res = client.get("/api/v1/counselor/warnings")
    warning_id = list_res.json()["data"]["items"][0]["id"]

    as_role("counselor", 999)
    res = client.put(f"/api/v1/counselor/warnings/{warning_id}/handle", json={"action": "handle"})
    assert res.status_code == 404


def test_add_group_member_idempotent_under_repeated_calls(client: TestClient, as_role, seed_counselor_data: None) -> None:
    as_role("counselor", 2)
    group_res = client.post("/api/v1/counselor/groups", json={"group_name": "G1", "color_tag": "#409EFF"})
    group_id = group_res.json()["data"]["group_id"]

    first = client.post(f"/api/v1/counselor/groups/{group_id}/members", json={"user_id": 1})
    second = client.post(f"/api/v1/counselor/groups/{group_id}/members", json={"user_id": 1})
    assert first.status_code == 200
    assert second.status_code == 200
