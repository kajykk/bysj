"""ISS-072 回归测试：危机事件状态流转端点

测试覆盖：
- POST /api/v1/reviews/crisis-events/{id}/handle   (detected|reviewed|escalated → reviewed)
- POST /api/v1/reviews/crisis-events/{id}/escalate (detected|reviewed → escalated)
- POST /api/v1/reviews/crisis-events/{id}/close    (detected|reviewed|escalated → resolved)

状态机：detected → reviewed → escalated → resolved
"""

from __future__ import annotations

import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review import CrisisEvent


def _seed_event(
    db_session: AsyncSession, status: str, action: str | None = None
) -> int:
    """同步包装的危机事件种子函数，返回事件 ID."""
    from tests.conftest import run

    async def _seed() -> int:
        event = CrisisEvent(
            user_id=1,
            trigger_source="text",
            crisis_keywords='["焦虑"]',
            crisis_score=85.0,
            input_summary="测试输入",
            status=status,
            handled_by=1 if action else None,
            handled_action=action,
        )
        db_session.add(event)
        await db_session.commit()
        await db_session.refresh(event)
        return event.id

    return run(_seed())


@pytest_asyncio.fixture
def seed_crisis_event(db_session: AsyncSession) -> int:
    """插入一条 status=detected 的危机事件，返回其 ID."""
    return _seed_event(db_session, "detected")


@pytest_asyncio.fixture
def seed_crisis_event_reviewed(db_session: AsyncSession) -> int:
    """插入一条 status=reviewed 的危机事件."""
    return _seed_event(db_session, "reviewed", action="notify_counselor")


@pytest_asyncio.fixture
def seed_crisis_event_escalated(db_session: AsyncSession) -> int:
    """插入一条 status=escalated 的危机事件."""
    return _seed_event(db_session, "escalated", action="escalate")


@pytest_asyncio.fixture
def seed_crisis_event_resolved(db_session: AsyncSession) -> int:
    """插入一条 status=resolved 的危机事件."""
    return _seed_event(db_session, "resolved", action="resolved")


# ===== handle 端点 =====


