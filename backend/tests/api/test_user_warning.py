from __future__ import annotations

from datetime import time

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.contracts import ACTION_TYPE_WARNING_READ, ACTION_TYPE_WARNING_READ_ALL
from app.models.admin import OperationLog
from app.models.risk import WarningNotification, WarningSetting
from tests.conftest import run


def _seed_warning(db_session: AsyncSession, user_id: int = 1, counselor_id: int = 2) -> int:
    async def _seed() -> int:
        warning = WarningNotification(
            user_id=user_id,
            counselor_id=counselor_id,
            current_level=3,
            previous_level=2,
            trigger_reason="stress spike detected",
            is_read=False,
            is_handled=False,
        )
        db_session.add(warning)
        await db_session.commit()
        await db_session.refresh(warning)
        return warning.id

    return run(_seed())


def test_list_warnings_returns_enriched_items(client: TestClient, db_session: AsyncSession, seeded_user_id: int) -> None:
    warning_id = _seed_warning(db_session, user_id=seeded_user_id)

    res = client.get("/api/v1/user/warnings")
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["total"] == 1
    assert body["items"][0]["id"] == warning_id
    assert body["items"][0]["risk_level"] == "high"
    assert body["items"][0]["risk_level_label"] == "high"
    assert body["items"][0]["status"] == "pending"


def test_mark_warning_read_marks_single_item_and_logs(client: TestClient, db_session: AsyncSession, seeded_user_id: int) -> None:
    warning_id = _seed_warning(db_session, user_id=seeded_user_id)

    res = client.put(f"/api/v1/user/warnings/{warning_id}/read")
    assert res.status_code == 200

    async def _assert_state() -> tuple[bool, int]:
        warning = (await db_session.execute(select(WarningNotification).where(WarningNotification.id == warning_id))).scalar_one()
        log_count = len((await db_session.execute(select(OperationLog).where(OperationLog.action_type == ACTION_TYPE_WARNING_READ))).scalars().all())
        return warning.is_read, log_count

    is_read, log_count = run(_assert_state())
    assert is_read is True
    assert log_count == 1


def test_mark_all_warning_read_marks_all_and_logs(client: TestClient, db_session: AsyncSession, seeded_user_id: int) -> None:
    _seed_warning(db_session, user_id=seeded_user_id)
    _seed_warning(db_session, user_id=seeded_user_id)

    res = client.put("/api/v1/user/warnings/read-all")
    assert res.status_code == 200
    assert res.json()["data"]["count"] == 2

    async def _assert_state() -> tuple[int, int]:
        unread = len((await db_session.execute(select(WarningNotification).where(WarningNotification.user_id == seeded_user_id, WarningNotification.is_read.is_(False)))).scalars().all())
        logs = len((await db_session.execute(select(OperationLog).where(OperationLog.action_type == ACTION_TYPE_WARNING_READ_ALL))).scalars().all())
        return unread, logs

    unread, logs = run(_assert_state())
    assert unread == 0
    assert logs == 1


def test_warning_setting_round_trip(client: TestClient, db_session: AsyncSession, seeded_user_id: int) -> None:
    res = client.get("/api/v1/user/warning-settings")
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["threshold_level"] == 2

    update = client.put(
        "/api/v1/user/warning-settings",
        json={
            "notify_channels": {"in_app": True, "email": False},
            "threshold_level": 4,
            "quiet_hours_start": "22:00:00",
            "quiet_hours_end": "07:00:00",
        },
    )
    assert update.status_code == 200

    async def _assert_state() -> tuple[int, dict, time | None, time | None, int]:
        setting = (await db_session.execute(select(WarningSetting).where(WarningSetting.user_id == seeded_user_id))).scalar_one()
        logs = len((await db_session.execute(select(OperationLog).where(OperationLog.action_type == "update_warning_setting"))).scalars().all())
        return setting.threshold_level, setting.notify_channels, setting.quiet_hours_start, setting.quiet_hours_end, logs

    threshold_level, channels, quiet_start, quiet_end, logs = run(_assert_state())
    assert threshold_level == 4
    assert channels["email"] is False
    assert quiet_start == time(22, 0)
    assert quiet_end == time(7, 0)
    assert logs == 1
