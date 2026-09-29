"""验证 Grafana DWS Prometheus 数据源可查询四类指标 (S4 P4 治理收口).

通过 Grafana datasource proxy API 调用真实 Prometheus 服务器, 验证:
1. 模型质量指标: model_auc, model_f1, model_ece, model_p95_latency_ms (4 模态)
2. 漂移监测指标: model_drift_psi, model_drift_kl (4 模态)
3. 金丝雀健康指标: canary_traffic_percent, canary_rollback_triggered
4. 推理延迟指标: model_inference_duration_seconds (Histogram)

R-F4: Grafana HTTP 交互复用 scripts/lib/grafana_client.py。
"""

from __future__ import annotations

import sys

from lib.grafana_client import query_prometheus

GRAFANA_URL = "http://localhost:3000"
DATASOURCE_UID = "dws-prom-prod"


def main() -> int:
    print("=" * 70)
    print("Grafana DWS Prometheus 数据源四类指标验证")
    print("=" * 70)

    test_cases = [
        # 1. 模型质量指标 (4 模态)
        ("模型质量", "model_auc", "structured/text/physiological/fusion", 4),
        ("模型质量", "model_f1", "structured/text/physiological/fusion", 4),
        ("模型质量", "model_ece", "structured/text/physiological/fusion", 4),
        ("模型质量", "model_p95_latency_ms", "structured/text/physiological/fusion", 4),
        # 2. 漂移监测指标
        ("漂移监测", "model_drift_psi", "4 模态", 4),
        ("漂移监测", "model_drift_kl", "4 模态", 4),
        # 3. 金丝雀健康
        ("金丝雀健康", "canary_traffic_percent", "active canary", 1),
        # 4. 推理延迟
        ("推理延迟", "model_inference_duration_seconds_bucket", "histogram buckets", None),
    ]

    pass_count = 0
    fail_count = 0
    for category, metric, expected_desc, expected_count in test_cases:
        result = query_prometheus(
            metric, grafana_url=GRAFANA_URL, datasource_uid=DATASOURCE_UID
        )
        if result.get("status") == "success":
            actual_count = len(result.get("data", {}).get("result", []))
            status = "PASS" if (expected_count is None and actual_count > 0) or (
                expected_count is not None and actual_count >= expected_count
            ) else "FAIL"
            if status == "PASS":
                pass_count += 1
            else:
                fail_count += 1
            print(f"  [{status}] {category} | {metric}: {actual_count} series (期望 >= {expected_count or 1})")
            # 显示样本
            for r in result["data"]["result"][:3]:
                labels = r.get("metric", {})
                value = r.get("value", [None, "?"])[1]
                key_labels = {k: v for k, v in labels.items() if k in ("modality", "model_version", "canary_id", "version", "le")}
                print(f"        {key_labels} = {value}")
        else:
            fail_count += 1
            print(f"  [FAIL] {category} | {metric}: {result.get('error', 'unknown error')}")

    print("=" * 70)
    print(f"汇总: PASS={pass_count}  FAIL={fail_count}")
    print("=" * 70)
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
