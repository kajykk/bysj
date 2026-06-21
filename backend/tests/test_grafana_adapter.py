"""v1.37-grafana-dashboards: Grafana Adapter 端点单元测试 (T-GRAF-008).

覆盖测试组:
- TC-QUERY-001: /grafana/query metric 分发 (8/8, 本文件 7 + unknown_400)
- TC-DATAFRAME-001: Grafana dataframe 格式 (2/7 本文件, 其余由 T-GRAF-006 smoke 覆盖)
- TC-VAR-001: /grafana/variable 4 种类型 (4/4)
- 端点 smoke: /grafana/ + /grafana/health (1+1)

合计: 15 测试

技术依赖:
- conftest 提供: client (TestClient), as_role, db_session, seeded_user_id
- _compute_* 函数通过 monkeypatch mock 避免真实 DB 查询.
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-ci-only")

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.deps import require_sa_or_admin
from app.models.user import User


# ============ Fixtures ============


@pytest.fixture
def grafana_admin_client() -> TestClient:
    """提供 admin 身份覆盖的 TestClient."""
    async def _fake_admin():
        return User(
            id=0, username="grafana_admin", email="admin@test.com",
            role="admin", status="active", password_hash="!",
        )

    app.dependency_overrides[require_sa_or_admin] = _fake_admin
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(require_sa_or_admin, None)


@pytest.fixture
def mock_v136_compute(monkeypatch):
    """Mock v1.36 _compute_* 函数, 返回稳定的测试数据."""
    from app.api.v1 import observability as obs_mod

    # trend
    async def _mock_trend(db, start_time, end_time, bucket, severity, status, group_by):
        return {
            "total": 3,
            "by_severity": {"P0": 2, "P1": 1},
            "by_status": {"firing": 2, "resolved": 1},
            "by_rule": {"rule-A": 2, "rule-B": 1},
            "group_by": group_by,
            "bucket": bucket,
            "buckets": [
                {"timestamp": "2026-06-03T08:00:00Z", "count": 1, "by_severity": {"P0": 1}, "by_status": {"firing": 1}},
                {"timestamp": "2026-06-03T09:00:00Z", "count": 2, "by_severity": {"P0": 1, "P1": 1}, "by_status": {"firing": 1, "resolved": 1}},
            ],
        }

    # response_time
    async def _mock_rt(db, start_time, end_time, severity):
        return {
            "total_fired": 5, "total_acked": 4, "total_pending": 1,
            "response_time": {"mean": 120, "p50": 100, "p95": 200, "p99": 250, "min": 30, "max": 300},
            "by_severity": {"P0": {"mean": 80, "p50": 70, "p95": 150, "p99": 200}},
            "ack_rate": 0.8,
        }

    # escalation
    async def _mock_esc(db, start_time, end_time, severity):
        return {
            "total_fired": 10, "total_escalated": 2, "escalation_rate": 0.2,
            "by_level": {"P0": 1, "P1": 1},
            "by_severity": {},
            "by_rule": [],
        }

    # channel_stats
    async def _mock_ch(db, start_time, end_time, channel):
        return {
            "channels": {
                "webhook": {"sent": 5, "failed": 0, "total": 5, "success_rate": 1.0, "avg_duration_ms": 30, "max_duration_ms": 50},
                "slack": {"sent": 3, "failed": 1, "total": 4, "success_rate": 0.75, "avg_duration_ms": 40, "max_duration_ms": 80},
            },
            "total_sent": 8, "total_failed": 1, "total": 9, "overall_success_rate": 0.89,
        }

    # silence_hit_rate
    async def _mock_sh(db, start_time, end_time):
        return {
            "total_fired": 10, "total_silenced": 3, "total_processed": 13,
            "hit_rate": 0.23,
            "by_matcher": [
                {"silence_name": "weekend", "silenced_count": 2, "by_severity": {"P0": 2}},
                {"silence_name": "nightly", "silenced_count": 1, "by_severity": {"P1": 1}},
            ],
            "by_severity": {},
        }

    # am_sync
    async def _mock_am(db, start_time, end_time, operation):
        return {
            "total_success": 8, "total_failed": 1, "total": 9,
            "success_rate": 0.89, "avg_duration_ms": 100,
            "by_operation": [
                {"operation": "push_silence", "success": 5, "failed": 0},
                {"operation": "delete_silence", "success": 3, "failed": 1},
            ],
            "recent_failures": [],
        }

    # lock_stats
    async def _mock_lock(db):
        return {
            "memory": {"acquired": 10, "skipped": 5, "fallback": 0, "errors": 0, "total": 15, "acquire_rate": 0.67, "fallback_rate": 0.0, "error_rate": 0.0},
            "last_flush_at": "2026-06-03T10:00:00Z",
            "recent_flushes": [],
            "historical_recent": {"recent_flush_count": 5, "total_acquired": 50, "total_skipped": 10, "total_fallback": 0, "total_errors": 0, "total": 60, "fallback_rate": 0.0, "error_rate": 0.0},
        }

    monkeypatch.setattr(obs_mod, "_compute_trend", _mock_trend)
    monkeypatch.setattr(obs_mod, "_compute_response_time", _mock_rt)
    monkeypatch.setattr(obs_mod, "_compute_escalation", _mock_esc)
    monkeypatch.setattr(obs_mod, "_compute_channel_stats", _mock_ch)
    monkeypatch.setattr(obs_mod, "_compute_silence_hit_rate", _mock_sh)
    monkeypatch.setattr(obs_mod, "_compute_am_sync", _mock_am)
    monkeypatch.setattr(obs_mod, "_compute_lock_stats", _mock_lock)

    return {
        "trend": _mock_trend, "response_time": _mock_rt, "escalation": _mock_esc,
        "channel_stats": _mock_ch, "silence_hit_rate": _mock_sh, "am_sync": _mock_am,
        "lock_stats": _mock_lock,
    }


# ============ Tests: 端点 smoke (1) ============


def test_health_returns_200(grafana_admin_client: TestClient) -> None:
    """T-GRAF-008: GET /grafana/health → 200 with version v1.37."""
    resp = grafana_admin_client.get("/api/v1/alerts/observability/grafana/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "v1.37"
    assert "timestamp" in body


# ============ Tests: /query 7 metric dispatch (7) ============


def test_query_trend(grafana_admin_client: TestClient, mock_v136_compute) -> None:
    """T-GRAF-008: /query trend → Grafana dataframe 格式."""
    resp = grafana_admin_client.post(
        "/api/v1/alerts/observability/grafana/query",
        json={"metric": "trend", "params": {}},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Dataframe format: list of {target, datapoints}
    assert isinstance(data, list)
    assert len(data) >= 1
    # Verify each series has expected structure
    for s in data:
        assert "target" in s
        assert "datapoints" in s
        assert isinstance(s["datapoints"], list)
    # Verify P0 and P1 series are present (group_by=severity)
    targets = {s["target"] for s in data}
    assert "alert_P0" in targets
    assert "alert_P1" in targets


def test_query_response_time(grafana_admin_client: TestClient, mock_v136_compute) -> None:
    """T-GRAF-008: /query response_time → 包含 mean/p50/p95/p99."""
    resp = grafana_admin_client.post(
        "/api/v1/alerts/observability/grafana/query",
        json={"metric": "response_time", "params": {}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    targets = {s["target"] for s in data}
    # 必须包含 4 个分位数
    for tgt in ("response_time_mean", "response_time_p50", "response_time_p95", "response_time_p99"):
        assert tgt in targets, f"missing {tgt}"


def test_query_escalation(grafana_admin_client: TestClient, mock_v136_compute) -> None:
    """T-GRAF-008: /query escalation → 包含 by_level 升级统计."""
    resp = grafana_admin_client.post(
        "/api/v1/alerts/observability/grafana/query",
        json={"metric": "escalation", "params": {}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    targets = {s["target"] for s in data}
    # 至少包含 P0/P1 升级数 + 总升级率
    assert "escalated_to_P0" in targets
    assert "escalated_to_P1" in targets
    assert "escalation_rate" in targets


def test_query_channel_stats(grafana_admin_client: TestClient, mock_v136_compute) -> None:
    """T-GRAF-008: /query channel_stats → 包含 per-channel 成功率."""
    resp = grafana_admin_client.post(
        "/api/v1/alerts/observability/grafana/query",
        json={"metric": "channel_stats", "params": {}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    targets = {s["target"] for s in data}
    assert "webhook_success_rate" in targets
    assert "slack_success_rate" in targets
    assert "overall_success_rate" in targets


def test_query_silence_hit_rate(grafana_admin_client: TestClient, mock_v136_compute) -> None:
    """T-GRAF-008: /query silence_hit_rate → 包含 hit_rate 和 by_matcher."""
    resp = grafana_admin_client.post(
        "/api/v1/alerts/observability/grafana/query",
        json={"metric": "silence_hit_rate", "params": {}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    targets = {s["target"] for s in data}
    assert "silence_hit_rate" in targets
    assert "matcher_weekend" in targets
    assert "matcher_nightly" in targets


def test_query_am_sync(grafana_admin_client: TestClient, mock_v136_compute) -> None:
    """T-GRAF-008: /query am_sync → 包含 success_rate 和 by_operation."""
    resp = grafana_admin_client.post(
        "/api/v1/alerts/observability/grafana/query",
        json={"metric": "am_sync", "params": {}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    targets = {s["target"] for s in data}
    assert "am_sync_success_rate" in targets
    assert "am_push_silence_success" in targets
    assert "am_delete_silence_failed" in targets


def test_query_lock_stats(grafana_admin_client: TestClient, mock_v136_compute) -> None:
    """T-GRAF-008: /query lock_stats → 包含锁指标."""
    resp = grafana_admin_client.post(
        "/api/v1/alerts/observability/grafana/query",
        json={"metric": "lock_stats", "params": {}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    targets = {s["target"] for s in data}
    assert "lock_acquire_rate" in targets
    assert "lock_fallback_rate" in targets
    assert "lock_error_rate" in targets


# ============ Tests: /query unknown metric (1) ============


def test_query_unknown_metric_400(grafana_admin_client: TestClient, mock_v136_compute) -> None:
    """T-GRAF-008: 未知 metric → 400/422.

    P1-SEC-023 修复后，metric 字段使用 Literal 类型在 Pydantic schema 层校验，
    返回 422 (Unprocessable Entity)。两种状态码均表示输入校验失败。
    """
    resp = grafana_admin_client.post(
        "/api/v1/alerts/observability/grafana/query",
        json={"metric": "unknown_metric", "params": {}},
    )
    assert resp.status_code in (400, 422)


# ============ Tests: dataframe 格式 (2) ============


def test_dataframe_trend_format(grafana_admin_client: TestClient, mock_v136_compute) -> None:
    """T-GRAF-008: trend dataframe 必须含 target + datapoints, datapoints[1] = epoch_ms."""
    resp = grafana_admin_client.post(
        "/api/v1/alerts/observability/grafana/query",
        json={"metric": "trend", "params": {}},
    )
    data = resp.json()
    for s in data:
        assert "target" in s
        assert "datapoints" in s
        for dp in s["datapoints"]:
            assert len(dp) == 2
            # dp[0] = value, dp[1] = epoch ms
            assert isinstance(dp[1], int)
            assert dp[1] > 1700000000000  # reasonable epoch ms (post-2023)


def test_dataframe_response_time_format(grafana_admin_client: TestClient, mock_v136_compute) -> None:
    """T-GRAF-008: response_time dataframe 是单点 series (stat 类型)."""
    resp = grafana_admin_client.post(
        "/api/v1/alerts/observability/grafana/query",
        json={"metric": "response_time", "params": {}},
    )
    data = resp.json()
    # response_time 是单点 (no time series)
    for s in data:
        assert len(s["datapoints"]) == 1
        # 单点的 ts 是 now
        assert s["datapoints"][0][1] > 1700000000000


# ============ Tests: /variable 4 types (4) ============


def test_variable_rule_returns_top20(grafana_admin_client: TestClient, mock_v136_compute) -> None:
    """T-GRAF-008: /variable type=rule → 列表 [{text, value}], 最多 20 个."""
    resp = grafana_admin_client.post(
        "/api/v1/alerts/observability/grafana/variable",
        json={"type": "rule"},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert isinstance(result, list)
    assert len(result) <= 20
    for item in result:
        assert "text" in item
        assert "value" in item
    # Mock 中有 2 个 rule (rule-A, rule-B)
    assert len(result) == 2
    assert result[0]["text"] == "rule-A"
    assert result[0]["value"] == "rule-A"


def test_variable_matcher_returns_top10(grafana_admin_client: TestClient, mock_v136_compute) -> None:
    """T-GRAF-008: /variable type=matcher → 列表, 最多 10 个."""
    resp = grafana_admin_client.post(
        "/api/v1/alerts/observability/grafana/variable",
        json={"type": "matcher"},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert isinstance(result, list)
    assert len(result) <= 10
    # Mock 中有 2 个 matcher
    assert len(result) == 2
    assert result[0]["text"] == "weekend"
    assert result[0]["value"] == "weekend"


def test_variable_operation_returns_all(grafana_admin_client: TestClient) -> None:
    """T-GRAF-008: /variable type=operation → 静态列表 (5 个: ALL + 4 ops)."""
    resp = grafana_admin_client.post(
        "/api/v1/alerts/observability/grafana/variable",
        json={"type": "operation"},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert isinstance(result, list)
    assert len(result) == 5
    values = {item["value"] for item in result}
    assert values == {"all", "push_silence", "delete_silence", "expire_silence", "pull_silences"}


def test_variable_channel_returns_all(grafana_admin_client: TestClient) -> None:
    """T-GRAF-008: /variable type=channel → 静态列表 (5 个: ALL + 4 channels)."""
    resp = grafana_admin_client.post(
        "/api/v1/alerts/observability/grafana/variable",
        json={"type": "channel"},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert isinstance(result, list)
    assert len(result) == 5
    values = {item["value"] for item in result}
    assert values == {"all", "webhook", "slack", "dingtalk", "email"}


# ============ Test count verification ============

def test_test_count() -> None:
    """Meta-test: 验证本文件测试数量 == 15 (不含本 meta-test)."""
    import inspect
    test_funcs = [
        name for name, obj in globals().items()
        if name.startswith("test_") and callable(obj) and name != "test_test_count"
    ]
    assert len(test_funcs) == 15, f"expected 15 tests, got {len(test_funcs)}: {test_funcs}"
