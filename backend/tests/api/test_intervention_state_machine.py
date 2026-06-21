from datetime import date

from fastapi.testclient import TestClient


def test_completed_cannot_skip_again(client: TestClient, as_role, seed_intervention_for_user: int) -> None:
    as_role("user", 1)
    task_id = seed_intervention_for_user

    complete_res = client.put(
        f"/api/v1/user/intervention/tasks/{task_id}/complete",
        json={"scheduled_date": date.today().isoformat()},
    )
    assert complete_res.status_code == 200

    skip_res = client.put(
        f"/api/v1/user/intervention/tasks/{task_id}/skip",
        json={"scheduled_date": date.today().isoformat(), "note": "skip after done"},
    )
    assert skip_res.status_code == 409


def test_pending_can_postpone(client: TestClient, as_role, seed_intervention_for_user: int) -> None:
    as_role("user", 1)
    task_id = seed_intervention_for_user
    postpone_res = client.put(
        f"/api/v1/user/intervention/tasks/{task_id}/postpone",
        json={"scheduled_date": date.today().isoformat(), "postpone_to": date.today().isoformat()},
    )
    assert postpone_res.status_code == 200


def test_completed_cannot_postpone_again(client: TestClient, as_role, seed_intervention_for_user: int) -> None:
    as_role("user", 1)
    task_id = seed_intervention_for_user

    complete_res = client.put(
        f"/api/v1/user/intervention/tasks/{task_id}/complete",
        json={"scheduled_date": date.today().isoformat()},
    )
    assert complete_res.status_code == 200

    postpone_res = client.put(
        f"/api/v1/user/intervention/tasks/{task_id}/postpone",
        json={"scheduled_date": date.today().isoformat(), "postpone_to": date.today().isoformat()},
    )
    assert postpone_res.status_code == 409
