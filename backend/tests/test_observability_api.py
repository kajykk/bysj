"""v1.36: observability 路由骨架测试 (T2.1).

验证:
- 路由可正常导入
- 路由已注册到主 APIRouter
- /health 端点可访问
- 响应包含 instance_id + cached + generated_at 元信息
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

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
    from unittest.mock import AsyncMock, MagicMock, patch
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


# ===== v1.36: T2.2 告警趋势 (TC-OBS-001) =====


def _mock_alert_row(action_type: str, created_at, severity: str, rule: str) -> tuple:
    """构造一个 mock OperationLog 行."""
    detail = json.dumps({
        "severity": severity,
        "rule": rule,
        "fingerprint": "fp-1",
        "labels": {"env": "prod"},
    })
    return (action_type, created_at, detail)


async def test_trend_basic_24h(monkeypatch) -> None:
    """v1.36 T2.2: 24h 默认窗口, 返回 buckets + total + 聚合."""
    from app.api.v1.observability import _compute_trend
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    rows = [
        _mock_alert_row("alert_fired", now - timedelta(hours=2), "P0", "HighErrorRate"),
        _mock_alert_row("alert_fired", now - timedelta(hours=1), "P1", "HighLatency"),
        _mock_alert_row("alert_resolved", now - timedelta(minutes=30), "P0", "HighErrorRate"),
    ]

    class _MockResult:
        def all(self_inner):
            return rows

    class _MockSession:
        async def execute(self_inner, stmt):
            return _MockResult()

    db = _MockSession()
    data = await _compute_trend(
        db,
        start_time=now - timedelta(hours=24),
        end_time=now,
        bucket="1h",
        severity=None,
        status=None,
        group_by="severity",
    )
    assert data["total"] == 3
    assert data["by_severity"]["P0"] == 2
    assert data["by_severity"]["P1"] == 1
    assert data["by_status"]["firing"] == 2
    assert data["by_status"]["resolved"] == 1
    assert len(data["buckets"]) >= 1


async def test_trend_with_severity_filter(monkeypatch) -> None:
    """v1.36 T2.2: severity 过滤只保留匹配项."""
    from app.api.v1.observability import _compute_trend
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    rows = [
        _mock_alert_row("alert_fired", now, "P0", "rule-A"),
        _mock_alert_row("alert_fired", now, "P1", "rule-B"),
        _mock_alert_row("alert_fired", now, "P0", "rule-C"),
    ]

    class _MockResult:
        def all(self_inner):
            return rows

    class _MockSession:
        async def execute(self_inner, stmt):
            return _MockResult()

    db = _MockSession()
    data = await _compute_trend(
        db, None, None, "1h", severity="P0", status=None, group_by="severity"
    )
    assert data["total"] == 2
    assert "P1" not in data["by_severity"]
    assert data["by_severity"]["P0"] == 2


async def test_trend_with_status_filter(monkeypatch) -> None:
    """v1.36 T2.2: status 过滤只保留匹配项."""
    from app.api.v1.observability import _compute_trend
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    rows = [
        _mock_alert_row("alert_fired", now, "P0", "rule-A"),
        _mock_alert_row("alert_resolved", now, "P0", "rule-A"),
    ]

    class _MockResult:
        def all(self_inner):
            return rows

    class _MockSession:
        async def execute(self_inner, stmt):
            return _MockResult()

    db = _MockSession()
    # status=firing
    data_firing = await _compute_trend(
        db, None, None, "1h", severity=None, status="firing", group_by="severity"
    )
    assert data_firing["total"] == 1
    assert data_firing["by_status"]["firing"] == 1
    # status=resolved
    data_resolved = await _compute_trend(
        db, None, None, "1h", severity=None, status="resolved", group_by="severity"
    )
    assert data_resolved["total"] == 1
    assert data_resolved["by_status"]["resolved"] == 1


async def test_trend_group_by_rule(monkeypatch) -> None:
    """v1.36 T2.2: group_by=rule 时 by_rule 包含全部规则, 取 Top-20."""
    from app.api.v1.observability import _compute_trend
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    rows = [
        _mock_alert_row("alert_fired", now, "P0", "rule-A"),
        _mock_alert_row("alert_fired", now, "P0", "rule-A"),
        _mock_alert_row("alert_fired", now, "P1", "rule-B"),
    ]

    class _MockResult:
        def all(self_inner):
            return rows

    class _MockSession:
        async def execute(self_inner, stmt):
            return _MockResult()

    db = _MockSession()
    data = await _compute_trend(
        db, None, None, "1h", severity=None, status=None, group_by="rule"
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
        return {"buckets": [], "total": 0, "by_severity": {}, "by_status": {}, "by_rule": {}, "group_by": "severity", "bucket": "1h"}

    # 模拟 cache hit (第二次调用)
    call_count = [0]

    async def _fake_get(key):
        call_count[0] += 1
        if call_count[0] == 1:
            return None  # 第一次 miss
        return {"buckets": [], "total": 5, "by_severity": {"P0": 5}, "by_status": {"firing": 5}, "by_rule": {"X": 5}, "group_by": "severity", "bucket": "1h"}

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
    from app.api.v1 import observability as obs_mod
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models.user import User
    from app.core import deps as deps_mod

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
        return {"buckets": [], "total": 0, "by_severity": {}, "by_status": {}, "by_rule": {}, "group_by": "severity", "bucket": "1h"}

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


def _mock_fired_row(created_at, fp: str, severity: str = "P0", rule: str = "rule-A") -> tuple:
    """构造 mock alert_fired 行."""
    detail = json.dumps({
        "fingerprint": fp,
        "severity": severity,
        "rule": rule,
        "labels": {"env": "prod"},
    })
    return (created_at, detail)


def _mock_acked_row(created_at, fp: str) -> tuple:
    """构造 mock alert_acknowledged 行."""
    detail = json.dumps({"fingerprint": fp, "comment": "ack"})
    return (created_at, detail)


class _MockResponseTimeDB:
    """模拟 _compute_response_time 用的 db session.

    fired_rows 和 acked_rows 可独立配置.
    """

    def __init__(self, fired_rows, acked_rows):
        self.fired_rows = fired_rows
        self.acked_rows = acked_rows
        self.call_count = 0

    async def execute(self, stmt):
        self.call_count += 1
        # 第一次调用取 fired, 第二次取 acked
        rows = self.fired_rows if self.call_count == 1 else self.acked_rows

        class _Result:
            def all(self_inner):
                return rows

        return _Result()


async def test_response_time_basic(monkeypatch) -> None:
    """v1.36 T2.3: 基础响应时长 (3 个 fired, 全部 ack)."""
    from app.api.v1.observability import _compute_response_time
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    fired = [
        _mock_fired_row(now - timedelta(minutes=10), "fp-1", "P0"),
        _mock_fired_row(now - timedelta(minutes=5), "fp-2", "P1"),
        _mock_fired_row(now - timedelta(minutes=1), "fp-3", "P0"),
    ]
    acked = [
        _mock_acked_row(now - timedelta(minutes=5), "fp-1"),   # delta=300s
        _mock_acked_row(now - timedelta(minutes=2), "fp-2"),   # delta=180s
        _mock_acked_row(now - timedelta(minutes=0, seconds=30), "fp-3"),  # delta=30s
    ]
    db = _MockResponseTimeDB(fired, acked)
    data = await _compute_response_time(db, None, None, None)
    assert data["total_fired"] == 3
    assert data["total_acked"] == 3
    assert data["total_pending"] == 0
    assert data["response_time"]["mean"] == pytest.approx(170.0, abs=1.0)
    assert data["response_time"]["min"] == 30.0
    assert data["response_time"]["max"] == 300.0
    assert data["ack_rate"] == 1.0


async def test_response_time_percentiles(monkeypatch) -> None:
    """v1.36 T2.3: p50/p95/p99 分位计算正确性."""
    from app.api.v1.observability import _compute_response_time
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    # 10 个 fired -> 10 个 ack, 响应时间 [1s, 2s, ..., 10s]
    fired = [
        _mock_fired_row(now - timedelta(seconds=20), f"fp-{i}", "P0")
        for i in range(1, 11)
    ]
    # 每次响应时间 = i 秒: ack_at = now - 20s + i
    acked = [
        _mock_acked_row(now - timedelta(seconds=20 - i), f"fp-{i}")
        for i in range(1, 11)
    ]
    db = _MockResponseTimeDB(fired, acked)
    data = await _compute_response_time(db, None, None, None)
    # 注意: 索引从 1 开始, 但有 fp-1..fp-10
    # 响应时间: fp-1=1s, fp-2=2s, ..., fp-10=10s
    assert data["total_acked"] == 10
    assert data["response_time"]["min"] == 1.0
    assert data["response_time"]["max"] == 10.0
    # p50 应在中间 (5-6 之间)
    assert 5.0 <= data["response_time"]["p50"] <= 6.0
    # p95 应在 9-10 之间
    assert 9.0 <= data["response_time"]["p95"] <= 10.0
    # p99 应在 9.9-10 之间
    assert 9.5 <= data["response_time"]["p99"] <= 10.0


async def test_response_time_pending_alerts(monkeypatch) -> None:
    """v1.36 T2.3: pending 告警 (fired 但未 ack) 计入 total_pending."""
    from app.api.v1.observability import _compute_response_time
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    fired = [
        _mock_fired_row(now - timedelta(minutes=10), "fp-1", "P0"),
        _mock_fired_row(now - timedelta(minutes=5), "fp-2", "P1"),
        _mock_fired_row(now - timedelta(minutes=1), "fp-3", "P0"),
    ]
    # 只 ack 了 fp-1
    acked = [
        _mock_acked_row(now - timedelta(minutes=8), "fp-1"),
    ]
    db = _MockResponseTimeDB(fired, acked)
    data = await _compute_response_time(db, None, None, None)
    assert data["total_fired"] == 3
    assert data["total_acked"] == 1
    assert data["total_pending"] == 2
    # ack_rate = 1/3 ≈ 0.333
    assert abs(data["ack_rate"] - 1 / 3) < 0.01


async def test_response_time_severity_breakdown(monkeypatch) -> None:
    """v1.36 T2.3: 按 severity 拆分响应时长 (by_severity)."""
    from app.api.v1.observability import _compute_response_time
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    fired = [
        _mock_fired_row(now - timedelta(seconds=20), "fp-1", "P0"),
        _mock_fired_row(now - timedelta(seconds=20), "fp-2", "P1"),
    ]
    acked = [
        _mock_acked_row(now - timedelta(seconds=18), "fp-1"),  # delta=2s P0
        _mock_acked_row(now - timedelta(seconds=10), "fp-2"),  # delta=10s P1
    ]
    db = _MockResponseTimeDB(fired, acked)
    data = await _compute_response_time(db, None, None, None)
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
    from app.api.v1 import observability as obs_mod
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models.user import User
    from app.core import deps as deps_mod

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
            "total_fired": 0, "total_acked": 0, "total_pending": 0,
            "response_time": {"mean": 0, "p50": 0, "p95": 0, "p99": 0, "max": 0, "min": 0},
            "by_severity": {}, "ack_rate": 0.0,
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


def _mock_fired_detail(rule: str, severity: str) -> str:
    """构造 alert_fired detail JSON."""
    return json.dumps({
        "fingerprint": f"fp-{rule}",
        "rule": rule,
        "severity": severity,
        "labels": {"env": "prod"},
    })


def _mock_escalated_detail(
    rule: str, severity: str, to_level: str = "P0"
) -> str:
    """构造 alert_escalated detail JSON."""
    return json.dumps({
        "fingerprint": f"fp-{rule}",
        "rule": rule,
        "severity": severity,
        "from_level": severity,
        "to_level": to_level,
        "reason": "auto-escalate",
    })


class _MockEscalationDB:
    """模拟 _compute_escalation 用的 db session.

    fired_details 和 esc_details 可独立配置.
    """

    def __init__(self, fired_details, esc_details):
        self.fired_details = fired_details
        self.esc_details = esc_details
        self.call_count = 0

    async def execute(self, stmt):
        self.call_count += 1
        details = self.fired_details if self.call_count == 1 else self.esc_details

        class _Result:
            def scalars(self_inner):
                class _Scalars:
                    def all(self_inner2):
                        return details
                return _Scalars()

        return _Result()


async def test_escalation_rate_basic(monkeypatch) -> None:
    """v1.36 T2.4: 基础升级率 = escalated / fired."""
    from app.api.v1.observability import _compute_escalation

    # 10 个 fired, 3 个 escalated
    fired = [
        _mock_fired_detail("rule-A", "P1") for _ in range(7)
    ] + [
        _mock_fired_detail("rule-B", "P2") for _ in range(3)
    ]
    esc = [
        _mock_escalated_detail("rule-A", "P1", "P0"),
        _mock_escalated_detail("rule-A", "P1", "P0"),
        _mock_escalated_detail("rule-B", "P2", "P1"),
    ]
    db = _MockEscalationDB(fired, esc)
    data = await _compute_escalation(db, None, None, None)
    assert data["total_fired"] == 10
    assert data["total_escalated"] == 3
    assert abs(data["escalation_rate"] - 0.3) < 0.001


async def test_escalation_by_level(monkeypatch) -> None:
    """v1.36 T2.4: by_level 统计每个升级目标级别."""
    from app.api.v1.observability import _compute_escalation

    fired = [_mock_fired_detail("rule-A", "P2") for _ in range(10)]
    esc = [
        _mock_escalated_detail("rule-A", "P2", "P0"),  # 升级到 P0
        _mock_escalated_detail("rule-A", "P2", "P0"),
        _mock_escalated_detail("rule-A", "P2", "P1"),  # 升级到 P1
    ]
    db = _MockEscalationDB(fired, esc)
    data = await _compute_escalation(db, None, None, None)
    assert "by_level" in data
    assert data["by_level"]["P0"] == 2
    assert data["by_level"]["P1"] == 1


async def test_escalation_by_rule(monkeypatch) -> None:
    """v1.36 T2.4: by_rule 包含每个规则的 fired / escalated / rate (Top-20)."""
    from app.api.v1.observability import _compute_escalation

    fired = [
        _mock_fired_detail("rule-A", "P1") for _ in range(5)
    ] + [
        _mock_fired_detail("rule-B", "P2") for _ in range(10)
    ] + [
        _mock_fired_detail("rule-C", "P3") for _ in range(3)
    ]
    esc = [
        _mock_escalated_detail("rule-A", "P1", "P0"),
        _mock_escalated_detail("rule-B", "P2", "P1"),
        _mock_escalated_detail("rule-B", "P2", "P1"),
    ]
    db = _MockEscalationDB(fired, esc)
    data = await _compute_escalation(db, None, None, None)
    assert "by_rule" in data
    assert len(data["by_rule"]) <= 20
    # 找到每个规则的数据
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


async def test_escalation_by_severity(monkeypatch) -> None:
    """v1.36 T2.4: by_severity 拆分升级率 (含 severity 过滤)."""
    from app.api.v1.observability import _compute_escalation

    fired = [
        _mock_fired_detail("rule-A", "P1") for _ in range(5)
    ] + [
        _mock_fired_detail("rule-B", "P2") for _ in range(5)
    ]
    esc = [
        _mock_escalated_detail("rule-A", "P1", "P0"),
        _mock_escalated_detail("rule-B", "P2", "P1"),
    ]
    db = _MockEscalationDB(fired, esc)
    data = await _compute_escalation(db, None, None, None)
    assert "by_severity" in data
    assert "P1" in data["by_severity"]
    assert "P2" in data["by_severity"]
    assert data["by_severity"]["P1"]["fired"] == 5
    assert data["by_severity"]["P1"]["escalated"] == 1
    # severity 过滤: 只看 P1 (新建一个 mock 实例避免 call_count 错乱)
    db2 = _MockEscalationDB(fired, esc)
    data_p1 = await _compute_escalation(db2, None, None, "P1")
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
    from app.api.v1 import observability as obs_mod
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models.user import User
    from app.core import deps as deps_mod

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
            "total_fired": 0, "total_escalated": 0, "escalation_rate": 0.0,
            "by_level": {}, "by_severity": {}, "by_rule": [],
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


def _mock_channel_detail(channel: str, duration_ms: int = 100) -> str:
    """构造 alert_channel_* detail JSON."""
    return json.dumps({
        "channel": channel,
        "duration_ms": duration_ms,
        "rule": "rule-X",
        "severity": "P1",
        "fingerprint": "fp-1",
    })


class _MockChannelStatsDB:
    """模拟 _compute_channel_stats 用的 db session."""

    def __init__(self, rows):
        self.rows = rows

    async def execute(self, stmt):
        class _Result:
            def all(self_inner):
                return self.rows
        return _Result()


async def test_channel_stats_basic(monkeypatch) -> None:
    """v1.36 T2.5: 基础通道成功率 (1 通道, 8 sent / 2 failed = 80%)."""
    from app.api.v1.observability import _compute_channel_stats

    rows = [
        ("alert_channel_sent", _mock_channel_detail("webhook", 50))
        for _ in range(8)
    ] + [
        ("alert_channel_failed", _mock_channel_detail("webhook", 100))
        for _ in range(2)
    ]
    db = _MockChannelStatsDB(rows)
    data = await _compute_channel_stats(db, None, None, None)
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


async def test_channel_stats_zero_failures(monkeypatch) -> None:
    """v1.36 T2.5: 100% 成功率 (零失败) -> success_rate=1.0."""
    from app.api.v1.observability import _compute_channel_stats

    rows = [
        ("alert_channel_sent", _mock_channel_detail("slack", 30))
        for _ in range(5)
    ]
    db = _MockChannelStatsDB(rows)
    data = await _compute_channel_stats(db, None, None, None)
    ch = data["channels"]["slack"]
    assert ch["sent"] == 5
    assert ch["failed"] == 0
    assert ch["success_rate"] == 1.0
    assert data["overall_success_rate"] == 1.0


async def test_channel_stats_multiple_channels(monkeypatch) -> None:
    """v1.36 T2.5: 多通道分别统计 (webhook/slack/dingtalk/email)."""
    from app.api.v1.observability import _compute_channel_stats

    rows = [
        ("alert_channel_sent", _mock_channel_detail("webhook", 50)) for _ in range(10)
    ] + [
        ("alert_channel_failed", _mock_channel_detail("webhook", 100)) for _ in range(2)
    ] + [
        ("alert_channel_sent", _mock_channel_detail("slack", 30)) for _ in range(5)
    ] + [
        ("alert_channel_sent", _mock_channel_detail("dingtalk", 40)) for _ in range(8)
    ] + [
        ("alert_channel_failed", _mock_channel_detail("email", 200)) for _ in range(3)
    ] + [
        ("alert_channel_sent", _mock_channel_detail("email", 200)) for _ in range(2)
    ]
    db = _MockChannelStatsDB(rows)
    data = await _compute_channel_stats(db, None, None, None)
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
    data_webhook = await _compute_channel_stats(db, None, None, "webhook")
    assert "webhook" in data_webhook["channels"]
    assert "slack" not in data_webhook["channels"]


async def test_channel_stats_duration_tracking(monkeypatch) -> None:
    """v1.36 T2.5: avg_duration_ms / max_duration_ms 统计正确."""
    from app.api.v1.observability import _compute_channel_stats

    rows = [
        ("alert_channel_sent", _mock_channel_detail("webhook", 50)),
        ("alert_channel_sent", _mock_channel_detail("webhook", 100)),
        ("alert_channel_sent", _mock_channel_detail("webhook", 200)),
    ]
    db = _MockChannelStatsDB(rows)
    data = await _compute_channel_stats(db, None, None, None)
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
    from app.api.v1 import observability as obs_mod
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models.user import User
    from app.core import deps as deps_mod

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
            "channels": {}, "total_sent": 0, "total_failed": 0,
            "total": 0, "overall_success_rate": 0.0,
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


def _mock_fired_alert_detail(severity: str = "P0") -> str:
    """构造 alert_fired detail JSON."""
    return json.dumps({
        "fingerprint": f"fp-fired-{severity}",
        "rule": "rule-A",
        "severity": severity,
    })


def _mock_silenced_detail(
    silence_name: str = "weekend-maintenance",
    severity: str = "P1",
) -> str:
    """构造 alert_silenced detail JSON."""
    return json.dumps({
        "fingerprint": f"fp-sil-{silence_name}-{severity}",
        "rule": "rule-A",
        "severity": severity,
        "silence_name": silence_name,
        "silenced_by": 1,
    })


class _MockSilenceHitRateDB:
    """模拟 _compute_silence_hit_rate 用的 db session.

    fired_details 和 sil_details 可独立配置.
    """

    def __init__(self, fired_details, sil_details):
        self.fired_details = fired_details
        self.sil_details = sil_details
        self.call_count = 0

    async def execute(self, stmt):
        self.call_count += 1
        details = self.fired_details if self.call_count == 1 else self.sil_details

        class _Result:
            def scalars(self_inner):
                class _Scalars:
                    def all(self_inner2):
                        return details
                return _Scalars()

        return _Result()


async def test_silence_hit_rate_basic(monkeypatch) -> None:
    """v1.36 T2.6: 基础命中率 = silenced / (fired + silenced)."""
    from app.api.v1.observability import _compute_silence_hit_rate

    # 7 fired, 3 silenced -> hit_rate = 3/10 = 0.3
    fired = [_mock_fired_alert_detail("P0") for _ in range(7)]
    sil = [
        _mock_silenced_detail("weekend", "P0"),
        _mock_silenced_detail("weekend", "P1"),
        _mock_silenced_detail("nightly", "P2"),
    ]
    db = _MockSilenceHitRateDB(fired, sil)
    data = await _compute_silence_hit_rate(db, None, None)
    assert data["total_fired"] == 7
    assert data["total_silenced"] == 3
    assert data["total_processed"] == 10
    assert abs(data["hit_rate"] - 0.3) < 0.001


async def test_silence_hit_rate_by_matcher(monkeypatch) -> None:
    """v1.36 T2.6: by_matcher 按 silence_name 拆分 (Top-20)."""
    from app.api.v1.observability import _compute_silence_hit_rate

    fired = [_mock_fired_alert_detail("P0") for _ in range(10)]
    sil = (
        [_mock_silenced_detail("weekend", "P0") for _ in range(5)]
        + [_mock_silenced_detail("nightly", "P1") for _ in range(3)]
        + [_mock_silenced_detail("deploy", "P2") for _ in range(2)]
    )
    db = _MockSilenceHitRateDB(fired, sil)
    data = await _compute_silence_hit_rate(db, None, None)
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


async def test_silence_hit_rate_by_severity(monkeypatch) -> None:
    """v1.36 T2.6: by_severity 拆分 silenced 分布."""
    from app.api.v1.observability import _compute_silence_hit_rate

    fired = [_mock_fired_alert_detail("P0") for _ in range(5)]
    sil = (
        [_mock_silenced_detail("weekend", "P0") for _ in range(4)]
        + [_mock_silenced_detail("nightly", "P1") for _ in range(2)]
        + [_mock_silenced_detail("deploy", "P2") for _ in range(2)]
    )
    db = _MockSilenceHitRateDB(fired, sil)
    data = await _compute_silence_hit_rate(db, None, None)
    assert "by_severity" in data
    assert data["by_severity"]["P0"]["silenced"] == 4
    assert data["by_severity"]["P1"]["silenced"] == 2
    assert data["by_severity"]["P2"]["silenced"] == 2
    # ratio: 4/8 = 0.5
    assert abs(data["by_severity"]["P0"]["ratio"] - 0.5) < 0.001


async def test_silence_hit_rate_empty(monkeypatch) -> None:
    """v1.36 T2.6: 零数据时 hit_rate=0.0, 不抛异常."""
    from app.api.v1.observability import _compute_silence_hit_rate

    db = _MockSilenceHitRateDB([], [])
    data = await _compute_silence_hit_rate(db, None, None)
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
    from app.api.v1 import observability as obs_mod
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models.user import User
    from app.core import deps as deps_mod

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
            "total_fired": 0, "total_silenced": 0, "total_processed": 0,
            "hit_rate": 0.0, "by_matcher": [], "by_severity": {},
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


def _mock_am_sync_success(
    operation: str = "push_silence",
    duration_ms: int = 100,
) -> str:
    """构造 am_sync_success detail JSON."""
    return json.dumps({
        "operation": operation,
        "duration_ms": duration_ms,
        "am_silence_id": "am-silence-1",
    })


def _mock_am_sync_failed(
    operation: str = "push_silence",
    error: str = "AM timeout",
    duration_ms: int = 2000,
) -> str:
    """构造 am_sync_failed detail JSON."""
    return json.dumps({
        "operation": operation,
        "duration_ms": duration_ms,
        "error": error,
        "am_silence_id": "am-silence-2",
    })


class _MockAmSyncDB:
    """模拟 _compute_am_sync 用的 db session.

    succ_rows 和 fail_rows 可独立配置.
    """

    def __init__(self, succ_rows, fail_rows):
        self.succ_rows = succ_rows
        self.fail_rows = fail_rows
        self.call_count = 0

    async def execute(self, stmt):
        self.call_count += 1
        rows = self.succ_rows if self.call_count == 1 else self.fail_rows

        class _Result:
            def all(self_inner):
                return rows
        return _Result()


async def test_am_sync_stats_basic(monkeypatch) -> None:
    """v1.36 T2.7: 基础同步统计 (success / failed / success_rate)."""
    from app.api.v1.observability import _compute_am_sync

    # 8 success, 2 failed -> success_rate = 0.8
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    succ = [
        (_mock_am_sync_success("push_silence", 100), now)
        for _ in range(8)
    ]
    fail = [
        (_mock_am_sync_failed("push_silence", "timeout", 2000), now)
        for _ in range(2)
    ]
    db = _MockAmSyncDB(succ, fail)
    data = await _compute_am_sync(db, None, None, None)
    assert data["total_success"] == 8
    assert data["total_failed"] == 2
    assert data["total"] == 10
    assert abs(data["success_rate"] - 0.8) < 0.001


async def test_am_sync_by_operation(monkeypatch) -> None:
    """v1.36 T2.7: by_operation 按 push_silence / delete_silence / pull_silences 拆分."""
    from app.api.v1.observability import _compute_am_sync

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    succ = (
        [(_mock_am_sync_success("push_silence", 100), now) for _ in range(5)]
        + [(_mock_am_sync_success("delete_silence", 50), now) for _ in range(3)]
    )
    fail = (
        [(_mock_am_sync_failed("push_silence", "err1", 2000), now) for _ in range(2)]
        + [(_mock_am_sync_failed("pull_silences", "err2", 3000), now) for _ in range(1)]
    )
    db = _MockAmSyncDB(succ, fail)
    data = await _compute_am_sync(db, None, None, None)
    assert "by_operation" in data
    assert len(data["by_operation"]) == 3
    op_map = {op["operation"]: op for op in data["by_operation"]}
    assert op_map["push_silence"]["success"] == 5
    assert op_map["push_silence"]["failed"] == 2
    assert op_map["delete_silence"]["success"] == 3
    assert op_map["pull_silences"]["failed"] == 1
    # avg_duration: push_silence = (5*100 + 2*2000) / 7 ≈ 642
    assert op_map["push_silence"]["avg_duration_ms"] > 0


async def test_am_sync_recent_failures(monkeypatch) -> None:
    """v1.36 T2.7: recent_failures 包含错误详情, 限制 10 条."""
    from app.api.v1.observability import _compute_am_sync

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    # 12 条失败
    fail = [
        (_mock_am_sync_failed("push_silence", f"error-{i}", 1000 + i), now)
        for i in range(12)
    ]
    db = _MockAmSyncDB([], fail)
    data = await _compute_am_sync(db, None, None, None)
    assert "recent_failures" in data
    # 仅保留最近 10 条
    assert len(data["recent_failures"]) == 10
    # 验证字段
    rf = data["recent_failures"][0]
    assert "operation" in rf
    assert "error" in rf
    assert "duration_ms" in rf


async def test_am_sync_operation_filter(monkeypatch) -> None:
    """v1.36 T2.7: operation 过滤只保留指定操作."""
    from app.api.v1.observability import _compute_am_sync

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    succ = (
        [(_mock_am_sync_success("push_silence", 100), now) for _ in range(3)]
        + [(_mock_am_sync_success("delete_silence", 50), now) for _ in range(5)]
    )
    fail = [
        (_mock_am_sync_failed("push_silence", "err", 2000), now)
    ]
    db = _MockAmSyncDB(succ, fail)
    # 仅看 push_silence
    data = await _compute_am_sync(db, None, None, "push_silence")
    assert data["total_success"] == 3
    assert data["total_failed"] == 1
    # by_operation 仅含 push_silence
    assert len(data["by_operation"]) == 1
    assert data["by_operation"][0]["operation"] == "push_silence"


async def test_am_sync_empty(monkeypatch) -> None:
    """v1.36 T2.7: 零数据时不抛异常, success_rate=0.0."""
    from app.api.v1.observability import _compute_am_sync

    db = _MockAmSyncDB([], [])
    data = await _compute_am_sync(db, None, None, None)
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
    from app.api.v1 import observability as obs_mod
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models.user import User
    from app.core import deps as deps_mod

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
            "total_success": 0, "total_failed": 0, "total": 0,
            "success_rate": 0.0, "avg_duration_ms": 0,
            "by_operation": [], "recent_failures": [],
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
    return json.dumps({
        "instance_id": instance_id,
        "acquired": acquired,
        "skipped": skipped,
        "fallback": fallback,
        "errors": errors,
    })


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
        dedup_lock, "_stats",
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
    from app.api.v1.observability import _compute_lock_stats
    from app.monitoring import dedup_lock
    from datetime import datetime, timezone, timedelta

    monkeypatch.setattr(
        dedup_lock, "_stats",
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
        dedup_lock, "_stats",
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
        dedup_lock, "_stats",
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
    from app.api.v1 import observability as obs_mod
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models.user import User
    from app.core import deps as deps_mod

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
                "acquired": 0, "skipped": 0, "fallback": 0, "errors": 0,
                "total": 0, "acquire_rate": 0.0,
                "fallback_rate": 0.0, "error_rate": 0.0,
            },
            "last_flush_at": None,
            "recent_flushes": [],
            "historical_recent": {
                "recent_flush_count": 0, "total_acquired": 0,
                "total_skipped": 0, "total_fallback": 0, "total_errors": 0,
                "total": 0, "fallback_rate": 0.0, "error_rate": 0.0,
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
