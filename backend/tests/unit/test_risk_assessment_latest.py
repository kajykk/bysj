"""uq_risk_assessments_latest 并发写入回归测试。

背景: 集成验证 E2E 期间后台日志出现 ``uq_risk_assessments_latest`` 唯一约束
冲突，但 HTTP 响应仍是 200，属于被 200 掩盖的写入失败。根因是 3 条保存路径
（请求内 2 条 + fire-and-forget 独立 session 1 条）的「清旧 + 插新」是
check-then-act，跨事务没有互斥。

本测试锁定两层契约:
1. 连续两次保存后，目标用户只存在 1 条 ``is_latest=True``；
2. 写之前必须先取 PG 事务级 advisory lock（并发互斥的来源），且 UPDATE
   必须发生在 INSERT 之前。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.risk import RiskAssessment
from app.services.risk_assessment_latest import (
    LATEST_ASSESSMENT_LOCK_NAMESPACE,
    save_latest_assessment,
)


def _assessment(user_id: int, score: float, level: int) -> RiskAssessment:
    return RiskAssessment(
        user_id=user_id,
        risk_score=score,
        risk_level=level,
        models_used=[],
        risk_factors=[],
        assessment_type="structured",
        is_latest=True,
    )


class _RecordingSession:
    """记录执行顺序的假 session（只覆盖 helper 用到的接口）。"""

    def __init__(self, dialect_name: str) -> None:
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect_name))
        self.calls: list[tuple[str, dict | None]] = []
        self.added: list[RiskAssessment] = []
        self.flushed = False

    async def execute(self, statement, params=None):
        self.calls.append((str(statement), params))

    def add(self, obj: RiskAssessment) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushed = True


@pytest.mark.asyncio
async def test_two_consecutive_saves_leave_single_latest(db_session, seeded_user_id):
    """连续两次保存（最接近 E2E 的重复触发）只保留一条 is_latest。"""
    first = _assessment(seeded_user_id, 10.0, 0)
    await save_latest_assessment(db_session, first)

    second = _assessment(seeded_user_id, 90.0, 3)
    await save_latest_assessment(db_session, second)

    rows = (
        await db_session.execute(
            select(RiskAssessment.id, RiskAssessment.is_latest).where(
                RiskAssessment.user_id == seeded_user_id
            )
        )
    ).all()

    assert len(rows) == 2, "两次保存应各自留下一条历史记录"
    latest_rows = [row for row in rows if row.is_latest]
    assert len(latest_rows) == 1, "uq_risk_assessments_latest 只允许一条 is_latest"
    assert second.is_latest is True


@pytest.mark.asyncio
async def test_postgres_locks_before_clearing_and_inserting():
    """PG 上必须是「取 advisory lock → 清旧 → 插新」的顺序。

    没有这把锁时，两个独立事务的 UPDATE 互不可见，后提交者会在唯一索引上
    冲突；这正是 E2E 日志里的报错。
    """
    session = _RecordingSession("postgresql")
    assessment = _assessment(42, 60.0, 2)

    await save_latest_assessment(session, assessment)

    assert len(session.calls) == 2
    lock_sql, lock_params = session.calls[0]
    assert "pg_advisory_xact_lock" in lock_sql
    assert lock_params is not None
    assert lock_params["namespace"] == LATEST_ASSESSMENT_LOCK_NAMESPACE
    assert lock_params["user_id"] == 42

    update_sql, _ = session.calls[1]
    assert update_sql.startswith("UPDATE risk_assessments")
    assert "is_latest" in update_sql

    assert session.added == [assessment]
    assert session.flushed is True


@pytest.mark.asyncio
async def test_sqlite_skips_advisory_lock_but_still_clears_first():
    """SQLite 无 advisory lock（单写者），但仍须先清旧再插新。"""
    session = _RecordingSession("sqlite")
    assessment = _assessment(7, 30.0, 1)

    await save_latest_assessment(session, assessment)

    assert len(session.calls) == 1
    update_sql, _ = session.calls[0]
    assert update_sql.startswith("UPDATE risk_assessments")
    assert session.added == [assessment]
