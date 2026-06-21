from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import OperationLog
from tests.conftest import run


def test_health_endpoint_returns_checks(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert "status" in body
    assert "checks" in body
    assert "database" in body["checks"]
    assert "redis" in body["checks"]


def test_admin_upsert_threshold_writes_operation_log(
    client: TestClient,
    as_role,
    db_session: AsyncSession,
) -> None:
    as_role("admin", 3)
    res = client.post(
        "/api/v1/admin/thresholds",
        json={
            "level": 5,
            "level_name": "critical",
            "min_score": 80,
            "max_score": 100,
            "color": "#f00",
            "action_required": "immediate",
        },
    )
    assert res.status_code == 200

    async def _count_logs() -> int:
        rows = (await db_session.execute(select(OperationLog))).scalars().all()
        return len(rows)

    assert run(_count_logs()) >= 1
