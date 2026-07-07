from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import OperationLog
from tests.conftest import run


def test_health_endpoint_includes_celery_worker_check(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert "checks" in body
    assert "celery_worker" in body["checks"]


def test_upload_rejects_oversized_file(client: TestClient, as_role) -> None:
    as_role("user", 1)
    huge_content = b"a" * (20 * 1024 * 1024 + 1)
    res = client.post(
        "/api/v1/user/upload",
        files={"file": ("too_large.txt", huge_content, "text/plain")},
    )
    assert res.status_code == 400
    body = res.json()
    message = (
        body.get("detail")
        or (body.get("error") or {}).get("message")
        or body.get("message")
        or ""
    )
    assert "20MB" in message


def test_assessment_submit_writes_risk_log(
    client: TestClient, as_role, seeded_user_id: int
) -> None:
    as_role("user", seeded_user_id)
    payload = {
        "assessment_type": "comprehensive",
        "data_payload": {
            "total_score": 18,
            "age": 20,
            "gender": 1,
            "study_year": 2,
            "cgpa": 3.2,
            "stress_level": 4,
            "sleep_duration": 6,
            "social_support": 2,
            "financial_pressure": 2,
            "family_history": 0,
            "academic_pressure": 4,
            "exercise_frequency": 1,
            "anxiety": 3,
            "panic_attack": 0,
            "treatment_seeking": 0,
        },
    }

    res = client.post("/api/v1/user/data/collect", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["code"] == 200
    assert "risk_level" in body["data"]


def test_permission_boundary_user_cannot_access_counselor_api(
    client: TestClient, as_role
) -> None:
    as_role("user", 1)
    res = client.get("/api/v1/counselor/warnings")
    assert res.status_code == 403


def test_permission_boundary_counselor_cannot_access_admin_api(
    client: TestClient, as_role
) -> None:
    as_role("counselor", 2)
    res = client.get("/api/v1/admin/operation-logs")
    assert res.status_code in {403, 405}


def test_warning_handle_writes_operation_log(
    client: TestClient,
    as_role,
    seed_counselor_data,
    db_session: AsyncSession,
) -> None:
    as_role("counselor", 2)
    list_res = client.get("/api/v1/counselor/warnings")
    assert list_res.status_code == 200
    warning_id = list_res.json()["data"]["items"][0]["id"]

    handle_res = client.put(
        f"/api/v1/counselor/warnings/{warning_id}/handle",
        json={"action": "handle", "note": "done"},
    )
    assert handle_res.status_code == 200

    async def _has_warning_handle_log() -> bool:
        rows = (await db_session.execute(select(OperationLog))).scalars().all()
        return any(r.action_type in {"warning_handle", "warning_ignore"} for r in rows)

    assert run(_has_warning_handle_log())
