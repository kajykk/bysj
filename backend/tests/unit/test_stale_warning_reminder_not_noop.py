"""P0-FIX-2026-10-11: stale_warning_reminder 不能是空跑任务。

背景（来自 2026-10-11 全量源码审查）：

``scheduler._stale_warning_reminder_impl`` 修复前只对每条滞留预警打一行
``logger.info`` 就结束 —— 不写库、不上报、不推送。任务名叫"提醒"，实际什么都没做。

这在心理健康场景里是**失效的兜底**而非"功能没做完"：风险扫描负责产生预警，
本任务本该在预警被漏掉时兜底，结果它自己也只在日志里嘟囔，运维看不到、
咨询师收不到、事后无法复盘。

修复后它做两件真实的事：写 OperationLog 留痕 + error 级 Sentry 上报。
本测试固化这些性质。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from app.models.admin import OperationLog
from app.models.risk import WarningNotification
from app.tasks import scheduler as scheduler_module


@pytest.fixture
def stale_env(monkeypatch, db_session):
    """把 impl 依赖的 AsyncSessionLocal 换成本测试的 db_session。"""

    class _CM:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(scheduler_module, "AsyncSessionLocal", lambda: _CM())


async def _make_stale_warning(db_session, user_id: int, counselor_id: int | None = 2) -> int:
    warn = WarningNotification(
        user_id=user_id,
        counselor_id=counselor_id,
        current_level=3,
        trigger_reason="STALE_REMINDER_TEST",
        is_handled=False,
        created_at=datetime.utcnow() - timedelta(hours=48),
    )
    db_session.add(warn)
    await db_session.flush()
    return warn.id


class TestStaleWarningReminderIsNotANoOp:
    @pytest.mark.asyncio
    async def test_writes_audit_log_for_stale_warning(
        self, db_session, stale_env, seeded_user_id
    ):
        from sqlalchemy import select

        warning_id = await _make_stale_warning(db_session, seeded_user_id)

        result = await scheduler_module._stale_warning_reminder_impl()
        assert result["reminded"] == 1

        logs = (
            (
                await db_session.execute(
                    select(OperationLog).where(
                        OperationLog.action_type == "warning.stale_reminder",
                        OperationLog.target_id == warning_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(logs) == 1, (
            "滞留预警未留下 OperationLog —— 任务仍然只是打日志，无法复盘"
        )
        detail = json.loads(logs[0].detail)
        assert detail["counselor_id"] == 2
        assert detail["user_id"] == seeded_user_id
        assert detail["current_level"] == 3

    @pytest.mark.asyncio
    async def test_unassigned_warning_also_leaves_trace(
        self, db_session, stale_env, seeded_user_id
    ):
        """没有归属咨询师的预警同样要留痕 —— 否则"分配环节漏掉"在数据上看不见。"""
        from sqlalchemy import select

        warning_id = await _make_stale_warning(
            db_session, seeded_user_id, counselor_id=None
        )

        result = await scheduler_module._stale_warning_reminder_impl()
        assert result["reminded"] == 1

        log = (
            (
                await db_session.execute(
                    select(OperationLog).where(
                        OperationLog.action_type == "warning.stale_reminder",
                        OperationLog.target_id == warning_id,
                    )
                )
            )
            .scalars()
            .first()
        )
        assert log is not None
        assert json.loads(log.detail)["counselor_id"] is None

    @pytest.mark.asyncio
    async def test_handled_warning_is_not_reminded(self, db_session, stale_env, seeded_user_id):
        from sqlalchemy import select

        warn = WarningNotification(
            user_id=seeded_user_id,
            counselor_id=2,
            current_level=3,
            trigger_reason="HANDLED_TEST",
            is_handled=True,
            created_at=datetime.utcnow() - timedelta(hours=48),
        )
        db_session.add(warn)
        await db_session.flush()

        result = await scheduler_module._stale_warning_reminder_impl()
        assert result["reminded"] == 0

        logs = (
            (
                await db_session.execute(
                    select(OperationLog).where(
                        OperationLog.action_type == "warning.stale_reminder"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert logs == []

    @pytest.mark.asyncio
    async def test_low_level_warning_is_not_reminded(
        self, db_session, stale_env, seeded_user_id
    ):
        """current_level < 3 的不属于高等级，不该产生噪声留痕。"""
        warn = WarningNotification(
            user_id=seeded_user_id,
            counselor_id=2,
            current_level=1,
            trigger_reason="LOW_LEVEL_TEST",
            is_handled=False,
            created_at=datetime.utcnow() - timedelta(hours=48),
        )
        db_session.add(warn)
        await db_session.flush()

        assert (await scheduler_module._stale_warning_reminder_impl())["reminded"] == 0

    @pytest.mark.asyncio
    async def test_does_not_flip_handled_flag(
        self, db_session, stale_env, seeded_user_id
    ):
        """本任务不得抢写 is_handled —— 那会与咨询师的真实处理动作打架。"""
        warning_id = await _make_stale_warning(db_session, seeded_user_id)

        await scheduler_module._stale_warning_reminder_impl()
        await db_session.refresh(
            (
                await db_session.get(WarningNotification, warning_id)
            )
        )
        still = await db_session.get(WarningNotification, warning_id)
        assert still.is_handled is False

    @pytest.mark.asyncio
    async def test_sentry_reported_when_reminders_exist(
        self, db_session, stale_env, seeded_user_id, monkeypatch
    ):
        """有滞留时必须 error 级上报，否则运维仍然看不到。"""
        captured: list[dict] = []

        import app.core.sentry as sentry_module

        monkeypatch.setattr(
            sentry_module, "capture_message", lambda *a, **kw: captured.append(kw or a)
        )

        await _make_stale_warning(db_session, seeded_user_id)
        await scheduler_module._stale_warning_reminder_impl()

        assert captured, "有滞留预警但未上报"
        level = (captured[0].get("level") if isinstance(captured[0], dict) else None)
        assert level == "error"

    @pytest.mark.asyncio
    async def test_silent_when_nothing_stale(
        self, db_session, stale_env, seeded_user_id, monkeypatch
    ):
        """无滞留时必须完全静默，否则每次调度都往 Sentry 灌噪声。"""
        captured: list = []
        import app.core.sentry as sentry_module

        monkeypatch.setattr(
            sentry_module, "capture_message", lambda *a, **kw: captured.append(a)
        )

        result = await scheduler_module._stale_warning_reminder_impl()
        assert result["reminded"] == 0
        assert captured == []