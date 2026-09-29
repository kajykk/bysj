"""T1 统一 GroupKFold 评估工具 (全模态通用).

背景:
    项目原评估协议不统一: 文本模态已有 GroupKFold(by source_idx), 但结构化/生理/融合
    模态用 train_test_split 或随机 KFold, 存在数据泄露风险且无法跨模态对比.
    
    本模块实现统一评估协议:
    1. GroupKFold by user_id (全模态统一分组键, 防止用户级泄露)
    2. StratifiedKFold (随机CV, 作为对比基线, 量化泄露程度)
    3. 5 折 × 3 种子 = 15 次评估, 报告 mean ± std + CI95

设计原则:
    - 不修改生产代码 (backend/app/), 仅作为评估脚本
    - 支持任意分类器 (LogReg, CatBoost, MLP, Stacking)
    - 输出 group_cv_metrics.json, 与文本模态格式对齐

Usage:
    from t1_group_cv_tool import evaluate_group_cv, evaluate_stratified_cv
    result = evaluate_group_cv(X, y, groups=user_ids, classifier=clf, label="tabular_group_cv")
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_recall_curve, roc_auc_score
from sklearn.model_selection import GroupKFold, StratifiedKFold

logger = logging.getLogger("T1-GroupCV")

# 统一评估参数 (与 m2_group_cv_eval.py 对齐)
N_FOLDS = 5
SEEDS = [42, 1337, 2024]
# t 值 (df=14, 95% CI 双尾)
T_VAL_14 = 2.145


@dataclass
class CVResult:
    """CV 评估结果."""

    label: str
    cv_strategy: str
    classifier: str
    n_folds: int
    seeds: list[int]
    n_evaluations: int
    n_groups: int | None
    f1_mean: float
    f1_std: float
    f1_ci95: float
    f1_ci_lower: float
    f1_ci_upper: float
    auc_mean: float
    auc_std: float
    auc_ci95: float
    auc_ci_lower: float
    auc_ci_upper: float
    acc_mean: float
    mean_threshold: float
    fold_details: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "cv_strategy": self.cv_strategy,
            "classifier": self.classifier,
            "n_folds": self.n_folds,
            "seeds": self.seeds,
            "n_evaluations": self.n_evaluations,
            "n_groups": self.n_groups,
            "f1_mean": self.f1_mean,
            "f1_std": self.f1_std,
            "f1_ci95": self.f1_ci95,
            "f1_ci_lower": self.f1_ci_lower,
            "f1_ci_upper": self.f1_ci_upper,
            "auc_mean": self.auc_mean,
            "auc_std": self.auc_std,
            "auc_ci95": self.auc_ci95,
            "auc_ci_lower": self.auc_ci_lower,
            "auc_ci_upper": self.auc_ci_upper,
            "acc_mean": self.acc_mean,
            "mean_threshold": self.mean_threshold,
            "fold_details": self.fold_details,
        }


def find_best_f1_threshold(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """在训练集上找最佳 F1 阈值."""
    precision, recall, thresholds = precision_recall_curve(y_true, y_prob)
    f1_scores = 2 * precision * recall / (precision + recall + 1e-8)
    if len(thresholds) == 0:
        return 0.5
    best_idx = np.argmax(f1_scores[:-1])
    return float(thresholds[best_idx])


def _aggregate_metrics(
    all_f1: list[float],
    all_auc: list[float],
    all_acc: list[float],
    all_thresholds: list[float],
) -> tuple[float, float, float, float, float, float, float, float, float, float]:
    """聚合指标, 计算 mean/std/CI95."""
    f1_arr = np.array(all_f1)
    auc_arr = np.array(all_auc)
    acc_arr = np.array(all_acc)
    n = len(all_f1)

    f1_mean, f1_std = float(f1_arr.mean()), float(f1_arr.std(ddof=1)) if n > 1 else 0.0
    auc_mean, auc_std = float(auc_arr.mean()), float(auc_arr.std(ddof=1)) if n > 1 else 0.0
    acc_mean = float(acc_arr.mean())

    f1_ci = T_VAL_14 * f1_std / np.sqrt(n) if n > 1 else 0.0
    auc_ci = T_VAL_14 * auc_std / np.sqrt(n) if n > 1 else 0.0

    return (
        f1_mean, f1_std, f1_ci, f1_mean - f1_ci, f1_mean + f1_ci,
        auc_mean, auc_std, auc_ci, auc_mean - auc_ci, auc_mean + auc_ci,
        acc_mean, float(np.mean(all_thresholds)),
    )


def _train_and_eval_fold(
    clf_factory: Callable,
    X_tr: np.ndarray,
    y_tr: np.ndarray,
    X_te: np.ndarray,
    y_te: np.ndarray,
    seed: int,
    fold_idx: int,
    scale: bool = True,
) -> tuple[float, float, float, float]:
    """训练并评估单折, 返回 (f1, auc, acc, threshold)."""
    if scale:
        from sklearn.preprocessing import StandardScaler

        scaler = StandardScaler()
        X_tr = scaler.fit_transform(X_tr)
        X_te = scaler.transform(X_te)

    clf = clf_factory(seed)
    clf.fit(X_tr, y_tr)

    y_prob = clf.predict_proba(X_te)[:, 1]
    y_prob_tr = clf.predict_proba(X_tr)[:, 1]
    threshold = find_best_f1_threshold(y_tr, y_prob_tr)

    y_pred = (y_prob >= threshold).astype(int)
    f1 = float(f1_score(y_te, y_pred, zero_division=0))
    auc = float(roc_auc_score(y_te, y_prob)) if len(np.unique(y_te)) > 1 else 0.5
    acc = float(accuracy_score(y_te, y_pred))

    return f1, auc, acc, threshold


def evaluate_group_cv(
    X: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    clf_factory: Callable | None = None,
    label: str = "group_cv",
    scale: bool = True,
) -> CVResult:
    """GroupKFold CV 评估 (按 groups 分组, 防止组间泄露).

    Args:
        X: 特征矩阵 (n_samples, n_features).
        y: 标签 (n_samples,).
        groups: 分组键 (n_samples,), 同一组的样本在同一折.
        clf_factory: 接受 seed 返回分类器的工厂函数. 默认 LogReg.
        label: 评估标签.
        scale: 是否标准化特征.

    Returns:
        CVResult 评估结果.
    """
    if clf_factory is None:
        clf_factory = lambda seed: LogisticRegression(
            C=1.0, class_weight="balanced", max_iter=2000,
            random_state=seed, solver="lbfgs",
        )

    n_groups = len(np.unique(groups))
    logger.info("=" * 50)
    logger.info("GroupKFold CV: %s (n=%d, n_groups=%d, pos_rate=%.2f%%)",
                label, len(y), n_groups, y.mean() * 100)
    logger.info("=" * 50)

    fold_details = []
    all_f1, all_auc, all_acc, all_thresholds = [], [], [], []

    for seed in SEEDS:
        gkf = GroupKFold(n_splits=N_FOLDS)
        splits = list(gkf.split(X, y, groups))
        # GroupKFold 不支持 shuffle, 通过 seed 打乱 fold 顺序
        rng = np.random.RandomState(seed)
        fold_order = rng.permutation(N_FOLDS)

        for fold_idx_orig, fold_idx in enumerate(fold_order):
            tr_idx, te_idx = splits[fold_idx]
            f1, auc, acc, threshold = _train_and_eval_fold(
                clf_factory, X[tr_idx], y[tr_idx], X[te_idx], y[te_idx],
                seed, fold_idx, scale,
            )
            all_f1.append(f1)
            all_auc.append(auc)
            all_acc.append(acc)
            all_thresholds.append(threshold)
            fold_details.append({
                "seed": seed, "fold": int(fold_idx), "f1": f1, "auc": auc,
                "acc": acc, "threshold": threshold,
                "n_train": int(len(tr_idx)), "n_test": int(len(te_idx)),
            })
            logger.info("Fold %d.%d: F1=%.4f, AUC=%.4f, thresh=%.3f, n_tr=%d, n_te=%d",
                        seed, fold_idx, f1, auc, threshold, len(tr_idx), len(te_idx))

    (f1_mean, f1_std, f1_ci, f1_lo, f1_hi,
     auc_mean, auc_std, auc_ci, auc_lo, auc_hi,
     acc_mean, mean_thresh) = _aggregate_metrics(all_f1, all_auc, all_acc, all_thresholds)

    logger.info("[%s] F1=%.4f±%.4f (CI95: [%.4f, %.4f])", label, f1_mean, f1_std, f1_lo, f1_hi)
    logger.info("[%s] AUC=%.4f±%.4f (CI95: [%.4f, %.4f])", label, auc_mean, auc_std, auc_lo, auc_hi)

    return CVResult(
        label=label, cv_strategy=f"GroupKFold (n_folds={N_FOLDS}, by groups)",
        classifier=clf_factory(SEEDS[0]).__class__.__name__,
        n_folds=N_FOLDS, seeds=SEEDS, n_evaluations=len(all_f1),
        n_groups=int(n_groups),
        f1_mean=f1_mean, f1_std=f1_std, f1_ci95=f1_ci, f1_ci_lower=f1_lo, f1_ci_upper=f1_hi,
        auc_mean=auc_mean, auc_std=auc_std, auc_ci95=auc_ci, auc_ci_lower=auc_lo, auc_ci_upper=auc_hi,
        acc_mean=acc_mean, mean_threshold=mean_thresh, fold_details=fold_details,
    )


def evaluate_stratified_cv(
    X: np.ndarray,
    y: np.ndarray,
    clf_factory: Callable | None = None,
    label: str = "stratified_cv",
    scale: bool = True,
) -> CVResult:
    """StratifiedKFold CV 评估 (随机CV, 作为对比基线).

    与 GroupKFold 对比可量化数据泄露程度.

    Args:
        X: 特征矩阵.
        y: 标签.
        clf_factory: 分类器工厂.
        label: 评估标签.
        scale: 是否标准化.

    Returns:
        CVResult 评估结果.
    """
    if clf_factory is None:
        clf_factory = lambda seed: LogisticRegression(
            C=1.0, class_weight="balanced", max_iter=2000,
            random_state=seed, solver="lbfgs",
        )

    logger.info("=" * 50)
    logger.info("StratifiedKFold CV: %s (n=%d, pos_rate=%.2f%%)",
                label, len(y), y.mean() * 100)
    logger.info("=" * 50)

    fold_details = []
    all_f1, all_auc, all_acc, all_thresholds = [], [], [], []

    for seed in SEEDS:
        skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
        for fold_idx, (tr_idx, te_idx) in enumerate(skf.split(X, y)):
            f1, auc, acc, threshold = _train_and_eval_fold(
                clf_factory, X[tr_idx], y[tr_idx], X[te_idx], y[te_idx],
                seed, fold_idx, scale,
            )
            all_f1.append(f1)
            all_auc.append(auc)
            all_acc.append(acc)
            all_thresholds.append(threshold)
            fold_details.append({
                "seed": seed, "fold": fold_idx, "f1": f1, "auc": auc,
                "acc": acc, "threshold": threshold,
                "n_train": int(len(tr_idx)), "n_test": int(len(te_idx)),
            })
            logger.info("Fold %d.%d: F1=%.4f, AUC=%.4f, thresh=%.3f, n_tr=%d, n_te=%d",
                        seed, fold_idx, f1, auc, threshold, len(tr_idx), len(te_idx))

    (f1_mean, f1_std, f1_ci, f1_lo, f1_hi,
     auc_mean, auc_std, auc_ci, auc_lo, auc_hi,
     acc_mean, mean_thresh) = _aggregate_metrics(all_f1, all_auc, all_acc, all_thresholds)

    logger.info("[%s] F1=%.4f±%.4f (CI95: [%.4f, %.4f])", label, f1_mean, f1_std, f1_lo, f1_hi)
    logger.info("[%s] AUC=%.4f±%.4f (CI95: [%.4f, %.4f])", label, auc_mean, auc_std, auc_lo, auc_hi)

    return CVResult(
        label=label, cv_strategy=f"StratifiedKFold (n_folds={N_FOLDS}, shuffled)",
        classifier=clf_factory(SEEDS[0]).__class__.__name__,
        n_folds=N_FOLDS, seeds=SEEDS, n_evaluations=len(all_f1),
        n_groups=None,
        f1_mean=f1_mean, f1_std=f1_std, f1_ci95=f1_ci, f1_ci_lower=f1_lo, f1_ci_upper=f1_hi,
        auc_mean=auc_mean, auc_std=auc_std, auc_ci95=auc_ci, auc_ci_lower=auc_lo, auc_ci_upper=auc_hi,
        acc_mean=acc_mean, mean_threshold=mean_thresh, fold_details=fold_details,
    )


def generate_gap_report(
    group_result: CVResult,
    stratified_result: CVResult,
    modality: str,
) -> dict:
    """生成 GroupKFold vs StratifiedKFold 差距报告.

    量化数据泄露程度: StratifiedKFold 指标 - GroupKFold 指标 = 泄露导致的虚高.

    Args:
        group_result: GroupKFold 评估结果.
        stratified_result: StratifiedKFold 评估结果.
        modality: 模态名 (text/structured/physiological/fusion).

    Returns:
        差距报告 dict.
    """
    f1_gap = stratified_result.f1_mean - group_result.f1_mean
    auc_gap = stratified_result.auc_mean - group_result.auc_mean

    # 泄露判定: gap > 0.10 视为严重泄露
    leakage_level = "none"
    if abs(f1_gap) > 0.10 or abs(auc_gap) > 0.10:
        leakage_level = "severe"
    elif abs(f1_gap) > 0.05 or abs(auc_gap) > 0.05:
        leakage_level = "moderate"
    elif abs(f1_gap) > 0.02 or abs(auc_gap) > 0.02:
        leakage_level = "mild"

    return {
        "modality": modality,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "group_cv": group_result.to_dict(),
        "stratified_cv": stratified_result.to_dict(),
        "gap": {
            "f1_gap": round(f1_gap, 4),
            "auc_gap": round(auc_gap, 4),
            "interpretation": (
                f"StratifiedKFold 比 GroupKFold F1 高 {f1_gap:.4f}, "
                f"AUC 高 {auc_gap:.4f}; "
                + ("虚高来自数据泄露" if f1_gap > 0.02 else "无明显泄露")
            ),
        },
        "leakage_level": leakage_level,
        "acceptance": {
            "target_f1": 0.60,
            "group_cv_meets_target": bool(group_result.f1_mean >= 0.60),
            "stratified_cv_meets_target": bool(stratified_result.f1_mean >= 0.60),
        },
    }
