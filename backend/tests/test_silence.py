"""v1.34: silence 模块测试"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.admin import AlertSilence
from app.monitoring.notifier import AlertPayload
from app.monitoring.silence import _matcher_matches, is_silenced


def _alert(labels: dict) -> AlertPayload:
    return AlertPayload(
        rule="Test",
        severity="P1",
        status="firing",
        message="test",
        labels=labels,
    )


def _silence(
    silence_id: int = 1,
    matcher: dict | None = None,
    starts_offset_min: int = -10,
    ends_offset_min: int = 10,
    is_active: bool = True,
) -> AlertSilence:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return AlertSilence(
        id=silence_id,
        name=f"silence-{silence_id}",
        matcher=matcher or {},
        starts_at=now + timedelta(minutes=starts_offset_min),
        ends_at=now + timedelta(minutes=ends_offset_min),
        created_by=None,
        comment="test",
        is_active=is_active,
    )


# ===== matcher 单元测试 =====


def test_matcher_empty_matches_all() -> None:
    """v1.34: 空 matcher 匹配所有."""
    assert _matcher_matches({}, {"alertname": "X", "severity": "P1"}) is True


def test_matcher_single_key() -> None:
    """v1.34: 单键匹配."""
    assert _matcher_matches({"severity": "P1"}, {"severity": "P1"}) is True
    assert _matcher_matches({"severity": "P1"}, {"severity": "P0"}) is False


def test_matcher_multiple_keys_and() -> None:
    """v1.34: 多键 AND 逻辑."""
    assert _matcher_matches(
        {"alertname": "X", "severity": "P1"},
        {"alertname": "X", "severity": "P1"},
    ) is True
    assert _matcher_matches(
        {"alertname": "X", "severity": "P1"},
        {"alertname": "X", "severity": "P0"},
    ) is False
    assert _matcher_matches(
        {"alertname": "X", "severity": "P1"},
        {"alertname": "Y", "severity": "P1"},
    ) is False


def test_matcher_missing_key_in_labels() -> None:
    """v1.34: labels 缺少 key 不匹配."""
    assert _matcher_matches({"alertname": "X"}, {}) is False


# ===== is_silenced 集成测试 =====


def _make_db_with_silences(silences: list[AlertSilence]) -> AsyncMock:
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = silences
    mock_db.execute.return_value = mock_result
    return mock_db


async def test_no_silences_not_silenced() -> None:
    """v1.34: 无静默规则应正常发送."""
    db = _make_db_with_silences([])
    silenced, rule = await is_silenced(_alert({"alertname": "X"}), db)
    assert silenced is False
    assert rule is None


async def test_empty_matcher_silences_all() -> None:
    """v1.34: 空 matcher 静默所有."""
    db = _make_db_with_silences([_silence(matcher={})])
    silenced, rule = await is_silenced(_alert({"alertname": "X"}), db)
    assert silenced is True
    assert rule is not None


async def test_alertname_match() -> None:
    """v1.34: alertname 匹配."""
    db = _make_db_with_silences([_silence(matcher={"alertname": "HighErrorRate"})])
    silenced, _ = await is_silenced(_alert({"alertname": "HighErrorRate"}), db)
    assert silenced is True


async def test_alertname_no_match() -> None:
    """v1.34: alertname 不匹配."""
    db = _make_db_with_silences([_silence(matcher={"alertname": "HighErrorRate"})])
    silenced, _ = await is_silenced(_alert({"alertname": "Other"}), db)
    assert silenced is False


async def test_severity_match() -> None:
    """v1.34: severity 匹配."""
    db = _make_db_with_silences([_silence(matcher={"severity": "P0"})])
    silenced, _ = await is_silenced(_alert({"severity": "P0"}), db)
    assert silenced is True


async def test_combined_match() -> None:
    """v1.34: 组合匹配 (alertname + severity)."""
    db = _make_db_with_silences([_silence(matcher={"alertname": "X", "severity": "P0"})])
    silenced, _ = await is_silenced(_alert({"alertname": "X", "severity": "P0"}), db)
    assert silenced is True
    silenced, _ = await is_silenced(_alert({"alertname": "X", "severity": "P1"}), db)
    assert silenced is False


async def test_multiple_silences_first_match() -> None:
    """v1.34: 多条静默规则应返回首个匹配."""
    s1 = _silence(silence_id=1, matcher={"alertname": "X"})
    s2 = _silence(silence_id=2, matcher={"alertname": "X"})
    db = _make_db_with_silences([s1, s2])
    silenced, rule = await is_silenced(_alert({"alertname": "X"}), db)
    assert silenced is True
    assert rule.id == 1
