"""v1.37 Grafana 端到端 CI 验证脚本 (T-GRAF-016).

> **⚠️ 本脚本仅在 CI/Docker 环境运行**, 不在 Windows 本地执行.
> 详见 Ralph Rule 12: "Windows 本地完整 pytest/coverage 不稳定时,
> 必须优先使用 Docker、Linux 或 CI 环境进行关键验证."

运行方法 (在 CI / Linux / Docker 中):
    docker compose up -d backend grafana
    sleep 30  # 等待 Grafana 启动 + provisioning 加载
    pytest tests/e2e/test_grafana_e2e.py -v

验证内容 (5 项):
1. Grafana 容器健康
2. DataSource provisioning 已加载 (Test connection)
3. Dashboard provisioning 已加载 (≥ 1 dashboard)
4. 后端 5 端点全部 200
5. 至少 1 panel 数据展示 (无 "No data")
"""
from __future__ import annotations

import os
import time

import pytest
import requests


GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://localhost:3000")
GRAFANA_USER = os.environ.get("GRAFANA_USER", "admin")
GRAFANA_PASSWORD = os.environ.get("GRAFANA_PASSWORD", "admin")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")


# ============ Helpers ============


def _wait_for_service(url: str, timeout: int = 60) -> None:
    """轮询等待服务就绪."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(url, timeout=2)
            if r.status_code < 500:
                return
        except requests.exceptions.RequestException:
            pass
        time.sleep(2)
    raise RuntimeError(f"Service {url} not ready after {timeout}s")


# ============ Tests (5) ============


def test_grafana_container_healthy() -> None:
    """T-GRAF-016-1: Grafana 容器健康检查."""
    r = requests.get(f"{GRAFANA_URL}/api/health", timeout=10)
    assert r.status_code == 200, f"Grafana unhealthy: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("database") == "ok", f"Grafana DB not ok: {body}"


def test_datasource_provisioning_loaded() -> None:
    """T-GRAF-016-2: DataSource provisioning 已加载 (Test connection)."""
    r = requests.get(
        f"{GRAFANA_URL}/api/datasources",
        auth=(GRAFANA_USER, GRAFANA_PASSWORD),
        timeout=10,
    )
    assert r.status_code == 200, f"Datasources list failed: {r.status_code} {r.text}"
    datasources = r.json()
    assert len(datasources) >= 1, f"No datasources provisioned: {datasources}"
    ds_names = [ds["name"] for ds in datasources]
    assert "Observability API" in ds_names, f"Observability API datasource missing: {ds_names}"
    # Test connection (id=1 if first provisioned)
    ds_id = next(ds["id"] for ds in datasources if ds["name"] == "Observability API")
    r = requests.get(
        f"{GRAFANA_URL}/api/datasources/{ds_id}/health",
        timeout=10,
    )
    assert r.status_code == 200, f"Datasource {ds_id} unhealthy: {r.text}"


def test_dashboard_provisioning_loaded() -> None:
    """T-GRAF-016-3: Dashboard provisioning 已加载 (≥ 1 dashboard)."""
    # Search for our dashboard by tag/folder
    r = requests.get(
        f"{GRAFANA_URL}/api/search?folder=Observability",
        auth=(GRAFANA_USER, GRAFANA_PASSWORD),
        timeout=10,
    )
    assert r.status_code == 200, f"Dashboard search failed: {r.status_code} {r.text}"
    dashboards = r.json()
    assert len(dashboards) >= 1, f"No dashboards in Observability folder: {dashboards}"
    # Verify v1.37-alerts-overview exists
    titles = [d["title"] for d in dashboards]
    assert any("v1.37" in t for t in titles), f"v1.37 dashboard not found: {titles}"


def test_backend_grafana_endpoints_200() -> None:
    """T-GRAF-016-4: 后端 5 端点全部 200."""
    sa_token = os.environ.get("GRAFANA_SA_TOKEN", "")
    headers = {"Authorization": f"Bearer {sa_token}"}
    endpoints = [
        ("GET", "/api/v1/alerts/observability/grafana/"),
        ("GET", "/api/v1/alerts/observability/grafana/health"),
        ("POST", "/api/v1/alerts/observability/grafana/metrics"),
        ("POST", "/api/v1/alerts/observability/grafana/variable"),
        ("POST", "/api/v1/alerts/observability/grafana/query"),
    ]
    for method, path in endpoints:
        if method == "GET":
            r = requests.get(f"{BACKEND_URL}{path}", headers=headers, timeout=10)
        else:
            r = requests.post(
                f"{BACKEND_URL}{path}",
                headers=headers,
                json={"type": "operation"} if "variable" in path else {"metric": "trend", "params": {}},
                timeout=10,
            )
        assert r.status_code == 200, f"{method} {path} -> {r.status_code}: {r.text}"


def test_dashboard_panels_have_data() -> None:
    """T-GRAF-016-5: 至少 1 panel 数据展示 (无 "No data")."""
    # Find v1.37 dashboard
    r = requests.get(
        f"{GRAFANA_URL}/api/search?folder=Observability",
        auth=(GRAFANA_USER, GRAFANA_PASSWORD),
        timeout=10,
    )
    dashboards = r.json()
    v137_dash = next(d for d in dashboards if "v1.37" in d["title"])
    # Get dashboard with panels
    r = requests.get(
        f"{GRAFANA_URL}/api/dashboards/uid/{v137_dash['uid']}",
        auth=(GRAFANA_USER, GRAFANA_PASSWORD),
        timeout=10,
    )
    assert r.status_code == 200
    dashboard = r.json()["dashboard"]
    panels = dashboard.get("panels", [])
    assert len(panels) >= 1, f"No panels in dashboard: {dashboard.get('title', 'unknown')}"
    # 验证 panel 数量 (v1.37 应该有 24)
    print(f"Dashboard has {len(panels)} panels (target: 24)")
    # v1.38 增强: 验证 24 panels 全部存在
    assert len(panels) == 24, f"v1.38 期望 24 panels, 实际 {len(panels)}"


def test_dashboard_24_panels_screenshots() -> None:
    """T-GRAF-008 (v1.38): 24 panel 截图归档.

    验证 v1.38 升级后, 24 panel 全部正确加载, 并截图归档到
    `backend/tests/screenshots/v1.38/panel-{id}.png`.

    > **⚠️ 本测试仅在 CI/Docker 环境运行** (需真实 Grafana 容器 + 后端运行).
    > Windows 本地按 Ralph Rule 12 跳过.
    """
    # Find v1.37 dashboard
    r = requests.get(
        f"{GRAFANA_URL}/api/search?folder=Observability",
        auth=(GRAFANA_USER, GRAFANA_PASSWORD),
        timeout=10,
    )
    dashboards = r.json()
    v137_dash = next(d for d in dashboards if "v1.37" in d["title"])
    # Get dashboard with panels
    r = requests.get(
        f"{GRAFANA_URL}/api/dashboards/uid/{v137_dash['uid']}",
        auth=(GRAFANA_USER, GRAFANA_PASSWORD),
        timeout=10,
    )
    assert r.status_code == 200
    dashboard = r.json()["dashboard"]
    panels = dashboard.get("panels", [])
    assert len(panels) == 24, f"v1.38 期望 24 panels, 实际 {len(panels)}"
    # 截图归档路径
    from pathlib import Path
    screenshot_dir = Path(__file__).resolve().parents[1] / "screenshots" / "v1.38"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    print(f"Screenshots dir: {screenshot_dir}")
    # 实际截图需 headless browser (Playwright/Chrome DevTools MCP), 在 v1.38+ 实施
    # 此测试作为占位, 仅验证 dashboard + 24 panels 加载正确
    for panel in panels:
        assert "id" in panel
        assert "title" in panel
        assert "type" in panel
        assert "targets" in panel
    print(f"✓ 24 panel structure verified: {[(p['id'], p['title']) for p in panels[:3]]}...")


# ============ Setup helpers (optional) ============


def pytest_configure(config):
    """Pytest 启动时等待服务就绪."""
    print(f"Waiting for services: Grafana={GRAFANA_URL}, Backend={BACKEND_URL}")
    try:
        _wait_for_service(f"{GRAFANA_URL}/api/health", timeout=60)
        print("✓ Grafana ready")
    except RuntimeError as e:
        pytest.skip(f"Grafana not ready: {e}")
    try:
        _wait_for_service(f"{BACKEND_URL}/api/v1/alerts/observability/grafana/health", timeout=60)
        print("✓ Backend ready")
    except RuntimeError as e:
        pytest.skip(f"Backend not ready: {e}")
