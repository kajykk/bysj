"""v1.34: dedup 模块测试"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from app.models.admin import OperationLog
from app.monitoring.dedup import should_send
from app.monitoring.notifier import AlertPayload


def _make_log(
    fingerprint: str, age_minutes: int, action_type: str = "alert_fired"
) -> OperationLog:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    detail = json.dumps({"fingerprint": fingerprint, "rule": "Test", "severity": "P1"})
    return OperationLog(
        operator_id=None,
        operator_role="system",
        action_type=action_type,
        target_type="alert",
        target_id=None,
        detail=detail,
        created_at=now - timedelta(minutes=age_minutes),
    )


def _make_db_with_logs(logs: list[OperationLog]) -> AsyncMock:
    """构造一个返回指定 logs 的 mock async db."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = logs
    mock_db.execute.return_value = mock_result
    return mock_db


def _alert(fingerprint: str | None) -> AlertPayload:
    return AlertPayload(
        rule="Test",
        severity="P1",
        status="firing",
        message="test",
        fingerprint=fingerprint,
    )


async def test_should_send_no_fingerprint() -> None:
    """v1.34: 无 fingerprint 永远发送."""
    db = _make_db_with_logs([])
    result = await should_send(_alert(None), db)
    assert result is True


async def test_should_send_no_history() -> None:
    """v1.34: 无历史记录应发送."""
    db = _make_db_with_logs([])
    result = await should_send(_alert("fp-1"), db)
    assert result is True


async def test_should_skip_duplicate_within_5min() -> None:
    """v1.34: 5 分钟内同 fingerprint 不发送."""
    log = _make_log("fp-1", age_minutes=2)
    db = _make_db_with_logs([log])
    result = await should_send(_alert("fp-1"), db)
    assert result is False


async def test_should_send_again_after_5min() -> None:
    """v1.34: 超过 5 分钟再次发送."""
    log = _make_log("fp-1", age_minutes=10)
    db = _make_db_with_logs([log])
    result = await should_send(_alert("fp-1"), db)
    assert result is True


async def test_dedup_different_fingerprints_independent() -> None:
    """v1.34: 不同 fingerprint 互不影响."""
    log1 = _make_log("fp-1", age_minutes=1)
    db = _make_db_with_logs([log1])
    result = await should_send(_alert("fp-2"), db)
    assert result is True


async def test_dedup_resolved_does_not_block() -> None:
    """v1.34: SQL 已过滤 resolved, 空结果应发送."""
    # SQL 查询条件: action_type == 'alert_fired', 所以 resolved 不会被返回
    # mock 模拟 SQL 行为: 返回空列表
    db = _make_db_with_logs([])
    result = await should_send(_alert("fp-1"), db)
    assert result is True


async def test_dedup_respects_window() -> None:
    """v1.34: 自定义窗口生效."""
    log = _make_log("fp-1", age_minutes=3)
    db = _make_db_with_logs([log])
    # 5 分钟窗口 -> 跳过
    assert (await should_send(_alert("fp-1"), db, window=timedelta(minutes=5))) is False
    # 2 分钟窗口 -> 发送
    assert (await should_send(_alert("fp-1"), db, window=timedelta(minutes=2))) is True
