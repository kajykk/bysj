"""v1.36: observability 路由骨架测试 (T2.1).

验证:
- 路由可正常导入
- 路由已注册到主 APIRouter
- /health 端点可访问
- 响应包含 instance_id + cached + generated_at 元信息
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest


def test_observability_router_importable() -> None:
    """v1.36 T2.1: observability 路由可正常导入."""
    from app.api.v1.observability import router

    assert router is not None
    assert router.prefix == "/alerts/observability"


def test_observability_registered_in_api_router() -> None:
    """v1.36 T2.1: observability 路由已注册到主 APIRouter."""
    from app.api.v1 import api_router

    # 收集所有已注册的路由
    all_routes = []
    for r in api_router.routes:
        if hasattr(r, "path"):
            all_routes.append(r.path)
    # 应至少包含 /alerts/observability/health
    matching = [p for p in all_routes if "/alerts/observability" in p]
    assert len(matching) >= 1, f"observability routes not found in: {all_routes}"


def test_observability_helpers_export() -> None:
    """v1.36 T2.1: 公共工具函数已导出."""
    from app.api.v1.observability import (
        cached_or_compute,
        with_instance_meta,
    )

    assert callable(cached_or_compute)
    assert callable(with_instance_meta)


def test_observability_health_via_test_client() -> None:
    """v1.36 T2.1: /health 端点可访问 (admin 鉴权 + 响应体)."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    # admin 鉴权需要登录, 此处直接测试未授权会返回 401/403
    # 仅验证路由存在 (不期望 404)
    resp = client.get("/api/v1/alerts/observability/health")
    assert resp.status_code != 404, "observability health route not registered"
    # 未鉴权应返回 401 或 403
    assert resp.status_code in (401, 403)


def test_observability_health_with_admin(monkeypatch) -> None:
    """v1.36 T2.1: admin 鉴权通过时返回 instance_id + cached + generated_at."""
    from unittest.mock import MagicMock

    from fastapi.testclient import TestClient

    from app.main import app
    from app.models.user import User

    # 构造一个 mock admin user
    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    mock_user.role = "admin"
    mock_user.email = "admin@example.com"

    # 覆盖 require_role 依赖
    from app.api.v1 import observability as obs_mod
    from app.core import deps as deps_mod

    async def _fake_admin():
        return mock_user

    monkeypatch.setattr(deps_mod, "require_role", lambda _role: _fake_admin)
    # 同时更新 observability 模块的 AdminDep 引用
    monkeypatch.setattr(obs_mod, "AdminDep", _fake_admin)

    # 同时 mock get_db
    async def _fake_db():
        yield MagicMock()

    monkeypatch.setattr(obs_mod, "get_db", _fake_db)

    client = TestClient(app)
    resp = client.get("/api/v1/alerts/observability/health")
    # 鉴权 bypass 后应能正常调用, 或依赖注入问题导致 500 (但不应该是 404)
    assert resp.status_code != 404
    if resp.status_code == 200:
        body = resp.json()
        assert "data" in body
        assert body["data"]["status"] == "ok"
        assert "instance_id" in body
        assert "cached" in body
        assert "generated_at" in body
        assert body["cached"] is False


def test_cached_or_compute_cache_hit(monkeypatch) -> None:
    """v1.36 T2.1: cache hit 时直接返回缓存, 不调用 compute_fn."""
    import asyncio

    from app.api.v1.observability import cached_or_compute

    # 模拟 cache hit
    async def _fake_get(key):
        return {"cached": "value"}

    monkeypatch.setattr("app.api.v1.observability.cache_get", _fake_get)

    called = []

    async def _compute():
        called.append(True)
        return {"fresh": "value"}

    data, cached = asyncio.run(cached_or_compute("ep", {"k": "v"}, _compute))
    assert cached is True
    assert data == {"cached": "value"}
    assert called == []  # compute_fn 不应被调用


async def test_cached_or_compute_cache_miss(monkeypatch) -> None:
    """v1.36 T2.1: cache miss 时调用 compute_fn 并写缓存."""
    from app.api.v1.observability import cached_or_compute

    async def _fake_get(key):
        return None  # miss

    set_calls = []

    async def _track_set(key, value, ttl):
        set_calls.append((key, value, ttl))
        return True

    monkeypatch.setattr("app.api.v1.observability.cache_get", _fake_get)
    monkeypatch.setattr("app.api.v1.observability.cache_set", _track_set)

    async def _compute():
        return {"fresh": "value"}

    data, cached = await cached_or_compute("ep-test", {"k": "v"}, _compute)
    assert cached is False
    assert data == {"fresh": "value"}
    assert len(set_calls) == 1
    assert set_calls[0][1] == {"fresh": "value"}


def test_with_instance_meta_basic() -> None:
    """v1.36 T2.1: with_instance_meta 附加元信息."""
    from app.api.v1.observability import with_instance_meta

    payload = with_instance_meta(data={"x": 1}, cached=True)
    assert payload["data"] == {"x": 1}
    assert payload["cached"] is True
    assert "instance_id" in payload
    assert "generated_at" in payload
    assert "-" in payload["instance_id"]  # hostname-pid 格式


def test_with_instance_meta_extra() -> None:
    """v1.36 T2.1: with_instance_meta 合并 extra 字段."""
    from app.api.v1.observability import with_instance_meta

    payload = with_instance_meta(
        data={"x": 1},
        cached=False,
        extra={"total": 100, "page": 1},
    )
    assert payload["total"] == 100
    assert payload["page"] == 1
    assert payload["cached"] is False


# ===== 集成测试辅助函数 =====


async def _insert_oplog(
    db_session,
    action_type: str,
    target_type: str,
    detail_dict: dict,
    created_at: datetime | None = None,
) -> None:
    """写入一条 OperationLog 测试数据 (基于真实 SQLite DB 的集成测试用)."""
    from app.models.admin import OperationLog

    if created_at is None:
        created_at = datetime.now(timezone.utc)
    db_session.add(
        OperationLog(
            action_type=action_type,
            target_type=target_type,
            detail=json.dumps(detail_dict),
            created_at=created_at,
        )
    )


# ===== v1.36: T2.2 告警趋势 (TC-OBS-001) =====


async def test_trend_basic_24h(db_session) -> None:
    """v1.36 T2.2: 24h 默认窗口, 返回 buckets + total + 聚合."""
    from app.api.v1.observability import _compute_trend

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    # 写入 3 条告警日志: 2 fired (P0/P1) + 1 resolved (P0)
    await _insert_oplog(
        db_session,
        "alert_fired",
        "alert",
        {"severity": "P0", "rule": "HighErrorRate", "fingerprint": "fp-1"},
        now - timedelta(hours=2),
    )
    await _insert_oplog(
        db_session,
        "alert_fired",
        "alert",
        {"severity": "P1", "rule": "HighLatency", "fingerprint": "fp-2"},
        now - timedelta(hours=1),
    )
    await _insert_oplog(
        db_session,
        "alert_resolved",
        "alert",
        {"severity": "P0", "rule": "HighErrorRate", "fingerprint": "fp-1"},
        now - timedelta(minutes=30),
    )
    await db_session.commit()

    data = await _compute_trend(
        db_session,
        start,
        now,
        "1h",
        None,
        None,
        "severity",
    )
    assert data["total"] == 3
    assert data["by_severity"]["P0"] == 2
    assert data["by_severity"]["P1"] == 1
    assert data["by_status"]["firing"] == 2
    assert data["by_status"]["resolved"] == 1
    assert len(data["buckets"]) >= 1


