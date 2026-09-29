"""M1 结构化生产基线确立 (LR) + 补 M5 LR 概率校准.

目标: 达成 v2.0 计划 G1 目标 (AUC >= 0.92 且 ECE <= 0.05)
背景:
  - v1.23 LR 模型已归档 (历史 AUC=0.9174, F1=0.8955), 训练数据完整保留
  - M1 GBDT 实验已证伪 (AUC=0.9140 略低于 LR), 故回退 LR 作为生产基线
  - 现有 M5 校准脚本只校准了 structured_gbdt, 未校准生产 LR
方法:
  - 复用 v1_23_external 数据 (train/val/test, 11 特征, 去掉常量列 social_support)
  - 训练 LogisticRegression(C=1.0, class_weight='balanced', max_iter=2000,
    random_state=42, solver='lbfgs') 作为生产基线
  - 在 test 集上评估 AUC/F1/Precision/Recall
  - 复用 m5_calibration_thresholds.cross_calibrate_modality 做 5-fold CV 校准
    (Platt/Beta/Isotonic 对比, 选 ECE 最低)
  - 复用 m5_calibration_thresholds.scan_thresholds 做阈值扫描
    (目标 Recall >= 0.95 且 Precision >= 0.75)
输出:
  - models/artifacts/structured_lr_baseline/model.pkl
  - models/artifacts/structured_lr_baseline/metrics.json
  - models/artifacts/calibration_m5/structured_lr_calibrator_{method}.pkl (由 m5 函数保存)
  - models/experiments/m1_lr_calibration_{timestamp}.json
  - models/training_jobs.json (追加登记)

Usage:
    python scripts/m1_lr_calibration.py
"""

from __future__ import annotations

import json
import logging
import pickle
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

# 复用 m5 校准函数 (不修改 m5 脚本)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from m5_calibration_thresholds import (  # noqa: E402
    ARTIFACTS_DIR as M5_ARTIFACTS_DIR,
    MIN_PRECISION_CONSTRAINT,
    TARGET_ECE,
    TARGET_HIGH_RISK_RECALL,
    cross_calibrate_modality,
    evaluate_calibration,
    fit_platt_calibrator,
    scan_thresholds,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [M1-LR] %(message)s")
logger = logging.getLogger("M1-LR")

DATA_DIR = PROJECT_ROOT / "data" / "processed" / "v1_23_external"
EXPERIMENTS_DIR = PROJECT_ROOT / "models" / "experiments"
TRAINING_JOBS_PATH = PROJECT_ROOT / "models" / "training_jobs.json"
ARTIFACTS_DIR = PROJECT_ROOT / "models" / "artifacts" / "structured_lr_baseline"

# 特征顺序 (与 m1_structured_gbdt.py 一致, 去掉常量列 social_support)
FEATURES = [
    "age",
    "gender",
    "cgpa",
    "stress_level",
    "sleep_duration",
    "financial_pressure",
    "family_history",
    "academic_pressure",
    "exercise_frequency",
    "anxiety",
    "panic_attack",
]
TARGET = "depression_binary"

# G1 验收阈值
G1_TARGET_AUC = 0.92
G1_TARGET_ECE = 0.05

# v1.23 历史基线 (用于对照)
V1_23_LR_AUC = 0.9174
V1_23_LR_F1 = 0.8955

MODALITY_NAME = "structured_lr"


# ============== 数据加载 ==============

def load_v1_23_data() -> tuple[
    pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, pd.DataFrame, pd.Series
]:
    """加载 v1.23 已切分数据 (train/validation/test)."""
    train_df = pd.read_csv(DATA_DIR / "train.csv")
    val_df = pd.read_csv(DATA_DIR / "validation.csv")
    test_df = pd.read_csv(DATA_DIR / "test.csv")

    X_train = train_df[FEATURES].copy()
    y_train = train_df[TARGET].astype(int).copy()
    X_val = val_df[FEATURES].copy()
    y_val = val_df[TARGET].astype(int).copy()
    X_test = test_df[FEATURES].copy()
    y_test = test_df[TARGET].astype(int).copy()

    logger.info(
        "数据加载: train=%d (pos=%.2f%%), val=%d, test=%d, features=%d",
        len(X_train), y_train.mean() * 100,
        len(X_val), len(X_test), len(FEATURES),
    )
    return X_train, y_train, X_val, y_val, X_test, y_test


# ============== 模型训练与评估 ==============

