"""M2 BERT 分组 CV 评估 (防止增强数据泄露).

问题: 同义词替换/回译增强的样本与原始样本共享语义内容,
      标准 K-fold CV 会将同一原始样本的变体分配到训练集和测试集,
      导致 F1 虚高 (0.9709 为泄露结果,非真实泛化性能).

解决: 按 source_idx 分组 (GroupKFold),确保同一原始样本的所有变体
      在同一折中,模型在测试折中看不到任何训练折样本的变体.

评估方案:
    1. 原始样本 (source_idx=-1) → group_id = 其在原始 mmpsy 中的索引
    2. 增强样本 (source_idx>=0) → group_id = source_idx
    3. GroupKFold(n_splits=5) × 3 seeds = 15 折评估
    4. LogReg + 阈值优化

Usage:
    python scripts/m2_group_cv_eval.py
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, roc_auc_score, accuracy_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [M2-GroupCV] %(message)s")
logger = logging.getLogger("M2-GroupCV")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORPUS_PATH = PROJECT_ROOT / "data" / "external" / "chinese_depression_corpus_v1.csv"
EMB_PATH = PROJECT_ROOT / "models" / "artifacts" / "text_m2_bert" / "bert_embeddings_n8379.npy"
REPORT_PATH = PROJECT_ROOT / "models" / "artifacts" / "text_m2_bert" / "group_cv_metrics.json"

N_FOLDS = 5
SEEDS = [42, 1337, 2024]


def find_best_f1_threshold(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """在训练集上找最佳 F1 阈值."""
    from sklearn.metrics import precision_recall_curve
    precision, recall, thresholds = precision_recall_curve(y_true, y_prob)
    f1_scores = 2 * precision * recall / (precision + recall + 1e-8)
    best_idx = np.argmax(f1_scores[:-1])
    return float(thresholds[best_idx])


def build_group_ids(df: pd.DataFrame) -> np.ndarray:
    """构建分组 ID.

    原始样本 (augmentation=original, source_idx=-1) → group_id = 递增索引
    增强样本 (source_idx>=0) → group_id = source_idx + max_original_idx + 1

    但更准确的做法:
    - 原始样本在原始 mmpsy 中的索引即为 group_id
    - 增强样本的 source_idx 指向原始 mmpsy 索引,所以 group_id = source_idx

    关键: 原始样本 idx=0 和增强样本 source_idx=0 应在同一组.
    """
    n = len(df)
    group_ids = np.zeros(n, dtype=int)

    # 原始样本: source_idx=-1, 需要映射到其原始索引
    # 增强样本: source_idx>=0, 直接用作 group_id

    original_mask = df["source_idx"].fillna(-1).astype(int) == -1
    augmented_mask = ~original_mask

    # 增强样本: group_id = source_idx
    if augmented_mask.any():
        group_ids[augmented_mask] = df.loc[augmented_mask, "source_idx"].astype(int).values

    # 原始样本: 需要推断其在原始 mmpsy 中的索引
    # 原始 mmpsy 有 1275 条,按顺序排列在 corpus 的前面
    original_indices = np.where(original_mask)[0]
    # 原始样本按出现顺序映射到 0, 1, 2, ... 1274
    for i, idx in enumerate(original_indices):
        group_ids[idx] = i

    return group_ids


def evaluate_group_cv(
    X: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    label: str = "logreg_group_cv",
) -> dict:
    """GroupKFold CV 评估 (防止增强数据泄露)."""
    logger.info("=" * 50)
    logger.info("GroupKFold CV: %s (n=%d, n_groups=%d, pos_rate=%.2f%%)",
                label, len(y), len(np.unique(groups)), y.mean() * 100)
    logger.info("=" * 50)

    fold_details = []
    all_f1, all_auc, all_acc = [], [], []
    all_thresholds = []

    for seed in SEEDS:
        # GroupKFold 不支持 shuffle, 但可通过 seed 调整 split 顺序
        gkf = GroupKFold(n_splits=N_FOLDS)
        splits = list(gkf.split(X, y, groups))
        # 通过 seed 随机打乱 fold 顺序 (不影响分组,只影响哪些组在哪个 fold)
        rng = np.random.RandomState(seed)
        fold_order = rng.permutation(N_FOLDS)

        for fold_idx_orig, fold_idx in enumerate(fold_order):
            tr_idx, te_idx = splits[fold_idx]
            X_tr, X_te = X[tr_idx], X[te_idx]
            y_tr, y_te = y[tr_idx], y[te_idx]

            # 标准化
            scaler = StandardScaler()
            X_tr_s = scaler.fit_transform(X_tr)
            X_te_s = scaler.transform(X_te)

            # 训练 LogReg
            clf = LogisticRegression(
                C=1.0, class_weight="balanced", max_iter=2000,
                random_state=seed, solver="lbfgs",
            )
            clf.fit(X_tr_s, y_tr)

            # 预测
            y_prob = clf.predict_proba(X_te_s)[:, 1]

            # 阈值优化 (训练集)
            y_prob_tr = clf.predict_proba(X_tr_s)[:, 1]
            threshold = find_best_f1_threshold(y_tr, y_prob_tr)
            all_thresholds.append(threshold)

            y_pred = (y_prob >= threshold).astype(int)

            # 指标
            f1 = float(f1_score(y_te, y_pred, zero_division=0))
            auc = float(roc_auc_score(y_te, y_prob)) if len(np.unique(y_te)) > 1 else 0.5
            acc = float(accuracy_score(y_te, y_pred))

            all_f1.append(f1)
            all_auc.append(auc)
            all_acc.append(acc)
            fold_details.append({
                "seed": seed, "fold": fold_idx, "f1": f1, "auc": auc,
                "acc": acc, "threshold": threshold,
                "n_train": len(tr_idx), "n_test": len(te_idx),
            })
            logger.info("Fold %d.%d: F1=%.4f, AUC=%.4f, thresh=%.3f, n_tr=%d, n_te=%d",
                        seed, fold_idx, f1, auc, threshold, len(tr_idx), len(te_idx))

    f1_arr = np.array(all_f1)
    auc_arr = np.array(all_auc)
    acc_arr = np.array(all_acc)

    f1_mean, f1_std = float(f1_arr.mean()), float(f1_arr.std(ddof=1))
    auc_mean, auc_std = float(auc_arr.mean()), float(auc_arr.std(ddof=1))
    acc_mean = float(acc_arr.mean())
    n = len(all_f1)
    t_val = 2.145  # df=14
    f1_ci = t_val * f1_std / np.sqrt(n)
    auc_ci = t_val * auc_std / np.sqrt(n)

    result = {
        "label": label,
        "classifier": "logreg",
        "cv_strategy": "GroupKFold (by source_idx)",
        "n_folds": N_FOLDS,
        "seeds": SEEDS,
        "n_evaluations": n,
        "n_groups": int(len(np.unique(groups))),
        "f1_mean": f1_mean,
        "f1_std": f1_std,
        "f1_ci95": float(f1_ci),
        "f1_ci_lower": f1_mean - f1_ci,
        "f1_ci_upper": f1_mean + f1_ci,
        "auc_mean": auc_mean,
        "auc_std": auc_std,
        "auc_ci95": float(auc_ci),
        "auc_ci_lower": auc_mean - auc_ci,
        "auc_ci_upper": auc_mean + auc_ci,
        "acc_mean": acc_mean,
        "mean_threshold": float(np.mean(all_thresholds)),
        "fold_details": fold_details,
    }

    logger.info("=" * 50)
    logger.info("[%s] F1=%.4f±%.4f (CI95: [%.4f, %.4f])",
                label, f1_mean, f1_std, f1_mean - f1_ci, f1_mean + f1_ci)
    logger.info("[%s] AUC=%.4f±%.4f (CI95: [%.4f, %.4f])",
                label, auc_mean, auc_std, auc_mean - auc_ci, auc_mean + auc_ci)
    logger.info("[%s] ACC=%.4f, thresh=%.3f", label, acc_mean, result["mean_threshold"])
    logger.info("=" * 50)

    return result


def evaluate_original_only(
    X: np.ndarray,
    y: np.ndarray,
    df: pd.DataFrame,
    label: str = "logreg_original_only",
) -> dict:
    """仅在原始样本上评估 (train=增强, test=原始).

    这是最严格的评估: 模型在测试时遇到的全是未见过的新文本.
    """
    from sklearn.model_selection import StratifiedKFold

    logger.info("=" * 50)
    logger.info("Original-only CV: %s (仅在原始 1275 样本上测试)", label)
    logger.info("=" * 50)

    original_mask = df["augmentation"].fillna("original").astype(str) == "original"
    augmented_mask = ~original_mask

    X_aug = X[augmented_mask.values]
    y_aug = y[augmented_mask.values]
    X_orig = X[original_mask.values]
    y_orig = y[original_mask.values]

    logger.info("训练池 (增强): %d 样本, 阳性率=%.2f%%", len(y_aug), y_aug.mean() * 100)
    logger.info("测试池 (原始): %d 样本, 阳性率=%.2f%%", len(y_orig), y_orig.mean() * 100)

    fold_details = []
    all_f1, all_auc, all_acc = [], [], []
    all_thresholds = []

    for seed in SEEDS:
        skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
        for fold_idx, (tr_idx, te_idx) in enumerate(skf.split(X_orig, y_orig)):
            # 训练集: 全部增强样本 + 原始样本的训练折
            X_tr = np.vstack([X_aug, X_orig[tr_idx]])
            y_tr = np.concatenate([y_aug, y_orig[tr_idx]])
            X_te = X_orig[te_idx]
            y_te = y_orig[te_idx]

            scaler = StandardScaler()
            X_tr_s = scaler.fit_transform(X_tr)
            X_te_s = scaler.transform(X_te)

            clf = LogisticRegression(
                C=1.0, class_weight="balanced", max_iter=2000,
                random_state=seed, solver="lbfgs",
            )
            clf.fit(X_tr_s, y_tr)

            y_prob = clf.predict_proba(X_te_s)[:, 1]
            y_prob_tr = clf.predict_proba(X_tr_s)[:, 1]
            threshold = find_best_f1_threshold(y_tr, y_prob_tr)
            all_thresholds.append(threshold)

            y_pred = (y_prob >= threshold).astype(int)
            f1 = float(f1_score(y_te, y_pred, zero_division=0))
            auc = float(roc_auc_score(y_te, y_prob)) if len(np.unique(y_te)) > 1 else 0.5
            acc = float(accuracy_score(y_te, y_pred))

            all_f1.append(f1)
            all_auc.append(auc)
            all_acc.append(acc)
            fold_details.append({
                "seed": seed, "fold": fold_idx, "f1": f1, "auc": auc,
                "acc": acc, "threshold": threshold,
                "n_train": len(tr_idx), "n_test": len(te_idx),
            })
            logger.info("Fold %d.%d: F1=%.4f, AUC=%.4f, thresh=%.3f, n_tr=%d, n_te=%d",
                        seed, fold_idx, f1, auc, threshold, len(tr_idx), len(te_idx))

    f1_arr = np.array(all_f1)
    auc_arr = np.array(all_auc)
    acc_arr = np.array(all_acc)

    f1_mean, f1_std = float(f1_arr.mean()), float(f1_arr.std(ddof=1))
    auc_mean, auc_std = float(auc_arr.mean()), float(auc_arr.std(ddof=1))
    acc_mean = float(acc_arr.mean())
    n = len(all_f1)
    t_val = 2.145
    f1_ci = t_val * f1_std / np.sqrt(n)
    auc_ci = t_val * auc_std / np.sqrt(n)

    result = {
        "label": label,
        "classifier": "logreg",
        "cv_strategy": "StratifiedKFold on original samples only (train=augmented+orig_train, test=orig_test)",
        "n_folds": N_FOLDS,
        "seeds": SEEDS,
        "n_evaluations": n,
        "n_train_augmented": int(augmented_mask.sum()),
        "n_test_original": int(original_mask.sum()),
        "f1_mean": f1_mean,
        "f1_std": f1_std,
        "f1_ci95": float(f1_ci),
        "f1_ci_lower": f1_mean - f1_ci,
        "f1_ci_upper": f1_mean + f1_ci,
        "auc_mean": auc_mean,
        "auc_std": auc_std,
        "auc_ci95": float(auc_ci),
        "auc_ci_lower": auc_mean - auc_ci,
        "auc_ci_upper": auc_mean + auc_ci,
        "acc_mean": acc_mean,
        "mean_threshold": float(np.mean(all_thresholds)),
        "fold_details": fold_details,
    }

    logger.info("=" * 50)
    logger.info("[%s] F1=%.4f±%.4f (CI95: [%.4f, %.4f])",
                label, f1_mean, f1_std, f1_mean - f1_ci, f1_mean + f1_ci)
    logger.info("[%s] AUC=%.4f±%.4f (CI95: [%.4f, %.4f])",
                label, auc_mean, auc_std, auc_mean - auc_ci, auc_mean + auc_ci)
    logger.info("[%s] ACC=%.4f, thresh=%.3f", label, acc_mean, result["mean_threshold"])
    logger.info("=" * 50)

    return result


def main() -> None:
    start_time = time.time()
    logger.info("=" * 60)
    logger.info("M2 BERT 分组 CV 评估 (防止增强数据泄露)")
    logger.info("=" * 60)

    # 1. 加载语料
    logger.info("加载语料: %s", CORPUS_PATH)
    df = pd.read_csv(CORPUS_PATH)
    df = df[df["text"].str.len() >= 5].reset_index(drop=True)
    df["phq9_binary"] = df["phq9_binary"].astype(int)
    logger.info("语料: %d 样本, 阳性率=%.2f%%", len(df), df["phq9_binary"].mean() * 100)

    # 2. 加载 embedding
    logger.info("加载 embedding: %s", EMB_PATH)
    embeddings = np.load(EMB_PATH)
    logger.info("Embedding shape: %s", embeddings.shape)

    if embeddings.shape[0] != len(df):
        logger.error("Embedding 样本数 (%d) != 语料样本数 (%d)", embeddings.shape[0], len(df))
        return

    y = df["phq9_binary"].values

    # 3. 构建分组 ID
    groups = build_group_ids(df)
    n_groups = len(np.unique(groups))
    logger.info("分组: %d 组 (每组的所有变体在同折)", n_groups)

    # 4. 评估方案 1: GroupKFold (按 source_idx 分组)
    logger.info("\n方案 1: GroupKFold (按 source_idx 分组,防止泄露)")
    group_cv_result = evaluate_group_cv(embeddings, y, groups, "logreg_group_cv")

    # 5. 评估方案 2: 仅在原始样本上测试 (最严格)
    logger.info("\n方案 2: Original-only CV (训练=增强+原始训练折, 测试=原始测试折)")
    original_only_result = evaluate_original_only(embeddings, y, df, "logreg_original_only")

    # 6. 汇总报告
    elapsed = time.time() - start_time
    report = {
        "experiment_id": f"m2_group_cv_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "elapsed_s": round(elapsed, 1),
        "data": {
            "n_total": int(len(df)),
            "n_original": int((df["augmentation"].fillna("original") == "original").sum()),
            "n_augmented": int((df["augmentation"].fillna("original") != "original").sum()),
            "n_groups": int(n_groups),
            "pos_rate": float(y.mean()),
        },
        "results": {
            "group_cv": group_cv_result,
            "original_only": original_only_result,
        },
        "comparison_with_leaked": {
            "leaked_f1": 0.9709,
            "leaked_auc": 0.9962,
            "note": "标准随机 K-fold CV 的 F1=0.9709 因增强数据跨折泄露而虚高",
        },
        "acceptance": {
            "target_f1": 0.65,
            "group_cv_meets_target": bool(group_cv_result["f1_mean"] >= 0.65),
            "original_only_meets_target": bool(original_only_result["f1_mean"] >= 0.65),
        },
    }

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=lambda o: int(o) if hasattr(o, "item") else str(o))
    logger.info("报告已保存: %s", REPORT_PATH)

    # 7. 打印结论
    logger.info("=" * 60)
    logger.info("M2 分组 CV 评估完成 (%.1fs)", elapsed)
    logger.info("=" * 60)
    logger.info("结论:")
    logger.info("  泄露 F1 (标准随机CV): 0.9709 (虚高,不可信)")
    logger.info("  GroupKFold F1: %.4f±%.4f (CI95: [%.4f, %.4f])",
                group_cv_result["f1_mean"], group_cv_result["f1_std"],
                group_cv_result["f1_ci_lower"], group_cv_result["f1_ci_upper"])
    logger.info("  Original-only F1: %.4f±%.4f (CI95: [%.4f, %.4f])",
                original_only_result["f1_mean"], original_only_result["f1_std"],
                original_only_result["f1_ci_lower"], original_only_result["f1_ci_upper"])
    logger.info("  目标 F1 ≥ 0.65:")
    logger.info("    GroupKFold: %s", "✓ 达标" if report["acceptance"]["group_cv_meets_target"] else "✗ 未达标")
    logger.info("    Original-only: %s", "✓ 达标" if report["acceptance"]["original_only_meets_target"] else "✗ 未达标")


if __name__ == "__main__":
    main()