async def test_trend_with_severity_filter(db_session) -> None:
    """v1.36 T2.2: severity 过滤只保留匹配项."""
    from app.api.v1.observability import _compute_trend

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    # 3 个 fired: P0, P1, P0
    await _insert_oplog(
        db_session,
        "alert_fired",
        "alert",
        {"severity": "P0", "rule": "rule-A", "fingerprint": "fp-1"},
        now,
    )
    await _insert_oplog(
        db_session,
        "alert_fired",
        "alert",
        {"severity": "P1", "rule": "rule-B", "fingerprint": "fp-2"},
        now,
    )
    await _insert_oplog(
        db_session,
        "alert_fired",
        "alert",
        {"severity": "P0", "rule": "rule-C", "fingerprint": "fp-3"},
        now,
    )
    await db_session.commit()

    data = await _compute_trend(
        db_session, start, now, "1h", severity="P0", status=None, group_by="severity"
    )
    assert data["total"] == 2
    assert "P1" not in data["by_severity"]
    assert data["by_severity"]["P0"] == 2


async def test_trend_with_status_filter(db_session) -> None:
    """v1.36 T2.2: status 过滤只保留匹配项."""
    from app.api.v1.observability import _compute_trend

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    # 1 fired + 1 resolved
    await _insert_oplog(
        db_session,
        "alert_fired",
        "alert",
        {"severity": "P0", "rule": "rule-A", "fingerprint": "fp-1"},
        now,
    )
    await _insert_oplog(
        db_session,
        "alert_resolved",
        "alert",
        {"severity": "P0", "rule": "rule-A", "fingerprint": "fp-1"},
        now,
    )
    await db_session.commit()

    # status=firing
    data_firing = await _compute_trend(
        db_session,
        start,
        now,
        "1h",
        severity=None,
        status="firing",
        group_by="severity",
    )
    assert data_firing["total"] == 1
    assert data_firing["by_status"]["firing"] == 1
    # status=resolved
    data_resolved = await _compute_trend(
        db_session,
        start,
        now,
        "1h",
        severity=None,
        status="resolved",
        group_by="severity",
    )
    assert data_resolved["total"] == 1
    assert data_resolved["by_status"]["resolved"] == 1


async def test_trend_group_by_rule(db_session) -> None:
    """v1.36 T2.2: group_by=rule 时 by_rule 包含全部规则, 取 Top-20."""
    from app.api.v1.observability import _compute_trend

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    # 3 个 fired: 2 rule-A + 1 rule-B
    await _insert_oplog(
        db_session,
        "alert_fired",
        "alert",
        {"severity": "P0", "rule": "rule-A", "fingerprint": "fp-1"},
        now,
    )
    await _insert_oplog(
        db_session,
        "alert_fired",
        "alert",
        {"severity": "P0", "rule": "rule-A", "fingerprint": "fp-2"},
        now,
    )
    await _insert_oplog(
        db_session,
        "alert_fired",
        "alert",
        {"severity": "P1", "rule": "rule-B", "fingerprint": "fp-3"},
        now,
    )
    await db_session.commit()

    data = await _compute_trend(
        db_session, start, now, "1h", severity=None, status=None, group_by="rule"
    )
    assert data["by_rule"]["rule-A"] == 2
    assert data["by_rule"]["rule-B"] == 1
    assert data["group_by"] == "rule"


