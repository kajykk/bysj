"""B2 推理基准报告: 从 Prometheus 拉取推理延迟数据, 生成 G5 基线.

目标:
    1. 从 Prometheus 查询 model_inference_duration_seconds 指标
    2. 计算 P50/P95/P99 延迟 (按模态分解)
    3. 验证 G5 目标: 融合单次预测 P95 ≤500ms
    4. 生成基准报告

Usage:
    python scripts/b2_inference_benchmark.py
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [B2] %(message)s")
logger = logging.getLogger("B2")

PROMETHEUS_URL = "http://localhost:9090"
OUTPUT_DIR = PROJECT_ROOT / "models" / "artifacts" / "b2_inference_benchmark"


def query_prometheus(query: str, range_query: bool = False, **kwargs) -> dict:
    """查询 Prometheus.

    Args:
        query: PromQL 查询.
        range_query: 是否范围查询.

    Returns:
        Prometheus 响应 dict.
    """
    endpoint = "/api/v1/query_range" if range_query else "/api/v1/query"
    params = {"query": query}
    params.update(kwargs)
    url = f"{PROMETHEUS_URL}{endpoint}?{urlencode(params)}"

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        logger.error("无法连接 Prometheus: %s", PROMETHEUS_URL)
        return {"status": "error", "error": "connection_failed"}
    except requests.exceptions.Timeout:
        logger.error("Prometheus 查询超时")
        return {"status": "error", "error": "timeout"}
    except Exception as e:
        logger.error("Prometheus 查询失败: %s", e)
        return {"status": "error", "error": str(e)}


def extract_inference_metrics() -> dict:
    """从 Prometheus 提取推理指标."""
    metrics = {
        "total_requests": {},
        "duration_stats": {},
        "by_modality": {},
    }

    # 1. 总请求数 (by model_name, status)
    logger.info("查询 model_inference_total...")
    resp = query_prometheus("model_inference_total")
    if resp.get("status") == "success":
        for result in resp["data"]["result"]:
            labels = result["metric"]
            model = labels.get("model_name", "unknown")
            status = labels.get("status", "unknown")
            value = float(result["value"][1])
            key = f"{model}/{status}"
            metrics["total_requests"][key] = value
            logger.info("  %s: %d", key, int(value))

    # 2. 延迟统计 (count, sum)
    logger.info("查询 model_inference_duration_seconds_count/sum...")
    for metric_type in ["count", "sum"]:
        resp = query_prometheus(f"model_inference_duration_seconds_{metric_type}")
        if resp.get("status") == "success":
            for result in resp["data"]["result"]:
                labels = result["metric"]
                model = labels.get("model_name", "unknown")
                value = float(result["value"][1])
                if model not in metrics["duration_stats"]:
                    metrics["duration_stats"][model] = {}
                metrics["duration_stats"][model][metric_type] = value

    # 3. 直方图分位数 (P50/P95/P99)
    logger.info("查询延迟分位数 (P50/P95/P99)...")
    for model_name in ["structured", "text", "fusion", "fusion_canary", "physiological"]:
        for quantile, label in [(0.5, "p50"), (0.95, "p95"), (0.99, "p99")]:
            query = f'histogram_quantile({quantile}, sum(rate(model_inference_duration_seconds_bucket{{model_name="{model_name}"}}[5m])) by (le))'
            resp = query_prometheus(query)
            if resp.get("status") == "success" and resp["data"]["result"]:
                value = float(resp["data"]["result"][0]["value"][1])
                if model_name not in metrics["by_modality"]:
                    metrics["by_modality"][model_name] = {}
                metrics["by_modality"][model_name][label] = value
                logger.info("  %s %s: %.3fs (%.1fms)", model_name, label, value, value * 1000)

    return metrics


def check_g5_target(metrics: dict) -> dict:
    """检查 G5 目标: 融合 P95 ≤500ms."""
    fusion_metrics = metrics["by_modality"].get("fusion", {})
    p95 = fusion_metrics.get("p95")

    return {
        "target": "融合单次预测 P95 ≤500ms",
        "fusion_p95_ms": round(p95 * 1000, 1) if p95 else None,
        "meets_target": bool(p95 is not None and p95 <= 0.5),
        "margin_ms": round((0.5 - p95) * 1000, 1) if p95 else None,
    }


def generate_report(metrics: dict, g5_check: dict) -> dict:
    """生成基准报告."""
    return {
        "experiment_id": f"b2_inference_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Prometheus (dws-prometheus:9090)",
        "metrics": metrics,
        "g5_target_check": g5_check,
        "analysis": {
            "total_models_tracked": len(metrics["total_requests"]),
            "modalities_with_latency_data": list(metrics["by_modality"].keys()),
            "slowest_modality": max(
                metrics["by_modality"].items(),
                key=lambda x: x[1].get("p95", 0),
            )[0] if metrics["by_modality"] else None,
        },
        "conclusion": {
            "g5_meets_target": g5_check["meets_target"],
            "note": (
                "G5 达标: 融合 P95 ≤500ms" if g5_check["meets_target"]
                else f"G5 未达标: 融合 P95 = {g5_check.get('fusion_p95_ms')}ms > 500ms"
                if g5_check.get("fusion_p95_ms")
                else "G5 无法判定: 无融合延迟数据 (需触发融合推理)"
            ),
        },
    }


def main() -> None:
    logger.info("=" * 60)
    logger.info("B2 推理基准报告")
    logger.info("=" * 60)

    # 检查 Prometheus 可用性
    logger.info("检查 Prometheus 可用性: %s", PROMETHEUS_URL)
    health = query_prometheus("up")
    if health.get("status") != "success":
        logger.error("Prometheus 不可用, 退出")
        logger.info("提示: 启动 Prometheus 容器 (docker compose up -d prometheus)")
        # 生成空报告
        report = {
            "experiment_id": f"b2_inference_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "Prometheus (dws-prometheus:9090)",
            "status": "prometheus_unavailable",
            "error": "无法连接 Prometheus, 请确保容器运行",
            "g5_target_check": {"meets_target": False, "note": "Prometheus 不可用"},
        }
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_DIR / "b2_benchmark_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return

    # 提取指标
    metrics = extract_inference_metrics()

    # 检查 G5 目标
    g5_check = check_g5_target(metrics)

    # 生成报告
    report = generate_report(metrics, g5_check)

    # 保存
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_DIR / "b2_benchmark_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info("报告已保存: %s", report_path)

    # 结论
    logger.info("\n" + "=" * 60)
    logger.info("B2 推理基准结论:")
    logger.info("=" * 60)
    logger.info("模态延迟 (P95):")
    for model, stats in metrics["by_modality"].items():
        p50 = stats.get("p50", 0)
        p95 = stats.get("p95", 0)
        p99 = stats.get("p99", 0)
        logger.info("  %s: P50=%.1fms, P95=%.1fms, P99=%.1fms",
                    model, p50 * 1000, p95 * 1000, p99 * 1000)
    logger.info("\nG5 目标 (融合 P95 ≤500ms): %s",
                "✓ 达标" if g5_check["meets_target"] else "✗ 未达标")
    if g5_check.get("fusion_p95_ms"):
        logger.info("  融合 P95: %.1fms (余量: %.1fms)",
                    g5_check["fusion_p95_ms"], g5_check.get("margin_ms", 0))
    logger.info("\n请求总数:")
    for key, count in metrics["total_requests"].items():
        logger.info("  %s: %d", key, int(count))


if __name__ == "__main__":
    main()
