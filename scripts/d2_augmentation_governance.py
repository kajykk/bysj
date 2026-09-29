"""D2 增强数据质量治理: SimHash 近重复检测 + 单源增强倍数限制.

目标:
    1. SimHash 近重复检测 (汉明距离 < 3 视为近重复)
    2. 单源增强倍数 ≤ 3 (每个原始样本最多保留 3 个增强变体)
    3. 优先保留与原始样本差异大的增强样本 (提高多样性)
    4. 输出清洗后数据集 + 治理报告

预期收益:
    GroupKFold F1 从 0.444 回升至 ≥0.60 (G2 阶段目标 0.55)

Usage:
    python scripts/d2_augmentation_governance.py
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from t1_group_cv_tool import evaluate_group_cv, evaluate_stratified_cv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [D2] %(message)s")
logger = logging.getLogger("D2")

CORPUS_PATH = PROJECT_ROOT / "data" / "external" / "chinese_depression_corpus_v1.csv"
OUTPUT_PATH = PROJECT_ROOT / "data" / "external" / "chinese_depression_corpus_v2_clean.csv"
REPORT_PATH = PROJECT_ROOT / "models" / "artifacts" / "text_m2_bert" / "d2_governance_report.json"

MAX_AUG_PER_SOURCE = 3
SIMHASH_BITS = 64
HAMMING_THRESHOLD = 3


def tokenize_zh(text: str) -> list[str]:
    """中文分词: 字符级 3-gram + 英文单词."""
    if not isinstance(text, str):
        return []
    # 英文单词
    en_tokens = re.findall(r"[a-zA-Z]+", text)
    # 中文字符级 3-gram
    zh_chars = re.findall(r"[\u4e00-\u9fff]", text)
    zh_grams = ["".join(zh_chars[i : i + 3]) for i in range(len(zh_chars) - 2)]
    return en_tokens + zh_grams


def simhash(text: str, bits: int = SIMHASH_BITS) -> int:
    """计算文本的 SimHash 值 (64位)."""
    tokens = tokenize_zh(text)
    if not tokens:
        return 0
    v = [0] * bits
    for token in tokens:
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        for i in range(bits):
            if h & (1 << i):
                v[i] += 1
            else:
                v[i] -= 1
    fingerprint = 0
    for i in range(bits):
        if v[i] > 0:
            fingerprint |= (1 << i)
    return fingerprint


def hamming_distance(a: int, b: int) -> int:
    """计算两个 SimHash 的汉明距离."""
    return bin(a ^ b).count("1")


def is_near_duplicate(a: int, b: int, threshold: int = HAMMING_THRESHOLD) -> bool:
    """判断是否近重复 (汉明距离 < threshold)."""
    return hamming_distance(a, b) < threshold


def governance_augmentation(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """增强数据治理: SimHash 去重 + 单源倍数限制.

    Args:
        df: 原始数据集 (含 source_idx, text 列).

    Returns:
        (清洗后 DataFrame, 治理报告)
    """
    start = time.time()
    logger.info("开始增强数据治理...")
    logger.info("输入: %d 样本 (原始 %d, 增强 %d)",
                len(df), (df["source_idx"] == -1).sum(), (df["source_idx"] >= 0).sum())

    # 1. 计算所有样本的 SimHash
    logger.info("计算 SimHash (64位)...")
    df = df.copy()
    df["simhash"] = df["text"].apply(simhash)

    # 2. 分离原始和增强样本
    orig_df = df[df["source_idx"] == -1].copy()
    aug_df = df[df["source_idx"] >= 0].copy()

    # 3. 按 source_idx 分组, 组内去重 + 限制倍数
    kept_indices = list(orig_df.index)  # 保留所有原始样本
    stats = {
        "total_aug_before": len(aug_df),
        "sources_total": aug_df["source_idx"].nunique(),
        "near_duplicate_removed": 0,
        "excess_removed": 0,
        "kept_per_source": [],
    }

    for source_idx, group in aug_df.groupby("source_idx"):
        # 获取对应的原始样本 SimHash
        orig_match = orig_df[orig_df.index == source_idx] if source_idx < len(orig_df) else None
        orig_hash = orig_match["simhash"].iloc[0] if orig_match is not None and len(orig_match) > 0 else None

        # 组内去重: 与原始样本近重复的剔除
        kept_in_group = []
        for idx, row in group.iterrows():
            # 与原始样本近重复?
            if orig_hash is not None and is_near_duplicate(row["simhash"], orig_hash):
                stats["near_duplicate_removed"] += 1
                continue
            # 与已保留的增强样本近重复?
            is_dup = False
            for kept_idx in kept_in_group:
                if is_near_duplicate(row["simhash"], df.loc[kept_idx, "simhash"]):
                    stats["near_duplicate_removed"] += 1
                    is_dup = True
                    break
            if not is_dup:
                kept_in_group.append(idx)

        # 限制每源最多 MAX_AUG_PER_SOURCE 个
        if len(kept_in_group) > MAX_AUG_PER_SOURCE:
            # 优先保留与原始样本差异大的 (汉明距离大的)
            if orig_hash is not None:
                kept_in_group.sort(
                    key=lambda idx: hamming_distance(df.loc[idx, "simhash"], orig_hash),
                    reverse=True,
                )
            kept_in_group = kept_in_group[:MAX_AUG_PER_SOURCE]
            stats["excess_removed"] += len(group) - len(kept_in_group) - stats["near_duplicate_removed"]

        kept_indices.extend(kept_in_group)
        stats["kept_per_source"].append({"source_idx": int(source_idx), "kept": len(kept_in_group)})

    # 4. 构建清洗后数据集
    clean_df = df.loc[sorted(kept_indices)].copy()
    clean_df = clean_df.drop(columns=["simhash"])

    stats["total_after"] = len(clean_df)
    stats["aug_after"] = (clean_df["source_idx"] >= 0).sum()
    stats["orig_after"] = (clean_df["source_idx"] == -1).sum()
    stats["max_aug_per_source"] = max(stats["kept_per_source"], key=lambda x: x["kept"])["kept"] if stats["kept_per_source"] else 0
    stats["avg_aug_per_source"] = float(np.mean([x["kept"] for x in stats["kept_per_source"]])) if stats["kept_per_source"] else 0
    stats["elapsed_s"] = round(time.time() - start, 1)

    logger.info("治理完成: %d → %d (剔除 %d 近重复, %d 超量)",
                len(df), len(clean_df), stats["near_duplicate_removed"], stats["excess_removed"])
    logger.info("增强倍数: %.1f → %.1f (最大 %d)",
                len(aug_df) / max(aug_df["source_idx"].nunique(), 1),
                stats["avg_aug_per_source"], stats["max_aug_per_source"])

    return clean_df, stats


def evaluate_cleaned_data(clean_df: pd.DataFrame) -> dict:
    """用 GroupKFold 评估清洗后数据集.

    使用简单的 TF-IDF + LogReg 评估, 验证 F1 是否回升.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    logger.info("评估清洗后数据集 (TF-IDF + LogReg, GroupKFold)...")

    # 准备数据
    X_text = clean_df["text"].fillna("").values
    y = clean_df["phq9_binary"].values
    groups = clean_df["source_idx"].values  # 用 source_idx 分组
    # 原始样本 source_idx=-1, 需要映射到唯一组
    # 将 source_idx=-1 映射到不同的组 (每个原始样本独立一组)
    orig_mask = groups == -1
    orig_indices = np.where(orig_mask)[0]
    group_ids = groups.copy().astype(int)
    for i, idx in enumerate(orig_indices):
        group_ids[idx] = 100000 + i  # 原始样本各自独立分组

    # TF-IDF 特征
    logger.info("TF-IDF 向量化...")
    vectorizer = TfidfVectorizer(max_features=5000, ngram_range=(1, 2), min_df=2)
    X = vectorizer.fit_transform(X_text).toarray()
    logger.info("特征矩阵: %s", X.shape)

    # GroupKFold 评估
    clf_factory = lambda seed: LogisticRegression(
        C=1.0, class_weight="balanced", max_iter=2000,
        random_state=seed, solver="lbfgs",
    )

    group_result = evaluate_group_cv(
        X, y, group_ids,
        clf_factory=clf_factory,
        label="text_clean_group_cv",
        scale=False,  # TF-IDF 已归一化
    )

    stratified_result = evaluate_stratified_cv(
        X, y,
        clf_factory=clf_factory,
        label="text_clean_stratified_cv",
        scale=False,
    )

    # 显式导入, 避免作用域问题
    from t1_group_cv_tool import generate_gap_report as _gen_gap
    report = _gen_gap(group_result, stratified_result, "text_clean")
    return report


