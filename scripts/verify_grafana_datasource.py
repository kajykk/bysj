"""验证 Grafana Prometheus 数据源可查询指标 (宿主机执行).

R-F4: Grafana HTTP 交互复用 scripts/lib/grafana_client.py。
"""
import sys

from lib.grafana_client import query_prometheus

GRAFANA_URL = "http://localhost:3000"
DATASOURCE_UID = "PB0F7F7A2A1B0E0FA"


def query_prometheus_post(expr: str) -> dict:
    """通过 Grafana API 查询 Prometheus 数据源 (POST)."""
    return query_prometheus(
        expr,
        grafana_url=GRAFANA_URL,
        datasource_uid=DATASOURCE_UID,
        method="POST",
    )


def main() -> int:
    print("=" * 60)
    print("验证 Grafana Prometheus 数据源查询")
    print("=" * 60)

    queries = [
        ("model_auc", 'model_auc{modality=~"structured|text|physiological|fusion"}'),
        ("model_f1", 'model_f1{modality=~"structured|text|physiological|fusion"}'),
        ("model_ece", 'model_ece{modality=~"structured|text|physiological|fusion"}'),
        ("model_drift_psi", 'model_drift_psi{modality=~"structured|text|physiological|fusion"}'),
        ("canary_traffic_percent", "canary_traffic_percent"),
        ("model_inference_total", "model_inference_total"),
    ]

    all_ok = True
    for name, expr in queries:
        result = query_prometheus_post(expr)
        if "error" in result:
            print(f"  [FAIL] {name}: {result['error']}")
            if "body" in result:
                print(f"         {result['body']}")
            all_ok = False
        else:
            data = result.get("data", {})
            results = data.get("result", [])
            count = len(results)
            if count > 0:
                sample = results[0]
                value = sample.get("value", [None, "?"])[1]
                print(f"  [OK]   {name}: {count} 条结果, 样本值={value}")
            else:
                print(f"  [WARN] {name}: 0 条结果 (可能鉴权失败或无数据)")
                all_ok = False

    print("\n" + "=" * 60)
    if all_ok:
        print("✅ Grafana Prometheus 数据源查询成功!")
    else:
        print("⚠️  部分查询失败, 可能需要检查数据源鉴权配置")
    print("=" * 60)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
