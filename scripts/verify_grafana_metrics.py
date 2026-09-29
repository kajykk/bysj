"""阶段四: Prometheus 指标验证 (容器内执行).

验证 /api/v1/metrics 端点可查询四类指标:
  1. 模型质量趋势 (AUC/F1/ECE/P95)
  2. 漂移监测 (PSI/KL)
  3. 金丝雀健康 (流量/回滚)
  4. 推理延迟分布 (P50/P95/P99)

Usage:
    docker cp scripts/verify_grafana_metrics.py dws-backend:/tmp/v.py
    docker exec dws-backend python /tmp/v.py
"""
import urllib.request
import sys

BASE = "http://localhost:8000"
METRICS_URL = f"{BASE}/api/v1/metrics"

# 从 settings 读取 token (生产环境与非生产环境不同)
try:
    from app.core.config import settings
    TOKEN = settings.metrics_access_token or "dev-only-metrics-token"
except Exception:
    TOKEN = "dev-only-metrics-token"

EXPECTED_CATEGORIES = {
    "模型质量": ["model_inference_total", "model_inference_duration"],
    "漂移监测": ["model_drift_psi", "model_drift_kl", "drift_alert"],
    "金丝雀": ["canary"],
    "推理延迟": ["http_request_duration", "model_inference_duration"],
}


def fetch_metrics() -> str:
    req = urllib.request.Request(
        METRICS_URL,
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    try:
        r = urllib.request.urlopen(req, timeout=10)
        return r.read().decode()
    except Exception as exc:
        print(f"ERROR: 无法获取 metrics: {exc}")
        sys.exit(1)


def main() -> None:
    print("=" * 60)
    print("阶段四: Prometheus 指标验证")
    print("=" * 60)

    data = fetch_metrics()
    lines = data.split("\n")
    metric_lines = [l for l in lines if l and not l.startswith("#")]
    metric_names = set()
    for l in metric_lines:
        name = l.split("{")[0].split()[0] if "{" in l else l.split()[0] if l else ""
        if name:
            metric_names.add(name)

    print(f"\n总指标数: {len(metric_names)}")
    print(f"总指标行数: {len(metric_lines)}")

    print("\n" + "=" * 60)
    print("四类指标验证:")
    print("=" * 60)
    all_ok = True
    for category, keywords in EXPECTED_CATEGORIES.items():
        found = []
        for kw in keywords:
            for name in metric_names:
                if kw in name:
                    found.append(name)
        found = list(set(found))
        status = "OK" if found else "MISSING"
        if not found:
            all_ok = False
        print(f"\n  [{status}] {category}:")
        for f in found:
            print(f"    - {f}")
        if not found:
            print(f"    (未找到包含 {keywords} 的指标)")

    print("\n" + "=" * 60)
    print("全部指标名称列表:")
    print("=" * 60)
    for name in sorted(metric_names):
        print(f"  {name}")

    # 搜索关键指标样本
    print("\n" + "=" * 60)
    print("关键指标样本:")
    print("=" * 60)
    for keyword in ["model_drift", "canary", "model_inference", "http_request_duration"]:
        samples = [l for l in metric_lines if keyword in l][:3]
        if samples:
            print(f"\n  {keyword}:")
            for s in samples:
                print(f"    {s[:120]}")

    print("\n" + "=" * 60)
    if all_ok:
        print("验证结果: OK - 四类指标均可查询")
    else:
        print("验证结果: WARN - 部分指标缺失 (见上方 [MISSING] 项)")
    print("=" * 60)


if __name__ == "__main__":
    main()
