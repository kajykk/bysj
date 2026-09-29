"""S4 P3: ML 质量指标推送脚本.

从 models/experiments/*.json 读取已完成的实验结果,
将 AUC/F1/ECE/P95/Recall/Precision 指标推送到 Prometheus /metrics 端点
(通过修改后端进程内的 Gauge, 或直接 HTTP POST 到 /metrics 的 push gateway).

v2.0 计划 S4 要求: AUC/F1/ECE/P95 指标看板接入 Grafana.

工作方式:
    1. 扫描 models/experiments/ 目录, 识别各模态最新实验 JSON
    2. 提取 AUC/F1/ECE/P95/Recall/Precision 指标
    3. 调用 app.core.metrics 的 Gauge.set() 更新进程内指标
    4. 也可通过 HTTP GET /metrics 验证指标已暴露

Usage:
    python scripts/p3_push_ml_metrics.py
    python scripts/p3_push_ml_metrics.py --verify  # 推送后验证 /metrics 端点
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

# 添加 backend 到 path
BACKEND_ROOT = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS_DIR = PROJECT_ROOT / "models" / "experiments"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [P3] %(message)s")
logger = logging.getLogger("P3")


def find_latest_experiment(prefix: str) -> dict[str, Any] | None:
    """查找指定前缀的最新实验 JSON (跳过 detail 文件, 确保返回 dict)."""
    files = sorted(EXPERIMENTS_DIR.glob(f"{prefix}*.json"), reverse=True)
    for f in files:
        # 跳过 detail 文件 (通常为列表结构, 非汇总指标)
        if "detail" in f.name:
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                continue
            data["_source_file"] = f.name
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("读取 %s 失败: %s", f, e)
            continue
    return None


def extract_metrics() -> list[dict[str, Any]]:
    """从实验 JSON 提取各模态指标, 返回指标列表.

    每个元素: {modality, model_version, auc, f1, ece, p95_ms, recall, precision}
    """
    metrics: list[dict[str, Any]] = []

    # ── 结构化模态 (M1 LR+校准) ──
    m1 = find_latest_experiment("m1_lr_calibration_")
    if m1:
        calib = m1.get("calibration", {})
        # M1 JSON 结构: calibration.ece_post (校准后 ECE); threshold.best_recall/best_precision (成本敏感阈值)
        threshold = m1.get("threshold", {})
        test_metrics = m1.get("test_metrics", {})
        metrics.append({
            "modality": "structured",
            "model_version": "v1.23_lr_calibrated",
            "auc": test_metrics.get("roc_auc"),
            "f1": test_metrics.get("f1"),
            "ece": calib.get("ece_post"),  # 校准后 ECE
            "p95_ms": None,  # 结构化 LR 推理极快 (<1ms), 不单独测
            "recall": threshold.get("best_recall") or test_metrics.get("recall"),
            "precision": threshold.get("best_precision") or test_metrics.get("precision"),
            "source": m1["_source_file"],
        })
        logger.info("结构化 M1 LR: %s", m1["_source_file"])

    # ── 文本模态 (M2 BERT) ──
    m2_path = PROJECT_ROOT / "models" / "artifacts" / "text_m2_bert" / "metrics.json"
    if m2_path.exists():
        with open(m2_path, encoding="utf-8") as f:
            m2 = json.load(f)
        cv = m2.get("cv_results", {})
        metrics.append({
            "modality": "text",
            "model_version": "m2_bert_feature_extraction",
            "auc": cv.get("auc_mean"),
            "f1": cv.get("f1_mean"),
            "ece": None,  # M2 未单独做 ECE 校准
            "p95_ms": None,  # 由 P2 量化实验提供
            "recall": None,
            "precision": None,
            "source": "text_m2_bert/metrics.json",
        })
        logger.info("文本 M2 BERT: text_m2_bert/metrics.json")

    # ── 文本 P95 延迟 (P2 ONNX 量化) ──
    p2 = find_latest_experiment("p2_bert_onnx_")
    if p2:
        int8 = p2.get("int8", {})
        # 更新文本模态的 P95
        for m in metrics:
            if m["modality"] == "text":
                m["p95_ms"] = int8.get("latency_p95_ms")
                m["model_version"] = "m2_bert_int8_onnx"
                m["source"] = p2["_source_file"]
        logger.info("文本 P2 量化 P95: %s", p2["_source_file"])

    # ── 生理模态 (M3 MLP) ──
    m3 = find_latest_experiment("m3_physiological_")
    if m3:
        # M3 JSON 结构: best_metrics.{f1_mean, auc_mean}; best_config 仅为超参, 不含指标
        best_metrics = m3.get("best_metrics", {})
        auc = best_metrics.get("auc_mean")
        f1 = best_metrics.get("f1_mean")
        metrics.append({
            "modality": "physiological",
            "model_version": "v2_dl_mlp_regularized",
            "auc": auc,
            "f1": f1,
            "ece": None,  # 由 M5 校准实验提供
            "p95_ms": None,
            "recall": None,
            "precision": None,
            "source": m3["_source_file"],
        })
        logger.info("生理 M3 MLP: %s", m3["_source_file"])

    # ── 全模态 ECE (M5 校准) ──
    # M5 JSON 结构: modalities[] 数组, 每项含 {modality, calibration: {best_method, best_metrics: {ece, auc, ...}}}
    m5 = find_latest_experiment("m5_calibration_")
    if m5:
        modalities_list = m5.get("modalities", [])
        # 模态名映射: structured_gbdt→structured, physiological_mlp→physiological, text_bert→text
        modality_map = {
            "structured_gbdt": "structured",
            "structured_lr": "structured",
            "physiological_mlp": "physiological",
            "text_bert": "text",
            "text_tfidf": "text",
        }
        for entry in modalities_list:
            modality_key = entry.get("modality", "")
            calib_data = entry.get("calibration", {})
            best_metrics_m5 = calib_data.get("best_metrics", {})
            ece = best_metrics_m5.get("ece")
            auc_m5 = best_metrics_m5.get("auc")
            modality_name = modality_map.get(modality_key)
            if modality_name is None:
                # 兜底: 关键词匹配
                modality_name = (
                    "structured" if "structured" in modality_key else
                    "physiological" if "physio" in modality_key else
                    "text" if "text" in modality_key else None
                )
            if modality_name is None or ece is None:
                continue
            # 更新对应模态的 ECE (若已存在则不覆盖)
            for m in metrics:
                if m["modality"] == modality_name and m["ece"] is None:
                    m["ece"] = ece
                    # 若 AUC 缺失也补上 (M5 评估的 AUC)
                    if m.get("auc") is None and auc_m5 is not None:
                        m["auc"] = auc_m5
                    break
        logger.info("校准 M5: %s (%d 模态)", m5["_source_file"], len(modalities_list))

    # ── 融合模态 (M4 stacking_gbdt) ──
    m4 = find_latest_experiment("m4_fusion_")
    if m4:
        delong = m4.get("delong_tests", {})
        stacking_gbdt = delong.get("stacking_gbdt", {})
        cv_results = m4.get("cv_results", [])
        stacking_cv = next(
            (r for r in cv_results if r.get("strategy") == "stacking_gbdt"), {}
        )
        metrics.append({
            "modality": "fusion",
            "model_version": "stacking_gbdt",
            "auc": stacking_gbdt.get("auc_fusion") or stacking_cv.get("auc_mean"),
            "f1": stacking_cv.get("f1_mean"),
            "ece": None,
            "p95_ms": None,
            "recall": None,
            "precision": None,
            "source": m4["_source_file"],
        })
        logger.info("融合 M4 stacking: %s", m4["_source_file"])

    return metrics


def push_to_metrics_registry(metrics_list: list[dict[str, Any]]) -> int:
    """将指标推送到后端进程内 Prometheus Gauge."""
    from app.core.metrics import (
        model_auc,
        model_f1,
        model_ece,
        model_p95_latency_ms,
        model_recall,
        model_precision,
    )

    count = 0
    for m in metrics_list:
        modality = m["modality"]
        version = m["model_version"]

        if m.get("auc") is not None:
            model_auc.set(float(m["auc"]), modality=modality, model_version=version)
            count += 1
        if m.get("f1") is not None:
            model_f1.set(float(m["f1"]), modality=modality, model_version=version)
            count += 1
        if m.get("ece") is not None:
            model_ece.set(float(m["ece"]), modality=modality, model_version=version)
            count += 1
        if m.get("p95_ms") is not None:
            model_p95_latency_ms.set(float(m["p95_ms"]), modality=modality, model_version=version)
            count += 1
        if m.get("recall") is not None:
            model_recall.set(float(m["recall"]), modality=modality, model_version=version)
            count += 1
        if m.get("precision") is not None:
            model_precision.set(float(m["precision"]), modality=modality, model_version=version)
            count += 1

    return count


def verify_metrics_endpoint() -> bool:
    """验证 /metrics 端点是否暴露了 ML 质量指标."""
    import urllib.request

    try:
        with urllib.request.urlopen("http://localhost:8000/metrics", timeout=5) as resp:
            content = resp.read().decode("utf-8")
            ml_metrics_found = [
                "model_auc",
                "model_f1",
                "model_ece",
                "model_p95_latency_ms",
            ]
            found = {m: m in content for m in ml_metrics_found}
            logger.info("/metrics 端点验证: %s", found)
            return all(found.values())
    except Exception as e:
        logger.warning("/metrics 端点验证失败 (后端未启动?): %s", e)
        return False


def render_metrics_text(metrics_list: list[dict[str, Any]]) -> str:
    """渲染指标为 Prometheus exposition format (离线模式, 不依赖后端进程)."""
    lines: list[str] = []
    for metric_name, metric_type in [
        ("model_auc", "gauge"),
        ("model_f1", "gauge"),
        ("model_ece", "gauge"),
        ("model_p95_latency_ms", "gauge"),
        ("model_recall", "gauge"),
        ("model_precision", "gauge"),
    ]:
        lines.append(f"# HELP {metric_name} S4 P3 ML quality metric")
        lines.append(f"# TYPE {metric_name} {metric_type}")
        for m in metrics_list:
            field = metric_name.replace("model_", "").replace("_latency_ms", "_p95_ms")
            value = m.get(field)
            if value is not None:
                labels = f'modality="{m["modality"]}",model_version="{m["model_version"]}"'
                lines.append(f"{metric_name}{{{labels}}} {value}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="S4 P3 ML 质量指标推送")
    parser.add_argument("--verify", action="store_true", help="推送后验证 /metrics 端点")
    parser.add_argument("--offline", action="store_true", help="离线模式: 仅输出 exposition 文本")
    args = parser.parse_args()

    print("=" * 60)
    print("S4 P3: ML 质量指标推送 (AUC/F1/ECE/P95 → Grafana)")
    print("=" * 60)

    # 1. 提取指标
    metrics_list = extract_metrics()
    if not metrics_list:
        print("未找到任何实验结果, 请先运行 M1/M2/M3/M4/M5 实验")
        return 1

    print(f"\n提取到 {len(metrics_list)} 个模态的指标:")
    for m in metrics_list:
        print(f"  [{m['modality']}] {m['model_version']}: "
              f"AUC={m.get('auc')} F1={m.get('f1')} ECE={m.get('ece')} "
              f"P95={m.get('p95_ms')}ms (源: {m['source']})")

    # 2. 推送
    if args.offline:
        print("\n--- Prometheus Exposition (离线) ---")
        print(render_metrics_text(metrics_list))
    else:
        count = push_to_metrics_registry(metrics_list)
        print(f"\n已推送 {count} 个指标到 Prometheus Gauge")

    # 3. 验证
    if args.verify:
        print("\n--- /metrics 端点验证 ---")
        ok = verify_metrics_endpoint()
        if ok:
            print("✓ /metrics 端点已暴露所有 ML 质量指标")
        else:
            print("✗ /metrics 端点验证失败 (后端未启动或指标未注册)")
            print("  提示: 启动后端 (cd backend; uvicorn app.main:app) 后重试 --verify")

    # 4. 保存 exposition 快照 (供 Grafana 配置参考)
    snapshot_path = EXPERIMENTS_DIR / "p3_ml_metrics_snapshot.txt"
    with open(snapshot_path, "w", encoding="utf-8") as f:
        f.write(render_metrics_text(metrics_list))
    print(f"\n指标快照已保存: {snapshot_path}")

    print("\n" + "=" * 60)
    print("Grafana Dashboard 配置建议:")
    print("  1. 数据源: Prometheus (http://localhost:8000/metrics)")
    print("  2. 面板: model_auc / model_f1 / model_ece / model_p95_latency_ms")
    print("  3. 按 modality 分组: structured / text / physiological / fusion")
    print("  4. 告警规则: model_ece > 0.05 / model_p95_latency_ms > 300")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