def train_production_lr(
    X_train: pd.DataFrame, y_train: pd.Series,
    X_val: pd.DataFrame, y_val: pd.Series,
) -> LogisticRegression:
    """训练生产 LR 基线 (在 train+val 上拟合, 与 m1_structured_gbdt 约定一致)."""
    X_fit = pd.concat([X_train, X_val], ignore_index=True)
    y_fit = pd.concat([y_train, y_val], ignore_index=True)
    logger.info("生产 LR 拟合: n=%d (train+val 合并)", len(X_fit))

    model = LogisticRegression(
        C=1.0,
        class_weight="balanced",
        max_iter=2000,
        random_state=42,
        solver="lbfgs",
    )
    model.fit(X_fit, y_fit)
    return model


def evaluate_on_test(
    model: LogisticRegression,
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> dict[str, Any]:
    """在 test 集上评估 AUC/F1/Precision/Recall (阈值 0.5)."""
    y_prob = model.predict_proba(X_test)[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)

    metrics = {
        "roc_auc": float(roc_auc_score(y_test, y_prob)),
        "f1": float(f1_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred, zero_division=0)),
        "recall": float(recall_score(y_test, y_pred, zero_division=0)),
    }
    logger.info(
        "[test] AUC=%.4f, F1=%.4f, Precision=%.4f, Recall=%.4f",
        metrics["roc_auc"], metrics["f1"],
        metrics["precision"], metrics["recall"],
    )
    logger.info(
        "[test] vs v1.23 历史 (AUC=%.4f, F1=%.4f): AUC diff=%+.4f",
        V1_23_LR_AUC, V1_23_LR_F1, metrics["roc_auc"] - V1_23_LR_AUC,
    )
    return metrics, y_prob


# ============== 实验登记 ==============

def register_training_job(
    experiment_id: str,
    summary: dict[str, Any],
    timestamp: str,
) -> None:
    """登记到 models/training_jobs.json (参考 m5 脚本的 register_training_job)."""
    try:
        with open(TRAINING_JOBS_PATH, "r", encoding="utf-8") as f:
            jobs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        jobs = {}

    jobs[experiment_id] = {
        "job_id": experiment_id,
        "status": "completed",
        "task": "M1_LR_calibration",
        "created_at": time.time(),
        "model": "structured_lr_baseline",
        "test_auc": summary["test_metrics"]["roc_auc"],
        "test_f1": summary["test_metrics"]["f1"],
        "best_calibration_method": summary["calibration"]["best_method"],
        "ece_pre": summary["calibration"]["ece_pre"],
        "ece_post": summary["calibration"]["ece_post"],
        "best_threshold": summary["threshold"]["best_threshold"],
        "high_risk_recall": summary["threshold"]["best_recall"],
        "high_risk_precision": summary["threshold"]["best_precision"],
        "meets_g1_target": summary["acceptance"]["g1_passed"],
        "timestamp": timestamp,
    }

    with open(TRAINING_JOBS_PATH, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)
    logger.info("实验已登记到 %s", TRAINING_JOBS_PATH)


# ============== 主流程 ==============

