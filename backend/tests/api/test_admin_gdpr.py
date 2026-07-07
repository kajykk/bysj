"""ISS-074 回归测试：管理员 GDPR 端点

测试覆盖：
- GET  /api/v1/admin/gdpr/export/{user_id}  - 管理员导出任意用户数据
- POST /api/v1/admin/gdpr/delete/{user_id}  - 管理员匿名化任意用户（无需密码）

回归覆盖：
- 导出成功 + 审计日志写入 (admin.gdpr.export_user)
- 匿名化成功 + 双重审计日志（gdpr.account.deleted + admin.gdpr.delete_user）
- 非管理员 403
- 用户不存在 404
- 管理员自删被拒绝 400
- 缺少 reason 字段 422
- 未确认 confirm=false 400
"""

from __future__ import annotations

import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import OperationLog
from app.models.user import User


def _seed_target_user(db_session: AsyncSession, user_id: int = 100) -> int:
    """同步包装的种子函数：插入一个普通用户作为 GDPR 操作目标."""
    from app.core.pii_crypto import compute_blind_index
    from app.core.security import get_password_hash
    from tests.conftest import run

    async def _seed() -> int:
        db_session.add(
            User(
                id=user_id,
                username="gdpr_target",
                email="gdpr_target@test.com",
                email_hash=compute_blind_index("gdpr_target@test.com", "email"),
                password_hash=get_password_hash("TestPwd-2024-Secure!"),
                role="user",
                status="active",
            )
        )
        await db_session.commit()
        return user_id

    return run(_seed())


@pytest_asyncio.fixture
def seed_target_user_id(db_session: AsyncSession) -> int:
    """插入一个 ID=100 的普通用户作为 GDPR 操作目标."""
    return _seed_target_user(db_session, user_id=100)


# ===== 导出端点 =====


class TestAdminGdprExport:
    """ISS-074: GET /api/v1/admin/gdpr/export/{user_id}"""

    def test_export_success(
        self, client: TestClient, as_role, seeded_user_id, seed_target_user_id
    ):
        """管理员导出用户数据：返回 200 + JSON 流式响应."""
        as_role("admin", 3)
        res = client.get(f"/api/v1/admin/gdpr/export/{seed_target_user_id}")
        assert res.status_code == 200
        # 流式 JSON 响应应包含 export_metadata
        body = res.json()
        assert "export_metadata" in body
        assert body["export_metadata"]["user_id"] == seed_target_user_id
        assert "account" in body

    def test_export_writes_audit_log(
        self,
        client: TestClient,
        as_role,
        seeded_user_id,
        seed_target_user_id,
        db_session: AsyncSession,
    ):
        """导出操作必须写入 OperationLog."""
        from tests.conftest import run

        as_role("admin", 3)
        res = client.get(f"/api/v1/admin/gdpr/export/{seed_target_user_id}")
        assert res.status_code == 200

        async def _check_log():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "admin.gdpr.export_user",
                    OperationLog.target_id == seed_target_user_id,
                )
            )
            return result.scalar_one_or_none()

        log = run(_check_log())
        assert log is not None
        assert log.operator_id == 3
        assert log.operator_role == "admin"

    def test_export_user_not_found(self, client: TestClient, as_role, seeded_user_id):
        """不存在的用户返回 404."""
        as_role("admin", 3)
        res = client.get("/api/v1/admin/gdpr/export/99999")
        assert res.status_code == 404
        assert "不存在" in res.json()["error"]["message"]

    def test_export_user_forbidden(
        self, client: TestClient, as_role, seeded_user_id, seed_target_user_id
    ):
        """普通用户无权限，返回 403."""
        as_role("user", 1)
        res = client.get(f"/api/v1/admin/gdpr/export/{seed_target_user_id}")
        assert res.status_code == 403


# ===== 匿名化端点 =====


