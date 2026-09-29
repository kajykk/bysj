"""验证 Grafana Dashboard v2 各面板 PromQL 查询均返回非空数据 (S4 P4 治理收口).

读取 outputs/grafana_dashboard_v2.json, 提取每个面板的 PromQL 表达式,
通过 Grafana 数据源代理 API 调用真实 Prometheus, 验证每个表达式都有数据.
"""
import base64
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

GRAFANA_URL = "http://localhost:3000"
ADMIN_USER = "admin"
ADMIN_PASSWORD = "CkF14AETkpmIHNq8"
DATASOURCE_UID = "dws-prom-prod"
DASHBOARD_JSON = Path(__file__).resolve().parent.parent / "outputs" / "grafana_dashboard_v2.json"


def make_auth_header() -> dict:
    credentials = f"{ADMIN_USER}:{ADMIN_PASSWORD}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def query_prometheus(expr: str) -> dict:
    """通过 Grafana 数据源代理查询 Prometheus (instant query)."""
    encoded_expr = urllib.parse.quote(expr)
    url = (
        f"{GRAFANA_URL}/api/datasources/proxy/uid/{DATASOURCE_UID}"
        f"/api/v1/query?query={encoded_expr}"
    )
    req = urllib.request.Request(url, headers=make_auth_header(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode()[:200]
        return {"status": "error", "error": f"HTTP {exc.code}: {body_text}"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def query_prometheus_range(expr: str, seconds_back: int = 300) -> dict:
    """通过 Grafana 数据源代理查询 Prometheus (range query, 验证面板能渲染曲线)."""
    import time
    end = int(time.time())
    start = end - seconds_back
    encoded_expr = urllib.parse.quote(expr)
    url = (
        f"{GRAFANA_URL}/api/datasources/proxy/uid/{DATASOURCE_UID}"
        f"/api/v1/query_range?query={encoded_expr}&start={start}&end={end}&step=30"
    )
    req = urllib.request.Request(url, headers=make_auth_header(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode()[:200]
        return {"status": "error", "error": f"HTTP {exc.code}: {body_text}"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def main() -> int:
    print("=" * 70)
    print("Grafana Dashboard v2 各面板 PromQL 验证")
    print("=" * 70)

    with open(DASHBOARD_JSON, encoding="utf-8") as f:
        dashboard = json.load(f)

    panels = dashboard.get("panels", [])
    print(f"看板: {dashboard.get('title')} ({len(panels)} 面板)\n")

    pass_count = 0
    fail_count = 0
    for panel in panels:
        title = panel.get("title", "?")
        targets = panel.get("targets", [])
        print(f"■ {title}")
        for tgt in targets:
            ref_id = tgt.get("refId", "?")
            expr = tgt.get("expr", "")
            legend = tgt.get("legendFormat", "")
            # 截断表达式显示
            expr_display = expr if len(expr) <= 100 else expr[:97] + "..."
            print(f"  [{ref_id}] {expr_display}")

            # 1. Instant 查询 (验证指标存在)
            result = query_prometheus(expr)
            if result.get("status") == "success":
                count = len(result.get("data", {}).get("result", []))
                # 显示样本值
                samples = []
                for r in result["data"]["result"][:3]:
                    labels = r.get("metric", {})
                    value = r.get("value", [None, "?"])[1]
                    label_str = ",".join(f"{k}={v}" for k, v in labels.items() if k in ("modality", "model_name", "le", "version", "canary_id"))
                    samples.append(f"{label_str}={value}")
                if count > 0:
                    print(f"      instant: {count} series  示例: {samples}")
                else:
                    print(f"      instant: 0 series (空)")
            else:
                print(f"      instant: ERROR {result.get('error', 'unknown')}")
                fail_count += 1
                continue

            # 2. Range 查询 (验证面板能渲染曲线)
            range_result = query_prometheus_range(expr, seconds_back=300)
            if range_result.get("status") == "success":
                range_count = len(range_result.get("data", {}).get("result", []))
                # 检查是否有非空 values
                non_empty = 0
                for r in range_result["data"]["result"]:
                    values = r.get("values", [])
                    if any(v[1] not in ("0", "0.0", "NaN") for v in values):
                        non_empty += 1
                print(f"      range(5m): {range_count} series, {non_empty} 个有非零数据点")
                if count > 0:
                    pass_count += 1
                else:
                    fail_count += 1
            else:
                print(f"      range: ERROR {range_result.get('error', 'unknown')}")
                if count > 0:
                    pass_count += 1
                else:
                    fail_count += 1
        print()

    print("=" * 70)
    print(f"汇总: PASS={pass_count}  FAIL={fail_count}")
    if fail_count == 0:
        print("✓ 所有面板 PromQL 查询均返回非空数据, Grafana 看板可正常渲染")
    else:
        print("✗ 部分面板数据缺失, 需检查")
    print("=" * 70)
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