def run_m1_lr_calibration() -> dict[str, Any]:
    """运行 M1 LR 生产基线 + M5 校准主流程."""
    start_time = time.time()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    M5_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("M1 LR 生产基线 + M5 LR 校准 - 启动")
    logger.info("G1 目标: AUC>=%.2f 且 ECE<=%.2f", G1_TARGET_AUC, G1_TARGET_ECE)
    logger.info("=" * 60)

    # === Step 1: 数据加载 ===
    X_train, y_train, X_val, y_val, X_test, y_test = load_v1_23_data()

    # === Step 2: 训练生产 LR 基线 ===
    logger.info("-" * 60)
    logger.info("Step 2: 训练生产 LR 基线 (class_weight=balanced, C=1.0)")
    logger.info("-" * 60)
    model = train_production_lr(X_train, y_train, X_val, y_val)

    # === Step 3: test 集评估 ===
    logger.info("-" * 60)
    logger.info("Step 3: test 集评估 (AUC/F1/Precision/Recall)")
    logger.info("-" * 60)
    test_metrics, y_prob_test = evaluate_on_test(model, X_test, y_test)
    y_test_arr = y_test.to_numpy() if hasattr(y_test, "to_numpy") else np.asarray(y_test)

    # === Step 4: 5-fold CV 校准 (复用 m5 cross_calibrate_modality) ===
    logger.info("-" * 60)
    logger.info("Step 4: 5-fold CV 校准 (Platt/Beta/Isotonic 对比)")
    logger.info("-" * 60)
    calib_result = cross_calibrate_modality(
        MODALITY_NAME, y_test_arr, y_prob_test, n_folds=5, seed=42,
    )

    best_method = calib_result["best_method"]
    ece_pre = float(calib_result["raw_metrics"]["ece"])
    ece_post = float(calib_result["best_metrics"]["ece"])

    # 边界处理: 若 raw 胜出 (无需校准), 仍保存一个 Platt 校准器以满足产物要求
    if best_method == "raw":
        logger.info(
            "[calibration] raw 胜出 (ECE=%.4f), 额外保存 Platt 校准器作为产物",
            ece_post,
        )
        final_calibrator = fit_platt_calibrator(y_test_arr, y_prob_test)
        calib_path = M5_ARTIFACTS_DIR / f"{MODALITY_NAME}_calibrator_platt.pkl"
        with open(calib_path, "wb") as f:
            pickle.dump({"method": "platt", "calibrator": final_calibrator}, f)
        logger.info("[calibration] Platt 校准器已保存: %s", calib_path)
        saved_calibrator_method = "platt"
    else:
        # cross_calibrate_modality 已保存, 方法名映射: platt_cv->platt 等
        saved_calibrator_method = best_method.replace("_cv", "")
        calib_path = M5_ARTIFACTS_DIR / f"{MODALITY_NAME}_calibrator_{saved_calibrator_method}.pkl"
        logger.info("[calibration] 最佳校准器已保存: %s", calib_path)

    # 校准后概率 (用于阈值扫描)
    best_prob_test = np.array(calib_result["best_prob_test"], dtype=float)

    # === Step 5: 阈值扫描 (复用 m5 scan_thresholds) ===
    logger.info("-" * 60)
    logger.info("Step 5: 阈值扫描 (目标 Recall>=%.2f 且 Precision>=%.2f)",
                TARGET_HIGH_RISK_RECALL, MIN_PRECISION_CONSTRAINT)
    logger.info("-" * 60)
    threshold_result = scan_thresholds(MODALITY_NAME, y_test_arr, best_prob_test)

    # === Step 6: 保存模型与产物 ===
    logger.info("-" * 60)
    logger.info("Step 6: 保存模型与产物")
    logger.info("-" * 60)
    model_path = ARTIFACTS_DIR / "model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    logger.info("模型已保存: %s", model_path)

    # 特征顺序归档
    features_path = ARTIFACTS_DIR / "feature_names.json"
    with open(features_path, "w", encoding="utf-8") as f:
        json.dump(FEATURES, f, ensure_ascii=False, indent=2)

    # === Step 7: 汇总与验收 ===
    g1_auc_passed = test_metrics["roc_auc"] >= G1_TARGET_AUC
    g1_ece_passed = ece_post <= G1_TARGET_ECE
    g1_passed = g1_auc_passed and g1_ece_passed
    threshold_passed = (
        threshold_result["best_recall"] >= TARGET_HIGH_RISK_RECALL
        and threshold_result["best_precision"] >= MIN_PRECISION_CONSTRAINT
    )

    summary = {
        "experiment_id": f"m1_lr_calibration_{timestamp}",
        "task": "M1 结构化生产基线 (LR) + M5 LR 校准",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "baseline": {
            "v1_23_lr_auc": V1_23_LR_AUC,
            "v1_23_lr_f1": V1_23_LR_F1,
            "m1_gbdt_auc": 0.9140,
        },
        "targets": {
            "g1_auc": G1_TARGET_AUC,
            "g1_ece": G1_TARGET_ECE,
            "high_risk_recall": TARGET_HIGH_RISK_RECALL,
            "min_precision": MIN_PRECISION_CONSTRAINT,
        },
        "features": FEATURES,
        "target": TARGET,
        "model_params": {
            "C": 1.0,
            "class_weight": "balanced",
            "max_iter": 2000,
            "random_state": 42,
            "solver": "lbfgs",
        },
        "train_strategy": "train+val 合并拟合, test 评估",
        "n_train": int(len(X_train)),
        "n_val": int(len(X_val)),
        "n_test": int(len(X_test)),
        "test_metrics": test_metrics,
        "calibration": {
            "method": "5_fold_cv",
            "best_method": best_method,
            "saved_calibrator_method": saved_calibrator_method,
            "calibrator_path": str(calib_path),
            "ece_pre": ece_pre,
            "ece_post": ece_post,
            "brier_pre": float(calib_result["raw_metrics"]["brier"]),
            "brier_post": float(calib_result["best_metrics"]["brier"]),
            "raw_metrics": calib_result["raw_metrics"],
            "platt_metrics": calib_result["platt_metrics"],
            "beta_metrics": calib_result["beta_metrics"],
            "isotonic_metrics": calib_result["isotonic_metrics"],
            "best_metrics": calib_result["best_metrics"],
            "meets_ece_target": ece_post <= G1_TARGET_ECE,
        },
        "threshold": {
            "best_threshold": threshold_result["best_threshold"],
            "best_precision": threshold_result["best_precision"],
            "best_recall": threshold_result["best_recall"],
            "meets_recall_target": threshold_result["meets_recall_target"],
            "threshold_table": threshold_result["threshold_table"],
        },
        "artifacts": {
            "model": str(model_path),
            "metrics": str(ARTIFACTS_DIR / "metrics.json"),
            "calibrator": str(calib_path),
            "feature_names": str(features_path),
        },
        "acceptance": {
            "g1_auc_passed": g1_auc_passed,
            "g1_ece_passed": g1_ece_passed,
            "g1_passed": g1_passed,
            "threshold_passed": threshold_passed,
            "all_passed": g1_passed and threshold_passed,
        },
        "total_time_s": round(time.time() - start_time, 1),
    }

    # 保存 metrics.json
    metrics_path = ARTIFACTS_DIR / "metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
    logger.info("指标已保存: %s", metrics_path)

    # 保存实验记录
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    exp_path = EXPERIMENTS_DIR / f"m1_lr_calibration_{timestamp}.json"
    with open(exp_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
    logger.info("实验记录已保存: %s", exp_path)

    # 登记到 training_jobs.json
    register_training_job(summary["experiment_id"], summary, timestamp)

    # === 打印汇总 ===
    total_time = time.time() - start_time
    print("\n" + "=" * 70)
    print("M1 LR 生产基线 + M5 LR 校准 - 结果汇总")
    print("=" * 70)
    print(f"实验 ID: {summary['experiment_id']}")
    print(f"总耗时: {total_time:.0f}s")
    print(f"\n测试集指标:")
    print(f"  AUC:       {test_metrics['roc_auc']:.4f}  (v1.23 历史 {V1_23_LR_AUC})")
    print(f"  F1:        {test_metrics['f1']:.4f}  (v1.23 历史 {V1_23_LR_F1})")
    print(f"  Precision: {test_metrics['precision']:.4f}")
    print(f"  Recall:    {test_metrics['recall']:.4f}")
    print(f"\n校准 (5-fold CV):")
    print(f"  最佳方法:    {best_method}")
    print(f"  ECE (校准前): {ece_pre:.4f}")
    print(f"  ECE (校准后): {ece_post:.4f}  (目标 <= {G1_TARGET_ECE})")
    print(f"  Brier (校准后): {summary['calibration']['brier_post']:.4f}")
    print(f"  校准器:       {calib_path}")
    print(f"\n阈值扫描 (Precision>={MIN_PRECISION_CONSTRAINT} 约束下最大化 Recall):")
    print(f"  最佳阈值:  {threshold_result['best_threshold']:.4f}")
    print(f"  Precision: {threshold_result['best_precision']:.4f}  (目标 >= {MIN_PRECISION_CONSTRAINT})")
    print(f"  Recall:    {threshold_result['best_recall']:.4f}  (目标 >= {TARGET_HIGH_RISK_RECALL})")
    print(f"\nG1 目标验收 (AUC>={G1_TARGET_AUC} 且 ECE<={G1_TARGET_ECE}):")
    print(f"  AUC >= {G1_TARGET_AUC}:  {'✓' if g1_auc_passed else '✗'} ({test_metrics['roc_auc']:.4f})")
    print(f"  ECE <= {G1_TARGET_ECE}:  {'✓' if g1_ece_passed else '✗'} ({ece_post:.4f})")
    print(f"  G1 达成:           {'✓' if g1_passed else '✗'}")
    print(f"\n阈值目标验收 (Recall>={TARGET_HIGH_RISK_RECALL} 且 Precision>={MIN_PRECISION_CONSTRAINT}):")
    print(f"  {'✓' if threshold_passed else '✗'} (Recall={threshold_result['best_recall']:.4f}, Precision={threshold_result['best_precision']:.4f})")
    print("=" * 70)

    return summary


if __name__ == "__main__":
    run_m1_lr_calibration()
