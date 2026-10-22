"""阶段四: 精确检查 /metrics 端点四类指标数据行 (容器内执行)."""
import os
import urllib.request
import sys

URL = "http://localhost:8000/api/v1/metrics"

# L13 修复（ROUND_23）：优先级 环境变量 > 应用配置 > dev-only 占位符。
# 占位符 "dev-only-metrics-token" 不是真实凭据（本地 /metrics 未配置访问令牌
# 时的默认形态），已在结构扫描闸门的白名单中逐条登记：
# backend/tests/test_p2_49_round23b_secret_scan.py
TOKEN = os.environ.get("BYSJ_METRICS_TOKEN") or "dev-only-metrics-token"

try:
    from app.core.config import settings
    TOKEN = os.environ.get("BYSJ_METRICS_TOKEN") or settings.metrics_access_token or "dev-only-metrics-token"
except Exception:
    pass

req = urllib.request.Request(URL, headers={"Authorization": f"Bearer {TOKEN}"})
try:
    data = urllib.request.urlopen(req, timeout=10).read().decode()
except Exception as exc:
    print(f"ERROR: {exc}")
    sys.exit(1)

# 只看数据行 (非 # 开头, 非空)
data_lines = [l for l in data.split("\n") if l and not l.startswith("#")]

KEYWORDS = [
    "model_auc",
    "model_f1",
    "model_ece",
    "model_p95_latency_ms",
    "model_recall",
    "model_precision",
    "model_drift_psi",
    "model_drift_kl",
    "canary_traffic_percent",
    "canary_rollback_triggered_total",
    "model_inference_total",
    "model_inference_duration_seconds",
]

print("=" * 60)
print("阶段四: /metrics 端点四类指标数据行检查")
print("=" * 60)
for k in KEYWORDS:
    # 只查找数据行 (以指标名开头, 后面跟 {、空格、_bucket、_sum、_count)
    matches = [
        l for l in data_lines
        if l.startswith(k + "{") or l.startswith(k + " ") or l.startswith(k + "_bucket") or l.startswith(k + "_sum") or l.startswith(k + "_count")
    ]
    status = f"FOUND ({len(matches)} 行)" if matches else "MISSING (无数据行)"
    print(f"  [{status}] {k}")
    for m in matches[:2]:
        print(f"    {m[:120]}")

print(f"\n总计数据行数: {len(data_lines)}")
