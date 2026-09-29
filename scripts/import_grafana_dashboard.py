"""阶段四: 导入 Grafana Dashboard JSON 到 Grafana (宿主机执行).

通过 Grafana HTTP API 导入 outputs/grafana_dashboard_v2.json, 验证看板可访问.

Usage:
    python scripts/import_grafana_dashboard.py
"""
import json
import sys
import urllib.request
import base64
from pathlib import Path

GRAFANA_URL = "http://localhost:3000"
ADMIN_USER = "admin"
ADMIN_PASSWORD = "CkF14AETkpmIHNq8"
DASHBOARD_JSON = Path(__file__).resolve().parent.parent / "outputs" / "grafana_dashboard_v2.json"


def make_auth_header() -> dict:
    credentials = f"{ADMIN_USER}:{ADMIN_PASSWORD}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {encoded}", "Content-Type": "application/json"}


def check_grafana_health() -> bool:
    """检查 Grafana 是否就绪."""
    try:
        req = urllib.request.Request(f"{GRAFANA_URL}/api/health")
        r = urllib.request.urlopen(req, timeout=10)
        data = json.loads(r.read().decode())
        print(f"Grafana 健康检查: {data}")
        return data.get("database") == "ok"
    except Exception as exc:
        print(f"ERROR: Grafana 不可访问: {exc}")
        return False


def import_dashboard() -> dict | None:
    """通过 API 导入 dashboard JSON."""
    if not DASHBOARD_JSON.exists():
        print(f"ERROR: Dashboard JSON 不存在: {DASHBOARD_JSON}")
        return None

    with open(DASHBOARD_JSON, encoding="utf-8") as f:
        dashboard = json.load(f)

    # Grafana API 要求 dashboard 包装在 {dashboard: ..., folderId: 0, overwrite: true} 中
    # 且 dashboard 内部的 id 应为 null (让 Grafana 分配)
    dashboard["id"] = None

    payload = {
        "dashboard": dashboard,
        "folderId": 0,
        "overwrite": True,
    }

    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{GRAFANA_URL}/api/dashboards/db",
        data=body,
        headers=make_auth_header(),
        method="POST",
    )
    try:
        r = urllib.request.urlopen(req, timeout=15)
        result = json.loads(r.read().decode())
        print(f"导入结果: {result}")
        return result
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode()[:300]}")
        return None
    except Exception as exc:
        print(f"ERROR: {exc}")
        return None


def verify_datasource() -> bool:
    """验证 Prometheus 数据源是否已配置且可查询."""
    req = urllib.request.Request(
        f"{GRAFANA_URL}/api/datasources",
        headers=make_auth_header(),
    )
    try:
        r = urllib.request.urlopen(req, timeout=10)
        datasources = json.loads(r.read().decode())
        print(f"\n数据源列表 ({len(datasources)} 个):")
        for ds in datasources:
            print(f"  - uid={ds.get('uid')} name={ds.get('name')} type={ds.get('type')} url={ds.get('url')}")
        # 检查 Prometheus 数据源
        prom = [ds for ds in datasources if ds.get("type") == "prometheus"]
        return len(prom) > 0
    except Exception as exc:
        print(f"ERROR: {exc}")
        return False


def verify_dashboard() -> bool:
    """验证 dashboard 已导入且可查询."""
    # 通过 UID 查找
    req = urllib.request.Request(
        f"{GRAFANA_URL}/api/dashboards/uid/dws-model-governance-v2",
        headers=make_auth_header(),
    )
    try:
        r = urllib.request.urlopen(req, timeout=10)
        data = json.loads(r.read().decode())
        dashboard = data.get("dashboard", {})
        title = dashboard.get("title", "?")
        panels = dashboard.get("panels", [])
        print(f"\n看板验证:")
        print(f"  标题: {title}")
        print(f"  面板数: {len(panels)}")
        for p in panels:
            print(f"    - {p.get('title', '?')}")
        return len(panels) > 0
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            print("ERROR: 看板未找到 (404)")
        else:
            print(f"HTTP {exc.code}: {exc.read().decode()[:200]}")
        return False
    except Exception as exc:
        print(f"ERROR: {exc}")
        return False


def main() -> int:
    print("=" * 60)
    print("阶段四: 导入 Grafana Dashboard")
    print("=" * 60)

    # 1. 健康检查
    print("\n1. Grafana 健康检查...")
    if not check_grafana_health():
        print("Grafana 不可用, 退出")
        return 1

    # 2. 验证数据源
    print("\n2. 验证数据源...")
    if not verify_datasource():
        print("WARN: 未找到 Prometheus 数据源")

    # 3. 导入 dashboard
    print("\n3. 导入 dashboard JSON...")
    result = import_dashboard()
    if not result or result.get("status") != "success":
        print("ERROR: 导入失败")
        return 1

    # 4. 验证 dashboard
    print("\n4. 验证已导入的 dashboard...")
    if not verify_dashboard():
        print("ERROR: 看板验证失败")
        return 1

    print("\n" + "=" * 60)
    print("Grafana Dashboard 导入成功!")
    print(f"访问地址: {GRAFANA_URL}/d/dws-model-governance-v2")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
