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


def test_health_live_returns_instant_ok(client: TestClient) -> None:
    """P0-1.1: /health/live 轻量存活探针, 不执行 I/O, 立即返回 ok."""
    res = client.get("/health/live")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"


def test_health_ready_returns_checks(client: TestClient) -> None:
    """P0-1.1: /health/ready 就绪探针, 非阻塞返回缓存健康快照."""
    res = client.get("/health/ready")
    assert res.status_code == 200
    body = res.json()
    assert "status" in body
    assert "checks" in body
    assert "database" in body["checks"]


def test_health_startup_returns_started_flag(client: TestClient) -> None:
    """P0-1.1: /health/startup 启动探针, 应用启动后返回 started=True."""
    res = client.get("/health/startup")
    assert res.status_code == 200
    body = res.json()
    assert "status" in body
    assert "started" in body
    # TestClient 会在 lifespan 完成后处理请求, 因此 started 应为 True
    assert body["started"] is True


def test_admin_upsert_threshold_writes_operation_log(
    client: TestClient,
    as_role,
    db_session: AsyncSession,
) -> None:
    as_role("admin", 3)
    res = client.post(
        "/api/v1/admin/thresholds",
        json={
            "level": 4,
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
