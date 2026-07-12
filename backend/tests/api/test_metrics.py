"""Prometheus /metrics 端点测试 (v1.30)"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# CRIT-007: Metrics 端点要求 Bearer 令牌鉴权，非生产环境使用默认 dev token
_METRICS_AUTH = {"Authorization": "Bearer dev-only-metrics-token"}


@pytest.fixture(autouse=True)
def reset_metrics():
    """每个测试前重置指标, 避免测试间相互影响."""
    from app.core.metrics import reset_registry

    reset_registry()
    yield


def test_metrics_endpoint_returns_200(client: TestClient) -> None:
    """GET /api/v1/metrics 应返回 200."""
    response = client.get("/api/v1/metrics", headers=_METRICS_AUTH)
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")


def test_metrics_endpoint_format_valid(client: TestClient) -> None:
    """返回的 exposition 格式应包含 HELP 和 TYPE 注释."""
    response = client.get("/api/v1/metrics", headers=_METRICS_AUTH)
    body = response.text
    # 必须有 HELP 和 TYPE 注释
    assert "# HELP" in body
    assert "# TYPE" in body


def test_metrics_contains_app_info(client: TestClient) -> None:
    """应包含 app_info 指标."""
    response = client.get("/api/v1/metrics", headers=_METRICS_AUTH)
    body = response.text
    assert "app" in body
    assert "v1.32" in body


def test_http_request_counter_increments(client: TestClient) -> None:
    """触发 5 个 GET /health, http_requests_total 应增加 5."""
    for _ in range(5):
        client.get("/health")

    response = client.get("/api/v1/metrics", headers=_METRICS_AUTH)
    body = response.text
    # /health 出现 >= 5 次
    health_count = 0
    for line in body.splitlines():
        if (
            line.startswith("http_requests_total{")
            and 'path="/health"' in line
            and 'status="200"' in line
        ):
            health_count = int(float(line.split()[-1]))
    assert health_count >= 5


def test_histogram_has_buckets(client: TestClient) -> None:
    """http_request_duration_seconds_bucket 应有 le label."""
    client.get("/health")
    response = client.get("/api/v1/metrics", headers=_METRICS_AUTH)
    body = response.text
    assert "http_request_duration_seconds_bucket" in body
    assert 'le="+Inf"' in body or 'le="+Inf"' in body
    assert "http_request_duration_seconds_count" in body
    assert "http_request_duration_seconds_sum" in body


def test_metrics_excludes_metrics_endpoint_itself(client: TestClient) -> None:
    """/metrics 自身不应出现在 http_requests_total 计数中 (避免自激)."""
    # 先请求 /metrics 一次, 然后验证它不在指标中
    client.get("/api/v1/metrics", headers=_METRICS_AUTH)
    response = client.get("/api/v1/metrics", headers=_METRICS_AUTH)
    body = response.text
    # /api/v1/metrics 不应有计数行
    for line in body.splitlines():
        if line.startswith("http_requests_total{"):
            assert 'path="/api/v1/metrics"' not in line


def test_websocket_gauge(client: TestClient, seeded_user_id: int) -> None:
    """建立 WebSocket 连接应增加 websocket_connections_active."""
    from app.core.security import create_access_token

    token = create_access_token({"sub": "1", "role": "user"})

    # 获取初始值
    response = client.get("/api/v1/metrics", headers=_METRICS_AUTH)
    initial_body = response.text
    initial_value = 0.0
    for line in initial_body.splitlines():
        if line.startswith("websocket_connections_active "):
            initial_value = float(line.split()[-1])

    with client.websocket_connect("/ws/1") as ws:
        ws.send_text('{"type":"auth","token":"%s"}' % token)
        ws.send_text('{"type":"ping"}')
        ws.receive_json()

        response = client.get("/api/v1/metrics", headers=_METRICS_AUTH)
        body = response.text
        current_value = 0.0
        for line in body.splitlines():
            if line.startswith("websocket_connections_active "):
                current_value = float(line.split()[-1])
        # 连接建立后, gauge 应增加
        assert current_value > initial_value


def test_counter_label_validation() -> None:
    """Counter 应对错误标签抛出 ValueError."""
    from app.core.metrics import http_requests_total

    with pytest.raises(ValueError):
        http_requests_total.inc(wrong_label="x")


def test_render_exposition_idempotent(client: TestClient) -> None:
    """连续两次 render 应得到相同的已注册指标定义 (HELP/TYPE 注释行).

    注: 指标值行 (metric_name value) 可能因非确定性状态指标 (如
    observability_escalation_rate, smtp_circuit_state) 的条件渲染而不同,
    因此只比较 HELP 注释行 (指标注册是确定性的).
    """
    r1 = client.get("/api/v1/metrics", headers=_METRICS_AUTH).text
    r2 = client.get("/api/v1/metrics", headers=_METRICS_AUTH).text
    r1_help = sorted(line for line in r1.splitlines() if line.startswith("# HELP"))
    r2_help = sorted(line for line in r2.splitlines() if line.startswith("# HELP"))
    assert r1_help == r2_help, (
        f"HELP 注释行不一致, r1 独有: {set(r1_help) - set(r2_help)}, "
        f"r2 独有: {set(r2_help) - set(r1_help)}"
    )