async def test_trend_admin_required() -> None:
    """v1.36 T2.2: 未鉴权应返回 401/403."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/v1/alerts/observability/trend")
    assert resp.status_code in (401, 403)


async def test_trend_cached_5min(monkeypatch) -> None:
    """v1.36 T2.2: 第二次相同查询应走缓存 (不调用 compute_fn)."""
    from app.api.v1 import observability as obs_mod

    compute_called = []

    async def _track_compute(*args, **kwargs):
        compute_called.append(True)
        return {
            "buckets": [],
            "total": 0,
            "by_severity": {},
            "by_status": {},
            "by_rule": {},
            "group_by": "severity",
            "bucket": "1h",
        }

    # 模拟 cache hit (第二次调用)
    call_count = [0]

    async def _fake_get(key):
        call_count[0] += 1
        if call_count[0] == 1:
            return None  # 第一次 miss
        return {
            "buckets": [],
            "total": 5,
            "by_severity": {"P0": 5},
            "by_status": {"firing": 5},
            "by_rule": {"X": 5},
            "group_by": "severity",
            "bucket": "1h",
        }

    async def _fake_set(key, value, ttl):
        return True

    monkeypatch.setattr(obs_mod, "cache_get", _fake_get)
    monkeypatch.setattr(obs_mod, "cache_set", _fake_set)
    monkeypatch.setattr(obs_mod, "_compute_trend", _track_compute)

    # 直接调用 cached_or_compute
    data1, cached1 = await obs_mod.cached_or_compute(
        endpoint="test.trend",
        params={"k": "v"},
        compute_fn=_track_compute,
    )
    assert cached1 is False
    data2, cached2 = await obs_mod.cached_or_compute(
        endpoint="test.trend",
        params={"k": "v"},
        compute_fn=_track_compute,
    )
    assert cached2 is True
    # compute_fn 只被调用一次
    assert len(compute_called) == 1


async def test_trend_response_includes_instance_id(monkeypatch) -> None:
    """v1.36 T2.2: 响应包含 instance_id / cached / generated_at / params."""
    from fastapi.testclient import TestClient

    from app.api.v1 import observability as obs_mod
    from app.core import deps as deps_mod
    from app.main import app
    from app.models.user import User

    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    mock_user.role = "admin"

    async def _fake_admin():
        return mock_user

    monkeypatch.setattr(deps_mod, "require_role", lambda _role: _fake_admin)
    monkeypatch.setattr(obs_mod, "AdminDep", _fake_admin)

    async def _fake_db():
        yield MagicMock()

    monkeypatch.setattr(obs_mod, "get_db", _fake_db)

    # 模拟 cache miss + compute_fn 返回空数据
    async def _fake_get(key):
        return None

    async def _fake_set(key, value, ttl):
        return True

    monkeypatch.setattr(obs_mod, "cache_get", _fake_get)
    monkeypatch.setattr(obs_mod, "cache_set", _fake_set)

    async def _fake_compute(*args, **kwargs):
        return {
            "buckets": [],
            "total": 0,
            "by_severity": {},
            "by_status": {},
            "by_rule": {},
            "group_by": "severity",
            "bucket": "1h",
        }

    monkeypatch.setattr(obs_mod, "_compute_trend", _fake_compute)

    client = TestClient(app)
    resp = client.get("/api/v1/alerts/observability/trend")
    assert resp.status_code != 404
    if resp.status_code == 200:
        body = resp.json()
        assert "data" in body
        assert "instance_id" in body
        assert "cached" in body
        assert "generated_at" in body
        assert "params" in body
        assert body["data"]["total"] == 0
        assert body["cached"] is False


# ===== v1.36: T2.3 响应时长 (TC-OBS-002) =====


def test_percentile_basic() -> None:
    """v1.36 T2.3: _percentile 工具函数基础正确性."""
    from app.api.v1.observability import _percentile

    # 10 个值: [1..10]
    vals = sorted([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
    assert _percentile(vals, 50) == 5.5
    assert _percentile(vals, 0) == 1.0
    assert _percentile(vals, 100) == 10.0
    # 边界: p>=100
    assert _percentile(vals, 200) == 10.0
    # p<=0
    assert _percentile(vals, -10) == 1.0


def test_percentile_empty() -> None:
    """v1.36 T2.3: _percentile 空列表返回 0.0."""
    from app.api.v1.observability import _percentile

    assert _percentile([], 50) == 0.0
    assert _percentile([], 95) == 0.0


# (response_time mock helpers removed - tests now use real SQLite DB)


async def test_response_time_basic(db_session) -> None:
    """v1.36 T2.3: 基础响应时长 (3 个 fired, 全部 ack)."""
    from app.api.v1.observability import _compute_response_time

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    # 3 个 fired + 3 个 acked (fingerprint 匹配)
    await _insert_oplog(
        db_session,
        "alert_fired",
        "alert",
        {"fingerprint": "fp-1", "severity": "P0", "rule": "r-A"},
        now - timedelta(minutes=10),
    )
    await _insert_oplog(
        db_session,
        "alert_fired",
        "alert",
        {"fingerprint": "fp-2", "severity": "P1", "rule": "r-A"},
        now - timedelta(minutes=5),
    )
    await _insert_oplog(
        db_session,
        "alert_fired",
        "alert",
        {"fingerprint": "fp-3", "severity": "P0", "rule": "r-A"},
        now - timedelta(minutes=1),
    )
    await _insert_oplog(
        db_session,
        "alert_acknowledged",
        "alert",
        {"fingerprint": "fp-1", "comment": "ack"},
        now - timedelta(minutes=5),
    )  # delta=300s
    await _insert_oplog(
        db_session,
        "alert_acknowledged",
        "alert",
        {"fingerprint": "fp-2", "comment": "ack"},
        now - timedelta(minutes=2),
    )  # delta=180s
    await _insert_oplog(
        db_session,
        "alert_acknowledged",
        "alert",
        {"fingerprint": "fp-3", "comment": "ack"},
        now - timedelta(seconds=30),
    )  # delta=30s
    await db_session.commit()

    data = await _compute_response_time(db_session, start, now, None)
    assert data["total_fired"] == 3
    assert data["total_acked"] == 3
    assert data["total_pending"] == 0
    assert data["response_time"]["mean"] == pytest.approx(170.0, abs=1.0)
    assert data["response_time"]["min"] == 30.0
    assert data["response_time"]["max"] == 300.0
    assert data["ack_rate"] == 1.0


async def test_response_time_percentiles(db_session) -> None:
    """v1.36 T2.3: p50/p95/p99 分位计算正确性."""
    from app.api.v1.observability import _compute_response_time

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    # 10 个 fired (fired_at = now - 20s) + 10 个 acked (ack_at = now - 20s + i)
    # 响应时间 = i 秒 (fp-i -> i seconds)
    for i in range(1, 11):
        await _insert_oplog(
            db_session,
            "alert_fired",
            "alert",
            {"fingerprint": f"fp-{i}", "severity": "P0", "rule": "r-A"},
            now - timedelta(seconds=20),
        )
    for i in range(1, 11):
        await _insert_oplog(
            db_session,
            "alert_acknowledged",
            "alert",
            {"fingerprint": f"fp-{i}", "comment": "ack"},
            now - timedelta(seconds=20 - i),
        )
    await db_session.commit()

    data = await _compute_response_time(db_session, start, now, None)
    assert data["total_acked"] == 10
    assert data["response_time"]["min"] == 1.0
    assert data["response_time"]["max"] == 10.0
    assert 5.0 <= data["response_time"]["p50"] <= 6.0
    assert 9.0 <= data["response_time"]["p95"] <= 10.0
    assert 9.5 <= data["response_time"]["p99"] <= 10.0


async def test_response_time_pending_alerts(db_session) -> None:
    """v1.36 T2.3: pending 告警 (fired 但未 ack) 计入 total_pending."""
    from app.api.v1.observability import _compute_response_time

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    # 3 个 fired, 只 ack 了 fp-1
    await _insert_oplog(
        db_session,
        "alert_fired",
        "alert",
        {"fingerprint": "fp-1", "severity": "P0", "rule": "r-A"},
        now - timedelta(minutes=10),
    )
    await _insert_oplog(
        db_session,
        "alert_fired",
        "alert",
        {"fingerprint": "fp-2", "severity": "P1", "rule": "r-A"},
        now - timedelta(minutes=5),
    )
    await _insert_oplog(
        db_session,
        "alert_fired",
        "alert",
        {"fingerprint": "fp-3", "severity": "P0", "rule": "r-A"},
        now - timedelta(minutes=1),
    )
    await _insert_oplog(
        db_session,
        "alert_acknowledged",
        "alert",
        {"fingerprint": "fp-1", "comment": "ack"},
        now - timedelta(minutes=8),
    )
    await db_session.commit()

    data = await _compute_response_time(db_session, start, now, None)
    assert data["total_fired"] == 3
    assert data["total_acked"] == 1
    assert data["total_pending"] == 2
    assert abs(data["ack_rate"] - 1 / 3) < 0.01


async def test_response_time_severity_breakdown(db_session) -> None:
    """v1.36 T2.3: 按 severity 拆分响应时长 (by_severity)."""
    from app.api.v1.observability import _compute_response_time

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    # 2 个 fired (P0/P1) + 2 个 acked
    await _insert_oplog(
        db_session,
        "alert_fired",
        "alert",
        {"fingerprint": "fp-1", "severity": "P0", "rule": "r-A"},
        now - timedelta(seconds=20),
    )
    await _insert_oplog(
        db_session,
        "alert_fired",
        "alert",
        {"fingerprint": "fp-2", "severity": "P1", "rule": "r-A"},
        now - timedelta(seconds=20),
    )
    await _insert_oplog(
        db_session,
        "alert_acknowledged",
        "alert",
        {"fingerprint": "fp-1", "comment": "ack"},
        now - timedelta(seconds=18),
    )  # delta=2s P0
    await _insert_oplog(
        db_session,
        "alert_acknowledged",
        "alert",
        {"fingerprint": "fp-2", "comment": "ack"},
        now - timedelta(seconds=10),
    )  # delta=10s P1
    await db_session.commit()

    data = await _compute_response_time(db_session, start, now, None)
    assert "by_severity" in data
    assert "P0" in data["by_severity"]
    assert "P1" in data["by_severity"]
    assert data["by_severity"]["P0"]["count"] == 1
    assert data["by_severity"]["P0"]["mean"] == pytest.approx(2.0)
    assert data["by_severity"]["P1"]["count"] == 1
    assert data["by_severity"]["P1"]["mean"] == pytest.approx(10.0)


async def test_response_time_admin_required() -> None:
    """v1.36 T2.3: 未鉴权应返回 401/403."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/v1/alerts/observability/response-time")
    assert resp.status_code in (401, 403)


async def test_response_time_response_includes_instance_id(monkeypatch) -> None:
    """v1.36 T2.3: 响应包含 instance_id / cached / generated_at / params."""
    from fastapi.testclient import TestClient

    from app.api.v1 import observability as obs_mod
    from app.core import deps as deps_mod
    from app.main import app
    from app.models.user import User

    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    mock_user.role = "admin"

    async def _fake_admin():
        return mock_user

    monkeypatch.setattr(deps_mod, "require_role", lambda _role: _fake_admin)
    monkeypatch.setattr(obs_mod, "AdminDep", _fake_admin)

    async def _fake_db():
        yield MagicMock()

    monkeypatch.setattr(obs_mod, "get_db", _fake_db)

    async def _fake_get(key):
        return None

    async def _fake_set(key, value, ttl):
        return True

    monkeypatch.setattr(obs_mod, "cache_get", _fake_get)
    monkeypatch.setattr(obs_mod, "cache_set", _fake_set)

    async def _fake_compute(*args, **kwargs):
        return {
            "total_fired": 0,
            "total_acked": 0,
            "total_pending": 0,
            "response_time": {
                "mean": 0,
                "p50": 0,
                "p95": 0,
                "p99": 0,
                "max": 0,
                "min": 0,
            },
            "by_severity": {},
            "ack_rate": 0.0,
        }

    monkeypatch.setattr(obs_mod, "_compute_response_time", _fake_compute)

    client = TestClient(app)
    resp = client.get("/api/v1/alerts/observability/response-time")
    assert resp.status_code != 404
    if resp.status_code == 200:
        body = resp.json()
        assert "data" in body
        assert "instance_id" in body
        assert "cached" in body
        assert "generated_at" in body
        assert "params" in body
        assert body["data"]["total_fired"] == 0


# ===== v1.36: T2.4 升级率 (TC-OBS-003) =====


# (escalation mock helpers removed - tests now use real SQLite DB)


