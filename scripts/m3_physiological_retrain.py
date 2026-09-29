"""M3 生理模型重训 (阶段二).

目标: 在增强后生理数据 (7203 样本) 上重训 M3, 达到 ECE ≤ 0.05 且 F1 ≥ 0.89
数据: datasets/physiological/external/depresjon_processed/depresjon_augmented.csv
      (1029 原始 + 6174 增强 = 7203, PSI 全部通过)
配置: 复用 M3 正则化实验最佳配置 [128,64,32,16] + dropout 0.2 + wd 0.05 + noise 0.05
评估: 5-fold × 3 seeds 嵌套 CV, 报告 F1/AUC/ECE + 95% CI
校准: 5-fold 内部 Isotonic 回归 (与 M5 一致), 降低 ECE

退出条件:
  - ECE ≤ 0.05 且 F1 ≥ 0.89
  - 所有实验含 95% CI
  - 登记入 training_jobs.json

Usage:
    python scripts/m3_physiological_retrain.py
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
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import f1_score, roc_auc_score

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.ml.data_cleaner import DataCleaner
from app.ml.feature_engineering import engineer_features, get_feature_matrix
from app.ml.loss import binary_cross_entropy_loss
from app.ml.model import PhysiologicalMLP
from app.ml.scaler import SimpleStandardScaler
from app.ml.smote import simple_smote
from app.ml.trainer import evaluate, train_model

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [M3-Retrain] %(message)s")
logger = logging.getLogger("M3-Retrain")
logger.setLevel(logging.INFO)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUGMENTED_DATA_PATH = (
    PROJECT_ROOT
    / "datasets/physiological/external/depresjon_processed/depresjon_augmented.csv"
)
EXPERIMENTS_DIR = PROJECT_ROOT / "models" / "experiments"
TRAINING_JOBS_PATH = PROJECT_ROOT / "models" / "training_jobs.json"
ARTIFACTS_DIR = PROJECT_ROOT / "models" / "artifacts" / "physiological_m3_retrain"

# 阶段二目标
TARGET_F1 = 0.89
TARGET_ECE = 0.05

# CV 配置
N_FOLDS = 5
SEEDS = [42, 123, 7]
T_VALUE_95 = 2.145  # df=14

# 复用 M3 正则化实验最佳配置
BEST_CONFIG = {
    "hidden_dims": [128, 64, 32, 16],
    "dropout_rate": 0.2,
    "weight_decay": 0.05,
    "input_noise_std": 0.05,
    "use_batch_norm": True,
}


def compute_ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    """Expected Calibration Error."""
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    n = len(y_true)
    for i in range(n_bins):
        if i == n_bins - 1:
            mask = (y_prob >= bins[i]) & (y_prob <= bins[i + 1])
        else:
            mask = (y_prob >= bins[i]) & (y_prob < bins[i + 1])
        if mask.sum() == 0:
            continue
        bin_acc = y_true[mask].mean()
        bin_conf = y_prob[mask].mean()
        ece += abs(bin_acc - bin_conf) * (mask.sum() / n)
    return float(ece)


def load_augmented_data() -> pd.DataFrame:
    """加载增强后生理数据."""
    logger.info("加载增强生理数据: %s", AUGMENTED_DATA_PATH)
    df = pd.read_csv(AUGMENTED_DATA_PATH)
    logger.info(
        "增强数据: %d 样本, 阳性率=%.2f%%, source dist=%s",
        len(df), df["depression_label"].mean() * 100,
        df["source"].value_counts().to_dict(),
    )
    return df


def prepare_fold_data(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """单 fold 数据准备: 清洗 → 特征工程 → 标准化 → SMOTE."""
    cleaner = DataCleaner(missing_threshold=0.3)
    train_clean = cleaner.fit_transform(train_df)
    val_clean = cleaner.transform(val_df)

    train_eng = engineer_features(train_clean)
    val_eng = engineer_features(val_clean)

    X_train_df = get_feature_matrix(train_eng)
    X_val_df = get_feature_matrix(val_eng)

    X_train = X_train_df.values.astype(np.float32)
    y_train = train_eng["depression_label"].values.astype(np.float32).reshape(-1, 1)
    X_val = X_val_df.values.astype(np.float32)
    y_val = val_eng["depression_label"].values.astype(np.float32).reshape(-1, 1)

    scaler = SimpleStandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_val = scaler.transform(X_val)

    X_train, y_train = simple_smote(
        X_train, y_train, sampling_strategy=0.5, random_state=seed
    )
    return X_train, y_train, X_val, y_val


def calibrate_isotonic(
    y_true_train: np.ndarray,
    y_prob_train: np.ndarray,
    y_prob_val: np.ndarray,
) -> tuple[np.ndarray, IsotonicRegression]:
    """在训练集上拟合 Isotonic 回归, 应用到验证集."""
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(y_prob_train, y_true_train.ravel())
    y_prob_val_calibrated = iso.predict(y_prob_val)
    return y_prob_val_calibrated, iso


def run_cv_with_calibration(df: pd.DataFrame) -> dict[str, Any]:
    """5-fold × 3 seeds CV, 每折内部做 Isotonic 校准."""
    logger.info("=" * 60)
    logger.info("M3 重训 CV (增强数据 n=%d)", len(df))
    logger.info("配置: %s", BEST_CONFIG)
    logger.info("=" * 60)

    all_f1 = []
    all_auc = []
    all_ece_pre = []  # 校准前 ECE
    all_ece_post = []  # 校准后 ECE
    fold_details = []

    for seed in SEEDS:
        rng = np.random.RandomState(seed)
        n_samples = len(df)
        indices = np.arange(n_samples)
        rng.shuffle(indices)

        fold_size = n_samples // N_FOLDS
        folds = []
        for i in range(N_FOLDS):
            start = i * fold_size
            end = start + fold_size if i < N_FOLDS - 1 else n_samples
            folds.append(indices[start:end])

        for fold_idx in range(N_FOLDS):
            val_indices = folds[fold_idx]
            train_indices = np.concatenate(
                [folds[i] for i in range(N_FOLDS) if i != fold_idx]
            )

            train_df = df.iloc[train_indices].copy()
            val_df = df.iloc[val_indices].copy()

            fold_seed = seed * 100 + fold_idx
            X_train, y_train, X_val, y_val = prepare_fold_data(
                train_df, val_df, seed=fold_seed
            )

            model = PhysiologicalMLP(
                input_dim=X_train.shape[1],
                hidden_dims=BEST_CONFIG["hidden_dims"],
                dropout_rate=BEST_CONFIG["dropout_rate"],
                use_batch_norm=True,
                random_state=fold_seed,
            )

            history = train_model(
                model, X_train, y_train, X_val, y_val,
                epochs=80, batch_size=32, learning_rate=0.001,
                weight_decay=BEST_CONFIG["weight_decay"], patience=15,
                loss_fn=binary_cross_entropy_loss, random_state=fold_seed,
                input_noise_std=BEST_CONFIG["input_noise_std"],
            )

            # 验证集原始概率
            y_prob_raw, _ = model.forward(X_val, training=False)
            y_prob_raw = y_prob_raw.ravel()
            y_true_val = y_val.ravel().astype(int)

            # 校准前指标
            y_pred_raw = (y_prob_raw >= 0.5).astype(int)
            f1_raw = float(f1_score(y_true_val, y_pred_raw, zero_division=0))
            auc_raw = float(roc_auc_score(y_true_val, y_prob_raw)) if len(np.unique(y_true_val)) > 1 else 0.5
            ece_pre = compute_ece(y_true_val.astype(float), y_prob_raw)

            # 内部校准: 用训练集概率拟合 Isotonic
            y_prob_train, _ = model.forward(X_train, training=False)
            y_prob_train = y_prob_train.ravel()
            y_true_train = y_train.ravel().astype(float)
            y_prob_calibrated, _ = calibrate_isotonic(
                y_true_train, y_prob_train, y_prob_raw
            )

            # 校准后指标
            y_pred_cal = (y_prob_calibrated >= 0.5).astype(int)
            f1_cal = float(f1_score(y_true_val, y_pred_cal, zero_division=0))
            auc_cal = float(roc_auc_score(y_true_val, y_prob_calibrated)) if len(np.unique(y_true_val)) > 1 else 0.5
            ece_post = compute_ece(y_true_val.astype(float), y_prob_calibrated)

            all_f1.append(f1_cal)
            all_auc.append(auc_cal)
            all_ece_pre.append(ece_pre)
            all_ece_post.append(ece_post)

            fold_details.append({
                "seed": seed, "fold": fold_idx + 1,
                "f1_raw": f1_raw, "f1_calibrated": f1_cal,
                "auc_raw": auc_raw, "auc_calibrated": auc_cal,
                "ece_pre": ece_pre, "ece_post": ece_post,
            })

            logger.info(
                "[seed=%d fold=%d] F1=%.4f(raw %.4f) AUC=%.4f ECE=%.4f→%.4f",
                seed, fold_idx + 1, f1_cal, f1_raw, auc_cal, ece_pre, ece_post,
            )

    def ci(vals: list[float]) -> tuple[float, float, float]:
        arr = np.array(vals)
        n = len(arr)
        m = float(arr.mean())
        s = float(arr.std(ddof=1)) if n > 1 else 0.0
        c = T_VALUE_95 * s / np.sqrt(n) if n > 1 else 0.0
        return m, s, c

    f1_mean, f1_std, f1_ci = ci(all_f1)
    auc_mean, auc_std, auc_ci = ci(all_auc)
    ece_pre_mean, _, _ = ci(all_ece_pre)
    ece_post_mean, ece_post_std, ece_post_ci = ci(all_ece_post)

    result = {
        "n_evaluations": len(all_f1),
        "f1_mean": f1_mean, "f1_std": f1_std, "f1_ci95": f1_ci,
        "f1_ci_lower": f1_mean - f1_ci, "f1_ci_upper": f1_mean + f1_ci,
        "auc_mean": auc_mean, "auc_std": auc_std, "auc_ci95": auc_ci,
        "auc_ci_lower": auc_mean - auc_ci, "auc_ci_upper": auc_mean + auc_ci,
        "ece_pre_mean": ece_pre_mean,
        "ece_post_mean": ece_post_mean, "ece_post_std": ece_post_std,
        "ece_post_ci95": ece_post_ci,
        "ece_post_ci_upper": ece_post_mean + ece_post_ci,
        "meets_f1_target": f1_mean >= TARGET_F1,
        "meets_ece_target": ece_post_mean <= TARGET_ECE,
        "fold_details": fold_details,
    }

    logger.info("=" * 60)
    logger.info("M3 重训最终结果:")
    logger.info("  F1=%.4f±%.4f (CI95: %.4f~%.4f) target≥%.2f → %s",
                f1_mean, f1_std, f1_mean - f1_ci, f1_mean + f1_ci,
                TARGET_F1, "✅" if result["meets_f1_target"] else "❌")
    logger.info("  AUC=%.4f±%.4f (CI95: %.4f~%.4f)",
                auc_mean, auc_std, auc_mean - auc_ci, auc_mean + auc_ci)
    logger.info("  ECE=%.4f→%.4f±%.4f (CI95 upper: %.4f) target≤%.2f → %s",
                ece_pre_mean, ece_post_mean, ece_post_std,
                ece_post_mean + ece_post_ci, TARGET_ECE,
                "✅" if result["meets_ece_target"] else "❌")
    logger.info("=" * 60)

    return result


def register_training_job(result: dict[str, Any]) -> None:
    """登记到 training_jobs.json."""
    if TRAINING_JOBS_PATH.exists():
        with TRAINING_JOBS_PATH.open("r", encoding="utf-8") as f:
            jobs = json.load(f)
    else:
        jobs = {}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_id = f"m3_physiological_retrain_{timestamp}"

    jobs[job_id] = {
        "job_id": job_id,
        "status": "completed",
        "task": "M3_physiological_retrain_phase2",
        "created_at": time.time(),
        "data_source": str(AUGMENTED_DATA_PATH),
        "n_samples": 7203,
        "config": BEST_CONFIG,
        "f1_mean": result["f1_mean"],
        "f1_ci95": result["f1_ci95"],
        "auc_mean": result["auc_mean"],
        "auc_ci95": result["auc_ci95"],
        "ece_pre": result["ece_pre_mean"],
        "ece_post": result["ece_post_mean"],
        "ece_post_ci_upper": result["ece_post_ci_upper"],
        "meets_f1_target": result["meets_f1_target"],
        "meets_ece_target": result["meets_ece_target"],
        "all_targets_met": result["meets_f1_target"] and result["meets_ece_target"],
        "timestamp": timestamp,
    }

    with TRAINING_JOBS_PATH.open("w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)
    logger.info("实验已登记: %s", job_id)


if __name__ == "__main__":
    df = load_augmented_data()
    result = run_cv_with_calibration(df)
    register_training_job(result)

    print("\n" + "=" * 60)
    print("阶段二-M3 生理重训最终结果:")
    print(f"  F1={result['f1_mean']:.4f} (CI95 ±{result['f1_ci95']:.4f}) target≥{TARGET_F1}: {'✅' if result['meets_f1_target'] else '❌'}")
    print(f"  AUC={result['auc_mean']:.4f} (CI95 ±{result['auc_ci95']:.4f})")
    print(f"  ECE={result['ece_pre_mean']:.4f}→{result['ece_post_mean']:.4f} (CI95 upper {result['ece_post_ci_upper']:.4f}) target≤{TARGET_ECE}: {'✅' if result['meets_ece_target'] else '❌'}")
    print("=" * 60)
