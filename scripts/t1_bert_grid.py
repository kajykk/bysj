"""T1 BERT 训练配方网格搜索.

目标: 在现有 1275 条中文数据上,通过 lr × epochs 网格搜索提升域外 F1 从 0.59 到 ≥ 0.65.

网格:
    - lr ∈ {1e-5, 2e-5, 3e-5}
    - epochs ∈ {5, 8, 10}
    - freeze_layers = 6 (固定, 之前实验确认最优)
    - warmup = 10% (固定)

策略:
    1. Phase 1 快速筛选: quick 模式 (1 seed × 5 folds = 5 折, ~10 分钟/组)
       跑 6 组关键配置 (跳过已知的 lr=2e-5/epochs=5)
    2. Phase 2 完整验证: 对 Phase 1 最优的 2 组, 用 3 seeds × 5 folds = 15 折验证

Usage:
    python scripts/t1_bert_grid.py --phase 1    # 快速筛选
    python scripts/t1_bert_grid.py --phase 2    # 完整验证 (需指定 --best-configs)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# 添加项目根目录到 path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.m2_text_bert import (
    BERT_MODEL_NAME,
    D3_BASELINE,
    SEEDS,
    TARGET_F1,
    load_mmpsy_data,
    get_device,
    evaluate_cv_finetune,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [T1] %(message)s")
logger = logging.getLogger("T1")

EXPERIMENTS_DIR = PROJECT_ROOT / "models" / "experiments"
TRAINING_JOBS_PATH = PROJECT_ROOT / "models" / "training_jobs.json"
T1_RESULTS_PATH = PROJECT_ROOT / "models" / "experiments" / "t1_grid_results.json"

# 网格配置
FREEZE_LAYERS = 6  # 固定(之前实验确认最优)

# Phase 1: 快速筛选配置(跳过已知的 lr=2e-5/epochs=5, 因 F1=0.59 已有记录)
PHASE1_CONFIGS = [
    {"lr": 3e-5, "epochs": 5,  "label": "lr3e5_ep5"},
    {"lr": 3e-5, "epochs": 8,  "label": "lr3e5_ep8"},
    {"lr": 3e-5, "epochs": 10, "label": "lr3e5_ep10"},
    {"lr": 1e-5, "epochs": 8,  "label": "lr1e5_ep8"},
    {"lr": 1e-5, "epochs": 10, "label": "lr1e5_ep10"},
    {"lr": 2e-5, "epochs": 8,  "label": "lr2e5_ep8"},
]


def run_grid_phase1() -> dict:
    """Phase 1: quick 模式快速筛选 6 组配置."""
    logger.info("=" * 60)
    logger.info("T1 Phase 1: 快速筛选 (quick=1 seed × 5 folds)")
    logger.info("网格: %d 组配置", len(PHASE1_CONFIGS))
    logger.info("=" * 60)

    df = load_mmpsy_data()
    texts = df["text"].tolist()
    y = df["phq9_binary"].astype(int).values

    device = get_device()
    if device != "cuda":
        logger.error("Phase 1 需要 GPU (fine_tune 模式), 当前 device=%s", device)
        return {"error": f"需要 GPU, 当前 {device}"}

    results = []
    best_f1 = 0.0
    best_config = None
    baseline_f1 = 0.59  # 已知 lr=2e-5/epochs=5/freeze=6 的 F1

    for i, cfg in enumerate(PHASE1_CONFIGS):
        logger.info("-" * 50)
        logger.info("[%d/%d] %s (lr=%s, epochs=%d, freeze=%d)",
                    i + 1, len(PHASE1_CONFIGS), cfg["label"],
                    cfg["lr"], cfg["epochs"], FREEZE_LAYERS)
        logger.info("-" * 50)

        t0 = time.time()
        cv_result = evaluate_cv_finetune(
            texts, y, device,
            seeds=[42],  # quick: 1 seed × 5 folds = 5 折
            epochs=cfg["epochs"],
            freeze_layers=FREEZE_LAYERS,
            lr=cfg["lr"],
        )
        elapsed = time.time() - t0

        result = {
            "label": cfg["label"],
            "lr": cfg["lr"],
            "epochs": cfg["epochs"],
            "freeze_layers": FREEZE_LAYERS,
            "f1_mean": cv_result["f1_mean"],
            "f1_std": cv_result["f1_std"],
            "auc_mean": cv_result["auc_mean"],
            "auc_std": cv_result["auc_std"],
            "acc_mean": cv_result["acc_mean"],
            "mean_threshold": cv_result["mean_threshold"],
            "elapsed_s": round(elapsed, 1),
            "n_evaluations": cv_result["n_evaluations"],
            "beats_baseline": cv_result["f1_mean"] > baseline_f1,
            "meets_target": cv_result["f1_mean"] >= 0.65,
        }
        results.append(result)

        logger.info("[%s] F1=%.4f±%.4f, AUC=%.4f, time=%.0fs %s",
                    cfg["label"], result["f1_mean"], result["f1_std"],
                    result["auc_mean"], elapsed,
                    "✓ BEATS BASELINE" if result["beats_baseline"] else "")

        if result["f1_mean"] > best_f1:
            best_f1 = result["f1_mean"]
            best_config = cfg

    # 汇总
    summary = {
        "phase": 1,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "baseline_f1": baseline_f1,
        "target_f1": 0.65,
        "n_configs": len(PHASE1_CONFIGS),
        "best_config": best_config,
        "best_f1": best_f1,
        "all_results": results,
        "beats_baseline_configs": [r for r in results if r["beats_baseline"]],
        "meets_target_configs": [r for r in results if r["meets_target"]],
    }

    # 保存结果
    T1_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(T1_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    logger.info("Phase 1 结果已保存: %s", T1_RESULTS_PATH)

    # 打印汇总
    logger.info("=" * 60)
    logger.info("T1 Phase 1 汇总")
    logger.info("=" * 60)
    logger.info("基线 F1=%.4f (lr=2e-5, ep=5, freeze=6)", baseline_f1)
    logger.info("目标 F1=%.4f", 0.65)
    logger.info("")
    for r in sorted(results, key=lambda x: -x["f1_mean"]):
        marker = " ✓" if r["beats_baseline"] else ""
        target = " ★ TARGET" if r["meets_target"] else ""
        logger.info("  %s: F1=%.4f±%.4f, AUC=%.4f, %ds%s%s",
                    r["label"], r["f1_mean"], r["f1_std"], r["auc_mean"],
                    int(r["elapsed_s"]), marker, target)
    logger.info("")
    logger.info("最优配置: %s (F1=%.4f)", best_config["label"], best_f1)

    # 推荐 Phase 2 验证配置
    top2 = sorted(results, key=lambda x: -x["f1_mean"])[:2]
    logger.info("推荐 Phase 2 完整验证: %s",
                ", ".join(r["label"] for r in top2))

    return summary


def run_grid_phase2(best_configs: list[dict] = None) -> dict:
    """Phase 2: 对最优配置用 3 seeds × 5 folds 完整验证."""
    if best_configs is None:
        # 从 Phase 1 结果加载 top 2
        if not T1_RESULTS_PATH.exists():
            logger.error("Phase 1 结果不存在, 请先运行 --phase 1")
            return {"error": "Phase 1 结果不存在"}
        with open(T1_RESULTS_PATH, "r", encoding="utf-8") as f:
            phase1 = json.load(f)
        top2 = sorted(phase1["all_results"], key=lambda x: -x["f1_mean"])[:2]
        best_configs = [{"lr": r["lr"], "epochs": r["epochs"],
                         "label": r["label"]} for r in top2]

    logger.info("=" * 60)
    logger.info("T1 Phase 2: 完整验证 (3 seeds × 5 folds = 15 折)")
    logger.info("配置: %d 组", len(best_configs))
    logger.info("=" * 60)

    df = load_mmpsy_data()
    texts = df["text"].tolist()
    y = df["phq9_binary"].astype(int).values

    device = get_device()
    if device != "cuda":
        logger.error("Phase 2 需要 GPU, 当前 device=%s", device)
        return {"error": f"需要 GPU, 当前 {device}"}

    results = []
    for i, cfg in enumerate(best_configs):
        logger.info("-" * 50)
        logger.info("[%d/%d] %s (lr=%s, epochs=%d, freeze=%d)",
                    i + 1, len(best_configs), cfg["label"],
                    cfg["lr"], cfg["epochs"], FREEZE_LAYERS)
        logger.info("-" * 50)

        t0 = time.time()
        cv_result = evaluate_cv_finetune(
            texts, y, device,
            seeds=SEEDS,  # 完整: 3 seeds × 5 folds = 15 折
            epochs=cfg["epochs"],
            freeze_layers=FREEZE_LAYERS,
            lr=cfg["lr"],
        )
        elapsed = time.time() - t0

        result = {
            "label": cfg["label"],
            "lr": cfg["lr"],
            "epochs": cfg["epochs"],
            "freeze_layers": FREEZE_LAYERS,
            "f1_mean": cv_result["f1_mean"],
            "f1_std": cv_result["f1_std"],
            "f1_ci95": cv_result["f1_ci95"],
            "f1_ci_lower": cv_result["f1_ci_lower"],
            "f1_ci_upper": cv_result["f1_ci_upper"],
            "auc_mean": cv_result["auc_mean"],
            "auc_std": cv_result["auc_std"],
            "acc_mean": cv_result["acc_mean"],
            "mean_threshold": cv_result["mean_threshold"],
            "elapsed_s": round(elapsed, 1),
            "n_evaluations": cv_result["n_evaluations"],
            "meets_target": cv_result["f1_mean"] >= 0.65,
            "fold_details": cv_result["fold_details"],
        }
        results.append(result)

        logger.info("[%s] F1=%.4f±%.4f (CI95: %.4f~%.4f), AUC=%.4f, time=%.0fs",
                    cfg["label"], result["f1_mean"], result["f1_std"],
                    result["f1_ci_lower"], result["f1_ci_upper"],
                    result["auc_mean"], elapsed)

    summary = {
        "phase": 2,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "baseline_f1": 0.59,
        "target_f1": 0.65,
        "n_configs": len(best_configs),
        "all_results": results,
        "meets_target_configs": [r for r in results if r["meets_target"]],
    }

    # 更新 T1 结果
    if T1_RESULTS_PATH.exists():
        with open(T1_RESULTS_PATH, "r", encoding="utf-8") as f:
            full = json.load(f)
        full["phase2"] = summary
    else:
        full = {"phase2": summary}

    with open(T1_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(full, f, ensure_ascii=False, indent=2)

    # 更新 training_jobs.json
    try:
        with open(TRAINING_JOBS_PATH, "r", encoding="utf-8") as f:
            jobs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        jobs = {}

    for r in results:
        job_id = f"t1_grid_{r['label']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        jobs[job_id] = {
            "job_id": job_id,
            "status": "completed",
            "task": "T1_bert_grid",
            "created_at": time.time(),
            "lr": r["lr"],
            "epochs": r["epochs"],
            "freeze_layers": r["freeze_layers"],
            "f1_mean": r["f1_mean"],
            "f1_ci95": r["f1_ci95"],
            "auc_mean": r["auc_mean"],
            "meets_target": r["meets_target"],
        }

    with open(TRAINING_JOBS_PATH, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)

    logger.info("=" * 60)
    logger.info("T1 Phase 2 完成,结果已保存: %s", T1_RESULTS_PATH)
    logger.info("=" * 60)
    for r in sorted(results, key=lambda x: -x["f1_mean"]):
        target = " ★ TARGET MET" if r["meets_target"] else ""
        logger.info("  %s: F1=%.4f±%.4f (CI95: %.4f~%.4f), AUC=%.4f%s",
                    r["label"], r["f1_mean"], r["f1_std"],
                    r["f1_ci_lower"], r["f1_ci_upper"],
                    r["auc_mean"], target)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="T1 BERT 训练配方网格搜索")
    parser.add_argument("--phase", type=int, choices=[1, 2], default=1,
                        help="1=快速筛选(quick 1 seed), 2=完整验证(3 seeds)")
    args = parser.parse_args()

    if args.phase == 1:
        run_grid_phase1()
    else:
        run_grid_phase2()


if __name__ == "__main__":
    main()