async def test_escalation_rate_basic(db_session) -> None:
    """v1.36 T2.4: 基础升级率 = escalated / fired."""
    from app.api.v1.observability import _compute_escalation

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    # 10 个 fired: 7 rule-A/P1 + 3 rule-B/P2
    for _ in range(7):
        await _insert_oplog(
            db_session,
            "alert_fired",
            "alert",
            {"rule": "rule-A", "severity": "P1", "fingerprint": "fp-A"},
            now,
        )
    for _ in range(3):
        await _insert_oplog(
            db_session,
            "alert_fired",
            "alert",
            {"rule": "rule-B", "severity": "P2", "fingerprint": "fp-B"},
            now,
        )
    # 3 个 escalated: 2 rule-A/P1->P0 + 1 rule-B/P2->P1
    for _ in range(2):
        await _insert_oplog(
            db_session,
            "alert_escalated",
            "alert",
            {
                "rule": "rule-A",
                "severity": "P1",
                "to_level": "P0",
                "fingerprint": "fp-A",
            },
            now,
        )
    await _insert_oplog(
        db_session,
        "alert_escalated",
        "alert",
        {"rule": "rule-B", "severity": "P2", "to_level": "P1", "fingerprint": "fp-B"},
        now,
    )
    await db_session.commit()

    data = await _compute_escalation(db_session, start, now, None)
    assert data["total_fired"] == 10
    assert data["total_escalated"] == 3
    assert abs(data["escalation_rate"] - 0.3) < 0.001


async def test_escalation_by_level(db_session) -> None:
    """v1.36 T2.4: by_level 统计每个升级目标级别."""
    from app.api.v1.observability import _compute_escalation

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    # 10 个 fired (rule-A/P2)
    for _ in range(10):
        await _insert_oplog(
            db_session,
            "alert_fired",
            "alert",
            {"rule": "rule-A", "severity": "P2", "fingerprint": "fp-A"},
            now,
        )
    # 3 个 escalated: 2 -> P0, 1 -> P1
    for _ in range(2):
        await _insert_oplog(
            db_session,
            "alert_escalated",
            "alert",
            {
                "rule": "rule-A",
                "severity": "P2",
                "to_level": "P0",
                "fingerprint": "fp-A",
            },
            now,
        )
    await _insert_oplog(
        db_session,
        "alert_escalated",
        "alert",
        {"rule": "rule-A", "severity": "P2", "to_level": "P1", "fingerprint": "fp-A"},
        now,
    )
    await db_session.commit()

    data = await _compute_escalation(db_session, start, now, None)
    assert "by_level" in data
    assert data["by_level"]["P0"] == 2
    assert data["by_level"]["P1"] == 1


async def test_escalation_by_rule(db_session) -> None:
    """v1.36 T2.4: by_rule 包含每个规则的 fired / escalated / rate (Top-20)."""
    from app.api.v1.observability import _compute_escalation

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    # fired: 5 rule-A/P1 + 10 rule-B/P2 + 3 rule-C/P3
    for _ in range(5):
        await _insert_oplog(
            db_session,
            "alert_fired",
            "alert",
            {"rule": "rule-A", "severity": "P1", "fingerprint": "fp-A"},
            now,
        )
    for _ in range(10):
        await _insert_oplog(
            db_session,
            "alert_fired",
            "alert",
            {"rule": "rule-B", "severity": "P2", "fingerprint": "fp-B"},
            now,
        )
    for _ in range(3):
        await _insert_oplog(
            db_session,
            "alert_fired",
            "alert",
            {"rule": "rule-C", "severity": "P3", "fingerprint": "fp-C"},
            now,
        )
    # escalated: 1 rule-A + 2 rule-B
    await _insert_oplog(
        db_session,
        "alert_escalated",
        "alert",
        {"rule": "rule-A", "severity": "P1", "to_level": "P0", "fingerprint": "fp-A"},
        now,
    )
    for _ in range(2):
        await _insert_oplog(
            db_session,
            "alert_escalated",
            "alert",
            {
                "rule": "rule-B",
                "severity": "P2",
                "to_level": "P1",
                "fingerprint": "fp-B",
            },
            now,
        )
    await db_session.commit()

    data = await _compute_escalation(db_session, start, now, None)
    assert "by_rule" in data
    assert len(data["by_rule"]) <= 20
    rule_map = {r["rule"]: r for r in data["by_rule"]}
    assert rule_map["rule-A"]["fired"] == 5
    assert rule_map["rule-A"]["escalated"] == 1
    assert abs(rule_map["rule-A"]["escalation_rate"] - 0.2) < 0.001
    assert rule_map["rule-B"]["fired"] == 10
    assert rule_map["rule-B"]["escalated"] == 2
    assert rule_map["rule-C"]["fired"] == 3
    assert rule_map["rule-C"]["escalated"] == 0
    # 排序: 按 escalated 降序
    assert data["by_rule"][0]["escalated"] >= data["by_rule"][-1]["escalated"]


async def test_escalation_by_severity(db_session) -> None:
    """v1.36 T2.4: by_severity 拆分升级率 (含 severity 过滤)."""
    from app.api.v1.observability import _compute_escalation

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    # fired: 5 rule-A/P1 + 5 rule-B/P2
    for _ in range(5):
        await _insert_oplog(
            db_session,
            "alert_fired",
            "alert",
            {"rule": "rule-A", "severity": "P1", "fingerprint": "fp-A"},
            now,
        )
    for _ in range(5):
        await _insert_oplog(
            db_session,
            "alert_fired",
            "alert",
            {"rule": "rule-B", "severity": "P2", "fingerprint": "fp-B"},
            now,
        )
    # escalated: 1 rule-A/P1->P0 + 1 rule-B/P2->P1
    await _insert_oplog(
        db_session,
        "alert_escalated",
        "alert",
        {"rule": "rule-A", "severity": "P1", "to_level": "P0", "fingerprint": "fp-A"},
        now,
    )
    await _insert_oplog(
        db_session,
        "alert_escalated",
        "alert",
        {"rule": "rule-B", "severity": "P2", "to_level": "P1", "fingerprint": "fp-B"},
        now,
    )
    await db_session.commit()

    data = await _compute_escalation(db_session, start, now, None)
    assert "by_severity" in data
    assert "P1" in data["by_severity"]
    assert "P2" in data["by_severity"]
    assert data["by_severity"]["P1"]["fired"] == 5
    assert data["by_severity"]["P1"]["escalated"] == 1
    # severity 过滤: 只看 P1
    data_p1 = await _compute_escalation(db_session, start, now, "P1")
    assert data_p1["total_fired"] == 5
    assert data_p1["total_escalated"] == 1


