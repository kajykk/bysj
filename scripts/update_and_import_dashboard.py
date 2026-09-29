"""阶段四: 更新 dashboard JSON 数据源引用并导入到 Grafana.

将 outputs/grafana_dashboard_v2.json 中所有 "Prometheus" 数据源引用
替换为新数据源 "DWS Prometheus" (uid=dws-prom-prod), 然后通过 HTTP API 导入.

这解决了旧 Prometheus 数据源 (指向 backend:8000, 只读) 无法支持 range query 的问题,
切换到真实 Prometheus 服务器 (dws-prometheus:9090) 后看板可正常显示.
"""
import base64
import json
import sys
import urllib.request
from pathlib import Path

GRAFANA_URL = "http://localhost:3000"
ADMIN_USER = "admin"
ADMIN_PASSWORD = "CkF14AETkpmIHNq8"
DASHBOARD_JSON = Path(__file__).resolve().parent.parent / "outputs" / "grafana_dashboard_v2.json"
NEW_DATASOURCE_UID = "dws-prom-prod"
NEW_DATASOURCE_TYPE = "prometheus"


def make_auth_header() -> dict:
    credentials = f"{ADMIN_USER}:{ADMIN_PASSWORD}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {encoded}", "Content-Type": "application/json"}


def update_datasource_refs(obj):
    """递归遍历 JSON, 将 datasource: "Prometheus" 替换为 UID 对象格式."""
    if isinstance(obj, dict):
        # 修复面板级 datasource
        if "datasource" in obj and obj["datasource"] == "Prometheus":
            obj["datasource"] = {"type": NEW_DATASOURCE_TYPE, "uid": NEW_DATASOURCE_UID}
        # 修复 target 级 datasource
        for k, v in obj.items():
            if k == "datasource" and isinstance(v, str) and v == "Prometheus":
                obj[k] = {"type": NEW_DATASOURCE_TYPE, "uid": NEW_DATASOURCE_UID}
            else:
                update_datasource_refs(v)
    elif isinstance(obj, list):
        for item in obj:
            update_datasource_refs(item)
    return obj


def main() -> int:
    print("=" * 60)
    print("更新 dashboard 数据源引用并导入 Grafana")
    print("=" * 60)

    if not DASHBOARD_JSON.exists():
        print(f"ERROR: {DASHBOARD_JSON} 不存在")
        return 1

    # 1. 读取并更新 JSON
    with open(DASHBOARD_JSON, encoding="utf-8") as f:
        dashboard = json.load(f)
    print(f"原始 dashboard: {dashboard.get('title')} ({len(dashboard.get('panels', []))} 面板)")

    update_datasource_refs(dashboard)

    # 验证替换
    panel_ds = [p.get("datasource") for p in dashboard.get("panels", [])]
    print(f"面板数据源引用: {panel_ds}")

    # 2. 包装为 Grafana API payload
    dashboard["id"] = None
    payload = {
        "dashboard": dashboard,
        "folderId": 0,
        "overwrite": True,
    }

    # 3. POST 到 Grafana
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{GRAFANA_URL}/api/dashboards/db",
        data=body,
        headers=make_auth_header(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            result = json.loads(r.read().decode())
            print(f"导入结果: status={result.get('status')} url={result.get('url')}")
            if result.get("status") != "success":
                print(f"ERROR: {result}")
                return 1
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    # 4. 验证导入
    req = urllib.request.Request(
        f"{GRAFANA_URL}/api/dashboards/uid/dws-model-governance-v2",
        headers=make_auth_header(),
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode())
        d = data.get("dashboard", {})
        print(f"\n验证: title={d.get('title')} panels={len(d.get('panels', []))}")
        for p in d.get("panels", []):
            ds = p.get("datasource")
            if isinstance(ds, dict):
                ds_str = f"uid={ds.get('uid')}"
            else:
                ds_str = f"name={ds}"
            print(f"  - {p.get('title')} [{ds_str}]")

    # 5. 保存更新后的 JSON
    with open(DASHBOARD_JSON, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, ensure_ascii=False, indent=2)
    print(f"\n已更新本地文件: {DASHBOARD_JSON}")

    print("\n" + "=" * 60)
    print(f"看板访问地址: {GRAFANA_URL}/d/dws-model-governance-v2")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
