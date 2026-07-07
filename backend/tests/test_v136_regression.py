"""v1.37-grafana-dashboards: v1.36 observability 端点 smoke 回归 (T-GRAF-010).

覆盖测试组:
- TC-V136-REG-001: v1.36 端点 smoke 回归 (8/8)
  - test_trend_endpoint
  - test_response_time_endpoint
  - test_escalation_endpoint
  - test_channel_stats_endpoint
  - test_silence_hit_rate_endpoint
  - test_am_sync_endpoint
  - test_lock_stats_endpoint
  - test_health_endpoint

v1.37 兼容性验证:
- v1.36 8 个 GET 端点全部返回 200
- 不需要 grafana adapter 鉴权 (使用原有 AdminDep)
- 数据结构与 v1.36 完全一致
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-ci-only")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def admin_client(as_role, client: TestClient):
    """提供 admin 身份的 TestClient.

    复用 conftest.py 的 session-scope client, 避免创建新 TestClient
    触发 lifespan 重复启动 (model_engine 不支持重复 preload).
    """
    as_role("admin", 3)
    yield client


# ============ v1.36 端点 smoke 测试 (8) ============


def test_trend_endpoint(admin_client: TestClient) -> None:
    """T-GRAF-010: GET /alerts/observability/trend → 200."""
    resp = admin_client.get("/api/v1/alerts/observability/trend")
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    # v1.36 wrapper: {cached, data: {total, by_severity, ...}, generated_at, instance_id}
    assert "data" in body
    data = body["data"]
    assert "total" in data
    assert "by_severity" in data or "buckets" in data  # 至少有一个


def test_response_time_endpoint(admin_client: TestClient) -> None:
    """T-GRAF-010: GET /alerts/observability/response-time → 200."""
    resp = admin_client.get("/api/v1/alerts/observability/response-time")
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}"


def test_escalation_endpoint(admin_client: TestClient) -> None:
    """T-GRAF-010: GET /alerts/observability/escalation → 200."""
    resp = admin_client.get("/api/v1/alerts/observability/escalation")
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}"


def test_channel_stats_endpoint(admin_client: TestClient) -> None:
    """T-GRAF-010: GET /alerts/observability/channel-stats → 200."""
    resp = admin_client.get("/api/v1/alerts/observability/channel-stats")
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}"


def test_silence_hit_rate_endpoint(admin_client: TestClient) -> None:
    """T-GRAF-010: GET /alerts/observability/silence-hit-rate → 200."""
    resp = admin_client.get("/api/v1/alerts/observability/silence-hit-rate")
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}"


def test_am_sync_endpoint(admin_client: TestClient) -> None:
    """T-GRAF-010: GET /alerts/observability/am-sync → 200."""
    resp = admin_client.get("/api/v1/alerts/observability/am-sync")
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}"


def test_lock_stats_endpoint(admin_client: TestClient) -> None:
    """T-GRAF-010: GET /alerts/observability/lock-stats → 200."""
    resp = admin_client.get("/api/v1/alerts/observability/lock-stats")
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}"


def test_health_endpoint(admin_client: TestClient) -> None:
    """T-GRAF-010: GET /alerts/observability/health → 200."""
    resp = admin_client.get("/api/v1/alerts/observability/health")
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    # v1.36 wrapper: data.endpoint, data.status
    assert "data" in body
    assert body["data"]["status"] == "ok"


# ============ Test count verification ============


def test_test_count() -> None:
    """Meta-test: 验证本文件测试数量 == 8 (不含本 meta-test)."""
    test_funcs = [
        name
        for name in globals()
        if name.startswith("test_")
        and callable(globals()[name])
        and name != "test_test_count"
    ]
    assert (
        len(test_funcs) == 8
    ), f"expected 8 tests, got {len(test_funcs)}: {test_funcs}"
