"""2026-07-05 全量审计 P3/P4 问题回归测试.

ISS-038 (version 鉴权) / ISS-070 (已处理预警误报 404) /
ISS-092 (CSV RFC 5987 filename*) / ISS-093 (ValueError 语义 400/404) /
ISS-094 (upsert 幂等控制)
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.admin import OperationLog, WarningThreshold
from app.models.risk import WarningNotification
from tests.conftest import run

# ===== ISS-038: /version 需要认证 =====


def test_version_endpoint_requires_auth(client: TestClient) -> None:
    """ISS-038: 无认证调用 /api/v1/version 应返回 401."""
    from app.core.deps import get_current_user

    client.app.dependency_overrides.pop(get_current_user, None)
    res = client.get("/api/v1/version")
    assert res.status_code == 401


def test_version_endpoint_authenticated(client: TestClient, as_role) -> None:
    """ISS-038: 已登录用户仍可访问 /api/v1/version."""
    as_role("user", 1)
    res = client.get("/api/v1/version")
    assert res.status_code == 200
    assert "version" in res.json()


# ===== ISS-070: 已处理预警不应误报 404 =====


def test_counselor_handle_already_handled_warning_returns_status(
    client: TestClient, as_role, db_session, seeded_user_id
) -> None:
    """ISS-070: 已处理 (不同 action) 的预警应返回 200 + status, 而非 404."""
    async def _seed() -> int:
        warning = WarningNotification(
            user_id=1,
            counselor_id=2,
            current_level=3,
            trigger_reason="risk up",
            is_handled=True,
            handle_action="ignore",
        )
        db_session.add(warning)
        await db_session.commit()
        await db_session.refresh(warning)
        return warning.id

    warning_id = run(_seed())

    as_role("counselor", 2)
    res = client.put(
        f"/api/v1/counselor/warnings/{warning_id}/handle",
        json={"action": "handle"},
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["status"] == "ignored"
    assert data["warning_id"] == warning_id


def test_counselor_handle_missing_warning_still_404(
    client: TestClient, as_role
) -> None:
    """ISS-070: 真正不存在的预警仍返回 404."""
    as_role("counselor", 2)
    res = client.put(
        "/api/v1/counselor/warnings/99999/handle", json={"action": "handle"}
    )
    assert res.status_code == 404


# ===== ISS-092: CSV 导出 Content-Disposition RFC 5987 =====


def test_crisis_export_content_disposition_rfc5987(
    client: TestClient, as_role
) -> None:
    """ISS-092: Content-Disposition 含 filename* = UTF-8'' 编码."""
    as_role("admin", 3)
    end = date.today()
    start = end - timedelta(days=1)
    res = client.get(
        f"/api/v1/admin/crisis-events/export?start_date={start.isoformat()}&end_date={end.isoformat()}"
    )
    assert res.status_code == 200
    cd = res.headers.get("content-disposition", "")
    assert 'filename="crisis_events_' in cd
    assert "filename*=UTF-8''crisis_events_" in cd


# ===== ISS-093: ValueError 语义 (业务参数 → 400) =====


def test_admin_config_non_whitelist_key_400(client: TestClient, as_role) -> None:
    """ISS-093: 非白名单配置键是业务参数错误 → 400 (原未捕获 → 500)."""
    as_role("admin", 3)
    res = client.post(
        "/api/v1/admin/configs",
        json={"config_key": "evil_key_not_allowed", "config_value": {"v": 1}},
    )
    assert res.status_code == 400, res.text
    assert "白名单" in res.json()["message"]


def test_admin_template_update_missing_404(client: TestClient, as_role) -> None:
    """ISS-093: 模板不存在仍映射 404."""
    as_role("admin", 3)
    res = client.post(
        "/api/v1/admin/templates",
        json={
            "id": 99999,
            "template_name": "t",
            "applicable_levels": [2],
            "task_list": [{"task_name": "a", "task_type": "meditation"}],
        },
    )
    assert res.status_code == 404, res.text


# ===== ISS-094: upsert 幂等 (Idempotency-Key) =====


class _FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


def test_threshold_upsert_idempotency_replays_same_key(
    client: TestClient, as_role, db_session, monkeypatch
) -> None:
    """ISS-094: 相同 Idempotency-Key 重复提交不重复执行 (只写一次审计日志)."""
    fake = _FakeRedis()

    async def _client():
        return fake

    monkeypatch.setattr("app.core.idempotency.get_redis_client", _client)

    as_role("admin", 3)
    payload = {
        "level": 1,
        "level_name": "low",
        "min_score": 0,
        "max_score": 20,
        "color": "#00f",
        "action_required": "none",
    }
    headers = {"Idempotency-Key": "idem-thr-1"}
    r1 = client.post("/api/v1/admin/thresholds", json=payload, headers=headers)
    assert r1.status_code == 200, r1.text
    r2 = client.post("/api/v1/admin/thresholds", json=payload, headers=headers)
    assert r2.status_code == 200, r2.text
    assert r1.json() == r2.json()

    async def _count_logs() -> int:
        rows = (
            await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "upsert_warning_threshold",
                    OperationLog.operator_id == 3,
                )
            )
        ).scalars().all()
        return len(rows)

    assert run(_count_logs()) == 1, "幂等重放不应重复写入审计日志"


def test_threshold_upsert_different_keys_both_execute(
    client: TestClient, as_role, db_session, monkeypatch
) -> None:
    """ISS-094: 不同 Idempotency-Key 视为不同请求, 均正常执行."""
    fake = _FakeRedis()

    async def _client():
        return fake

    monkeypatch.setattr("app.core.idempotency.get_redis_client", _client)

    as_role("admin", 3)
    payload = {
        "level": 2,
        "level_name": "medium",
        "min_score": 21,
        "max_score": 50,
        "color": "#ff0",
        "action_required": "watch",
    }
    r1 = client.post(
        "/api/v1/admin/thresholds",
        json=payload,
        headers={"Idempotency-Key": "key-a"},
    )
    r2 = client.post(
        "/api/v1/admin/thresholds",
        json=payload,
        headers={"Idempotency-Key": "key-b"},
    )
    assert r1.status_code == 200 and r2.status_code == 200

    async def _count() -> int:
        rows = (
            await db_session.execute(
                select(WarningThreshold).where(WarningThreshold.level == 2)
            )
        ).scalars().all()
        return len(rows)

    assert run(_count()) == 1, "upsert 按 level 幂等, 不应产生重复行"
