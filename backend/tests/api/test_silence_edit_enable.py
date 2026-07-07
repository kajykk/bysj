"""ISS-073 回归测试：静默规则编辑与启用端点

测试覆盖：
- PUT  /api/v1/alerts/silences/{id}        - 编辑静默规则 (admin)
- POST /api/v1/alerts/silences/{id}/enable - 启用已停用的规则 (admin)

回归覆盖：
- 编辑成功 + 审计日志写入
- 启用成功 + 幂等性 + 审计日志写入
- 非管理员 403
- 不存在 404
- 输入校验（matcher 空、时间顺序、持续期）
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AlertSilence, OperationLog


def _seed_silence(
    db_session: AsyncSession,
    *,
    name: str = "test-silence",
    is_active: bool = True,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
) -> int:
    """同步包装的静默规则种子函数，返回规则 ID."""
    from tests.conftest import run

    if starts_at is None:
        starts_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    if ends_at is None:
        ends_at = datetime.now(timezone.utc) + timedelta(hours=2)

    async def _seed() -> int:
        silence = AlertSilence(
            name=name,
            matcher={"alertname": "HighCpu"},
            starts_at=starts_at,
            ends_at=ends_at,
            created_by=3,
            is_active=is_active,
            comment="seed",
        )
        db_session.add(silence)
        await db_session.commit()
        await db_session.refresh(silence)
        return silence.id

    return run(_seed())


@pytest_asyncio.fixture
def seed_active_silence(db_session: AsyncSession) -> int:
    """插入一条 is_active=True 的静默规则."""
    return _seed_silence(db_session, name="active-rule", is_active=True)


@pytest_asyncio.fixture
def seed_inactive_silence(db_session: AsyncSession) -> int:
    """插入一条 is_active=False 的静默规则."""
    return _seed_silence(db_session, name="inactive-rule", is_active=False)


# ===== 编辑端点 PUT =====


class TestUpdateSilence:
    """ISS-073: PUT /api/v1/alerts/silences/{id}"""

    def test_update_success(
        self, client: TestClient, as_role, seeded_user_id, seed_active_silence
    ):
        """编辑成功：修改名称与备注，返回 200 + 更新后的数据."""
        as_role("admin", 3)
        now = datetime.now(timezone.utc)
        res = client.put(
            f"/api/v1/alerts/silences/{seed_active_silence}",
            json={
                "name": "updated-name",
                "matcher": {"alertname": "HighMem"},
                "starts_at": (now - timedelta(minutes=5)).isoformat(),
                "ends_at": (now + timedelta(hours=3)).isoformat(),
                "comment": "updated-comment",
            },
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["name"] == "updated-name"
        assert data["matcher"] == {"alertname": "HighMem"}
        assert data["comment"] == "updated-comment"
        assert data["is_active"] is True  # 编辑不影响 is_active

    def test_update_writes_audit_log(
        self,
        client: TestClient,
        as_role,
        seeded_user_id,
        seed_active_silence,
        db_session: AsyncSession,
    ):
        """编辑操作必须写入 OperationLog 审计日志（权限/安全场景需第二人复核）."""
        from tests.conftest import run

        as_role("admin", 3)
        now = datetime.now(timezone.utc)
        res = client.put(
            f"/api/v1/alerts/silences/{seed_active_silence}",
            json={
                "name": "audit-test",
                "matcher": {"alertname": "X"},
                "starts_at": (now - timedelta(minutes=5)).isoformat(),
                "ends_at": (now + timedelta(hours=1)).isoformat(),
            },
        )
        assert res.status_code == 200

        async def _check_log():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "update_silence",
                    OperationLog.target_id == seed_active_silence,
                )
            )
            return result.scalar_one_or_none()

        log = run(_check_log())
        assert log is not None
        assert log.operator_id == 3
        assert log.operator_role == "admin"
        assert log.target_type == "alert_silence"

    def test_update_not_found(self, client: TestClient, as_role, seeded_user_id):
        """不存在的规则返回 404."""
        as_role("admin", 3)
        now = datetime.now(timezone.utc)
        res = client.put(
            "/api/v1/alerts/silences/99999",
            json={
                "name": "x",
                "matcher": {"alertname": "X"},
                "starts_at": (now - timedelta(minutes=5)).isoformat(),
                "ends_at": (now + timedelta(hours=1)).isoformat(),
            },
        )
        assert res.status_code == 404
        assert "not found" in res.json()["error"]["message"]

    def test_update_user_forbidden(
        self, client: TestClient, as_role, seeded_user_id, seed_active_silence
    ):
        """普通用户无 admin 角色，返回 403."""
        as_role("user", 1)
        now = datetime.now(timezone.utc)
        res = client.put(
            f"/api/v1/alerts/silences/{seed_active_silence}",
            json={
                "name": "x",
                "matcher": {"alertname": "X"},
                "starts_at": (now - timedelta(minutes=5)).isoformat(),
                "ends_at": (now + timedelta(hours=1)).isoformat(),
            },
        )
        assert res.status_code == 403

    def test_update_empty_matcher_rejected(
        self, client: TestClient, as_role, seeded_user_id, seed_active_silence
    ):
        """matcher 为空应被拒绝（避免静默所有告警）."""
        as_role("admin", 3)
        now = datetime.now(timezone.utc)
        res = client.put(
            f"/api/v1/alerts/silences/{seed_active_silence}",
            json={
                "name": "x",
                "matcher": {},
                "starts_at": (now - timedelta(minutes=5)).isoformat(),
                "ends_at": (now + timedelta(hours=1)).isoformat(),
            },
        )
        # Pydantic validator 抛 ValueError → 全局异常处理器返回 422
        assert res.status_code in (400, 422)

    def test_update_bad_time_order_rejected(
        self, client: TestClient, as_role, seeded_user_id, seed_active_silence
    ):
        """ends_at 早于 starts_at 应被拒绝."""
        as_role("admin", 3)
        now = datetime.now(timezone.utc)
        res = client.put(
            f"/api/v1/alerts/silences/{seed_active_silence}",
            json={
                "name": "x",
                "matcher": {"alertname": "X"},
                "starts_at": (now + timedelta(hours=2)).isoformat(),
                "ends_at": (now + timedelta(hours=1)).isoformat(),
            },
        )
        assert res.status_code in (400, 422)

    def test_update_duration_over_90_days_rejected(
        self, client: TestClient, as_role, seeded_user_id, seed_active_silence
    ):
        """静默持续期超过 90 天应被拒绝."""
        as_role("admin", 3)
        now = datetime.now(timezone.utc)
        res = client.put(
            f"/api/v1/alerts/silences/{seed_active_silence}",
            json={
                "name": "x",
                "matcher": {"alertname": "X"},
                "starts_at": now.isoformat(),
                "ends_at": (now + timedelta(days=91)).isoformat(),
            },
        )
        assert res.status_code in (400, 422)


# ===== 启用端点 POST /enable =====


class TestEnableSilence:
    """ISS-073: POST /api/v1/alerts/silences/{id}/enable"""

    def test_enable_inactive_success(
        self, client: TestClient, as_role, seeded_user_id, seed_inactive_silence
    ):
        """启用已停用的规则：is_active False → True."""
        as_role("admin", 3)
        res = client.post(f"/api/v1/alerts/silences/{seed_inactive_silence}/enable")
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["is_active"] is True

    def test_enable_idempotent(
        self, client: TestClient, as_role, seeded_user_id, seed_active_silence
    ):
        """已启用的规则再次启用：幂等返回 200，不写审计日志."""
        as_role("admin", 3)
        res = client.post(f"/api/v1/alerts/silences/{seed_active_silence}/enable")
        assert res.status_code == 200
        assert res.json()["data"]["is_active"] is True

    def test_enable_writes_audit_log(
        self,
        client: TestClient,
        as_role,
        seeded_user_id,
        seed_inactive_silence,
        db_session: AsyncSession,
    ):
        """启用操作必须写入 OperationLog."""
        from tests.conftest import run

        as_role("admin", 3)
        res = client.post(f"/api/v1/alerts/silences/{seed_inactive_silence}/enable")
        assert res.status_code == 200

        async def _check_log():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "enable_silence",
                    OperationLog.target_id == seed_inactive_silence,
                )
            )
            return result.scalar_one_or_none()

        log = run(_check_log())
        assert log is not None
        assert log.operator_id == 3

    def test_enable_not_found(self, client: TestClient, as_role, seeded_user_id):
        """不存在的规则返回 404."""
        as_role("admin", 3)
        res = client.post("/api/v1/alerts/silences/99999/enable")
        assert res.status_code == 404
        assert "not found" in res.json()["error"]["message"]

    def test_enable_user_forbidden(
        self, client: TestClient, as_role, seeded_user_id, seed_inactive_silence
    ):
        """普通用户无 admin 角色，返回 403."""
        as_role("user", 1)
        res = client.post(f"/api/v1/alerts/silences/{seed_inactive_silence}/enable")
        assert res.status_code == 403


# ===== 编辑+启用集成测试 =====


class TestSilenceEditEnableIntegration:
    """ISS-073 集成：删除 → 启用 → 编辑 完整生命周期"""

    def test_delete_then_enable_then_edit(
        self, client: TestClient, as_role, seeded_user_id, seed_active_silence
    ):
        """完整生命周期：删除（软）→ 启用 → 编辑."""
        as_role("admin", 3)
        silence_id = seed_active_silence

        # 1. 删除（软删除，is_active=False）
        res = client.delete(f"/api/v1/alerts/silences/{silence_id}")
        assert res.status_code == 200
        assert res.json()["data"]["is_active"] is False

        # 2. 启用
        res = client.post(f"/api/v1/alerts/silences/{silence_id}/enable")
        assert res.status_code == 200
        assert res.json()["data"]["is_active"] is True

        # 3. 编辑
        now = datetime.now(timezone.utc)
        res = client.put(
            f"/api/v1/alerts/silences/{silence_id}",
            json={
                "name": "lifecycle-updated",
                "matcher": {"alertname": "NewAlert"},
                "starts_at": (now - timedelta(minutes=1)).isoformat(),
                "ends_at": (now + timedelta(hours=1)).isoformat(),
                "comment": "lifecycle test",
            },
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["name"] == "lifecycle-updated"
        assert data["matcher"] == {"alertname": "NewAlert"}
        assert data["is_active"] is True  # 编辑保持启用状态