class TestHandleCrisisEvent:
    """ISS-072: POST /api/v1/reviews/crisis-events/{id}/handle"""

    def test_handle_detected_to_reviewed(
        self, client: TestClient, as_role, seeded_user_id, seed_crisis_event
    ):
        """detected → reviewed：合法转换."""
        as_role("admin", 3)
        res = client.post(
            f"/api/v1/reviews/crisis-events/{seed_crisis_event}/handle",
            json={"action": "notify_counselor", "note": "已通知咨询师"},
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["status"] == "reviewed"
        assert data["handled_action"] == "notify_counselor"
        assert data["handled_by"] == 3
        assert data["handled_at"] is not None

    def test_handle_reviewed_to_reviewed(
        self, client: TestClient, as_role, seeded_user_id, seed_crisis_event_reviewed
    ):
        """reviewed → reviewed：可重新处理（追加动作）."""
        as_role("admin", 3)
        res = client.post(
            f"/api/v1/reviews/crisis-events/{seed_crisis_event_reviewed}/handle",
            json={"action": "emergency_contact", "note": "联系紧急联系人"},
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["status"] == "reviewed"
        assert data["handled_action"] == "emergency_contact"

    def test_handle_escalated_to_reviewed(
        self, client: TestClient, as_role, seeded_user_id, seed_crisis_event_escalated
    ):
        """escalated → reviewed：合法转换."""
        as_role("admin", 3)
        res = client.post(
            f"/api/v1/reviews/crisis-events/{seed_crisis_event_escalated}/handle",
            json={"action": "notify_counselor"},
        )
        assert res.status_code == 200
        assert res.json()["data"]["status"] == "reviewed"

    def test_handle_resolved_rejected(
        self, client: TestClient, as_role, seeded_user_id, seed_crisis_event_resolved
    ):
        """resolved → reviewed：非法转换（终态），应返回 400."""
        as_role("admin", 3)
        res = client.post(
            f"/api/v1/reviews/crisis-events/{seed_crisis_event_resolved}/handle",
            json={"action": "notify_counselor"},
        )
        assert res.status_code == 400
        assert "非法状态转换" in res.json()["error"]["message"]

    def test_handle_invalid_action(
        self, client: TestClient, as_role, seeded_user_id, seed_crisis_event
    ):
        """ISS-072 + M-Svc-8：白名单校验非法 action."""
        as_role("admin", 3)
        res = client.post(
            f"/api/v1/reviews/crisis-events/{seed_crisis_event}/handle",
            json={"action": "arbitrary_string"},
        )
        assert res.status_code == 400
        assert "无效的 action" in res.json()["error"]["message"]

    def test_handle_not_found(self, client: TestClient, as_role, seeded_user_id):
        """事件不存在返回 400."""
        as_role("admin", 3)
        res = client.post(
            "/api/v1/reviews/crisis-events/99999/handle",
            json={"action": "notify_counselor"},
        )
        assert res.status_code == 400
        assert "not found" in res.json()["error"]["message"]

    def test_handle_user_forbidden(
        self, client: TestClient, as_role, seeded_user_id, seed_crisis_event
    ):
        """普通用户无 crisis_event.handle 权限，返回 403."""
        as_role("user", 1)
        res = client.post(
            f"/api/v1/reviews/crisis-events/{seed_crisis_event}/handle",
            json={"action": "notify_counselor"},
        )
        assert res.status_code == 403


# ===== escalate 端点 =====


class TestEscalateCrisisEvent:
    """ISS-072: POST /api/v1/reviews/crisis-events/{id}/escalate"""

    def test_escalate_detected_to_escalated(
        self, client: TestClient, as_role, seeded_user_id, seed_crisis_event
    ):
        """detected → escalated：合法转换."""
        as_role("admin", 3)
        res = client.post(
            f"/api/v1/reviews/crisis-events/{seed_crisis_event}/escalate",
            json={"reason": "高危用户需上级介入"},
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["status"] == "escalated"
        assert data["handled_action"] == "escalate"

    def test_escalate_reviewed_to_escalated(
        self, client: TestClient, as_role, seeded_user_id, seed_crisis_event_reviewed
    ):
        """reviewed → escalated：合法转换."""
        as_role("admin", 3)
        res = client.post(
            f"/api/v1/reviews/crisis-events/{seed_crisis_event_reviewed}/escalate",
            json={"reason": "咨询师处理后仍未缓解"},
        )
        assert res.status_code == 200
        assert res.json()["data"]["status"] == "escalated"

    def test_escalate_escalated_rejected(
        self, client: TestClient, as_role, seeded_user_id, seed_crisis_event_escalated
    ):
        """escalated → escalated：非法转换（已升级不能再升级），应返回 400."""
        as_role("admin", 3)
        res = client.post(
            f"/api/v1/reviews/crisis-events/{seed_crisis_event_escalated}/escalate",
            json={"reason": "再次升级"},
        )
        assert res.status_code == 400
        assert "非法状态转换" in res.json()["error"]["message"]

    def test_escalate_resolved_rejected(
        self, client: TestClient, as_role, seeded_user_id, seed_crisis_event_resolved
    ):
        """resolved → escalated：非法转换."""
        as_role("admin", 3)
        res = client.post(
            f"/api/v1/reviews/crisis-events/{seed_crisis_event_resolved}/escalate",
            json={"reason": "再升级"},
        )
        assert res.status_code == 400

    def test_escalate_missing_reason(
        self, client: TestClient, as_role, seeded_user_id, seed_crisis_event
    ):
        """缺必填字段 reason 返回 422."""
        as_role("admin", 3)
        res = client.post(
            f"/api/v1/reviews/crisis-events/{seed_crisis_event}/escalate",
            json={},
        )
        assert res.status_code == 422


# ===== close 端点 =====


class TestCloseCrisisEvent:
    """ISS-072: POST /api/v1/reviews/crisis-events/{id}/close"""

    def test_close_detected_to_resolved(
        self, client: TestClient, as_role, seeded_user_id, seed_crisis_event
    ):
        """detected → resolved：合法转换（管理员直接关闭）."""
        as_role("admin", 3)
        res = client.post(
            f"/api/v1/reviews/crisis-events/{seed_crisis_event}/close",
            json={"note": "误报，关闭"},
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["status"] == "resolved"
        assert data["handled_action"] == "resolved"

    def test_close_reviewed_to_resolved(
        self, client: TestClient, as_role, seeded_user_id, seed_crisis_event_reviewed
    ):
        """reviewed → resolved：合法转换."""
        as_role("admin", 3)
        res = client.post(
            f"/api/v1/reviews/crisis-events/{seed_crisis_event_reviewed}/close",
            json={"note": "已处理完毕"},
        )
        assert res.status_code == 200
        assert res.json()["data"]["status"] == "resolved"

    def test_close_escalated_to_resolved(
        self, client: TestClient, as_role, seeded_user_id, seed_crisis_event_escalated
    ):
        """escalated → resolved：合法转换."""
        as_role("admin", 3)
        res = client.post(
            f"/api/v1/reviews/crisis-events/{seed_crisis_event_escalated}/close",
            json={"note": "升级后已处置完毕"},
        )
        assert res.status_code == 200
        assert res.json()["data"]["status"] == "resolved"

    def test_close_resolved_rejected(
        self, client: TestClient, as_role, seeded_user_id, seed_crisis_event_resolved
    ):
        """resolved → resolved：非法转换（终态）."""
        as_role("admin", 3)
        res = client.post(
            f"/api/v1/reviews/crisis-events/{seed_crisis_event_resolved}/close",
            json={"note": "再次关闭"},
        )
        assert res.status_code == 400
        assert "非法状态转换" in res.json()["error"]["message"]

    def test_close_optional_note(
        self, client: TestClient, as_role, seeded_user_id, seed_crisis_event
    ):
        """note 可选，缺省时仍可关闭."""
        as_role("admin", 3)
        res = client.post(
            f"/api/v1/reviews/crisis-events/{seed_crisis_event}/close",
            json={},
        )
        assert res.status_code == 200
        assert res.json()["data"]["status"] == "resolved"


# ===== 状态机完整性测试 =====


class TestCrisisStateMachineIntegration:
    """ISS-072: 完整状态机集成测试 - detected → reviewed → escalated → resolved"""

    def test_full_lifecycle_handle_escalate_close(
        self, client: TestClient, as_role, seeded_user_id, db_session: AsyncSession
    ):
        """完整生命周期：detected → reviewed → escalated → resolved"""
        from tests.conftest import run

        as_role("admin", 3)

        # 1. 创建事件
        async def _create_event() -> int:
            event = CrisisEvent(
                user_id=1,
                trigger_source="text",
                crisis_keywords='["焦虑"]',
                crisis_score=90.0,
                input_summary="测试",
                status="detected",
            )
            db_session.add(event)
            await db_session.commit()
            await db_session.refresh(event)
            return event.id

        event_id = run(_create_event())

        # 2. detected → reviewed (handle)
        res = client.post(
            f"/api/v1/reviews/crisis-events/{event_id}/handle",
            json={"action": "notify_counselor", "note": "通知咨询师"},
        )
        assert res.status_code == 200
        assert res.json()["data"]["status"] == "reviewed"

        # 3. reviewed → escalated
        res = client.post(
            f"/api/v1/reviews/crisis-events/{event_id}/escalate",
            json={"reason": "需要上级介入"},
        )
        assert res.status_code == 200
        assert res.json()["data"]["status"] == "escalated"

        # 4. escalated → resolved (close)
        res = client.post(
            f"/api/v1/reviews/crisis-events/{event_id}/close",
            json={"note": "处置完毕"},
        )
        assert res.status_code == 200
        assert res.json()["data"]["status"] == "resolved"

        # 5. resolved 是终态，不可再变更
        res = client.post(
            f"/api/v1/reviews/crisis-events/{event_id}/handle",
            json={"action": "notify_counselor"},
        )
        assert res.status_code == 400