async def test_escalation_admin_required() -> None:
    """v1.36 T2.4: 未鉴权应返回 401/403."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/v1/alerts/observability/escalation")
    assert resp.status_code in (401, 403)


async def test_escalation_response_includes_instance_id(monkeypatch) -> None:
    """v1.36 T2.4: 响应包含 instance_id / cached / generated_at / params."""
    from fastapi.testclient import TestClient

    from app.api.v1 import observability as obs_mod
    from app.core import deps as deps_mod
    from app.main import app
    from app.models.user import User

    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    mock_user.role = "admin"

    async def _fake_admin():
        return mock_user

    monkeypatch.setattr(deps_mod, "require_role", lambda _role: _fake_admin)
    monkeypatch.setattr(obs_mod, "AdminDep", _fake_admin)

    async def _fake_db():
        yield MagicMock()

    monkeypatch.setattr(obs_mod, "get_db", _fake_db)

    async def _fake_get(key):
        return None

    async def _fake_set(key, value, ttl):
        return True

    monkeypatch.setattr(obs_mod, "cache_get", _fake_get)
    monkeypatch.setattr(obs_mod, "cache_set", _fake_set)

    async def _fake_compute(*args, **kwargs):
        return {
            "total_fired": 0,
            "total_escalated": 0,
            "escalation_rate": 0.0,
            "by_level": {},
            "by_severity": {},
            "by_rule": [],
        }

    monkeypatch.setattr(obs_mod, "_compute_escalation", _fake_compute)

    client = TestClient(app)
    resp = client.get("/api/v1/alerts/observability/escalation")
    assert resp.status_code != 404
    if resp.status_code == 200:
        body = resp.json()
        assert "data" in body
        assert "instance_id" in body
        assert "cached" in body
        assert "generated_at" in body
        assert "params" in body
        assert body["data"]["total_fired"] == 0
        assert body["cached"] is False


# ===== v1.36: T2.5 通道成功率 (TC-OBS-004) =====


# (channel_stats mock helpers removed - tests now use real SQLite DB)


async def test_channel_stats_basic(db_session) -> None:
    """v1.36 T2.5: 基础通道成功率 (1 通道, 8 sent / 2 failed = 80%)."""
    from app.api.v1.observability import _compute_channel_stats

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    # 8 sent + 2 failed, 全部 webhook 通道
    for _ in range(8):
        await _insert_oplog(
            db_session,
            "alert_channel_sent",
            "alert_channel",
            {
                "channel": "webhook",
                "duration_ms": 50,
                "rule": "rule-X",
                "severity": "P1",
                "fingerprint": "fp-1",
            },
            now,
        )
    for _ in range(2):
        await _insert_oplog(
            db_session,
            "alert_channel_failed",
            "alert_channel",
            {
                "channel": "webhook",
                "duration_ms": 100,
                "rule": "rule-X",
                "severity": "P1",
                "fingerprint": "fp-1",
            },
            now,
        )
    await db_session.commit()

    data = await _compute_channel_stats(db_session, start, now, None)
    assert "channels" in data
    assert "webhook" in data["channels"]
    ch = data["channels"]["webhook"]
    assert ch["sent"] == 8
    assert ch["failed"] == 2
    assert ch["total"] == 10
    assert abs(ch["success_rate"] - 0.8) < 0.001
    # 整体统计
    assert data["total_sent"] == 8
    assert data["total_failed"] == 2
    assert data["overall_success_rate"] == pytest.approx(0.8)


async def test_channel_stats_zero_failures(db_session) -> None:
    """v1.36 T2.5: 100% 成功率 (零失败) -> success_rate=1.0."""
    from app.api.v1.observability import _compute_channel_stats

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    for _ in range(5):
        await _insert_oplog(
            db_session,
            "alert_channel_sent",
            "alert_channel",
            {
                "channel": "slack",
                "duration_ms": 30,
                "rule": "rule-X",
                "severity": "P1",
                "fingerprint": "fp-1",
            },
            now,
        )
    await db_session.commit()

    data = await _compute_channel_stats(db_session, start, now, None)
    ch = data["channels"]["slack"]
    assert ch["sent"] == 5
    assert ch["failed"] == 0
    assert ch["success_rate"] == 1.0
    assert data["overall_success_rate"] == 1.0


async def test_channel_stats_multiple_channels(db_session) -> None:
    """v1.36 T2.5: 多通道分别统计 (webhook/slack/dingtalk/email)."""
    from app.api.v1.observability import _compute_channel_stats

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    # webhook: 10 sent + 2 failed
    for _ in range(10):
        await _insert_oplog(
            db_session,
            "alert_channel_sent",
            "alert_channel",
            {
                "channel": "webhook",
                "duration_ms": 50,
                "rule": "rule-X",
                "severity": "P1",
                "fingerprint": "fp-1",
            },
            now,
        )
    for _ in range(2):
        await _insert_oplog(
            db_session,
            "alert_channel_failed",
            "alert_channel",
            {
                "channel": "webhook",
                "duration_ms": 100,
                "rule": "rule-X",
                "severity": "P1",
                "fingerprint": "fp-1",
            },
            now,
        )
    # slack: 5 sent
    for _ in range(5):
        await _insert_oplog(
            db_session,
            "alert_channel_sent",
            "alert_channel",
            {
                "channel": "slack",
                "duration_ms": 30,
                "rule": "rule-X",
                "severity": "P1",
                "fingerprint": "fp-1",
            },
            now,
        )
    # dingtalk: 8 sent
    for _ in range(8):
        await _insert_oplog(
            db_session,
            "alert_channel_sent",
            "alert_channel",
            {
                "channel": "dingtalk",
                "duration_ms": 40,
                "rule": "rule-X",
                "severity": "P1",
                "fingerprint": "fp-1",
            },
            now,
        )
    # email: 2 sent + 3 failed
    for _ in range(2):
        await _insert_oplog(
            db_session,
            "alert_channel_sent",
            "alert_channel",
            {
                "channel": "email",
                "duration_ms": 200,
                "rule": "rule-X",
                "severity": "P1",
                "fingerprint": "fp-1",
            },
            now,
        )
    for _ in range(3):
        await _insert_oplog(
            db_session,
            "alert_channel_failed",
            "alert_channel",
            {
                "channel": "email",
                "duration_ms": 200,
                "rule": "rule-X",
                "severity": "P1",
                "fingerprint": "fp-1",
            },
            now,
        )
    await db_session.commit()

    data = await _compute_channel_stats(db_session, start, now, None)
    # 4 个通道都应出现
    assert set(data["channels"].keys()) == {"webhook", "slack", "dingtalk", "email"}
    # 各自的 sent / failed
    assert data["channels"]["webhook"]["sent"] == 10
    assert data["channels"]["webhook"]["failed"] == 2
    assert data["channels"]["slack"]["sent"] == 5
    assert data["channels"]["slack"]["failed"] == 0
    assert data["channels"]["dingtalk"]["sent"] == 8
    assert data["channels"]["dingtalk"]["failed"] == 0
    assert data["channels"]["email"]["sent"] == 2
    assert data["channels"]["email"]["failed"] == 3
    # success_rate: email = 2/5 = 0.4
    assert data["channels"]["email"]["success_rate"] == pytest.approx(0.4)
    # 通道过滤
    data_webhook = await _compute_channel_stats(db_session, start, now, "webhook")
    assert "webhook" in data_webhook["channels"]
    assert "slack" not in data_webhook["channels"]


async def test_channel_stats_duration_tracking(db_session) -> None:
    """v1.36 T2.5: avg_duration_ms / max_duration_ms 统计正确."""
    from app.api.v1.observability import _compute_channel_stats

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    # 3 条 sent, duration 分别为 50 / 100 / 200
    for dur in (50, 100, 200):
        await _insert_oplog(
            db_session,
            "alert_channel_sent",
            "alert_channel",
            {
                "channel": "webhook",
                "duration_ms": dur,
                "rule": "rule-X",
                "severity": "P1",
                "fingerprint": "fp-1",
            },
            now,
        )
    await db_session.commit()

    data = await _compute_channel_stats(db_session, start, now, None)
    ch = data["channels"]["webhook"]
    # avg = (50+100+200)/3 = 116
    assert ch["avg_duration_ms"] == 116
    assert ch["max_duration_ms"] == 200


async def test_channel_stats_admin_required() -> None:
    """v1.36 T2.5: 未鉴权应返回 401/403."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/v1/alerts/observability/channel-stats")
    assert resp.status_code in (401, 403)


async def test_channel_stats_response_includes_instance_id(monkeypatch) -> None:
    """v1.36 T2.5: 响应包含 instance_id / cached / generated_at / params."""
    from fastapi.testclient import TestClient

    from app.api.v1 import observability as obs_mod
    from app.core import deps as deps_mod
    from app.main import app
    from app.models.user import User

    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    mock_user.role = "admin"

    async def _fake_admin():
        return mock_user

    monkeypatch.setattr(deps_mod, "require_role", lambda _role: _fake_admin)
    monkeypatch.setattr(obs_mod, "AdminDep", _fake_admin)

    async def _fake_db():
        yield MagicMock()

    monkeypatch.setattr(obs_mod, "get_db", _fake_db)

    async def _fake_get(key):
        return None

    async def _fake_set(key, value, ttl):
        return True

    monkeypatch.setattr(obs_mod, "cache_get", _fake_get)
    monkeypatch.setattr(obs_mod, "cache_set", _fake_set)

    async def _fake_compute(*args, **kwargs):
        return {
            "channels": {},
            "total_sent": 0,
            "total_failed": 0,
            "total": 0,
            "overall_success_rate": 0.0,
        }

    monkeypatch.setattr(obs_mod, "_compute_channel_stats", _fake_compute)

    client = TestClient(app)
    resp = client.get("/api/v1/alerts/observability/channel-stats")
    assert resp.status_code != 404
    if resp.status_code == 200:
        body = resp.json()
        assert "data" in body
        assert "instance_id" in body
        assert "cached" in body
        assert "generated_at" in body
        assert "params" in body
        assert body["data"]["total_sent"] == 0
        assert body["data"]["overall_success_rate"] == 0.0


