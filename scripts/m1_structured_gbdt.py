"""M1 结构化模型升级: GBDT 替换/对照 v1.23 LogReg.

目标: F1 0.8955 → ≥0.90, AUC 0.9174 → ≥0.94
方法: XGBoost + LightGBM + 单调性约束 + SHAP 解释 + 5-fold × 3 seeds CV
数据: data/processed/v1_23_external/ (19916 train / 4318 val / 4318 test, 12 features)
验收:
  - 5-fold CV AUC ≥ 0.94
  - 测试集与 CV 差 < 2pt
  - SHAP 特征方向与临床先验一致

Usage:
    python scripts/m1_structured_gbdt.py
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
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold

import xgboost as xgb
import lightgbm as lgb

logging.basicConfig(level=logging.INFO, format="%(asctime)s [M1] %(message)s")
logger = logging.getLogger("M1")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "processed" / "v1_23_external"
EXPERIMENTS_DIR = PROJECT_ROOT / "models" / "experiments"
TRAINING_JOBS_PATH = PROJECT_ROOT / "models" / "training_jobs.json"
ARTIFACTS_DIR = PROJECT_ROOT / "models" / "artifacts" / "structured_m1"

# M1 验收阈值
TARGET_F1 = 0.90
TARGET_AUC = 0.94
MAX_CV_TEST_GAP = 0.02  # 测试集与 CV 差 < 2pt

# 95% CI t-value for df=14 (5-fold × 3 seeds - 1 = 14)
T_VALUE_95 = 2.145
N_SEEDS = 3
N_FOLDS = 5
SEEDS = [42, 1337, 2024]  # 固定 seed=42 起步, 加 2 个不同 seed 测稳定性

# 跳过耗时的随机搜索 (30 分钟), 直接使用预计算的最佳参数
# 之前一轮随机搜索 (n_iter=30) 已得到以下结果:
#   XGBoost:    best_cv_auc=0.9126
#   LightGBM:   best_cv_auc=0.9123
# 两者均低于 v1.23 LR 基线 0.9174, 但保留作为对照
SKIP_SEARCH = True
PRECOMPUTED_BEST_PARAMS = {
    "xgboost": {
        "max_depth": 3,
        "learning_rate": 0.03,
        "n_estimators": 400,
        "subsample": 1.0,
        "colsample_bytree": 0.8,
        "min_child_weight": 5,
        "gamma": 0.0,
        "reg_alpha": 1.0,
        "reg_lambda": 0.1,
    },
    "lightgbm": {
        "max_depth": 4,
        "learning_rate": 0.01,
        "n_estimators": 800,
        "subsample": 0.9,
        "colsample_bytree": 0.7,
        "min_child_samples": 50,
        "reg_alpha": 1.0,
        "reg_lambda": 0.1,
    },
}

# 特征顺序（去除常量列 social_support）— 与 v1.23 features 对齐
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

# 单调性约束（与 FEATURES 顺序对齐, 1=递增, -1=递减, 0=无约束）
# 临床先验:
#   stress_level +1, financial_pressure +1, family_history +1,
#   academic_pressure +1, anxiety +1, panic_attack +1,
#   exercise_frequency -1
#   sleep_duration/cgpa/age/gender 关系非线性或弱, 设 0
MONOTONE_CONSTRAINTS = [0, 0, 0, 1, 0, 1, 1, 1, -1, 1, 1]

# 临床先验方向（用于 SHAP 验证）
CLINICAL_PRIOR = {
    "stress_level": "+",       # 压力↑ 抑郁↑
    "financial_pressure": "+", # 经济压力↑ 抑郁↑
    "family_history": "+",     # 家族史↑ 抑郁↑
    "academic_pressure": "+",  # 学业压力↑ 抑郁↑
    "anxiety": "+",            # 焦虑↑ 抑郁↑
    "panic_attack": "+",       # 惊恐↑ 抑郁↑
    "exercise_frequency": "-", # 运动↑ 抑郁↓
}


# ============== 数据加载 ==============

def load_v1_23_data() -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    """加载 v1.23 已切分数据."""
    train_df = pd.read_csv(DATA_DIR / "train.csv")
    val_df = pd.read_csv(DATA_DIR / "validation.csv")
    test_df = pd.read_csv(DATA_DIR / "test.csv")

    # 去除常量列 social_support (metadata 已声明)
    drop_cols = [c for c in ["social_support"] if c in train_df.columns]

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
    logger.info("已去除常量列: %s", drop_cols if drop_cols else "(无)")

    return X_train, y_train, X_val, y_val, X_test, y_test


# ============== 模型搜索空间 ==============

def build_xgb_param_space() -> dict[str, Any]:
    """XGBoost 超参搜索空间 (含单调性约束)."""
    return {
        "max_depth": [3, 4, 5, 6, 7, 8],
        "learning_rate": [0.01, 0.03, 0.05, 0.1, 0.15],
        "n_estimators": [200, 400, 600, 800, 1000],
        "subsample": [0.7, 0.8, 0.9, 1.0],
        "colsample_bytree": [0.7, 0.8, 0.9, 1.0],
        "min_child_weight": [1, 3, 5, 10],
        "gamma": [0.0, 0.1, 0.3, 0.5],
        "reg_alpha": [0.0, 0.01, 0.1, 1.0],
        "reg_lambda": [0.1, 1.0, 5.0, 10.0],
    }


def build_lgb_param_space() -> dict[str, Any]:
    """LightGBM 超参搜索空间 (含单调性约束)."""
    return {
        "max_depth": [-1, 4, 6, 8, 10],
        "learning_rate": [0.01, 0.03, 0.05, 0.1, 0.15],
        "n_estimators": [200, 400, 600, 800, 1000],
        "subsample": [0.7, 0.8, 0.9, 1.0],
        "colsample_bytree": [0.7, 0.8, 0.9, 1.0],
        "min_child_samples": [5, 10, 20, 50],
        "reg_alpha": [0.0, 0.01, 0.1, 1.0],
        "reg_lambda": [0.0, 0.1, 1.0, 5.0],
    }


def build_xgb_model(params: dict[str, Any], use_monotone: bool = True) -> xgb.XGBClassifier:
    """构造 XGBoost 分类器.

    params 可包含 random_state (由 evaluate_config 注入), 默认 42.
    use_monotone=True 时附加单调性约束 (临床先验), False 用于对照.
    """
    # 分离 random_state (避免 **params 与显式参数冲突)
    params = dict(params)  # 避免修改传入字典 (允许复用)
    rs = params.pop("random_state", 42)
    kwargs: dict[str, Any] = dict(
        **params,
        objective="binary:logistic",
        eval_metric="auc",
        tree_method="hist",
        random_state=rs,
        n_jobs=-1,
        verbosity=0,
    )
    if use_monotone:
        kwargs["monotone_constraints"] = tuple(MONOTONE_CONSTRAINTS)
    return xgb.XGBClassifier(**kwargs)


def build_lgb_model(params: dict[str, Any], use_monotone: bool = True) -> lgb.LGBMClassifier:
    """构造 LightGBM 分类器.

    params 可包含 random_state (由 evaluate_config 注入), 默认 42.
    use_monotone=True 时附加单调性约束 (临床先验), False 用于对照.
    """
    params = dict(params)
    rs = params.pop("random_state", 42)
    kwargs: dict[str, Any] = dict(
        **params,
        objective="binary",
        metric="auc",
        random_state=rs,
        n_jobs=-1,
        verbosity=-1,
    )
    if use_monotone:
        kwargs["monotone_constraints"] = MONOTONE_CONSTRAINTS
    return lgb.LGBMClassifier(**kwargs)


def build_xgb_model_no_monotone(params: dict[str, Any]) -> xgb.XGBClassifier:
    """XGBoost 无单调性约束 (对照实验)."""
    return build_xgb_model(params, use_monotone=False)


# ============== 超参搜索 (随机 + CV) ==============

def random_search_cv(
    model_name: str,
    build_fn: Any,
    param_space: dict[str, Any],
    X: pd.DataFrame,
    y: pd.Series,
    n_iter: int = 30,
) -> dict[str, Any]:
    """随机超参搜索 + 5-fold CV (固定 split, 单 seed=42).

    返回最优配置及 CV 指标. 仅用于粗选, 精确评估在 evaluate_config 中用 3 seeds.
    """
    rng = np.random.RandomState(42)
    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=42)

    best_auc = -1.0
    best_params: dict[str, Any] = {}
    all_trials: list[dict[str, Any]] = []

    # 采样 n_iter 组参数组合
    param_list = []
    for _ in range(n_iter):
        params = {k: rng.choice(v) for k, v in param_space.items()}
        # 类型转换 (numpy int64/float64 -> python native)
        for k, v in params.items():
            if isinstance(v, (np.integer,)):
                params[k] = int(v)
            elif isinstance(v, (np.floating,)):
                params[k] = float(v)
        param_list.append(params)

    logger.info("[%s] 随机搜索: %d 组参数, 每组 5-fold CV", model_name, n_iter)

    for i, params in enumerate(param_list):
        fold_aucs = []
        fold_f1s = []
        for tr_idx, va_idx in skf.split(X, y):
            X_tr, X_va = X.iloc[tr_idx], X.iloc[va_idx]
            y_tr, y_va = y.iloc[tr_idx], y.iloc[va_idx]

            try:
                model = build_fn(params)
                model.fit(X_tr, y_tr)
                y_prob = model.predict_proba(X_va)[:, 1]
                y_pred = (y_prob >= 0.5).astype(int)
                fold_aucs.append(float(roc_auc_score(y_va, y_prob)))
                fold_f1s.append(float(f1_score(y_va, y_pred)))
            except Exception as e:
                logger.warning("  trial %d failed: %s", i + 1, str(e)[:100])
                fold_aucs.append(0.5)
                fold_f1s.append(0.0)

        auc_mean = float(np.mean(fold_aucs))
        f1_mean = float(np.mean(fold_f1s))
        all_trials.append({
            "params": params,
            "cv_auc_mean": auc_mean,
            "cv_f1_mean": f1_mean,
        })

        if auc_mean > best_auc:
            best_auc = auc_mean
            best_params = params

        if (i + 1) % 5 == 0:
            logger.info(
                "  [%s] %d/%d trials done. best_auc=%.4f",
                model_name, i + 1, n_iter, best_auc,
            )

    logger.info(
        "[%s] 随机搜索完成. best_auc=%.4f, best_params=%s",
        model_name, best_auc, best_params,
    )

    return {
        "model_name": model_name,
        "best_params": best_params,
        "best_cv_auc": best_auc,
        "n_trials": n_iter,
        "all_trials": all_trials,
    }


# ============== 精确评估: 5-fold × 3 seeds ==============

def evaluate_config(
    model_name: str,
    build_fn: Any,
    params: dict[str, Any],
    X: pd.DataFrame,
    y: pd.Series,
) -> dict[str, Any]:
    """对指定参数做 5-fold × 3 seeds = 15 次评估, 返回均值±std 与 95% CI."""
    fold_details = []
    all_f1 = []
    all_auc = []

    for seed in SEEDS:
        skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
        for fold_idx, (tr_idx, va_idx) in enumerate(skf.split(X, y)):
            X_tr, X_va = X.iloc[tr_idx], X.iloc[va_idx]
            y_tr, y_va = y.iloc[tr_idx], y.iloc[va_idx]

            # 调整随机种子
            adjusted_params = dict(params)
            adjusted_params["random_state"] = seed
            model = build_fn(adjusted_params)
            model.fit(X_tr, y_tr)

            y_prob = model.predict_proba(X_va)[:, 1]
            y_pred = (y_prob >= 0.5).astype(int)

            f1 = float(f1_score(y_va, y_pred))
            auc = float(roc_auc_score(y_va, y_prob))
            prec = float(precision_score(y_va, y_pred, zero_division=0))
            rec = float(recall_score(y_va, y_pred, zero_division=0))

            all_f1.append(f1)
            all_auc.append(auc)
            fold_details.append({
                "seed": seed,
                "fold": fold_idx,
                "f1": f1,
                "auc": auc,
                "precision": prec,
                "recall": rec,
            })

    f1_arr = np.array(all_f1)
    auc_arr = np.array(all_auc)
    f1_mean, f1_std = float(f1_arr.mean()), float(f1_arr.std(ddof=1))
    auc_mean, auc_std = float(auc_arr.mean()), float(auc_arr.std(ddof=1))
    f1_ci = T_VALUE_95 * f1_std / np.sqrt(len(all_f1))
    auc_ci = T_VALUE_95 * auc_std / np.sqrt(len(all_auc))

    return {
        "model_name": model_name,
        "params": params,
        "f1_mean": f1_mean,
        "f1_std": f1_std,
        "f1_ci95": f1_ci,
        "f1_ci_lower": f1_mean - f1_ci,
        "f1_ci_upper": f1_mean + f1_ci,
        "auc_mean": auc_mean,
        "auc_std": auc_std,
        "auc_ci95": auc_ci,
        "auc_ci_lower": auc_mean - auc_ci,
        "auc_ci_upper": auc_mean + auc_ci,
        "n_evaluations": len(all_f1),
        "fold_details": fold_details,
        "meets_f1_target": f1_mean >= TARGET_F1,
        "meets_auc_target": auc_mean >= TARGET_AUC,
    }


# ============== 测试集评估 + SHAP 解释 ==============

def evaluate_on_test(
    model_name: str,
    build_fn: Any,
    params: dict[str, Any],
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> dict[str, Any]:
    """在完整训练集上训练, 测试集上评估, 并计算 SHAP 值."""
    logger.info("[%s] 在完整训练集上训练最终模型 (n=%d)...", model_name, len(X_train))
    model = build_fn(params)
    model.fit(X_train, y_train)

    y_prob = model.predict_proba(X_test)[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)

    test_metrics = {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred, zero_division=0)),
        "recall": float(recall_score(y_test, y_pred, zero_division=0)),
        "f1": float(f1_score(y_test, y_pred)),
        "roc_auc": float(roc_auc_score(y_test, y_prob)),
    }

    # SHAP 解释 (TreeExplainer)
    shap_results = compute_shap(model, model_name, X_test)

    return {
        "model_name": model_name,
        "test_metrics": test_metrics,
        "shap_results": shap_results,
        "model_object": model,
    }


def compute_shap(model: Any, model_name: str, X_test: pd.DataFrame) -> dict[str, Any]:
    """用 TreeExplainer 计算 SHAP 值并验证特征方向."""
    try:
        import shap
        # TreeExplainer 对 XGBoost/LightGBM 都原生支持
        explainer = shap.TreeExplainer(model)
        # 采样避免内存爆炸 (max 1000 样本)
        X_sample = X_test.iloc[:min(1000, len(X_test))]
        shap_values = explainer.shap_values(X_sample)

        # LightGBM 二分类可能返回 list[2], 取正类
        if isinstance(shap_values, list) and len(shap_values) == 2:
            shap_values_arr = np.array(shap_values[1])
        else:
            shap_values_arr = np.array(shap_values)

        # mean |SHAP| 作为特征重要性
        mean_abs_shap = np.abs(shap_values_arr).mean(axis=0)
        feature_importance = [
            {"feature": FEATURES[i], "mean_abs_shap": float(mean_abs_shap[i])}
            for i in range(len(FEATURES))
        ]
        feature_importance.sort(key=lambda x: x["mean_abs_shap"], reverse=True)

        # 验证临床先验方向: 用 SHAP 与特征值的 Spearman 相关方向
        # (正值=特征↑导致 SHAP↑→ 预测↑, 负值反之)
        direction_check = []
        for i, feat in enumerate(FEATURES):
            if feat not in CLINICAL_PRIOR:
                continue
            feat_vals = X_sample[feat].values
            shap_col = shap_values_arr[:, i]
            # 用线性相关符号 (近似单调性方向)
            if feat_vals.std() > 0 and shap_col.std() > 0:
                corr = float(np.corrcoef(feat_vals, shap_col)[0, 1])
            else:
                corr = 0.0
            expected_sign = CLINICAL_PRIOR[feat]
            actual_sign = "+" if corr > 0.05 else ("-" if corr < -0.05 else "0")
            consistent = (expected_sign == actual_sign) or actual_sign == "0"
            direction_check.append({
                "feature": feat,
                "expected": expected_sign,
                "actual": actual_sign,
                "correlation": corr,
                "consistent": consistent,
            })

        n_consistent = sum(1 for d in direction_check if d["consistent"])
        n_total = len(direction_check)
        all_consistent = n_consistent == n_total

        # 保存 SHAP summary 图
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
            plt.figure(figsize=(10, 6))
            shap.summary_plot(
                shap_values_arr, X_sample,
                feature_names=FEATURES, show=False, max_display=len(FEATURES),
            )
            plt.tight_layout()
            shap_plot_path = ARTIFACTS_DIR / f"shap_summary_{model_name}.png"
            plt.savefig(shap_plot_path, dpi=120, bbox_inches="tight")
            plt.close()
            logger.info("[%s] SHAP summary 图已保存: %s", model_name, shap_plot_path)
        except Exception as e:
            logger.warning("[%s] SHAP 图保存失败: %s", model_name, str(e)[:100])

        return {
            "feature_importance": feature_importance,
            "direction_check": direction_check,
            "n_consistent": n_consistent,
            "n_total": n_total,
            "all_clinical_consistent": all_consistent,
            "n_samples_explained": len(X_sample),
        }
    except Exception as e:
        logger.warning("[%s] SHAP 计算失败: %s", model_name, str(e)[:200])
        return {"error": str(e)}


# ============== 实验登记 ==============

def register_training_job(
    experiment_id: str,
    best_result: dict[str, Any],
    best_model_name: str,
    timestamp: str,
) -> None:
    """将实验登记到 models/training_jobs.json."""
    try:
        with open(TRAINING_JOBS_PATH, "r", encoding="utf-8") as f:
            jobs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        jobs = {}

    jobs[experiment_id] = {
        "job_id": experiment_id,
        "status": "completed",
        "task": "M1_structured_gbdt",
        "created_at": time.time(),
        "best_model": best_model_name,
        "best_params": best_result["params"],
        "f1_mean": best_result["f1_mean"],
        "auc_mean": best_result["auc_mean"],
        "meets_targets": best_result["meets_f1_target"] and best_result["meets_auc_target"],
        "timestamp": timestamp,
    }

    with open(TRAINING_JOBS_PATH, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)
    logger.info("实验已登记到 %s", TRAINING_JOBS_PATH)


# ============== 主流程 ==============

def run_m1_optimization() -> dict[str, Any]:
    """运行 M1 GBDT 优化流程."""
    start_time = time.time()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    X_train, y_train, X_val, y_val, X_test, y_test = load_v1_23_data()

    # 合并 train + val 作为 CV 训练集 (test 集保持独立)
    X_cv = pd.concat([X_train, X_val], ignore_index=True)
    y_cv = pd.concat([y_train, y_val], ignore_index=True)
    logger.info("CV 数据集: %d 样本 (train+val 合并)", len(X_cv))

    # === Step 1: 随机超参搜索 (粗选) ===
    logger.info("=" * 60)
    logger.info("Step 1: 随机超参搜索 (n_iter=30, 5-fold CV, seed=42)")
    logger.info("=" * 60)

    if SKIP_SEARCH:
        logger.info("[SKIP_SEARCH=True] 跳过随机搜索, 使用预计算最佳参数:")
        logger.info("  XGBoost:    %s", PRECOMPUTED_BEST_PARAMS["xgboost"])
        logger.info("  LightGBM:   %s", PRECOMPUTED_BEST_PARAMS["lightgbm"])
        xgb_search = {
            "model_name": "xgboost",
            "best_params": PRECOMPUTED_BEST_PARAMS["xgboost"],
            "best_cv_auc": 0.9126,  # 之前搜索结果
            "n_trials": 30,
            "all_trials": [],
        }
        lgb_search = {
            "model_name": "lightgbm",
            "best_params": PRECOMPUTED_BEST_PARAMS["lightgbm"],
            "best_cv_auc": 0.9123,
            "n_trials": 30,
            "all_trials": [],
        }
    else:
        xgb_search = random_search_cv(
            "xgboost", build_xgb_model, build_xgb_param_space(),
            X_cv, y_cv, n_iter=30,
        )
        lgb_search = random_search_cv(
            "lightgbm", build_lgb_model, build_lgb_param_space(),
            X_cv, y_cv, n_iter=30,
        )

    # === Step 2: 精确评估 (5-fold × 3 seeds) ===
    logger.info("=" * 60)
    logger.info("Step 2: 精确评估 (5-fold × 3 seeds = 15 次评估)")
    logger.info("=" * 60)

    xgb_eval = evaluate_config(
        "xgboost", build_xgb_model, xgb_search["best_params"], X_cv, y_cv,
    )
    logger.info(
        "[XGBoost+monotone] F1=%.4f±%.4f (CI: %.4f~%.4f) AUC=%.4f±%.4f (CI: %.4f~%.4f)  [%.1fs]",
        xgb_eval["f1_mean"], xgb_eval["f1_std"],
        xgb_eval["f1_ci_lower"], xgb_eval["f1_ci_upper"],
        xgb_eval["auc_mean"], xgb_eval["auc_std"],
        xgb_eval["auc_ci_lower"], xgb_eval["auc_ci_upper"],
        time.time() - start_time,
    )

    lgb_eval = evaluate_config(
        "lightgbm", build_lgb_model, lgb_search["best_params"], X_cv, y_cv,
    )
    logger.info(
        "[LightGBM+monotone] F1=%.4f±%.4f (CI: %.4f~%.4f) AUC=%.4f±%.4f (CI: %.4f~%.4f)",
        lgb_eval["f1_mean"], lgb_eval["f1_std"],
        lgb_eval["f1_ci_lower"], lgb_eval["f1_ci_upper"],
        lgb_eval["auc_mean"], lgb_eval["auc_std"],
        lgb_eval["auc_ci_lower"], lgb_eval["auc_ci_upper"],
    )

    # 对照: XGBoost 无单调性约束 (诊断约束是否过度限制模型)
    xgb_no_monotone_eval = evaluate_config(
        "xgboost_no_monotone", build_xgb_model_no_monotone,
        xgb_search["best_params"], X_cv, y_cv,
    )
    logger.info(
        "[XGBoost no-monotone] F1=%.4f±%.4f AUC=%.4f±%.4f  [%.1fs]",
        xgb_no_monotone_eval["f1_mean"], xgb_no_monotone_eval["f1_std"],
        xgb_no_monotone_eval["auc_mean"], xgb_no_monotone_eval["auc_std"],
        time.time() - start_time,
    )

    # === Step 3: 选择最佳模型 ===
    candidates = [xgb_eval, lgb_eval, xgb_no_monotone_eval]
    candidates.sort(key=lambda r: r["auc_mean"], reverse=True)
    best = candidates[0]
    best_model_name = best["model_name"]
    # 选择对应的 build 函数
    if best_model_name == "xgboost":
        best_build_fn = build_xgb_model
    elif best_model_name == "lightgbm":
        best_build_fn = build_lgb_model
    else:  # xgboost_no_monotone
        best_build_fn = build_xgb_model_no_monotone
    logger.info("最佳模型: %s (AUC=%.4f, F1=%.4f)", best_model_name, best["auc_mean"], best["f1_mean"])

    # === Step 4: 测试集评估 + SHAP ===
    logger.info("=" * 60)
    logger.info("Step 4: 测试集评估 + SHAP 解释")
    logger.info("=" * 60)

    test_result = evaluate_on_test(
        best_model_name, best_build_fn, best["params"],
        X_cv, y_cv, X_test, y_test,
    )
    test_metrics = test_result["test_metrics"]
    shap_results = test_result["shap_results"]

    cv_test_auc_gap = abs(best["auc_mean"] - test_metrics["roc_auc"])
    logger.info(
        "测试集: F1=%.4f, AUC=%.4f | CV-Test AUC gap=%.4f (阈值<%.2f)",
        test_metrics["f1"], test_metrics["roc_auc"],
        cv_test_auc_gap, MAX_CV_TEST_GAP,
    )
    logger.info(
        "SHAP 临床一致性: %d/%d (%s)",
        shap_results.get("n_consistent", 0),
        shap_results.get("n_total", 0),
        "✓" if shap_results.get("all_clinical_consistent") else "✗",
    )

    # === Step 5: 保存模型和实验结果 ===
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    # 保存模型
    model_path = ARTIFACTS_DIR / "best_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(test_result["model_object"], f)

    # 保存指标
    metrics_payload = {
        "experiment_id": f"m1_structured_gbdt_{timestamp}",
        "task": "M1 结构化模型升级 (GBDT)",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "baseline": {
            "v1_23_lr_f1": 0.8955,
            "v1_23_lr_auc": 0.9174,
        },
        "targets": {"f1": TARGET_F1, "auc": TARGET_AUC, "max_cv_test_gap": MAX_CV_TEST_GAP},
        "features": FEATURES,
        "monotone_constraints": MONOTONE_CONSTRAINTS,
        "clinical_prior": CLINICAL_PRIOR,
        "best_model": best_model_name,
        "best_params": best["params"],
        "cv_metrics": {
            "f1_mean": best["f1_mean"],
            "f1_std": best["f1_std"],
            "f1_ci95": f"{best['f1_mean']:.4f} ± {best['f1_ci95']:.4f}",
            "auc_mean": best["auc_mean"],
            "auc_std": best["auc_std"],
            "auc_ci95": f"{best['auc_mean']:.4f} ± {best['auc_ci95']:.4f}",
            "n_evaluations": best["n_evaluations"],
        },
        "test_metrics": test_metrics,
        "cv_test_auc_gap": cv_test_auc_gap,
        "shap_results": shap_results,
        "all_candidates_summary": [
            {
                "model_name": r["model_name"],
                "params": r["params"],
                "f1_mean": r["f1_mean"],
                "auc_mean": r["auc_mean"],
            }
            for r in candidates
        ],
        "acceptance": {
            "meets_f1_target": best["meets_f1_target"],
            "meets_auc_target": best["meets_auc_target"],
            "meets_cv_test_gap": cv_test_auc_gap < MAX_CV_TEST_GAP,
            "shap_clinical_consistent": shap_results.get("all_clinical_consistent", False),
            "all_passed": (
                best["meets_f1_target"]
                and best["meets_auc_target"]
                and cv_test_auc_gap < MAX_CV_TEST_GAP
                and shap_results.get("all_clinical_consistent", False)
            ),
        },
    }

    metrics_path = ARTIFACTS_DIR / "metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics_payload, f, ensure_ascii=False, indent=2, default=str)
    logger.info("指标已保存: %s", metrics_path)

    # 保存特征顺序
    features_path = ARTIFACTS_DIR / "feature_names.json"
    with open(features_path, "w", encoding="utf-8") as f:
        json.dump(FEATURES, f, ensure_ascii=False, indent=2)

    # 实验登记
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    exp_path = EXPERIMENTS_DIR / f"m1_structured_gbdt_{timestamp}.json"
    with open(exp_path, "w", encoding="utf-8") as f:
        json.dump(metrics_payload, f, ensure_ascii=False, indent=2, default=str)
    logger.info("实验结果已保存: %s", exp_path)

    register_training_job(
        experiment_id=metrics_payload["experiment_id"],
        best_result=best,
        best_model_name=best_model_name,
        timestamp=timestamp,
    )

    # 打印汇总
    total_time = time.time() - start_time
    print("\n" + "=" * 70)
    print("M1 结构化模型升级 (GBDT) - 优化结果汇总")
    print("=" * 70)
    print(f"实验 ID: {metrics_payload['experiment_id']}")
    print(f"总耗时: {total_time:.0f}s")
    print(f"\n最佳模型: {best_model_name}")
    print(f"最佳参数: {best['params']}")
    print(f"\nCV 指标 (5-fold × 3 seeds = 15 评估):")
    print(f"  F1:  {best['f1_mean']:.4f} ± {best['f1_std']:.4f} (95% CI: {best['f1_ci_lower']:.4f} ~ {best['f1_ci_upper']:.4f})")
    print(f"  AUC: {best['auc_mean']:.4f} ± {best['auc_std']:.4f} (95% CI: {best['auc_ci_lower']:.4f} ~ {best['auc_ci_upper']:.4f})")
    print(f"\n测试集指标:")
    print(f"  F1:  {test_metrics['f1']:.4f}")
    print(f"  AUC: {test_metrics['roc_auc']:.4f}")
    print(f"  CV-Test AUC gap: {cv_test_auc_gap:.4f} (阈值 < {MAX_CV_TEST_GAP})")
    print(f"\n基线对比:")
    print(f"  v1.23 LR:  F1=0.8955, AUC=0.9174")
    print(f"  M1 GBDT:   F1={test_metrics['f1']:.4f}, AUC={test_metrics['roc_auc']:.4f}")
    print(f"\nSHAP 临床先验一致性: {shap_results.get('n_consistent', 0)}/{shap_results.get('n_total', 0)}")
    print(f"\n验收:")
    print(f"  CV F1 ≥ 0.90:           {'✓' if best['meets_f1_target'] else '✗'} ({best['f1_mean']:.4f})")
    print(f"  CV AUC ≥ 0.94:          {'✓' if best['meets_auc_target'] else '✗'} ({best['auc_mean']:.4f})")
    print(f"  CV-Test AUC gap < 2pt:  {'✓' if cv_test_auc_gap < MAX_CV_TEST_GAP else '✗'} ({cv_test_auc_gap:.4f})")
    print(f"  SHAP 临床方向一致:       {'✓' if shap_results.get('all_clinical_consistent') else '✗'}")
    print("=" * 70)

    return metrics_payload


if __name__ == "__main__":
    run_m1_optimization()