class TestAdminGdprDelete:
    """ISS-074: POST /api/v1/admin/gdpr/delete/{user_id}"""

    def test_delete_success(
        self,
        client: TestClient,
        as_role,
        seeded_user_id,
        seed_target_user_id,
        db_session: AsyncSession,
    ):
        """管理员匿名化用户：返回 200 + 用户 status='deleted'."""
        from tests.conftest import run

        as_role("admin", 3)
        res = client.post(
            f"/api/v1/admin/gdpr/delete/{seed_target_user_id}",
            json={"confirm": True, "reason": "用户书面申请删除"},
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert "anonymized_at" in data

        # 验证用户已被匿名化（status=deleted）
        async def _check_user():
            return await db_session.get(User, seed_target_user_id)

        user = run(_check_user())
        assert user is not None
        assert user.status == "deleted"
        # 用户名应被替换为匿名占位符
        assert user.username != "gdpr_target"

    def test_delete_writes_dual_audit_log(
        self,
        client: TestClient,
        as_role,
        seeded_user_id,
        seed_target_user_id,
        db_session: AsyncSession,
    ):
        """匿名化操作写入两条审计日志：用户自删日志 + 管理员越权日志."""
        from tests.conftest import run

        as_role("admin", 3)
        res = client.post(
            f"/api/v1/admin/gdpr/delete/{seed_target_user_id}",
            json={"confirm": True, "reason": "合规审计测试"},
        )
        assert res.status_code == 200

        async def _check_logs():
            # 用户自删日志（由 GDPRService.anonymize_user 写入）
            r1 = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "gdpr.account.deleted",
                    OperationLog.target_id == seed_target_user_id,
                )
            )
            # 管理员越权日志（由 admin endpoint 额外写入）
            r2 = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "admin.gdpr.delete_user",
                    OperationLog.target_id == seed_target_user_id,
                )
            )
            return r1.scalar_one_or_none(), r2.scalar_one_or_none()

        log1, log2 = run(_check_logs())
        assert log1 is not None, "gdpr.account.deleted 日志缺失"
        assert log2 is not None, "admin.gdpr.delete_user 日志缺失"
        assert log2.operator_id == 3
        assert log2.operator_role == "admin"

    def test_delete_user_not_found(self, client: TestClient, as_role, seeded_user_id):
        """不存在的用户返回 404."""
        as_role("admin", 3)
        res = client.post(
            "/api/v1/admin/gdpr/delete/99999",
            json={"confirm": True, "reason": "测试"},
        )
        assert res.status_code == 404

    def test_delete_self_rejected(self, client: TestClient, as_role, seeded_user_id):
        """管理员不可通过此端点删除自己，返回 400."""
        as_role("admin", 3)
        res = client.post(
            "/api/v1/admin/gdpr/delete/3",
            json={"confirm": True, "reason": "测试自删"},
        )
        assert res.status_code == 400
        assert "不可通过此端点删除自己" in res.json()["error"]["message"]

    def test_delete_confirm_false_rejected(
        self, client: TestClient, as_role, seeded_user_id, seed_target_user_id
    ):
        """confirm=false 被拒绝."""
        as_role("admin", 3)
        res = client.post(
            f"/api/v1/admin/gdpr/delete/{seed_target_user_id}",
            json={"confirm": False, "reason": "测试"},
        )
        assert res.status_code == 400
        assert "确认" in res.json()["error"]["message"]

    def test_delete_missing_reason_rejected(
        self, client: TestClient, as_role, seeded_user_id, seed_target_user_id
    ):
        """缺少 reason 字段返回 422（Pydantic 校验）."""
        as_role("admin", 3)
        res = client.post(
            f"/api/v1/admin/gdpr/delete/{seed_target_user_id}",
            json={"confirm": True},
        )
        assert res.status_code == 422

    def test_delete_user_forbidden(
        self, client: TestClient, as_role, seeded_user_id, seed_target_user_id
    ):
        """普通用户无权限，返回 403."""
        as_role("user", 1)
        res = client.post(
            f"/api/v1/admin/gdpr/delete/{seed_target_user_id}",
            json={"confirm": True, "reason": "测试"},
        )
        assert res.status_code == 403