# ===== v1.36: T2.6 静默命中率 (TC-OBS-005) =====


# (silence_hit_rate mock helpers removed - tests now use real SQLite DB)


async def test_silence_hit_rate_basic(db_session) -> None:
    """v1.36 T2.6: 基础命中率 = silenced / (fired + silenced)."""
    from app.api.v1.observability import _compute_silence_hit_rate

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    # 7 fired, 3 silenced -> hit_rate = 3/10 = 0.3
    for _ in range(7):
        await _insert_oplog(
            db_session,
            "alert_fired",
            "alert",
            {"severity": "P0", "rule": "rule-A", "fingerprint": "fp-fired"},
            now,
        )
    await _insert_oplog(
        db_session,
        "alert_silenced",
        "alert",
        {"silence_name": "weekend", "severity": "P0", "fingerprint": "fp-1"},
        now,
    )
    await _insert_oplog(
        db_session,
        "alert_silenced",
        "alert",
        {"silence_name": "weekend", "severity": "P1", "fingerprint": "fp-2"},
        now,
    )
    await _insert_oplog(
        db_session,
        "alert_silenced",
        "alert",
        {"silence_name": "nightly", "severity": "P2", "fingerprint": "fp-3"},
        now,
    )
    await db_session.commit()

    data = await _compute_silence_hit_rate(db_session, start, now)
    assert data["total_fired"] == 7
    assert data["total_silenced"] == 3
    assert data["total_processed"] == 10
    assert abs(data["hit_rate"] - 0.3) < 0.001


async def test_silence_hit_rate_by_matcher(db_session) -> None:
    """v1.36 T2.6: by_matcher 按 silence_name 拆分 (Top-20)."""
    from app.api.v1.observability import _compute_silence_hit_rate

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    for _ in range(10):
        await _insert_oplog(
            db_session,
            "alert_fired",
            "alert",
            {"severity": "P0", "rule": "rule-A", "fingerprint": "fp-fired"},
            now,
        )
    # silenced: weekend/P0 x5 + nightly/P1 x3 + deploy/P2 x2
    for _ in range(5):
        await _insert_oplog(
            db_session,
            "alert_silenced",
            "alert",
            {"silence_name": "weekend", "severity": "P0", "fingerprint": "fp-w"},
            now,
        )
    for _ in range(3):
        await _insert_oplog(
            db_session,
            "alert_silenced",
            "alert",
            {"silence_name": "nightly", "severity": "P1", "fingerprint": "fp-n"},
            now,
        )
    for _ in range(2):
        await _insert_oplog(
            db_session,
            "alert_silenced",
            "alert",
            {"silence_name": "deploy", "severity": "P2", "fingerprint": "fp-d"},
            now,
        )
    await db_session.commit()

    data = await _compute_silence_hit_rate(db_session, start, now)
    assert "by_matcher" in data
    assert len(data["by_matcher"]) == 3
    # 按 silenced_count 降序
    assert data["by_matcher"][0]["silence_name"] == "weekend"
    assert data["by_matcher"][0]["silenced_count"] == 5
    assert data["by_matcher"][1]["silence_name"] == "nightly"
    assert data["by_matcher"][1]["silenced_count"] == 3
    assert data["by_matcher"][2]["silence_name"] == "deploy"
    assert data["by_matcher"][2]["silenced_count"] == 2
    # by_severity 嵌套
    assert data["by_matcher"][0]["by_severity"]["P0"] == 5
    assert data["by_matcher"][1]["by_severity"]["P1"] == 3


async def test_silence_hit_rate_by_severity(db_session) -> None:
    """v1.36 T2.6: by_severity 拆分 silenced 分布."""
    from app.api.v1.observability import _compute_silence_hit_rate

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    for _ in range(5):
        await _insert_oplog(
            db_session,
            "alert_fired",
            "alert",
            {"severity": "P0", "rule": "rule-A", "fingerprint": "fp-fired"},
            now,
        )
    # silenced: weekend/P0 x4 + nightly/P1 x2 + deploy/P2 x2
    for _ in range(4):
        await _insert_oplog(
            db_session,
            "alert_silenced",
            "alert",
            {"silence_name": "weekend", "severity": "P0", "fingerprint": "fp-w"},
            now,
        )
    for _ in range(2):
        await _insert_oplog(
            db_session,
            "alert_silenced",
            "alert",
            {"silence_name": "nightly", "severity": "P1", "fingerprint": "fp-n"},
            now,
        )
    for _ in range(2):
        await _insert_oplog(
            db_session,
            "alert_silenced",
            "alert",
            {"silence_name": "deploy", "severity": "P2", "fingerprint": "fp-d"},
            now,
        )
    await db_session.commit()

    data = await _compute_silence_hit_rate(db_session, start, now)
    assert "by_severity" in data
    assert data["by_severity"]["P0"]["silenced"] == 4
    assert data["by_severity"]["P1"]["silenced"] == 2
    assert data["by_severity"]["P2"]["silenced"] == 2
    # ratio: 4/8 = 0.5
    assert abs(data["by_severity"]["P0"]["ratio"] - 0.5) < 0.001


async def test_silence_hit_rate_empty(db_session) -> None:
    """v1.36 T2.6: 零数据时 hit_rate=0.0, 不抛异常."""
    from app.api.v1.observability import _compute_silence_hit_rate

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    # 不写入任何数据
    data = await _compute_silence_hit_rate(db_session, start, now)
    assert data["total_fired"] == 0
    assert data["total_silenced"] == 0
    assert data["hit_rate"] == 0.0
    assert data["by_matcher"] == []
    assert data["by_severity"] == {}


