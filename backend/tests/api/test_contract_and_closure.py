import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import OperationLog
from app.models.counselor import ConsultationRecord


def test_user_warning_contract_unified_fields(
    client: TestClient, as_role, seed_counselor_data: None
) -> None:
    as_role("user", 1)
    res = client.get("/api/v1/user/warnings?page=1&page_size=10")
    assert res.status_code == 200

    payload = res.json()["data"]
    assert set(payload.keys()) == {"items", "total", "page", "page_size"}
    first = payload["items"][0]
    assert isinstance(first["risk_level"], str)
    assert first["risk_level"] in {"low", "medium", "high"}
    assert first["status"] in {"pending", "handled", "ignored"}


def test_counselor_handle_warning_logs_unified_action_type(
    client: TestClient,
    as_role,
    db_session: AsyncSession,
    seed_counselor_data: None,
) -> None:
    as_role("counselor", 2)
    list_res = client.get("/api/v1/counselor/warnings?page=1&page_size=10")
    warning_id = list_res.json()["data"]["items"][0]["id"]

    res = client.put(
        f"/api/v1/counselor/warnings/{warning_id}/handle",
        json={"action": "ignore", "note": "not needed"},
    )
    assert res.status_code == 200

    async def _query() -> list[OperationLog]:
        rows = (
            (
                await db_session.execute(
                    select(OperationLog)
                    .where(
                        OperationLog.target_type == "warning_notification",
                        OperationLog.target_id == warning_id,
                    )
                    .order_by(OperationLog.id.desc())
                )
            )
            .scalars()
            .all()
        )
        return rows

    rows = asyncio.run(_query())
    assert rows
    assert rows[0].action_type == "warning_ignore"


def test_create_consultation_record_requires_valid_warning_relation(
    client: TestClient,
    as_role,
    seed_counselor_data: None,
) -> None:
    as_role("counselor", 2)

    bad = client.post(
        "/api/v1/counselor/users/1/consultations",
        json={"warning_id": 99999, "main_topics": "topic"},
    )
    assert bad.status_code == 422


def test_consultation_list_contains_warning_link_fields(
    client: TestClient,
    as_role,
    db_session: AsyncSession,
    seed_counselor_data: None,
) -> None:
    as_role("counselor", 2)

    warning_list = client.get("/api/v1/counselor/warnings?page=1&page_size=10")
    warning_id = warning_list.json()["data"]["items"][0]["id"]

    create = client.post(
        "/api/v1/counselor/users/1/consultations",
        json={
            "warning_id": warning_id,
            "main_topics": "sleep",
            "next_plan": "follow up",
        },
    )
    assert create.status_code == 200

    res = client.get("/api/v1/counselor/users/1/consultations?page=1&page_size=10")
    assert res.status_code == 200
    first = res.json()["data"]["items"][0]
    assert first["warning_id"] == warning_id
    assert first["warning_status"] in {"pending", "handled", "ignored"}
    assert first["warning_risk_level"] in {"low", "medium", "high"}

    async def _query_record() -> ConsultationRecord | None:
        return (
            await db_session.execute(
                select(ConsultationRecord).where(
                    ConsultationRecord.id == create.json()["data"]["record_id"]
                )
            )
        ).scalar_one_or_none()

    record = asyncio.run(_query_record())
    assert record is not None
    assert record.warning_id == warning_id
