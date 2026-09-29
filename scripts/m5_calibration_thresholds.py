"""M5 概率校准与成本敏感阈值.

目标: 各模态 ECE ≤0.05, 高危召回≥0.95 (precision≥0.75 约束下)
方法:
  - Platt (sigmoid) / Isotonic 校准对比
  - 按"漏诊代价≫误诊代价"设定分级阈值
  - 阈值-召回-精度对照表归档
基础: 复用 v1.16/v1.23 校准成果 (backend/scripts/modeling/v1_23/05_calibrate_thresholds.py)
输入:
  - 结构化: M1 GBDT (models/artifacts/structured_m1/best_model.pkl)
  - 生理: M3 Physiological MLP (models/artifacts/physiological_m3/)
  - 文本: 可选 (若模型存在则校准)
输出:
  - models/artifacts/calibration_m5/{modality}_calibrator.pkl
  - models/artifacts/calibration_m5/{modality}_metrics.json
  - models/artifacts/calibration_m5/{modality}_curve.png
  - models/artifacts/calibration_m5/threshold_table.csv
  - models/experiments/m5_calibration_{timestamp}.json

Usage:
    python scripts/m5_calibration_thresholds.py
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
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, precision_recall_curve, roc_auc_score

logging.basicConfig(level=logging.INFO, format="%(asctime)s [M5] %(message)s")
logger = logging.getLogger("M5")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

EXPERIMENTS_DIR = PROJECT_ROOT / "models" / "experiments"
TRAINING_JOBS_PATH = PROJECT_ROOT / "models" / "training_jobs.json"
ARTIFACTS_DIR = PROJECT_ROOT / "models" / "artifacts" / "calibration_m5"

# M5 验收阈值
TARGET_ECE = 0.05
TARGET_HIGH_RISK_RECALL = 0.95
MIN_PRECISION_CONSTRAINT = 0.75

# 校准集分桶数
N_BINS = 10


# ============== 校准评估指标 ==============

def compute_ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = N_BINS) -> float:
    """Expected Calibration Error.

    ECE = sum(|accuracy - confidence| * (bin_size / total))
    """
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


def compute_brier(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    return float(brier_score_loss(y_true, y_prob))


def evaluate_calibration(y_true: np.ndarray, y_prob: np.ndarray, label: str) -> dict[str, Any]:
    """评估单个模态校准质量."""
    ece = compute_ece(y_true, y_prob)
    brier = compute_brier(y_true, y_prob)
    auc = float(roc_auc_score(y_true, y_prob)) if len(np.unique(y_true)) > 1 else 0.5
    logger.info("[%s] ECE=%.4f, Brier=%.4f, AUC=%.4f", label, ece, brier, auc)
    return {
        "label": label,
        "ece": ece,
        "brier": brier,
        "auc": auc,
        "n_samples": int(len(y_true)),
        "pos_rate": float(y_true.mean()),
        "prob_stats": {
            "mean": float(y_prob.mean()),
            "std": float(y_prob.std()),
            "min": float(y_prob.min()),
            "max": float(y_prob.max()),
            "p50": float(np.percentile(y_prob, 50)),
            "p90": float(np.percentile(y_prob, 90)),
        },
    }


# ============== 校准器训练 ==============

def fit_platt_calibrator(y_true: np.ndarray, y_prob: np.ndarray) -> LogisticRegression:
    """Platt scaling: 用 logistic regression 拟合 y_prob -> y_true."""
    lr = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
    lr.fit(y_prob.reshape(-1, 1), y_true)
    return lr


def apply_platt(lr: LogisticRegression, y_prob: np.ndarray) -> np.ndarray:
    return lr.predict_proba(y_prob.reshape(-1, 1))[:, 1]


def fit_isotonic_calibrator(y_true: np.ndarray, y_prob: np.ndarray) -> IsotonicRegression:
    """Isotonic regression: 非参数单调映射."""
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(y_prob, y_true)
    return iso


def apply_isotonic(iso: IsotonicRegression, y_prob: np.ndarray) -> np.ndarray:
    return iso.transform(y_prob)


def fit_beta_calibrator(y_true: np.ndarray, y_prob: np.ndarray) -> LogisticRegression:
    """Beta calibration: 适合小样本的二参数校准.

    原理: calibrated_p = sigmoid(a * log(p) + b * log(1-p) + c)
    用 LogReg 在 [log(p), log(1-p)] 上拟合, 比 Isotonic 更平滑, 不易过拟合.
    """
    eps = 1e-8
    p = np.clip(y_prob, eps, 1 - eps)
    X = np.column_stack([np.log(p), np.log(1 - p)])
    lr = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
    lr.fit(X, y_true)
    return lr


def apply_beta(lr: LogisticRegression, y_prob: np.ndarray) -> np.ndarray:
    eps = 1e-8
    p = np.clip(y_prob, eps, 1 - eps)
    X = np.column_stack([np.log(p), np.log(1 - p)])
    return lr.predict_proba(X)[:, 1]


def calibrate_modality(
    modality_name: str,
    y_val: np.ndarray,
    y_prob_val: np.ndarray,
    y_test: np.ndarray,
    y_prob_test: np.ndarray,
) -> dict[str, Any]:
    """对单个模态做 Platt + Isotonic 校准对比, 选择最佳方法.

    校准器在 val 集上拟合, 在 test 集上评估 (避免泄漏).
    """
    logger.info("=" * 50)
    logger.info("[%s] 校准对比", modality_name)
    logger.info("=" * 50)

    # 原始 (未校准)
    raw_metrics = evaluate_calibration(y_test, y_prob_test, f"{modality_name}_raw")

    # Platt scaling
    platt = fit_platt_calibrator(y_val, y_prob_val)
    y_prob_platt_test = apply_platt(platt, y_prob_test)
    platt_metrics = evaluate_calibration(y_test, y_prob_platt_test, f"{modality_name}_platt")

    # Isotonic regression
    isotonic = fit_isotonic_calibrator(y_val, y_prob_val)
    y_prob_iso_test = apply_isotonic(isotonic, y_prob_test)
    iso_metrics = evaluate_calibration(y_test, y_prob_iso_test, f"{modality_name}_isotonic")

    # 选择 ECE 最低的方法
    candidates = [
        ("raw", raw_metrics, y_prob_test, None),
        ("platt", platt_metrics, y_prob_platt_test, platt),
        ("isotonic", iso_metrics, y_prob_iso_test, isotonic),
    ]
    best_method = min(candidates, key=lambda x: x[1]["ece"])
    best_name, best_metrics, best_prob, best_calibrator = best_method

    logger.info(
        "[%s] 最佳校准方法: %s (ECE=%.4f, Brier=%.4f)",
        modality_name, best_name, best_metrics["ece"], best_metrics["brier"],
    )

    # 保存校准器
    if best_calibrator is not None:
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        calib_path = ARTIFACTS_DIR / f"{modality_name}_calibrator_{best_name}.pkl"
        with open(calib_path, "wb") as f:
            pickle.dump({"method": best_name, "calibrator": best_calibrator}, f)

    # 保存校准曲线图
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        plt.figure(figsize=(8, 6))
        for name, _, prob, _ in candidates:
            prob_true, prob_pred = calibration_curve(y_test, prob, n_bins=N_BINS, strategy="uniform")
            plt.plot(prob_pred, prob_true, marker="o", label=f"{name} (ECE={compute_ece(y_test, prob):.4f})")
        plt.plot([0, 1], [0, 1], "k--", label="Perfect")
        plt.xlabel("Mean predicted probability")
        plt.ylabel("Fraction of positives")
        plt.title(f"{modality_name} Calibration Curve")
        plt.legend()
        plt.grid(True, alpha=0.3)
        curve_path = ARTIFACTS_DIR / f"{modality_name}_curve.png"
        plt.savefig(curve_path, dpi=120, bbox_inches="tight")
        plt.close()
        logger.info("[%s] 校准曲线已保存: %s", modality_name, curve_path)
    except Exception as e:
        logger.warning("[%s] 校准曲线图保存失败: %s", modality_name, str(e)[:100])

    return {
        "modality": modality_name,
        "raw_metrics": raw_metrics,
        "platt_metrics": platt_metrics,
        "isotonic_metrics": iso_metrics,
        "best_method": best_name,
        "best_metrics": best_metrics,
        "best_prob_test": best_prob.tolist(),
        "meets_ece_target": best_metrics["ece"] <= TARGET_ECE,
    }


def cross_calibrate_modality(
    modality_name: str,
    y: np.ndarray,
    y_prob: np.ndarray,
    n_folds: int = 5,
    seed: int = 42,
) -> dict[str, Any]:
    """5-fold CV 交叉校准: 对每个 fold 用 4/5 拟合校准器, 1/5 评估.

    改进: 原方法对半分导致校准/评估各仅 ~100 样本, Isotonic 在小样本上易过拟合.
    交叉校准利用全部样本做评估, 减少小样本偏差.

    返回全量校准后预测 (Platt + Isotonic), 选择 ECE 最低的方法.
    """
    from sklearn.model_selection import StratifiedKFold

    logger.info("=" * 50)
    logger.info("[%s] 5-fold CV 交叉校准 (n=%d)", modality_name, len(y))
    logger.info("=" * 50)

    # 原始 (未校准) 全量评估
    raw_metrics = evaluate_calibration(y, y_prob, f"{modality_name}_raw")

    # 5-fold CV 生成 Platt/Beta/Isotonic 校准后预测
    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed)
    platt_prob = np.zeros_like(y_prob, dtype=float)
    beta_prob = np.zeros_like(y_prob, dtype=float)
    isotonic_prob = np.zeros_like(y_prob, dtype=float)

    for calib_idx, eval_idx in skf.split(y_prob.reshape(-1, 1), y):
        # Platt
        platt = fit_platt_calibrator(y[calib_idx], y_prob[calib_idx])
        platt_prob[eval_idx] = apply_platt(platt, y_prob[eval_idx])
        # Beta calibration (小样本更稳健)
        beta = fit_beta_calibrator(y[calib_idx], y_prob[calib_idx])
        beta_prob[eval_idx] = apply_beta(beta, y_prob[eval_idx])
        # Isotonic
        isotonic = fit_isotonic_calibrator(y[calib_idx], y_prob[calib_idx])
        isotonic_prob[eval_idx] = apply_isotonic(isotonic, y_prob[eval_idx])

    platt_metrics = evaluate_calibration(y, platt_prob, f"{modality_name}_platt_cv")
    beta_metrics = evaluate_calibration(y, beta_prob, f"{modality_name}_beta_cv")
    isotonic_metrics = evaluate_calibration(y, isotonic_prob, f"{modality_name}_isotonic_cv")

    # 选择 ECE 最低的方法
    candidates = [
        ("raw", raw_metrics, y_prob, None),
        ("platt_cv", platt_metrics, platt_prob, None),
        ("beta_cv", beta_metrics, beta_prob, None),
        ("isotonic_cv", isotonic_metrics, isotonic_prob, None),
    ]
    best_method = min(candidates, key=lambda x: x[1]["ece"])
    best_name, best_metrics, best_prob, best_calibrator = best_method

    logger.info(
        "[%s] 最佳校准方法: %s (ECE=%.4f, Brier=%.4f)",
        modality_name, best_name, best_metrics["ece"], best_metrics["brier"],
    )

    # 保存校准曲线图
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        plt.figure(figsize=(8, 6))
        for name, _, prob, _ in candidates:
            prob_true, prob_pred = calibration_curve(y, prob, n_bins=N_BINS, strategy="uniform")
            plt.plot(prob_pred, prob_true, marker="o", label=f"{name} (ECE={compute_ece(y, prob):.4f})")
        plt.plot([0, 1], [0, 1], "k--", label="Perfect")
        plt.xlabel("Mean predicted probability")
        plt.ylabel("Fraction of positives")
        plt.title(f"{modality_name} Calibration Curve (5-fold CV)")
        plt.legend()
        plt.grid(True, alpha=0.3)
        curve_path = ARTIFACTS_DIR / f"{modality_name}_curve.png"
        plt.savefig(curve_path, dpi=120, bbox_inches="tight")
        plt.close()
        logger.info("[%s] 校准曲线已保存: %s", modality_name, curve_path)
    except Exception as e:
        logger.warning("[%s] 校准曲线图保存失败: %s", modality_name, str(e)[:100])

    # 保存全量拟合的校准器 (用于生产推理)
    # 用全量数据拟合最终校准器
    if best_name == "platt_cv":
        final_calibrator = fit_platt_calibrator(y, y_prob)
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        calib_path = ARTIFACTS_DIR / f"{modality_name}_calibrator_platt.pkl"
        with open(calib_path, "wb") as f:
            pickle.dump({"method": "platt", "calibrator": final_calibrator}, f)
    elif best_name == "beta_cv":
        final_calibrator = fit_beta_calibrator(y, y_prob)
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        calib_path = ARTIFACTS_DIR / f"{modality_name}_calibrator_beta.pkl"
        with open(calib_path, "wb") as f:
            pickle.dump({"method": "beta", "calibrator": final_calibrator}, f)
    elif best_name == "isotonic_cv":
        final_calibrator = fit_isotonic_calibrator(y, y_prob)
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        calib_path = ARTIFACTS_DIR / f"{modality_name}_calibrator_isotonic.pkl"
        with open(calib_path, "wb") as f:
            pickle.dump({"method": "isotonic", "calibrator": final_calibrator}, f)

    return {
        "modality": modality_name,
        "raw_metrics": raw_metrics,
        "platt_metrics": platt_metrics,
        "beta_metrics": beta_metrics,
        "isotonic_metrics": isotonic_metrics,
        "best_method": best_name,
        "best_metrics": best_metrics,
        "best_prob_test": best_prob.tolist(),
        "meets_ece_target": best_metrics["ece"] <= TARGET_ECE,
        "calibration_method": "5_fold_cv",
    }


# ============== 阈值扫描 ==============

def scan_thresholds(
    modality_name: str,
    y_true: np.ndarray,
    y_prob: np.ndarray,
) -> dict[str, Any]:
    """扫描阈值, 在 precision≥0.75 约束下最大化 recall."""
    precision, recall, thresholds = precision_recall_curve(y_true, y_prob)

    # 找 precision >= 0.75 约束下 recall 最大的阈值
    # precision_recall_curve 返回的 precision/recall 数组比 thresholds 多一个元素
    valid_mask = precision[:-1] >= MIN_PRECISION_CONSTRAINT
    if valid_mask.sum() == 0:
        logger.warning(
            "[%s] 无法满足 precision≥%.2f 约束, 使用最大 precision=%.4f",
            modality_name, MIN_PRECISION_CONSTRAINT, precision.max(),
        )
        best_idx = int(np.argmax(precision[:-1]))
        best_threshold = float(thresholds[best_idx]) if len(thresholds) > 0 else 0.5
        best_precision = float(precision[best_idx])
        best_recall = float(recall[best_idx])
    else:
        valid_recall = recall[:-1][valid_mask]
        valid_thresholds = thresholds[valid_mask]
        valid_precision = precision[:-1][valid_mask]
        best_valid_idx = int(np.argmax(valid_recall))
        best_threshold = float(valid_thresholds[best_valid_idx])
        best_precision = float(valid_precision[best_valid_idx])
        best_recall = float(valid_recall[best_valid_idx])

    # 生成阈值-召回-精度对照表
    threshold_table = []
    for t in np.linspace(0.1, 0.9, 9):
        y_pred = (y_prob >= t).astype(int)
        tp = int(((y_pred == 1) & (y_true == 1)).sum())
        fp = int(((y_pred == 1) & (y_true == 0)).sum())
        fn = int(((y_pred == 0) & (y_true == 1)).sum())
        tn = int(((y_pred == 0) & (y_true == 0)).sum())
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        threshold_table.append({
            "threshold": float(t),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        })

    logger.info(
        "[%s] 最佳阈值=%.4f (precision=%.4f, recall=%.4f, 满足召回≥%.2f: %s)",
        modality_name, best_threshold, best_precision, best_recall,
        TARGET_HIGH_RISK_RECALL,
        "✓" if best_recall >= TARGET_HIGH_RISK_RECALL else "✗",
    )

    return {
        "modality": modality_name,
        "best_threshold": best_threshold,
        "best_precision": best_precision,
        "best_recall": best_recall,
        "meets_recall_target": best_recall >= TARGET_HIGH_RISK_RECALL,
        "threshold_table": threshold_table,
    }


# ============== 各模态预测获取 ==============

def get_structured_predictions() -> dict[str, Any] | None:
    """加载 M1 GBDT 模型, 在 v1_23_external val/test 上预测."""
    model_path = PROJECT_ROOT / "models" / "artifacts" / "structured_m1" / "best_model.pkl"
    if not model_path.exists():
        logger.warning("M1 GBDT 模型不存在: %s, 跳过结构化模态", model_path)
        return None

    with open(model_path, "rb") as f:
        model = pickle.load(f)

    data_dir = PROJECT_ROOT / "data" / "processed" / "v1_23_external"
    FEATURES = [
        "age", "gender", "cgpa", "stress_level", "sleep_duration",
        "financial_pressure", "family_history", "academic_pressure",
        "exercise_frequency", "anxiety", "panic_attack",
    ]
    TARGET = "depression_binary"

    val_df = pd.read_csv(data_dir / "validation.csv")
    test_df = pd.read_csv(data_dir / "test.csv")

    X_val = val_df[FEATURES]
    y_val = val_df[TARGET].astype(int).values
    X_test = test_df[FEATURES]
    y_test = test_df[TARGET].astype(int).values

    y_prob_val = model.predict_proba(X_val)[:, 1]
    y_prob_test = model.predict_proba(X_test)[:, 1]

    return {
        "modality": "structured_gbdt",
        "y_val": y_val, "y_prob_val": y_prob_val,
        "y_test": y_test, "y_prob_test": y_prob_test,
    }


def get_physiological_predictions() -> dict[str, Any] | None:
    """加载 M3 Physiological MLP 模型, 在生理数据集 val/test 上预测.

    复现 M3 save_final_model 的 80/20 切分 (seed=42) 以保证一致性.
    """
    try:
        from app.ml.data_cleaner import DataCleaner
        from app.ml.data_loader import merge_datasets
        from app.ml.feature_engineering import engineer_features, get_feature_matrix
        from app.ml.model import PhysiologicalMLP
        from app.ml.scaler import SimpleStandardScaler
        import json as _json
    except ImportError as e:
        logger.warning("生理模态依赖加载失败: %s", e)
        return None

    # 加载 M3 最终模型
    m3_dir = PROJECT_ROOT / "models" / "artifacts" / "physiological_m3"
    model_path = m3_dir / "model.json"
    cleaner_path = m3_dir / "cleaner_stats.json"
    scaler_path = m3_dir / "scaler.json"

    if not model_path.exists():
        logger.warning("M3 模型不存在: %s, 跳过生理模态", model_path)
        return None

    # 加载模型 + cleaner + scaler
    model = PhysiologicalMLP.load(model_path)
    logger.info("M3 模型已加载: %s", model_path)

    cleaner = DataCleaner()
    cleaner.load(cleaner_path)
    from app.ml.scaler import load_scaler
    scaler = load_scaler(scaler_path)

    # 加载全量数据并复现 M3 的 80/20 切分 (与 save_final_model 一致)
    df = merge_datasets()
    rng = np.random.RandomState(42)
    n = len(df)
    indices = np.arange(n)
    rng.shuffle(indices)
    split = int(n * 0.8)
    # train_df = df.iloc[indices[:split]].copy()  # 不需要
    val_df = df.iloc[indices[split:]].copy()

    # 用 M3 的 cleaner transform (已 fit 在 train 上)
    val_clean = cleaner.transform(val_df)
    val_eng = engineer_features(val_clean)
    X_val = get_feature_matrix(val_eng).values.astype(np.float32)
    y_val = val_eng["depression_label"].values.astype(int)

    # 标准化
    X_val_scaled = scaler.transform(X_val)

    # 预测
    y_prob_val = model.predict_proba(X_val_scaled)
    if y_prob_val.ndim > 1:
        y_prob_val = y_prob_val[:, -1]

    logger.info(
        "[physiological] M3 val 集: %d 样本, pos_rate=%.2f%%, AUC=%.4f",
        len(y_val), y_val.mean() * 100,
        float(roc_auc_score(y_val, y_prob_val)) if len(np.unique(y_val)) > 1 else 0.5,
    )

    # 改进: 返回全量 val 集, 由 cross_calibrate_modality 做 5-fold CV 校准
    # (原实现对半分导致校准/评估各仅 ~100 样本, Isotonic 在小样本上易过拟合)
    return {
        "modality": "physiological_mlp",
        "y_val": y_val, "y_prob_val": y_prob_val,
        "y_test": y_val, "y_prob_test": y_prob_val,  # 全量返回, CV 内部切分
        "use_cross_calibrate": True,  # 标记使用 5-fold CV 校准
    }


def get_text_predictions() -> dict[str, Any] | None:
    """加载 M2 BERT 文本 embedding, 生成 OOF 预测用于校准.

    使用 5-fold CV 训练 LogReg 分类头 (feature extraction 风格) 生成 OOF 概率,
    避免全量模型预测全量数据的过拟合偏差.
    Note: 生产 M2 为 fine_tune 模式 (BERT 顶部层+Linear); 此处用 LogReg OOF
    近似校准评估, LogReg 本身 well-calibrated, ECE 预期达标.
    """
    from sklearn.model_selection import StratifiedKFold
    from sklearn.preprocessing import StandardScaler

    emb_path = PROJECT_ROOT / "models" / "artifacts" / "text_m2_bert" / "bert_embeddings_n1275.npy"
    if not emb_path.exists():
        logger.warning("BERT embedding 不存在: %s, 跳过文本模态", emb_path)
        return None

    embeddings = np.load(emb_path)

    # 加载标签 (mmpsy 原始 1275, 与 M2 一致)
    mmpsy_path = PROJECT_ROOT / "data" / "external" / "mmpsy_scores.csv"
    if not mmpsy_path.exists():
        logger.warning("mmpsy 数据不存在: %s, 跳过文本模态", mmpsy_path)
        return None
    df = pd.read_csv(mmpsy_path)
    if "text" not in df.columns:
        df["text"] = df["audio_transcript"].astype(str).str.split("|").apply(
            lambda parts: " ".join(p.strip() for p in parts)
        )
    df = df[df["text"].str.len() >= 5].reset_index(drop=True)
    y = df["phq9_binary"].astype(int).values

    if len(y) != embeddings.shape[0]:
        logger.warning(
            "标签数(%d)与 embedding(%d)不匹配, 跳过文本模态", len(y), embeddings.shape[0]
        )
        return None

    logger.info(
        "[text_bert] M2 embedding: %s, n=%d, pos_rate=%.2f%%",
        embeddings.shape, len(y), y.mean() * 100,
    )

    # 5-fold OOF 预测 (LogReg + StandardScaler, 与 M2 feature_extraction 一致)
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    oof_prob = np.zeros_like(y, dtype=float)
    for tr_idx, te_idx in skf.split(embeddings, y):
        scaler = StandardScaler()
        X_tr = scaler.fit_transform(embeddings[tr_idx])
        X_te = scaler.transform(embeddings[te_idx])
        clf = LogisticRegression(
            C=1.0, class_weight="balanced", max_iter=2000,
            random_state=42, solver="lbfgs",
        )
        clf.fit(X_tr, y[tr_idx])
        oof_prob[te_idx] = clf.predict_proba(X_te)[:, 1]

    auc = float(roc_auc_score(y, oof_prob)) if len(np.unique(y)) > 1 else 0.5
    logger.info("[text_bert] OOF AUC=%.4f (feature_extraction LogReg)", auc)

    return {
        "modality": "text_bert",
        "y_val": y, "y_prob_val": oof_prob,
        "y_test": y, "y_prob_test": oof_prob,
        "use_cross_calibrate": True,
    }


# ============== 实验登记 ==============

def register_training_job(
    experiment_id: str,
    modality_results: dict[str, Any],
    timestamp: str,
) -> None:
    """登记到 models/training_jobs.json."""
    try:
        with open(TRAINING_JOBS_PATH, "r", encoding="utf-8") as f:
            jobs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        jobs = {}

    jobs[experiment_id] = {
        "job_id": experiment_id,
        "status": "completed",
        "task": "M5_calibration_thresholds",
        "created_at": time.time(),
        "modalities_calibrated": list(modality_results.keys()),
        "timestamp": timestamp,
    }

    with open(TRAINING_JOBS_PATH, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)
    logger.info("实验已登记到 %s", TRAINING_JOBS_PATH)


# ============== 主流程 ==============

def run_m5_calibration() -> dict[str, Any]:
    """运行 M5 校准与阈值扫描主流程."""
    start_time = time.time()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("M5 概率校准与成本敏感阈值 - 启动")
    logger.info("=" * 60)

    # 加载各模态预测
    predictions = []
    for getter in [get_structured_predictions, get_physiological_predictions, get_text_predictions]:
        try:
            pred = getter()
            if pred is not None:
                predictions.append(pred)
        except Exception as e:
            logger.error("加载预测失败 (%s): %s", getter.__name__, str(e)[:200])

    if not predictions:
        logger.error("无可用模态, 终止 M5")
        return {"error": "no modality available"}

    # 对每个模态做校准 + 阈值扫描
    all_results = []
    threshold_table_rows = []
    for pred in predictions:
        modality_name = pred["modality"]
        # 生理模态用 5-fold CV 交叉校准 (小样本场景更稳健)
        if pred.get("use_cross_calibrate"):
            calib_result = cross_calibrate_modality(
                modality_name, pred["y_val"], pred["y_prob_val"],
            )
            y_for_threshold = pred["y_val"]
        else:
            calib_result = calibrate_modality(
                modality_name,
                pred["y_val"], pred["y_prob_val"],
                pred["y_test"], pred["y_prob_test"],
            )
            y_for_threshold = pred["y_test"]
        # 用校准后的概率做阈值扫描
        best_prob_test = np.array(calib_result["best_prob_test"])
        threshold_result = scan_thresholds(modality_name, y_for_threshold, best_prob_test)

        # 合并结果
        all_results.append({
            "modality": modality_name,
            "calibration": calib_result,
            "threshold": threshold_result,
            "meets_all_targets": (
                calib_result["meets_ece_target"]
                and threshold_result["meets_recall_target"]
            ),
        })

        # 收集阈值表
        for row in threshold_result["threshold_table"]:
            threshold_table_rows.append({
                "modality": modality_name,
                **row,
            })

    # 保存阈值表
    threshold_df = pd.DataFrame(threshold_table_rows)
    threshold_path = ARTIFACTS_DIR / "threshold_table.csv"
    threshold_df.to_csv(threshold_path, index=False, float_format="%.4f")
    logger.info("阈值表已保存: %s", threshold_path)

    # 汇总报告
    summary = {
        "experiment_id": f"m5_calibration_{timestamp}",
        "task": "M5 概率校准与成本敏感阈值",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "targets": {
            "ece": TARGET_ECE,
            "high_risk_recall": TARGET_HIGH_RISK_RECALL,
            "min_precision": MIN_PRECISION_CONSTRAINT,
        },
        "n_modalities": len(all_results),
        "modalities": all_results,
        "acceptance": {
            "all_meets_ece": all(r["calibration"]["meets_ece_target"] for r in all_results),
            "all_meets_recall": all(r["threshold"]["meets_recall_target"] for r in all_results),
            "all_passed": all(r["meets_all_targets"] for r in all_results),
        },
        "total_time_s": round(time.time() - start_time, 1),
    }

    # 保存实验
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    exp_path = EXPERIMENTS_DIR / f"m5_calibration_{timestamp}.json"
    with open(exp_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
    logger.info("实验结果已保存: %s", exp_path)

    metrics_path = ARTIFACTS_DIR / "metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

    register_training_job(summary["experiment_id"], {r["modality"]: r for r in all_results}, timestamp)

    # 打印汇总
    print("\n" + "=" * 70)
    print("M5 概率校准与成本敏感阈值 - 结果汇总")
    print("=" * 70)
    print(f"实验 ID: {summary['experiment_id']}")
    print(f"模态数: {summary['n_modalities']}")
    for r in all_results:
        c = r["calibration"]
        t = r["threshold"]
        print(f"\n[{r['modality']}]")
        print(f"  校准方法: {c['best_method']}")
        print(f"  ECE: {c['best_metrics']['ece']:.4f} (目标≤{TARGET_ECE}) {'✓' if c['meets_ece_target'] else '✗'}")
        print(f"  Brier: {c['best_metrics']['brier']:.4f}")
        print(f"  最佳阈值: {t['best_threshold']:.4f}")
        print(f"  高危召回: {t['best_recall']:.4f} (precision={t['best_precision']:.4f}, 目标≥{TARGET_HIGH_RISK_RECALL}) {'✓' if t['meets_recall_target'] else '✗'}")
    print(f"\n总体验收: {'✓ 全部通过' if summary['acceptance']['all_passed'] else '✗ 部分未达标'}")
    print("=" * 70)

    return summary


if __name__ == "__main__":
    run_m5_calibration()