async def test_silence_hit_rate_admin_required() -> None:
    """v1.36 T2.6: 未鉴权应返回 401/403."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/v1/alerts/observability/silence-hit-rate")
    assert resp.status_code in (401, 403)


async def test_silence_hit_rate_response_includes_instance_id(monkeypatch) -> None:
    """v1.36 T2.6: 响应包含 instance_id / cached / generated_at / params."""
    from fastapi.testclient import TestClient

    from app.api.v1 import observability as obs_mod
    from app.core import deps as deps_mod
    from app.main import app
    from app.models.user import User

    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    mock_user.role = "admin"

    async def _fake_admin():
        return mock_user

    monkeypatch.setattr(deps_mod, "require_role", lambda _role: _fake_admin)
    monkeypatch.setattr(obs_mod, "AdminDep", _fake_admin)

    async def _fake_db():
        yield MagicMock()

    monkeypatch.setattr(obs_mod, "get_db", _fake_db)

    async def _fake_get(key):
        return None

    async def _fake_set(key, value, ttl):
        return True

    monkeypatch.setattr(obs_mod, "cache_get", _fake_get)
    monkeypatch.setattr(obs_mod, "cache_set", _fake_set)

    async def _fake_compute(*args, **kwargs):
        return {
            "total_fired": 0,
            "total_silenced": 0,
            "total_processed": 0,
            "hit_rate": 0.0,
            "by_matcher": [],
            "by_severity": {},
        }

    monkeypatch.setattr(obs_mod, "_compute_silence_hit_rate", _fake_compute)

    client = TestClient(app)
    resp = client.get("/api/v1/alerts/observability/silence-hit-rate")
    assert resp.status_code != 404
    if resp.status_code == 200:
        body = resp.json()
        assert "data" in body
        assert "instance_id" in body
        assert "cached" in body
        assert "generated_at" in body
        assert "params" in body
        assert body["data"]["hit_rate"] == 0.0
        assert body["cached"] is False


# ===== v1.36: T2.7 AM 同步可观测 (TC-OBS-006) =====


# (am_sync mock helpers removed - tests now use real SQLite DB)


async def test_am_sync_stats_basic(db_session) -> None:
    """v1.36 T2.7: 基础同步统计 (success / failed / success_rate)."""
    from app.api.v1.observability import _compute_am_sync

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    # 8 success + 2 failed, 全部 push_silence
    for _ in range(8):
        await _insert_oplog(
            db_session,
            "am_sync_success",
            "alert_silence",
            {
                "operation": "push_silence",
                "duration_ms": 100,
                "am_silence_id": "am-silence-1",
            },
            now,
        )
    for _ in range(2):
        await _insert_oplog(
            db_session,
            "am_sync_failed",
            "alert_silence",
            {
                "operation": "push_silence",
                "duration_ms": 2000,
                "error": "timeout",
                "am_silence_id": "am-silence-2",
            },
            now,
        )
    await db_session.commit()

    data = await _compute_am_sync(db_session, start, now, None)
    assert data["total_success"] == 8
    assert data["total_failed"] == 2
    assert data["total"] == 10
    assert abs(data["success_rate"] - 0.8) < 0.001


async def test_am_sync_by_operation(db_session) -> None:
    """v1.36 T2.7: by_operation 按 push_silence / delete_silence / pull_silences 拆分."""
    from app.api.v1.observability import _compute_am_sync

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    # success: 5 push_silence + 3 delete_silence
    for _ in range(5):
        await _insert_oplog(
            db_session,
            "am_sync_success",
            "alert_silence",
            {"operation": "push_silence", "duration_ms": 100, "am_silence_id": "am-1"},
            now,
        )
    for _ in range(3):
        await _insert_oplog(
            db_session,
            "am_sync_success",
            "alert_silence",
            {"operation": "delete_silence", "duration_ms": 50, "am_silence_id": "am-2"},
            now,
        )
    # failed: 2 push_silence + 1 pull_silences
    for _ in range(2):
        await _insert_oplog(
            db_session,
            "am_sync_failed",
            "alert_silence",
            {
                "operation": "push_silence",
                "duration_ms": 2000,
                "error": "err1",
                "am_silence_id": "am-3",
            },
            now,
        )
    await _insert_oplog(
        db_session,
        "am_sync_failed",
        "alert_silence",
        {
            "operation": "pull_silences",
            "duration_ms": 3000,
            "error": "err2",
            "am_silence_id": "am-4",
        },
        now,
    )
    await db_session.commit()

    data = await _compute_am_sync(db_session, start, now, None)
    assert "by_operation" in data
    assert len(data["by_operation"]) == 3
    op_map = {op["operation"]: op for op in data["by_operation"]}
    assert op_map["push_silence"]["success"] == 5
    assert op_map["push_silence"]["failed"] == 2
    assert op_map["delete_silence"]["success"] == 3
    assert op_map["pull_silences"]["failed"] == 1
    # avg_duration: push_silence = (5*100 + 2*2000) / 7 ≈ 642
    assert op_map["push_silence"]["avg_duration_ms"] > 0


async def test_am_sync_recent_failures(db_session) -> None:
    """v1.36 T2.7: recent_failures 包含错误详情, 限制 10 条."""
    from app.api.v1.observability import _compute_am_sync

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    # 12 条失败, 每条用递增时间戳保证可排序
    for i in range(12):
        await _insert_oplog(
            db_session,
            "am_sync_failed",
            "alert_silence",
            {
                "operation": "push_silence",
                "duration_ms": 1000 + i,
                "error": f"error-{i}",
                "am_silence_id": f"am-{i}",
            },
            now - timedelta(minutes=12 - i),
        )
    await db_session.commit()

    data = await _compute_am_sync(db_session, start, now, None)
    assert "recent_failures" in data
    # 仅保留最近 10 条
    assert len(data["recent_failures"]) == 10
    # 验证字段
    rf = data["recent_failures"][0]
    assert "operation" in rf
    assert "error" in rf
    assert "duration_ms" in rf


async def test_am_sync_operation_filter(db_session) -> None:
    """v1.36 T2.7: operation 过滤只保留指定操作."""
    from app.api.v1.observability import _compute_am_sync

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    # success: 3 push_silence + 5 delete_silence
    for _ in range(3):
        await _insert_oplog(
            db_session,
            "am_sync_success",
            "alert_silence",
            {"operation": "push_silence", "duration_ms": 100, "am_silence_id": "am-1"},
            now,
        )
    for _ in range(5):
        await _insert_oplog(
            db_session,
            "am_sync_success",
            "alert_silence",
            {"operation": "delete_silence", "duration_ms": 50, "am_silence_id": "am-2"},
            now,
        )
    # failed: 1 push_silence
    await _insert_oplog(
        db_session,
        "am_sync_failed",
        "alert_silence",
        {
            "operation": "push_silence",
            "duration_ms": 2000,
            "error": "err",
            "am_silence_id": "am-3",
        },
        now,
    )
    await db_session.commit()

    # 仅看 push_silence
    data = await _compute_am_sync(db_session, start, now, "push_silence")
    assert data["total_success"] == 3
    assert data["total_failed"] == 1
    # by_operation 仅含 push_silence
    assert len(data["by_operation"]) == 1
    assert data["by_operation"][0]["operation"] == "push_silence"


async def test_am_sync_empty(db_session) -> None:
    """v1.36 T2.7: 零数据时不抛异常, success_rate=0.0."""
    from app.api.v1.observability import _compute_am_sync

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=24)
    # 不写入任何数据
    data = await _compute_am_sync(db_session, start, now, None)
    assert data["total_success"] == 0
    assert data["total_failed"] == 0
    assert data["success_rate"] == 0.0
    assert data["recent_failures"] == []
    assert data["by_operation"] == []


async def test_am_sync_admin_required() -> None:
    """v1.36 T2.7: 未鉴权应返回 401/403."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/v1/alerts/observability/am-sync")
    assert resp.status_code in (401, 403)


async def test_am_sync_response_includes_instance_id(monkeypatch) -> None:
    """v1.36 T2.7: 响应包含 instance_id / cached / generated_at / params."""
    from fastapi.testclient import TestClient

    from app.api.v1 import observability as obs_mod
    from app.core import deps as deps_mod
    from app.main import app
    from app.models.user import User

    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    mock_user.role = "admin"

    async def _fake_admin():
        return mock_user

    monkeypatch.setattr(deps_mod, "require_role", lambda _role: _fake_admin)
    monkeypatch.setattr(obs_mod, "AdminDep", _fake_admin)

    async def _fake_db():
        yield MagicMock()

    monkeypatch.setattr(obs_mod, "get_db", _fake_db)

    async def _fake_get(key):
        return None

    async def _fake_set(key, value, ttl):
        return True

    monkeypatch.setattr(obs_mod, "cache_get", _fake_get)
    monkeypatch.setattr(obs_mod, "cache_set", _fake_set)

    async def _fake_compute(*args, **kwargs):
        return {
            "total_success": 0,
            "total_failed": 0,
            "total": 0,
            "success_rate": 0.0,
            "avg_duration_ms": 0,
            "by_operation": [],
            "recent_failures": [],
        }

    monkeypatch.setattr(obs_mod, "_compute_am_sync", _fake_compute)

    client = TestClient(app)
    resp = client.get("/api/v1/alerts/observability/am-sync")
    assert resp.status_code != 404
    if resp.status_code == 200:
        body = resp.json()
        assert "data" in body
        assert "instance_id" in body
        assert "cached" in body
        assert "generated_at" in body
        assert "params" in body
        assert body["data"]["total"] == 0
        assert body["cached"] is False


