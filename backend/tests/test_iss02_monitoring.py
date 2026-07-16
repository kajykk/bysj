"""ISS-02 第九轮：app/monitoring/* 内实现聚焦测试（numpy-free，本地可全绿）。

覆盖 6 个 0% 模块的真实业务逻辑（正是第八轮 Celery 包装胶水所包裹的内实现）：
- silence        : _matcher_matches（纯）+ is_silenced（mock db）
- dedup_lock     : 内存统计 API + try_acquire_lock/release_lock（mock aioredis）+ flush_lock_stats（mock db）
- dedup          : should_send（mock try_acquire_lock + mock db）
- alerting       : AlertingEngine.evaluate / _send_notification（mock requests）+ create_default_rules
- escalation     : compute_escalation（纯，多分支）+ run_escalation_check + apply_escalation（mock CompositeNotifier）
- am_sync        : local_to_am_format（纯）+ _get_am_url/_get_am_auth + _write_sync_log + push/delete/pull（mock _HTTP_SESSION）

全部以 mock DB session / redis / HTTP 驱动，不依赖真实后端、celery 或 numpy。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.monitoring import silence, dedup, dedup_lock, alerting, escalation, am_sync


# --------------------------------------------------------------------------- #
#  helpers
# --------------------------------------------------------------------------- #
def _mock_db_execute(rows):
    """构造一个 await db.execute(stmt) -> .scalars().all() == rows 的 mock db。"""
    scalar_res = MagicMock()
    scalar_res.all.return_value = rows
    exec_res = MagicMock()
    exec_res.scalars.return_value = scalar_res
    db = MagicMock()
    db.execute = AsyncMock(return_value=exec_res)
    return db


@pytest.fixture(autouse=True)
def _reset_dedup_stats():
    dedup_lock.reset_stats()
    yield
    dedup_lock.reset_stats()


# --------------------------------------------------------------------------- #
#  silence.py
# --------------------------------------------------------------------------- #
def test_matcher_matches_empty():
    assert silence._matcher_matches({}, {"a": "1"}) is True


def test_matcher_matches_exact():
    assert silence._matcher_matches({"a": "1"}, {"a": "1"}) is True


def test_matcher_matches_mismatch_value():
    assert silence._matcher_matches({"a": "1"}, {"a": "2"}) is False


def test_matcher_matches_missing_key():
    assert silence._matcher_matches({"a": "1"}, {}) is False


def test_matcher_matches_extra_labels_ok():
    assert silence._matcher_matches({"a": "1"}, {"a": "1", "b": "2"}) is True


async def test_is_silenced_match():
    rows = [SimpleNamespace(matcher={"alertname": "X"}, id=1, name="s1")]
    db = _mock_db_execute(rows)
    alert = SimpleNamespace(labels={"alertname": "X"}, fingerprint="f")
    silenced, sil = await silence.is_silenced(alert, db)
    assert silenced is True and sil.id == 1


async def test_is_silenced_no_match():
    rows = [SimpleNamespace(matcher={"alertname": "Y"}, id=1, name="s1")]
    db = _mock_db_execute(rows)
    alert = SimpleNamespace(labels={"alertname": "X"}, fingerprint="f")
    silenced, sil = await silence.is_silenced(alert, db)
    assert silenced is False and sil is None


async def test_is_silenced_no_active():
    db = _mock_db_execute([])
    alert = SimpleNamespace(labels={}, fingerprint="f")
    silenced, sil = await silence.is_silenced(alert, db)
    assert silenced is False and sil is None


# --------------------------------------------------------------------------- #
#  dedup_lock.py
# --------------------------------------------------------------------------- #
def test_stats_reset_and_snapshot():
    dedup_lock.reset_stats()
    assert dedup_lock.get_stats() == {"acquired": 0, "skipped": 0, "fallback": 0, "errors": 0}
    dedup_lock._stats["acquired"] = 5
    assert dedup_lock.get_stats()["acquired"] == 5


def test_last_flush_at():
    dedup_lock.set_last_flush_at("2026-01-01T00:00:00Z")
    assert dedup_lock.get_last_flush_at() == "2026-01-01T00:00:00Z"
    dedup_lock.set_last_flush_at(None)
    assert dedup_lock.get_last_flush_at() is None


async def test_try_acquire_lock_empty_fingerprint():
    assert await dedup_lock.try_acquire_lock("") is True


async def test_try_acquire_lock_acquired(monkeypatch):
    client = MagicMock()
    client.set = AsyncMock(return_value=True)
    client.aclose = AsyncMock()
    fake = MagicMock()
    fake.from_url = MagicMock(return_value=client)
    monkeypatch.setattr(dedup_lock, "aioredis", fake)
    assert await dedup_lock.try_acquire_lock("fp1", redis_url="redis://x") is True
    assert dedup_lock.get_stats()["acquired"] == 1


async def test_try_acquire_lock_not_acquired(monkeypatch):
    client = MagicMock()
    client.set = AsyncMock(return_value=None)  # SETNX 未获取
    client.aclose = AsyncMock()
    fake = MagicMock()
    fake.from_url = MagicMock(return_value=client)
    monkeypatch.setattr(dedup_lock, "aioredis", fake)
    assert await dedup_lock.try_acquire_lock("fp1", redis_url="redis://x") is False
    assert dedup_lock.get_stats()["skipped"] == 1


async def test_try_acquire_lock_redis_exception_fallback(monkeypatch):
    client = MagicMock()
    client.set = AsyncMock(side_effect=RuntimeError("boom"))
    client.aclose = AsyncMock()
    fake = MagicMock()
    fake.from_url = MagicMock(return_value=client)
    monkeypatch.setattr(dedup_lock, "aioredis", fake)
    # 降级：Redis 不可用返回 True（允许发送，后续 SQL dedup 二次校验）
    assert await dedup_lock.try_acquire_lock("fp1", redis_url="redis://x") is True
    assert dedup_lock.get_stats()["fallback"] == 1


async def test_release_lock_empty_fingerprint():
    assert await dedup_lock.release_lock("") is False


async def test_release_lock(monkeypatch):
    client = MagicMock()
    client.delete = AsyncMock(return_value=1)
    client.aclose = AsyncMock()
    fake = MagicMock()
    fake.from_url = MagicMock(return_value=client)
    monkeypatch.setattr(dedup_lock, "aioredis", fake)
    assert await dedup_lock.release_lock("fp1", redis_url="redis://x") is True


async def test_flush_lock_stats_all_zero():
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    assert await dedup_lock.flush_lock_stats(db) is True
    db.add.assert_not_called()


async def test_flush_lock_stats_writes(monkeypatch):
    dedup_lock._stats["acquired"] = 3
    monkeypatch.setattr("app.core.instance.get_instance_id", lambda: "inst-1")
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    assert await dedup_lock.flush_lock_stats(db) is True
    db.add.assert_called_once()
    assert dedup_lock.get_stats()["acquired"] == 0
    assert dedup_lock.get_last_flush_at() is not None


async def test_flush_lock_stats_failure(monkeypatch):
    dedup_lock._stats["acquired"] = 2
    monkeypatch.setattr("app.core.instance.get_instance_id", lambda: "inst-1")
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock(side_effect=RuntimeError("db down"))
    assert await dedup_lock.flush_lock_stats(db) is False
    assert dedup_lock.get_stats()["acquired"] == 2  # 失败不清零


# --------------------------------------------------------------------------- #
#  dedup.py
# --------------------------------------------------------------------------- #
async def test_should_send_no_fingerprint():
    alert = SimpleNamespace(fingerprint="")
    assert await dedup.should_send(alert, MagicMock()) is True


async def test_should_send_lock_not_acquired(monkeypatch):
    monkeypatch.setattr(dedup_lock, "try_acquire_lock", AsyncMock(return_value=False))
    alert = SimpleNamespace(fingerprint="fp1")
    assert await dedup.should_send(alert, MagicMock()) is False


async def test_should_send_no_recent(monkeypatch):
    monkeypatch.setattr(dedup_lock, "try_acquire_lock", AsyncMock(return_value=True))
    db = _mock_db_execute([])
    alert = SimpleNamespace(fingerprint="fp1")
    assert await dedup.should_send(alert, db) is True


async def test_should_send_recent_match(monkeypatch):
    monkeypatch.setattr(dedup_lock, "try_acquire_lock", AsyncMock(return_value=True))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row = SimpleNamespace(created_at=now, detail=json.dumps({"fingerprint": "fp1"}))
    db = _mock_db_execute([row])
    alert = SimpleNamespace(fingerprint="fp1")
    assert await dedup.should_send(alert, db) is False


async def test_should_send_old_match(monkeypatch):
    monkeypatch.setattr(dedup_lock, "try_acquire_lock", AsyncMock(return_value=True))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row = SimpleNamespace(created_at=now - timedelta(minutes=10), detail=json.dumps({"fingerprint": "fp1"}))
    db = _mock_db_execute([row])
    alert = SimpleNamespace(fingerprint="fp1")
    assert await dedup.should_send(alert, db) is True


async def test_should_send_bad_detail(monkeypatch):
    monkeypatch.setattr(dedup_lock, "try_acquire_lock", AsyncMock(return_value=True))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row = SimpleNamespace(created_at=now, detail="not-json")
    db = _mock_db_execute([row])
    alert = SimpleNamespace(fingerprint="fp1")
    assert await dedup.should_send(alert, db) is True


# --------------------------------------------------------------------------- #
#  alerting.py
# --------------------------------------------------------------------------- #
def test_create_default_rules():
    rules = alerting.create_default_rules()
    assert len(rules) == 4
    assert {r.name for r in rules} == {
        "error_rate_spike",
        "slow_request_p99",
        "high_memory_usage",
        "low_disk_space",
    }


def test_evaluate_trigger():
    eng = alerting.AlertingEngine()
    eng.add_rule(
        alerting.AlertRule(name="error_rate_spike", condition=lambda m: m.error_rate > 0.05, severity="P0")
    )
    events = eng.evaluate(alerting.MetricsSnapshot(error_rate=0.1))
    assert len(events) == 1 and events[0].severity == "P0"


def test_evaluate_no_trigger():
    eng = alerting.AlertingEngine()
    eng.add_rule(
        alerting.AlertRule(name="error_rate_spike", condition=lambda m: m.error_rate > 0.05, severity="P0")
    )
    assert eng.evaluate(alerting.MetricsSnapshot(error_rate=0.01)) == []


def test_evaluate_cooldown():
    eng = alerting.AlertingEngine()
    eng.add_rule(
        alerting.AlertRule(name="error_rate_spike", condition=lambda m: m.error_rate > 0.05, severity="P0")
    )
    snap = alerting.MetricsSnapshot(error_rate=0.1)
    assert len(eng.evaluate(snap)) == 1
    assert len(eng.evaluate(snap)) == 0  # 冷却期内


def test_evaluate_multiple_rules():
    eng = alerting.AlertingEngine()
    eng.add_rule(alerting.AlertRule(name="error_rate_spike", condition=lambda m: m.error_rate > 0.05, severity="P0"))
    eng.add_rule(alerting.AlertRule(name="high_memory_usage", condition=lambda m: m.memory_usage_percent > 85, severity="P1"))
    events = eng.evaluate(alerting.MetricsSnapshot(error_rate=0.1, memory_usage_percent=90))
    assert len(events) == 2


def test_send_notification_no_webhook():
    eng = alerting.AlertingEngine()
    eng._webhook_url = None
    eng._send_notification(MagicMock(), MagicMock())


def test_send_notification_success(monkeypatch):
    resp = MagicMock()
    resp.status_code = 200
    post = MagicMock(return_value=resp)
    monkeypatch.setattr(alerting.requests, "post", post)
    eng = alerting.AlertingEngine()
    eng._webhook_url = "http://hook"
    eng._send_notification(MagicMock(), MagicMock())
    post.assert_called_once()


def test_send_notification_retry_then_error(monkeypatch):
    resp = MagicMock()
    resp.status_code = 500
    resp.text = "err"
    post = MagicMock(return_value=resp)
    monkeypatch.setattr(alerting.requests, "post", post)
    monkeypatch.setattr(alerting.time, "sleep", lambda *a, **k: None)  # 避免真实 sleep
    eng = alerting.AlertingEngine()
    eng._webhook_url = "http://hook"
    eng._send_notification(MagicMock(), MagicMock())
    assert post.call_count == 3  # 指数退避重试 3 次


# --------------------------------------------------------------------------- #
#  escalation.py
# --------------------------------------------------------------------------- #
def _alert(action_type="alert_fired", created_at=None, detail=None):
    return SimpleNamespace(action_type=action_type, id=1, created_at=created_at, detail=detail)


def test_compute_not_firing():
    d = escalation.compute_escalation(_alert(action_type="other"), datetime(2026, 1, 1, 12, 0, 0))
    assert d.should_escalate is False and d.reason == "not firing"


def test_compute_no_created_at():
    d = escalation.compute_escalation(_alert(created_at=None), datetime(2026, 1, 1, 12, 0, 0))
    assert d.should_escalate is False and d.reason == "no created_at"


def test_compute_acknowledged():
    now = datetime(2026, 1, 1, 12, 0, 0)
    d = escalation.compute_escalation(
        _alert(created_at=now, detail=json.dumps({"acknowledged": True})), now
    )
    assert d.should_escalate is False and d.reason == "acknowledged"


def test_compute_p1_to_p0():
    now = datetime(2026, 1, 1, 12, 0, 0)
    alert = _alert(created_at=now - timedelta(minutes=11), detail=json.dumps({"severity": "P1", "escalation_level": 0}))
    d = escalation.compute_escalation(alert, now)
    assert d.should_escalate and d.new_severity == "P0" and d.detail["escalation_level"] == 1


def test_compute_p0_repeat():
    now = datetime(2026, 1, 1, 12, 0, 0)
    alert = _alert(created_at=now - timedelta(minutes=31), detail=json.dumps({"severity": "P0", "escalation_level": 0}))
    d = escalation.compute_escalation(alert, now)
    assert d.should_escalate and d.detail["escalation_level"] == 2


def test_compute_p0_final():
    now = datetime(2026, 1, 1, 12, 0, 0)
    # 已处于 level>=2 且超过 1h 才触发 P0_final（level<2 会先命中 P0_repeat）
    alert = _alert(created_at=now - timedelta(hours=2), detail=json.dumps({"severity": "P0", "escalation_level": 2}))
    d = escalation.compute_escalation(alert, now)
    assert d.should_escalate and d.detail["escalation_level"] == 3


def test_compute_no_need():
    now = datetime(2026, 1, 1, 12, 0, 0)
    alert = _alert(created_at=now - timedelta(minutes=2), detail=json.dumps({"severity": "P2", "escalation_level": 0}))
    d = escalation.compute_escalation(alert, now)
    assert d.should_escalate is False


def test_compute_level_capped():
    now = datetime(2026, 1, 1, 12, 0, 0)
    alert = _alert(created_at=now - timedelta(minutes=11), detail=json.dumps({"severity": "P1", "escalation_level": 1}))
    d = escalation.compute_escalation(alert, now)
    assert d.should_escalate is False  # 已升级过


async def test_run_escalation_check():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    alert = _alert(created_at=now - timedelta(minutes=11), detail=json.dumps({"severity": "P1", "escalation_level": 0}))
    db = _mock_db_execute([alert])
    decisions = await escalation.run_escalation_check(db)
    assert len(decisions) == 1 and decisions[0].should_escalate is True


async def test_apply_escalation(monkeypatch):
    monkeypatch.setattr(escalation, "CompositeNotifier", lambda: MagicMock(send=AsyncMock()))
    row = SimpleNamespace(detail=json.dumps({}))
    exec_res = MagicMock()
    exec_res.scalar_one_or_none.return_value = row
    db = MagicMock()
    db.execute = AsyncMock(return_value=exec_res)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    decision = escalation.EscalationDecision(
        alert_id=1, should_escalate=True, new_severity="P0", reason="r", detail={"escalation_level": 1}
    )
    executed = await escalation.apply_escalation(db, [decision])
    assert len(executed) == 1
    db.commit.assert_awaited()


# --------------------------------------------------------------------------- #
#  am_sync.py
# --------------------------------------------------------------------------- #
def test_local_to_am_format():
    start = datetime(2026, 1, 1, 0, 0, 0)
    end = datetime(2026, 1, 2, 0, 0, 0)
    r = am_sync.local_to_am_format(7, "n", {"a": "1", "b": "2"}, start, end, "c")
    assert r["createdBy"] == "dws-backend:7"
    assert r["matchers"] == [
        {"name": "a", "value": "1", "isRegex": False},
        {"name": "b", "value": "2", "isRegex": False},
    ]
    assert r["startsAt"] == start.isoformat()
    assert r["endsAt"] == end.isoformat()
    assert r["comment"] == "c"


def test_get_am_url(monkeypatch):
    monkeypatch.setenv("ALERTMANAGER_URL", "http://am:9093")
    assert am_sync._get_am_url() == "http://am:9093"
    monkeypatch.delenv("ALERTMANAGER_URL", raising=False)
    assert am_sync._get_am_url() is None


def test_get_am_auth(monkeypatch):
    monkeypatch.setenv("ALERTMANAGER_USER", "u")
    monkeypatch.setenv("ALERTMANAGER_PASSWORD", "p")
    assert am_sync._get_am_auth() == ("u", "p")
    monkeypatch.delenv("ALERTMANAGER_USER", raising=False)
    monkeypatch.delenv("ALERTMANAGER_PASSWORD", raising=False)
    assert am_sync._get_am_auth() is None


async def test_write_sync_log_no_db():
    # db=None 直接返回，不写日志
    await am_sync._write_sync_log(None, "push_silence", True)


async def test_write_sync_log_writes():
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    await am_sync._write_sync_log(db, "push_silence", True, am_silence_id="abc")
    db.add.assert_called_once()


async def test_push_silence_no_url(monkeypatch):
    monkeypatch.delenv("ALERTMANAGER_URL", raising=False)
    sess = MagicMock()
    monkeypatch.setattr(am_sync, "_HTTP_SESSION", sess)
    assert await am_sync.push_silence({"matchers": []}) is None
    sess.post.assert_not_called()


async def test_push_silence_success(monkeypatch):
    monkeypatch.setenv("ALERTMANAGER_URL", "http://am:9093")
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"silenceID": "abc"}
    sess = MagicMock()
    sess.post.return_value = resp
    monkeypatch.setattr(am_sync, "_HTTP_SESSION", sess)
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    result = await am_sync.push_silence({"matchers": []}, db=db)
    assert result == {"silenceID": "abc"}
    db.add.assert_called_once()


async def test_push_silence_http_error(monkeypatch):
    monkeypatch.setenv("ALERTMANAGER_URL", "http://am:9093")
    resp = MagicMock()
    resp.status_code = 500
    resp.text = "err"
    sess = MagicMock()
    sess.post.return_value = resp
    monkeypatch.setattr(am_sync, "_HTTP_SESSION", sess)
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    assert await am_sync.push_silence({"matchers": []}, db=db) is None


async def test_delete_silence_no_url(monkeypatch):
    monkeypatch.delenv("ALERTMANAGER_URL", raising=False)
    assert await am_sync.delete_silence("sid") is False
    monkeypatch.setenv("ALERTMANAGER_URL", "http://am")
    assert await am_sync.delete_silence("") is False


async def test_delete_silence_success(monkeypatch):
    monkeypatch.setenv("ALERTMANAGER_URL", "http://am:9093")
    resp = MagicMock()
    resp.status_code = 200
    sess = MagicMock()
    sess.delete.return_value = resp
    monkeypatch.setattr(am_sync, "_HTTP_SESSION", sess)
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    assert await am_sync.delete_silence("sid", db=db) is True


async def test_pull_silences_success(monkeypatch):
    monkeypatch.setenv("ALERTMANAGER_URL", "http://am:9093")
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = [{"id": "1"}]
    sess = MagicMock()
    sess.get.return_value = resp
    monkeypatch.setattr(am_sync, "_HTTP_SESSION", sess)
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    assert await am_sync.pull_silences(db=db) == [{"id": "1"}]
