"""来访者预警邮件（services.warning_email）单测.

覆盖：绑定咨询师解析、角色/状态/租户/邮箱校验、投递失败隔离、
``warning.created`` 事件接线。数据库使用 conftest 的 db_session
（commit -> flush，每用例回滚）。
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.states import BindingStatus
from app.models.tenant import Tenant
from app.models.user import User, UserCounselorBinding
from app.services import warning_email


@pytest.fixture
def mock_send(monkeypatch):
    mock = AsyncMock(return_value=True)
    monkeypatch.setattr(
        warning_email.EmailService, "send_warning_alert_email", mock
    )
    return mock


async def _bind(db_session, *, status: str = BindingStatus.ACTIVE) -> None:
    db_session.add(
        UserCounselorBinding(
            user_id=1, counselor_id=2, bind_code="B001", status=status
        )
    )
    await db_session.flush()


async def _send(db_session, **overrides) -> bool:
    kwargs = {
        "warning_id": 42,
        "user_id": 1,
        "counselor_id": 2,
        "risk_level": 3,
        "trigger_reason": "风险等级从2级上升到3级",
        "db": db_session,
    }
    kwargs.update(overrides)
    return await warning_email.send_warning_email(**kwargs)


class TestResolveAndSend:
    async def test_sends_to_bound_counselor(
        self, db_session, seeded_user_id, mock_send
    ):
        await _bind(db_session)

        ok = await _send(db_session)

        assert ok is True
        mock_send.assert_awaited_once()
        kwargs = mock_send.await_args.kwargs
        assert kwargs["email"] == "c@test.com"
        assert kwargs["client_name"] == "seed_user"
        assert kwargs["client_user_id"] == 1
        assert kwargs["risk_level"] == 3
        assert kwargs["trigger_reason"] == "风险等级从2级上升到3级"
        assert kwargs["warning_id"] == 42

    async def test_skips_without_counselor(
        self, db_session, seeded_user_id, mock_send
    ):
        assert await _send(db_session, counselor_id=None) is False
        mock_send.assert_not_awaited()

    async def test_skips_without_active_binding(
        self, db_session, seeded_user_id, mock_send
    ):
        assert await _send(db_session) is False
        mock_send.assert_not_awaited()

    async def test_skips_unbound_binding(
        self, db_session, seeded_user_id, mock_send
    ):
        await _bind(db_session, status=BindingStatus.INACTIVE)

        assert await _send(db_session) is False
        mock_send.assert_not_awaited()

    async def test_skips_non_counselor_role(
        self, db_session, seeded_user_id, mock_send
    ):
        # 用户 3 是 admin，即使被错误地写成 counselor_id 也不得收预警
        assert await _send(db_session, counselor_id=3) is False
        mock_send.assert_not_awaited()

    async def test_skips_inactive_counselor(
        self, db_session, seeded_user_id, mock_send
    ):
        await _bind(db_session)
        counselor = await db_session.get(User, 2)
        counselor.status = "inactive"
        await db_session.flush()

        assert await _send(db_session) is False
        mock_send.assert_not_awaited()

    async def test_skips_cross_tenant_counselor(
        self, db_session, seeded_user_id, mock_send
    ):
        db_session.add(
            Tenant(
                id=2,
                name="预警邮件测试租户",
                code=f"warning_email_{uuid4().hex[:8]}",
                status="active",
            )
        )
        await db_session.flush()
        await _bind(db_session)
        counselor = await db_session.get(User, 2)
        counselor.tenant_id = 2
        await db_session.flush()

        assert await _send(db_session) is False
        mock_send.assert_not_awaited()

    async def test_skips_invalid_email(
        self, db_session, seeded_user_id, mock_send
    ):
        await _bind(db_session)
        counselor = await db_session.get(User, 2)
        counselor.email = "not-an-email"
        await db_session.flush()

        assert await _send(db_session) is False
        mock_send.assert_not_awaited()

    async def test_delivery_failure_is_isolated(
        self, db_session, seeded_user_id, mock_send, caplog, monkeypatch
    ):
        await _bind(db_session)
        mock_send.side_effect = ValueError("smtp down")
        failures = []
        monkeypatch.setattr(
            warning_email, "record_silent_degradation", failures.append
        )

        with caplog.at_level(logging.ERROR, logger="app.services.warning_email"):
            ok = await _send(db_session)

        assert ok is False
        assert failures == ["services.warning_email.delivery_failed"]
        assert any(
            r.levelno >= logging.ERROR and "warning_email.delivery_failed" in r.message
            for r in caplog.records
        )


class TestEventHandler:
    async def test_maps_event_payload(self, monkeypatch):
        mock = AsyncMock(return_value=True)
        monkeypatch.setattr(warning_email, "send_warning_email", mock)

        await warning_email._on_warning_created(
            {
                "warning_id": 9,
                "user_id": 1,
                "risk_assessment_id": 100,
                "previous_level": 2,
                "current_level": 3,
                "trigger_reason": "升级",
                "counselor_id": 2,
            }
        )

        mock.assert_awaited_once_with(
            warning_id=9,
            user_id=1,
            counselor_id=2,
            risk_level=3,
            trigger_reason="升级",
        )

    async def test_invalid_payload_is_ignored(self, monkeypatch):
        mock = AsyncMock()
        monkeypatch.setattr(warning_email, "send_warning_email", mock)

        await warning_email._on_warning_created({"warning_id": 9})

        mock.assert_not_awaited()

    async def test_handler_never_raises(self, monkeypatch):
        monkeypatch.setattr(
            warning_email,
            "send_warning_email",
            AsyncMock(side_effect=RuntimeError("boom")),
        )
        failures = []
        monkeypatch.setattr(
            warning_email, "record_silent_degradation", failures.append
        )

        await warning_email._on_warning_created(
            {"warning_id": 9, "user_id": 1, "current_level": 3, "counselor_id": 2}
        )

        assert failures == ["services.warning_email.event_handler_failed"]

    def test_register_is_idempotent(self, monkeypatch):
        monkeypatch.setattr(warning_email, "_REGISTERED", False)
        subscribe = MagicMock()
        monkeypatch.setattr(warning_email.event_bus, "subscribe", subscribe)

        warning_email.register_warning_email_handler()
        warning_email.register_warning_email_handler()

        subscribe.assert_called_once_with(
            "warning.created", warning_email._on_warning_created
        )