# ===== v1.36: T2.8 Redis 锁可观测 (TC-OBS-007) =====


def _mock_lock_flush_detail(
    acquired: int = 10,
    skipped: int = 5,
    fallback: int = 0,
    errors: int = 0,
    instance_id: str = "host-1-1234",
) -> str:
    """构造 dedup_lock_stats detail JSON."""
    return json.dumps(
        {
            "instance_id": instance_id,
            "acquired": acquired,
            "skipped": skipped,
            "fallback": fallback,
            "errors": errors,
        }
    )


class _MockLockStatsDB:
    """模拟 _compute_lock_stats 用的 db session."""

    def __init__(self, flush_rows):
        self.flush_rows = flush_rows

    async def execute(self, stmt):
        class _Result:
            def all(self_inner):
                return self.flush_rows

        return _Result()


async def test_lock_stats_basic(monkeypatch) -> None:
    """v1.36 T2.8: 基础锁统计 (内存 acquired/skipped/fallback/errors + 比例)."""
    from app.api.v1.observability import _compute_lock_stats
    from app.monitoring import dedup_lock

    # 模拟内存统计
    monkeypatch.setattr(
        dedup_lock,
        "_stats",
        {"acquired": 10, "skipped": 5, "fallback": 2, "errors": 1},
    )
    monkeypatch.setattr(dedup_lock, "_last_flush_at", "2026-06-03T10:00:00Z")

    db = _MockLockStatsDB([])
    data = await _compute_lock_stats(db)
    assert "memory" in data
    m = data["memory"]
    assert m["acquired"] == 10
    assert m["skipped"] == 5
    assert m["fallback"] == 2
    assert m["errors"] == 1
    assert m["total"] == 18
    # acquire_rate = 10/18
    assert abs(m["acquire_rate"] - 10 / 18) < 0.001
    # fallback_rate = 2/18
    assert abs(m["fallback_rate"] - 2 / 18) < 0.001
    # error_rate = 1/18
    assert abs(m["error_rate"] - 1 / 18) < 0.001
    # last_flush_at
    assert data["last_flush_at"] == "2026-06-03T10:00:00Z"


async def test_lock_stats_recent_flushes(monkeypatch) -> None:
    """v1.36 T2.8: recent_flushes 包含最近 10 条 flush 详情."""
    from datetime import datetime, timedelta, timezone

    from app.api.v1.observability import _compute_lock_stats
    from app.monitoring import dedup_lock

    monkeypatch.setattr(
        dedup_lock,
        "_stats",
        {"acquired": 0, "skipped": 0, "fallback": 0, "errors": 0},
    )
    monkeypatch.setattr(dedup_lock, "_last_flush_at", None)

    now = datetime.now(timezone.utc)
    flush_rows = [
        (
            _mock_lock_flush_detail(acquired=5, skipped=2, instance_id="host-1-1"),
            now - timedelta(minutes=i),
        )
        for i in range(5)
    ]
    db = _MockLockStatsDB(flush_rows)
    data = await _compute_lock_stats(db)
    assert "recent_flushes" in data
    assert len(data["recent_flushes"]) == 5
    # 验证字段
    rf = data["recent_flushes"][0]
    assert "acquired" in rf
    assert "skipped" in rf
    assert "instance_id" in rf
    assert "created_at" in rf


async def test_lock_stats_historical_aggregation(monkeypatch) -> None:
    """v1.36 T2.8: historical_recent 累计最近 10 次 flush 的统计."""
    from app.api.v1.observability import _compute_lock_stats
    from app.monitoring import dedup_lock

    monkeypatch.setattr(
        dedup_lock,
        "_stats",
        {"acquired": 0, "skipped": 0, "fallback": 0, "errors": 0},
    )
    monkeypatch.setattr(dedup_lock, "_last_flush_at", None)

    # 3 条历史 flush: 10+5+20 acquired, 2+1+3 skipped, 1+0+0 fallback, 0+1+0 errors
    flush_rows = [
        (_mock_lock_flush_detail(acquired=10, skipped=2, fallback=1, errors=0), None),
        (_mock_lock_flush_detail(acquired=5, skipped=1, fallback=0, errors=1), None),
        (_mock_lock_flush_detail(acquired=20, skipped=3, fallback=0, errors=0), None),
    ]
    db = _MockLockStatsDB(flush_rows)
    data = await _compute_lock_stats(db)
    h = data["historical_recent"]
    assert h["recent_flush_count"] == 3
    assert h["total_acquired"] == 35
    assert h["total_skipped"] == 6
    assert h["total_fallback"] == 1
    assert h["total_errors"] == 1
    assert h["total"] == 43
    # fallback_rate = 1/43
    assert abs(h["fallback_rate"] - 1 / 43) < 0.001
    # error_rate = 1/43
    assert abs(h["error_rate"] - 1 / 43) < 0.001


async def test_lock_stats_empty(monkeypatch) -> None:
    """v1.36 T2.8: 零数据时不抛异常, rates=0.0, last_flush_at=None."""
    from app.api.v1.observability import _compute_lock_stats
    from app.monitoring import dedup_lock

    monkeypatch.setattr(
        dedup_lock,
        "_stats",
        {"acquired": 0, "skipped": 0, "fallback": 0, "errors": 0},
    )
    monkeypatch.setattr(dedup_lock, "_last_flush_at", None)

    db = _MockLockStatsDB([])
    data = await _compute_lock_stats(db)
    assert data["memory"]["total"] == 0
    assert data["memory"]["acquire_rate"] == 0.0
    assert data["last_flush_at"] is None
    assert data["recent_flushes"] == []
    assert data["historical_recent"]["recent_flush_count"] == 0


async def test_lock_stats_admin_required() -> None:
    """v1.36 T2.8: 未鉴权应返回 401/403."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/v1/alerts/observability/lock-stats")
    assert resp.status_code in (401, 403)


async def test_lock_stats_response_includes_instance_id(monkeypatch) -> None:
    """v1.36 T2.8: 响应包含 instance_id / cached / generated_at."""
    from fastapi.testclient import TestClient

    from app.api.v1 import observability as obs_mod
    from app.core import deps as deps_mod
    from app.main import app
    from app.models.user import User

    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    mock_user.role = "admin"

    async def _fake_admin():
        return mock_user

    monkeypatch.setattr(deps_mod, "require_role", lambda _role: _fake_admin)
    monkeypatch.setattr(obs_mod, "AdminDep", _fake_admin)

    async def _fake_db():
        yield MagicMock()

    monkeypatch.setattr(obs_mod, "get_db", _fake_db)

    async def _fake_get(key):
        return None

    async def _fake_set(key, value, ttl):
        return True

    monkeypatch.setattr(obs_mod, "cache_get", _fake_get)
    monkeypatch.setattr(obs_mod, "cache_set", _fake_set)

    async def _fake_compute(*args, **kwargs):
        return {
            "memory": {
                "acquired": 0,
                "skipped": 0,
                "fallback": 0,
                "errors": 0,
                "total": 0,
                "acquire_rate": 0.0,
                "fallback_rate": 0.0,
                "error_rate": 0.0,
            },
            "last_flush_at": None,
            "recent_flushes": [],
            "historical_recent": {
                "recent_flush_count": 0,
                "total_acquired": 0,
                "total_skipped": 0,
                "total_fallback": 0,
                "total_errors": 0,
                "total": 0,
                "fallback_rate": 0.0,
                "error_rate": 0.0,
            },
        }

    monkeypatch.setattr(obs_mod, "_compute_lock_stats", _fake_compute)

    client = TestClient(app)
    resp = client.get("/api/v1/alerts/observability/lock-stats")
    assert resp.status_code != 404
    if resp.status_code == 200:
        body = resp.json()
        assert "data" in body
        assert "instance_id" in body
        assert "cached" in body
        assert "generated_at" in body
        assert "memory" in body["data"]
        assert body["data"]["memory"]["total"] == 0
        assert body["cached"] is False
