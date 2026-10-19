"""ROUND_18 · T6（审查报告 M9）：预警升级的幂等与状态前置校验。

缺陷原文（§2.2 M9）：同 mixin 的 ``handle_warning`` 有"已处理且动作不一致则拒绝"
的保护，``escalate_warning`` 没有 —— 一条已 ``ignored``（咨询师判断无需干预）的
预警可被再次升级，``handle_action`` 被改写、原 ``handle_note`` 被覆盖，且每次调用
都追加一条审计。事故复盘时，"当时判断无需干预"这一结论会被后来的升级抹掉。

判据（三条行为，均可被真实变异打红）：
1. 首次升级：状态/原因落库 + 一条 ``warning_escalate`` 审计；
2. 重复升级：幂等返回 True，**不追加第二条审计、不覆盖首次升级原因**；
3. ``ignored → escalated``：拒绝（False），原结论与审计条目保持不变。
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core.contracts import (
    ACTION_TYPE_WARNING_ESCALATE,
    ACTION_TYPE_WARNING_IGNORE,
    WARNING_ACTION_ESCALATE,
    WARNING_ACTION_IGNORE,
)
from app.models.admin import OperationLog
from app.models.risk import WarningNotification
from app.models.user import User
from app.services.counselor_service import CounselorService


def _mk(uid: int, username: str, role: str) -> User:
    from app.core.pii_crypto import compute_blind_index
    from app.core.security import get_password_hash

    email = f"{username}@test.com"
    return User(
        id=uid,
        username=username,
        email=email,
        email_hash=compute_blind_index(email, "email"),
        password_hash=get_password_hash("testpass123"),
        role=role,
        status="active",
    )


@pytest.fixture
async def warning(db_session):
    """学生 1、咨询师 2 / 3，一条分配给咨询师 2 的未处理预警。"""
    db_session.add_all(
        [
            _mk(1, "r18_w_user", "user"),
            _mk(2, "r18_w_counselor", "counselor"),
            _mk(3, "r18_w_other", "counselor"),
        ]
    )
    await db_session.flush()
    row = WarningNotification(
        id=100,
        user_id=1,
        counselor_id=2,
        current_level=5,
        previous_level=3,
        trigger_reason="连续两次评估升级",
        is_read=False,
        is_handled=False,
    )
    db_session.add(row)
    await db_session.commit()
    return row


async def _audit_count(db, action_type: str) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(OperationLog).where(
                OperationLog.action_type == action_type
            )
        )
    ).scalar_one()


async def _reload(db, warning_id: int) -> WarningNotification:
    stmt = select(WarningNotification).where(WarningNotification.id == warning_id)
    return (await db.execute(stmt)).scalar_one()


async def test_escalate_first_time_sets_state_and_audit(warning, db_session):
    service = CounselorService(db_session)

    ok = await service.escalate_warning(2, 100, "已建议转介精神科")

    assert ok is True
    row = await _reload(db_session, 100)
    assert row.is_handled is True
    assert row.handle_action == WARNING_ACTION_ESCALATE
    assert row.handle_note == "已建议转介精神科"
    assert row.handled_at is not None
    assert await _audit_count(db_session, ACTION_TYPE_WARNING_ESCALATE) == 1


async def test_escalate_twice_is_idempotent(warning, db_session):
    service = CounselorService(db_session)
    await service.escalate_warning(2, 100, "首次升级原因")

    again = await service.escalate_warning(2, 100, "重复点击带进来的新原因")

    assert again is True
    row = await _reload(db_session, 100)
    # 首次升级原因保留（复盘中"当时为什么升级"不能被后来的请求覆盖）
    assert row.handle_note == "首次升级原因"
    assert await _audit_count(db_session, ACTION_TYPE_WARNING_ESCALATE) == 1


async def test_escalate_after_ignore_is_rejected(warning, db_session):
    service = CounselorService(db_session)
    handled = await service.handle_warning(
        2, 100, WARNING_ACTION_IGNORE, "评估为情境性波动，无需干预"
    )
    assert handled is True

    blocked = await service.escalate_warning(2, 100, "事后想改成升级")

    assert blocked is False
    row = await _reload(db_session, 100)
    assert row.handle_action == WARNING_ACTION_IGNORE
    assert row.handle_note == "评估为情境性波动，无需干预"
    assert await _audit_count(db_session, ACTION_TYPE_WARNING_ESCALATE) == 0
    assert await _audit_count(db_session, ACTION_TYPE_WARNING_IGNORE) == 1


async def test_escalate_other_counselor_warning_is_rejected(warning, db_session):
    """反向对照：非本人预警仍然拒绝（既有行为，未被本轮改动削弱）。"""
    service = CounselorService(db_session)

    assert await service.escalate_warning(3, 100, "越权升级") is False
    row = await _reload(db_session, 100)
    assert row.is_handled is False


async def test_escalate_missing_warning_returns_false(db_session):
    service = CounselorService(db_session)
    assert await service.escalate_warning(2, 99999, "不存在") is False