def main() -> None:
    logger.info("=" * 60)
    logger.info("D2 增强数据质量治理")
    logger.info("=" * 60)

    # 1. 加载原始数据
    if not CORPUS_PATH.exists():
        logger.error("数据集不存在: %s", CORPUS_PATH)
        return
    df = pd.read_csv(CORPUS_PATH)
    logger.info("加载: %s (%d 样本)", CORPUS_PATH, len(df))

    # 2. 治理
    clean_df, governance_stats = governance_augmentation(df)

    # 3. 保存清洗后数据
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    clean_df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8")
    logger.info("清洗后数据已保存: %s", OUTPUT_PATH)

    # 4. 评估
    eval_report = evaluate_cleaned_data(clean_df)

    # 5. 生成报告
    report = {
        "experiment_id": f"d2_governance_{time.strftime('%Y%m%d_%H%M%S')}",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "input_path": str(CORPUS_PATH),
        "output_path": str(OUTPUT_PATH),
        "params": {
            "max_aug_per_source": MAX_AUG_PER_SOURCE,
            "simhash_bits": SIMHASH_BITS,
            "hamming_threshold": HAMMING_THRESHOLD,
        },
        "governance_stats": governance_stats,
        "evaluation": eval_report,
        "conclusion": {
            "f1_before": 0.444,  # m2_group_cv_eval.py 基线
            "f1_after": eval_report["group_cv"]["f1_mean"],
            "f1_improvement": round(eval_report["group_cv"]["f1_mean"] - 0.444, 4),
            "target_f1": 0.55,  # 阶段一目标
            "meets_target": bool(eval_report["group_cv"]["f1_mean"] >= 0.55),
        },
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    logger.info("治理报告已保存: %s", REPORT_PATH)

    # 6. 结论
    logger.info("\n" + "=" * 60)
    logger.info("D2 治理结论:")
    logger.info("  F1: %.4f → %.4f (Δ=%+.4f)",
                0.444, eval_report["group_cv"]["f1_mean"],
                eval_report["group_cv"]["f1_mean"] - 0.444)
    logger.info("  AUC: %.4f → %.4f",
                0.724, eval_report["group_cv"]["auc_mean"])
    logger.info("  目标 F1≥0.55: %s",
                "✓ 达标" if report["conclusion"]["meets_target"] else "✗ 未达标")
    logger.info("  样本: %d → %d (剔除 %.1f%%)",
                len(df), len(clean_df), (1 - len(clean_df) / len(df)) * 100)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
