"""M3 生理 MLP 正则化重构优化脚本.

目标: val F1 0.7314 → ≥0.80, AUC ≥0.83, overfit 标志清零
方法: 固定 BN+dropout 0.2-0.3 配置, 弃用 overfit 的 Deep 变体,
      输入加噪声增强, 权重衰减扫描
评估: 5-fold × 3 seeds 重复 CV, 报告均值±std 与 95% CI
验收: train/val F1 差 <0.05, 5-fold CV F1≥0.80

Usage:
    python scripts/m3_physiological_regularization.py
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.ml.data_cleaner import DataCleaner
from app.ml.data_loader import merge_datasets
from app.ml.feature_engineering import engineer_features, get_feature_matrix
from app.ml.loss import binary_cross_entropy_loss
from app.ml.model import PhysiologicalMLP
from app.ml.scaler import SimpleStandardScaler
from app.ml.smote import simple_smote
from app.ml.trainer import evaluate, train_model

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [M3] %(message)s")
logger = logging.getLogger("M3")
logger.setLevel(logging.INFO)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS_DIR = PROJECT_ROOT / "models" / "experiments"
TRAINING_JOBS_PATH = PROJECT_ROOT / "models" / "training_jobs.json"
ARTIFACTS_DIR = PROJECT_ROOT / "models" / "artifacts" / "physiological_m3"

# M3 验收阈值
TARGET_F1 = 0.80
TARGET_AUC = 0.83
MAX_TRAIN_VAL_GAP = 0.05

# 95% CI t-value for df=14 (5-fold × 3 seeds - 1 = 14)
T_VALUE_95 = 2.145


def compute_ci(values: list[float], t_value: float = T_VALUE_95) -> tuple[float, float, float]:
    """计算均值、标准差和 95% 置信区间半宽."""
    arr = np.array(values)
    n = len(arr)
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1)) if n > 1 else 0.0
    ci_half = t_value * std / np.sqrt(n) if n > 1 else 0.0
    return mean, std, ci_half


def load_physiological_data() -> pd.DataFrame:
    """加载合并的生理数据集 (Depresjon + Kaggle)."""
    logger.info("加载生理数据集...")
    df = merge_datasets()
    logger.info("合并后样本数: %d (Depresjon + Kaggle)", len(df))
    return df


def prepare_fold_data(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """单 fold 数据准备: 清洗 → 特征工程 → 标准化 → SMOTE.

    所有 fit 操作仅在 train_df 上进行，防止数据泄漏。
    """
    # 1. 数据清洗 (fit on train only)
    cleaner = DataCleaner(missing_threshold=0.3)
    train_clean = cleaner.fit_transform(train_df)
    val_clean = cleaner.transform(val_df)

    # 2. 特征工程
    train_eng = engineer_features(train_clean)
    val_eng = engineer_features(val_clean)

    # 3. 提取特征矩阵
    X_train_df = get_feature_matrix(train_eng)
    X_val_df = get_feature_matrix(val_eng)
    feature_names = list(X_train_df.columns)

    X_train = X_train_df.values.astype(np.float32)
    y_train = train_eng["depression_label"].values.astype(np.float32).reshape(-1, 1)
    X_val = X_val_df.values.astype(np.float32)
    y_val = val_eng["depression_label"].values.astype(np.float32).reshape(-1, 1)

    # 4. 标准化 (fit on train only)
    scaler = SimpleStandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_val = scaler.transform(X_val)

    # 5. SMOTE (train only, 每 fold 派生不同种子)
    X_train, y_train = simple_smote(
        X_train, y_train, sampling_strategy=0.5, random_state=seed
    )

    return X_train, y_train, X_val, y_val


def evaluate_config(
    df: pd.DataFrame,
    hidden_dims: list[int],
    dropout_rate: float,
    weight_decay: float,
    input_noise_std: float,
    n_folds: int = 5,
    seeds: list[int] | None = None,
    epochs: int = 80,
    patience: int = 15,
) -> dict[str, Any]:
    """对单个配置运行 5-fold × 3 seeds 重复 CV.

    Returns:
        包含各 fold 指标、聚合统计和 overfit 检测的字典。
    """
    if seeds is None:
        seeds = [42, 123, 7]

    all_f1 = []
    all_auc = []
    all_gap = []
    fold_details = []

    for seed in seeds:
        rng = np.random.RandomState(seed)
        n_samples = len(df)
        indices = np.arange(n_samples)
        rng.shuffle(indices)

        # 创建 5 折
        fold_size = n_samples // n_folds
        folds = []
        for i in range(n_folds):
            start = i * fold_size
            end = start + fold_size if i < n_folds - 1 else n_samples
            folds.append(indices[start:end])

        for fold_idx in range(n_folds):
            val_indices = folds[fold_idx]
            train_indices = np.concatenate(
                [folds[i] for i in range(n_folds) if i != fold_idx]
            )

            train_df = df.iloc[train_indices].copy()
            val_df = df.iloc[val_indices].copy()

            fold_seed = seed * 100 + fold_idx
            X_train, y_train, X_val, y_val = prepare_fold_data(
                train_df, val_df, seed=fold_seed
            )

            model = PhysiologicalMLP(
                input_dim=X_train.shape[1],
                hidden_dims=hidden_dims,
                dropout_rate=dropout_rate,
                use_batch_norm=True,  # M3: 固定 BN=true
                random_state=fold_seed,
            )

            history = train_model(
                model,
                X_train,
                y_train,
                X_val,
                y_val,
                epochs=epochs,
                batch_size=32,
                learning_rate=0.001,
                weight_decay=weight_decay,
                patience=patience,
                loss_fn=binary_cross_entropy_loss,
                random_state=fold_seed,
                input_noise_std=input_noise_std,  # M3: 输入噪声增强
            )

            val_loss, val_metrics = evaluate(
                model, X_val, y_val, binary_cross_entropy_loss
            )

            # 计算 best epoch 处的 train/val gap
            # M3 修正: 输入噪声会人为降低 train_f1，导致 val > train。
            # 此情况非过拟合，仅当 train > val 时才标记 overfit。
            best_ep = history["best_epoch"]
            train_f1_at_best = history["train_f1"][best_ep]
            val_f1_at_best = history["val_f1"][best_ep]
            gap = max(0.0, train_f1_at_best - val_f1_at_best)

            all_f1.append(val_metrics["f1"])
            all_auc.append(val_metrics["roc_auc"])
            all_gap.append(gap)

            fold_details.append({
                "seed": seed,
                "fold": fold_idx + 1,
                "val_f1": float(val_metrics["f1"]),
                "val_auc": float(val_metrics["roc_auc"]),
                "train_f1_at_best": float(train_f1_at_best),
                "val_f1_at_best": float(val_f1_at_best),
                "gap": float(gap),
                "best_epoch": int(best_ep),
                "overfit_flag": gap > MAX_TRAIN_VAL_GAP,
            })

    f1_mean, f1_std, f1_ci = compute_ci(all_f1)
    auc_mean, auc_std, auc_ci = compute_ci(all_auc)
    gap_mean, gap_std, gap_ci = compute_ci(all_gap)

    return {
        "config": {
            "hidden_dims": hidden_dims,
            "dropout_rate": dropout_rate,
            "weight_decay": weight_decay,
            "input_noise_std": input_noise_std,
            "use_batch_norm": True,
        },
        "n_evaluations": len(all_f1),
        "f1_mean": f1_mean,
        "f1_std": f1_std,
        "f1_ci95": f1_ci,
        "f1_ci_lower": f1_mean - f1_ci,
        "f1_ci_upper": f1_mean + f1_ci,
        "auc_mean": auc_mean,
        "auc_std": auc_std,
        "auc_ci95": auc_ci,
        "gap_mean": gap_mean,
        "gap_std": gap_std,
        "overfit_flag_count": sum(1 for d in fold_details if d["overfit_flag"]),
        "fold_details": fold_details,
        "meets_f1_target": f1_mean >= TARGET_F1,
        "meets_auc_target": auc_mean >= TARGET_AUC,
        "meets_gap_target": gap_mean < MAX_TRAIN_VAL_GAP,
    }


def run_m3_optimization() -> dict[str, Any]:
    """运行 M3 完整优化流程."""
    start_time = time.time()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    df = load_physiological_data()

    # M3 配置扫描空间
    # 弃用 overfit 的 Deep[64,48,32,24,16]，保留 [64,32,16] 和 [128,64,32,16]
    configs = []
    for hidden_dims in ([64, 32, 16], [128, 64, 32, 16]):
        for dropout in (0.2, 0.3):
            for wd in (0.005, 0.01, 0.05):
                for noise in (0.0, 0.05, 0.1):
                    configs.append({
                        "hidden_dims": hidden_dims,
                        "dropout_rate": dropout,
                        "weight_decay": wd,
                        "input_noise_std": noise,
                    })

    logger.info("M3 配置扫描: %d 个配置, 每配置 5-fold × 3 seeds = 15 次评估", len(configs))
    logger.info("总训练次数: %d", len(configs) * 15)

    all_results = []
    for i, cfg in enumerate(configs):
        cfg_start = time.time()
        logger.info(
            "[%d/%d] arch=%s dp=%.1f wd=%.3f noise=%.2f ...",
            i + 1, len(configs),
            cfg["hidden_dims"], cfg["dropout_rate"],
            cfg["weight_decay"], cfg["input_noise_std"],
        )

        result = evaluate_config(
            df=df,
            hidden_dims=cfg["hidden_dims"],
            dropout_rate=cfg["dropout_rate"],
            weight_decay=cfg["weight_decay"],
            input_noise_std=cfg["input_noise_std"],
        )
        result["config_idx"] = i
        result["eval_time_s"] = round(time.time() - cfg_start, 1)
        all_results.append(result)

        logger.info(
            "  F1=%.4f±%.4f (CI: %.4f~%.4f) AUC=%.4f gap=%.4f overfit=%d  [%.1fs]",
            result["f1_mean"], result["f1_std"],
            result["f1_ci_lower"], result["f1_ci_upper"],
            result["auc_mean"], result["gap_mean"],
            result["overfit_flag_count"],
            result["eval_time_s"],
        )

    # 选择最佳配置 (按 F1 均值排序, overfit_flag_count 最少优先)
    all_results.sort(
        key=lambda r: (r["f1_mean"], -r["overfit_flag_count"]),
        reverse=True,
    )
    best = all_results[0]

    total_time = time.time() - start_time

    # 汇总报告
    summary = {
        "experiment_id": f"m3_physiological_{timestamp}",
        "task": "M3 生理 MLP 正则化重构",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "baseline": {
            "source": "optimization_v2_20260507_020036.json",
            "deep_variant_f1": 0.7314,
            "deep_variant_overfit": True,
            "bn_dp035_f1": 0.7262,
            "bn_dp035_overfit": False,
        },
        "targets": {"f1": TARGET_F1, "auc": TARGET_AUC, "max_gap": MAX_TRAIN_VAL_GAP},
        "n_configs": len(configs),
        "n_evaluations_per_config": 15,
        "total_train_runs": len(configs) * 15,
        "total_time_s": round(total_time, 1),
        "best_config": best["config"],
        "best_metrics": {
            "f1_mean": best["f1_mean"],
            "f1_std": best["f1_std"],
            "f1_ci95": f"{best['f1_mean']:.4f} ± {best['f1_ci95']:.4f}",
            "auc_mean": best["auc_mean"],
            "auc_std": best["auc_std"],
            "auc_ci95": f"{best['auc_mean']:.4f} ± {best['auc_ci95']:.4f}",
            "gap_mean": best["gap_mean"],
            "overfit_flag_count": best["overfit_flag_count"],
        },
        "acceptance": {
            "meets_f1_target": best["meets_f1_target"],
            "meets_auc_target": best["meets_auc_target"],
            "meets_gap_target": best["meets_gap_target"],
            "all_passed": best["meets_f1_target"] and best["meets_auc_target"] and best["meets_gap_target"],
        },
        "all_configs_summary": [
            {
                "config": r["config"],
                "f1_mean": r["f1_mean"],
                "f1_std": r["f1_std"],
                "auc_mean": r["auc_mean"],
                "gap_mean": r["gap_mean"],
                "overfit_flag_count": r["overfit_flag_count"],
            }
            for r in all_results
        ],
    }

    # 保存实验结果
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    exp_path = EXPERIMENTS_DIR / f"m3_physiological_{timestamp}.json"
    with open(exp_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    logger.info("实验结果已保存: %s", exp_path)

    # 保存最佳配置的详细 fold 结果
    best_detail_path = EXPERIMENTS_DIR / f"m3_best_detail_{timestamp}.json"
    with open(best_detail_path, "w", encoding="utf-8") as f:
        json.dump(
            {"best_config": best["config"], "fold_details": best["fold_details"]},
            f, ensure_ascii=False, indent=2,
        )

    # 注册训练任务
    register_training_job(summary["experiment_id"], best, timestamp)

    # 如果达标，训练最终模型并保存
    if best["meets_f1_target"] and best["meets_gap_target"]:
        logger.info("✓ M3 验收通过! 训练最终模型...")
        save_final_model(df, best["config"], timestamp)
    else:
        logger.warning(
            "✗ M3 未完全达标: F1=%.4f (目标≥%.2f), AUC=%.4f (目标≥%.2f), gap=%.4f (目标<%.2f)",
            best["f1_mean"], TARGET_F1,
            best["auc_mean"], TARGET_AUC,
            best["gap_mean"], MAX_TRAIN_VAL_GAP,
        )
        # 即使未达标，也保存最佳模型供后续分析
        logger.info("保存最佳模型供后续分析...")
        save_final_model(df, best["config"], timestamp)

    # 打印汇总
    print("\n" + "=" * 70)
    print("M3 生理 MLP 正则化重构 - 优化结果汇总")
    print("=" * 70)
    print(f"实验 ID: {summary['experiment_id']}")
    print(f"总训练次数: {summary['total_train_runs']} ({total_time:.0f}s)")
    print(f"\n最佳配置: {best['config']}")
    print(f"  F1:  {best['f1_mean']:.4f} ± {best['f1_std']:.4f} (95% CI: {best['f1_ci_lower']:.4f} ~ {best['f1_ci_upper']:.4f})")
    print(f"  AUC: {best['auc_mean']:.4f} ± {best['auc_std']:.4f}")
    print(f"  train/val gap: {best['gap_mean']:.4f} (overfit flags: {best['overfit_flag_count']}/15)")
    print(f"\n基线对比:")
    print(f"  Deep[64,48,32,24,16] (overfit):  F1=0.7314")
    print(f"  BN+dp0.35 (non-overfit):         F1=0.7262")
    print(f"  M3 最佳:                          F1={best['f1_mean']:.4f}")
    print(f"\n验收:")
    print(f"  F1 ≥ 0.80: {'✓' if best['meets_f1_target'] else '✗'} ({best['f1_mean']:.4f})")
    print(f"  AUC ≥ 0.83: {'✓' if best['meets_auc_target'] else '✗'} ({best['auc_mean']:.4f})")
    print(f"  gap < 0.05: {'✓' if best['meets_gap_target'] else '✗'} ({best['gap_mean']:.4f})")
    print("=" * 70)

    return summary


def save_final_model(
    df: pd.DataFrame,
    config: dict,
    timestamp: str,
) -> None:
    """用最佳配置在全量数据上训练最终模型并保存."""
    logger.info("训练最终模型 (全量数据, 80/20 split)...")

    # 全量数据 80/20 split
    rng = np.random.RandomState(42)
    n = len(df)
    indices = np.arange(n)
    rng.shuffle(indices)
    split = int(n * 0.8)
    train_df = df.iloc[indices[:split]].copy()
    val_df = df.iloc[indices[split:]].copy()

    X_train, y_train, X_val, y_val = prepare_fold_data(train_df, val_df, seed=42)

    model = PhysiologicalMLP(
        input_dim=X_train.shape[1],
        hidden_dims=config["hidden_dims"],
        dropout_rate=config["dropout_rate"],
        use_batch_norm=True,
        random_state=42,
    )

    history = train_model(
        model,
        X_train,
        y_train,
        X_val,
        y_val,
        epochs=120,
        batch_size=32,
        learning_rate=0.001,
        weight_decay=config["weight_decay"],
        patience=20,
        loss_fn=binary_cross_entropy_loss,
        random_state=42,
        input_noise_std=config["input_noise_std"],
    )

    val_loss, val_metrics = evaluate(model, X_val, y_val, binary_cross_entropy_loss)

    # 保存模型
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    model.save(ARTIFACTS_DIR / "model.json")

    # 保存 scaler 和 feature_names (从 prepare_fold_data 重新获取)
    cleaner = DataCleaner(missing_threshold=0.3)
    train_clean = cleaner.fit_transform(train_df)
    train_eng = engineer_features(train_clean)
    feature_names = list(get_feature_matrix(train_eng).columns)

    scaler = SimpleStandardScaler()
    X_full = get_feature_matrix(train_eng).values.astype(np.float32)
    scaler.fit_transform(X_full)
    scaler.save(ARTIFACTS_DIR / "scaler.json")
    cleaner.save(ARTIFACTS_DIR / "cleaner_stats.json")

    with open(ARTIFACTS_DIR / "feature_names.json", "w", encoding="utf-8") as f:
        json.dump(feature_names, f, ensure_ascii=False, indent=2)

    # 保存 metrics
    metrics = {
        "best_epoch": history["best_epoch"],
        "best_val_f1": float(history["best_val_f1"]),
        "test_metrics": val_metrics,
        "hyperparameters": {
            "epochs": 120,
            "batch_size": 32,
            "learning_rate": 0.001,
            "weight_decay": config["weight_decay"],
            "patience": 20,
            "hidden_dims": config["hidden_dims"],
            "dropout_rate": config["dropout_rate"],
            "use_batch_norm": True,
            "input_noise_std": config["input_noise_std"],
            "input_dim": X_train.shape[1],
        },
        "random_state": 42,
        "training_timestamp": datetime.now().isoformat(timespec="seconds"),
        "model_parameters": model.count_parameters(),
        "m3_optimization": True,
    }
    with open(ARTIFACTS_DIR / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    logger.info("最终模型已保存到 %s", ARTIFACTS_DIR)
    logger.info("最终模型指标: F1=%.4f, AUC=%.4f", val_metrics["f1"], val_metrics["roc_auc"])


def register_training_job(experiment_id: str, best_result: dict, timestamp: str) -> None:
    """将实验登记到 models/training_jobs.json."""
    try:
        with open(TRAINING_JOBS_PATH, "r", encoding="utf-8") as f:
            jobs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        jobs = {}

    jobs[experiment_id] = {
        "job_id": experiment_id,
        "status": "completed",
        "task": "M3_physiological_regularization",
        "created_at": time.time(),
        "best_config": best_result["config"],
        "f1_mean": best_result["f1_mean"],
        "auc_mean": best_result["auc_mean"],
        "meets_targets": best_result["meets_f1_target"] and best_result["meets_auc_target"] and best_result["meets_gap_target"],
        "timestamp": timestamp,
    }

    with open(TRAINING_JOBS_PATH, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)
    logger.info("实验已登记到 %s", TRAINING_JOBS_PATH)


if __name__ == "__main__":
    run_m3_optimization()
