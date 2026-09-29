"""D2 文本数据清洗与标签审计.

目标:
    1. 核查 Reddit 数据集(depression_dataset_reddit_cleaned.csv)的样本数、标签分布、文本质量
    2. 检测近重复样本(minhash + 精确哈希双重去重)
    3. 核查训练/测试集划分泄露风险(对照 train_text.py vs assess_and_retrain.py)
    4. 抽检 Reddit 自标签噪声(随机抽样 + 关键词启发式)
    5. 归档清洗报告到 model_assessment/d2_text_data_audit.json

参考:
    - scripts/ml_training/train_text.py: 生产训练(reddit+twitter 合并, random_state=42, test_size=0.2)
    - scripts/assess_and_retrain.py: 评估训练(reddit only, random_state=42, test_size=0.2)
    - model_assessment/assessment_summary.json: 历史记录 F1=0.965(text_tfidf_logistic_baseline)
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [D2] %(message)s")
logger = logging.getLogger("D2")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REDDIT_CSV = PROJECT_ROOT / "datasets" / "text" / "depression_dataset_reddit_cleaned.csv"
TWITTER_CSV = PROJECT_ROOT / "datasets" / "Mental-Health-Twitter.csv"
TRAIN_SPLIT_PATH = PROJECT_ROOT / "models" / "artifacts" / "text_depression_classifier" / "split_indices.json"
ASSESSMENT_SUMMARY = PROJECT_ROOT / "model_assessment" / "assessment_summary.json"
AUDIT_REPORT_PATH = PROJECT_ROOT / "model_assessment" / "d2_text_data_audit.json"


def normalize_text_for_hash(text: str) -> str:
    """规范化文本用于哈希去重(小写+去标点+压缩空白)."""
    text = str(text).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def text_fingerprint(text: str) -> str:
    """精确文本指纹(SHA256 of normalized text)."""
    return hashlib.sha256(normalize_text_for_hash(text).encode("utf-8")).hexdigest()


def minhash_signature(text: str, n_shingles: int = 50, n_hashes: int = 20) -> tuple[int, ...]:
    """简易 MinHash 签名(基于字符 shingles).

    用于近重复检测,不需要 datasketch 依赖.
    """
    norm = normalize_text_for_hash(text)
    if len(norm) < 10:
        return (0,) * n_hashes

    # 字符级 5-gram shingles
    shingles = [norm[i:i+5] for i in range(0, max(0, len(norm) - 4), max(1, len(norm) // n_shingles))]
    if not shingles:
        shingles = [norm]

    # n_hashes 个哈希函数(使用 salt 偏移)
    signature = []
    for h in range(n_hashes):
        min_hash = float("inf")
        for s in shingles:
            h_val = int(hashlib.md5(f"{h}:{s}".encode("utf-8")).hexdigest(), 16)
            if h_val < min_hash:
                min_hash = h_val
        signature.append(min_hash)
    return tuple(signature)


def jaccard_estimate(sig1: tuple[int, ...], sig2: tuple[int, ...]) -> float:
    """MinHash 签名的 Jaccard 相似度估计."""
    if len(sig1) != len(sig2) or not sig1:
        return 0.0
    matches = sum(1 for a, b in zip(sig1, sig2) if a == b)
    return matches / len(sig1)


def find_near_duplicates(df: pd.DataFrame, threshold: float = 0.8) -> list[dict]:
    """检测近重复样本对(MinHash + Jaccard).

    Args:
        df: 含 text 列的 DataFrame
        threshold: Jaccard 相似度阈值,超过则视为近重复

    Returns:
        近重复样本对列表 [{idx1, idx2, similarity, text1_preview, text2_preview}]
    """
    logger.info("计算 MinHash 签名: %d 样本", len(df))
    signatures = df["text"].apply(minhash_signature).tolist()

    near_dup_pairs = []
    n = len(df)
    for i in range(n):
        for j in range(i + 1, n):
            sim = jaccard_estimate(signatures[i], signatures[j])
            if sim >= threshold:
                near_dup_pairs.append({
                    "idx1": int(i),
                    "idx2": int(j),
                    "similarity": round(float(sim), 4),
                    "text1_preview": str(df.iloc[i]["text"])[:80],
                    "text2_preview": str(df.iloc[j]["text"])[:80],
                })

    logger.info("近重复检测完成: %d 对 (阈值=%.2f)", len(near_dup_pairs), threshold)
    return near_dup_pairs


def find_exact_duplicates(df: pd.DataFrame) -> dict:
    """检测精确重复(规范化文本哈希)."""
    logger.info("检测精确重复...")
    df["text_hash"] = df["text"].apply(text_fingerprint)
    hash_counts = df["text_hash"].value_counts()
    dup_hashes = hash_counts[hash_counts > 1]

    duplicate_groups = []
    for h, count in dup_hashes.items():
        indices = df[df["text_hash"] == h].index.tolist()
        labels = df.loc[indices, "label"].tolist()
        # 检查标签是否冲突
        label_conflict = len(set(labels)) > 1
        duplicate_groups.append({
            "hash": h[:16],
            "count": int(count),
            "indices": [int(i) for i in indices],
            "labels": [int(l) for l in labels],
            "label_conflict": bool(label_conflict),
            "text_preview": str(df.loc[indices[0], "text"])[:80],
        })

    return {
        "n_duplicate_groups": len(duplicate_groups),
        "n_duplicate_samples": int(sum(g["count"] - 1 for g in duplicate_groups)),
        "n_label_conflicts": int(sum(1 for g in duplicate_groups if g["label_conflict"])),
        "groups": duplicate_groups[:20],  # 只保存前 20 组
    }


def check_split_leakage() -> dict:
    """核查训练/测试集划分泄露风险.

    检查点:
        1. train_text.py 保存的 split_indices.json 是否存在
        2. assess_and_retrain.py 评估时是否复用了同一划分
        3. 评估模型与生产模型的训练数据是否一致
    """
    logger.info("核查训练/测试集划分泄露风险...")

    findings = {
        "train_split_exists": TRAIN_SPLIT_PATH.exists(),
        "issues": [],
        "risk_level": "low",
    }

    if not TRAIN_SPLIT_PATH.exists():
        findings["issues"].append({
            "issue": "split_indices.json 不存在",
            "detail": f"未找到 {TRAIN_SPLIT_PATH},无法校验划分一致性",
            "severity": "medium",
        })
        findings["risk_level"] = "medium"
        return findings

    with open(TRAIN_SPLIT_PATH, "r", encoding="utf-8") as f:
        train_split = json.load(f)

    findings["train_split_info"] = {
        "total_samples": train_split.get("total_samples"),
        "train_samples": train_split.get("train_samples"),
        "test_samples": train_split.get("test_samples"),
        "random_state": train_split.get("random_state"),
        "test_size_ratio": train_split.get("test_size_ratio"),
        "dataset_fingerprint": train_split.get("dataset_fingerprint", "")[:16],
        "split_hash": train_split.get("split_hash", "")[:16],
    }

    # 检查 assessment_summary.json 中的历史 F1=0.97 记录
    if ASSESSMENT_SUMMARY.exists():
        with open(ASSESSMENT_SUMMARY, "r", encoding="utf-8") as f:
            assessment = json.load(f)

        current = assessment.get("current_models", {})
        text_baseline = current.get("text_tfidf_logistic_baseline", {})

        if text_baseline:
            # 历史评估的 support=1547,对照 train_text.py 的 test_samples
            historical_support = None
            try:
                historical_support = int(
                    text_baseline.get("classification_report", {}).get("macro avg", {}).get("support", 0)
                )
            except (ValueError, TypeError):
                pass

            train_test_samples = train_split.get("test_samples")

            if historical_support and train_test_samples and historical_support != train_test_samples:
                findings["issues"].append({
                    "issue": "评估脚本与训练脚本测试集大小不一致",
                    "detail": (
                        f"assessment_summary.json 中 text_tfidf_logistic_baseline 的 support={historical_support}, "
                        f"但 train_text.py 的 split_indices.json 记录 test_samples={train_test_samples}. "
                        f"差异={historical_support - train_test_samples}. "
                        f"说明 assess_and_retrain.py 用了不同的数据集划分(只用 reddit,未合并 twitter)."
                    ),
                    "severity": "high",
                    "historical_support": historical_support,
                    "train_test_samples": train_test_samples,
                })
                findings["risk_level"] = "high"

            # 检查 F1 是否异常高
            historical_f1 = text_baseline.get("f1")
            if historical_f1 and historical_f1 > 0.95:
                findings["issues"].append({
                    "issue": "历史 F1 异常高(>0.95),可能误导为生产模型性能",
                    "detail": (
                        f"assessment_summary.json 记录 text_tfidf_logistic_baseline.f1={historical_f1:.4f}. "
                        f"但该指标来自 assess_and_retrain.py 自训自评的 reddit-only 模型, "
                        f"并非生产模型(models/artifacts/text_depression_classifier)的性能. "
                        f"生产模型用 reddit+twitter 合并数据训练,性能应单独评估."
                    ),
                    "severity": "high",
                    "historical_f1": historical_f1,
                })
                findings["risk_level"] = "high"

    return findings


def audit_label_noise(df: pd.DataFrame, n_sample: int = 50) -> dict:
    """抽检 Reddit 自标签噪声.

    Reddit 标签来源: 帖子所在子版块(r/depression=1, 其他=0)
    这是一种弱监督,可能存在噪声.

    抽检策略:
        1. 随机抽样 50 条(25 正/25 负)
        2. 启发式检查:抑郁关键词命中率
        3. 异常模式检测:标签=1 但无抑郁关键词 / 标签=0 但有强烈抑郁关键词
    """
    logger.info("抽检 Reddit 自标签噪声 (n=%d)...", n_sample)

    # 抑郁/自杀高风险关键词
    depression_keywords = [
        "depress", "hopeless", "suicid", "kill myself", "want to die",
        "end it all", "no point", "give up", "can t go on", "empty",
        "worthless", "alone", "tired of life", "mental health",
    ]
    positive_signals = ["medication", "therapist", "diagnosed", "treatment", "anxiety"]

    random.seed(42)
    pos_samples = df[df["label"] == 1].sample(min(n_sample // 2, len(df[df["label"] == 1])), random_state=42)
    neg_samples = df[df["label"] == 0].sample(min(n_sample // 2, len(df[df["label"] == 0])), random_state=42)

    audit_results = {
        "n_sampled": int(len(pos_samples) + len(neg_samples)),
        "positive_samples": [],
        "negative_samples": [],
        "suspected_mislabeled": [],
    }

    # 检查正样本:是否包含抑郁关键词
    for idx, row in pos_samples.iterrows():
        text_lower = str(row["text"]).lower()
        kw_hits = [kw for kw in depression_keywords if kw in text_lower]
        pos_hits = [kw for kw in positive_signals if kw in text_lower]

        entry = {
            "idx": int(idx),
            "label": 1,
            "text_preview": str(row["text"])[:120],
            "keyword_hits": kw_hits,
            "positive_signal_hits": pos_hits,
            "has_any_signal": len(kw_hits) > 0 or len(pos_hits) > 0,
        }
        audit_results["positive_samples"].append(entry)

        if not entry["has_any_signal"]:
            audit_results["suspected_mislabeled"].append({
                "idx": int(idx),
                "label": 1,
                "issue": "标签=1 但无抑郁关键词命中",
                "text_preview": str(row["text"])[:120],
            })

    # 检查负样本:是否包含强烈抑郁信号
    strong_signals = ["suicid", "kill myself", "want to die", "end it all"]
    for idx, row in neg_samples.iterrows():
        text_lower = str(row["text"]).lower()
        strong_hits = [kw for kw in strong_signals if kw in text_lower]

        entry = {
            "idx": int(idx),
            "label": 0,
            "text_preview": str(row["text"])[:120],
            "strong_keyword_hits": strong_hits,
        }
        audit_results["negative_samples"].append(entry)

        if strong_hits:
            audit_results["suspected_mislabeled"].append({
                "idx": int(idx),
                "label": 0,
                "issue": f"标签=0 但命中强烈抑郁关键词: {strong_hits}",
                "text_preview": str(row["text"])[:120],
            })

    audit_results["n_suspected_mislabeled"] = len(audit_results["suspected_mislabeled"])
    audit_results["mislabeled_rate_estimate"] = (
        audit_results["n_suspected_mislabeled"] / audit_results["n_sampled"]
        if audit_results["n_sampled"] > 0 else 0.0
    )

    logger.info("标签噪声抽检完成: %d/%d 疑似误标 (%.1f%%)",
                audit_results["n_suspected_mislabeled"],
                audit_results["n_sampled"],
                audit_results["mislabeled_rate_estimate"] * 100)

    return audit_results


def audit_text_quality(df: pd.DataFrame) -> dict:
    """审计文本质量."""
    logger.info("审计文本质量...")

    text_lengths = df["text"].str.len()
    word_counts = df["text"].str.split().str.len()

    return {
        "n_samples": int(len(df)),
        "label_distribution": df["label"].value_counts().to_dict(),
        "label_balance_ratio": float(
            min(df["label"].value_counts()) / max(df["label"].value_counts())
            if len(df["label"].value_counts()) > 1 else 0.0
        ),
        "text_length": {
            "mean": float(text_lengths.mean()),
            "median": float(text_lengths.median()),
            "min": int(text_lengths.min()),
            "max": int(text_lengths.max()),
            "p5": float(text_lengths.quantile(0.05)),
            "p95": float(text_lengths.quantile(0.95)),
        },
        "word_count": {
            "mean": float(word_counts.mean()),
            "median": float(word_counts.median()),
            "min": int(word_counts.min()),
            "max": int(word_counts.max()),
        },
        "n_empty_or_short": int((text_lengths < 5).sum()),
        "n_very_long": int((text_lengths > 5000).sum()),
        "n_with_non_ascii": int(df["text"].apply(lambda x: any(ord(c) > 127 for c in str(x))).sum()),
    }


def main() -> None:
    logger.info("=" * 60)
    logger.info("D2 文本数据清洗与标签审计")
    logger.info("=" * 60)

    if not REDDIT_CSV.exists():
        logger.error("Reddit 数据集不存在: %s", REDDIT_CSV)
        return

    # 加载数据
    df = pd.read_csv(REDDIT_CSV)
    df = df.rename(columns={"clean_text": "text", "is_depression": "label"})
    df["text"] = df["text"].fillna("").astype(str)
    df["label"] = pd.to_numeric(df["label"], errors="coerce").fillna(0).astype(int)
    df = df.dropna(subset=["text"])
    df = df[df["text"].str.len() >= 5].reset_index(drop=True)

    logger.info("加载完成: %d 样本", len(df))

    # 1. 文本质量审计
    quality = audit_text_quality(df)

    # 2. 精确重复检测
    exact_dups = find_exact_duplicates(df)

    # 3. 近重复检测(对子样本,避免 O(n^2) 过慢)
    # 如果样本 > 2000,只对前 2000 检测
    sample_for_near_dup = df if len(df) <= 2000 else df.sample(2000, random_state=42).reset_index(drop=True)
    near_dups = find_near_duplicates(sample_for_near_dup, threshold=0.8)

    # 4. 训练/测试集泄露核查
    leakage = check_split_leakage()

    # 5. 标签噪声抽检
    label_noise = audit_label_noise(df, n_sample=50)

    # 汇总报告
    report = {
        "audit_at": datetime.now().isoformat(timespec="seconds"),
        "audit_by": "v2.0 S1 D2 文本数据清洗与标签审计",
        "dataset_path": str(REDDIT_CSV.relative_to(PROJECT_ROOT)),
        "quality": quality,
        "exact_duplicates": exact_dups,
        "near_duplicates": {
            "n_pairs": len(near_dups),
            "sample_size": len(sample_for_near_dup),
            "threshold": 0.8,
            "pairs_preview": near_dups[:10],
        },
        "split_leakage_check": leakage,
        "label_noise_audit": label_noise,
        "summary": {
            "n_total_samples": int(len(df)),
            "n_exact_duplicates": exact_dups["n_duplicate_samples"],
            "n_near_duplicate_pairs": len(near_dups),
            "n_suspected_mislabeled": label_noise["n_suspected_mislabeled"],
            "mislabeled_rate_estimate": round(label_noise["mislabeled_rate_estimate"], 4),
            "split_leakage_risk": leakage["risk_level"],
            "split_leakage_issues": len(leakage["issues"]),
        },
        "recommendations": [],
    }

    # 生成建议
    recs = report["recommendations"]
    if exact_dups["n_duplicate_samples"] > 0:
        recs.append({
            "priority": "high",
            "action": f"剔除 {exact_dups['n_duplicate_samples']} 个精确重复样本",
            "reason": "精确重复会导致训练/测试集泄露,模型过拟合",
        })
    if len(near_dups) > 0:
        recs.append({
            "priority": "medium",
            "action": f"审查 {len(near_dups)} 对近重复样本,人工确认后剔除",
            "reason": "近重复可能来自同一用户多次发帖或转发",
        })
    if leakage["risk_level"] == "high":
        recs.append({
            "priority": "high",
            "action": "修正 assess_and_retrain.py 评估流程,使用 train_text.py 保存的 split_indices.json",
            "reason": "历史 F1=0.97 误导性强,是评估脚本自训自评的结果,非生产模型性能",
        })
    if label_noise["mislabeled_rate_estimate"] > 0.1:
        recs.append({
            "priority": "medium",
            "action": f"标签噪声率 {label_noise['mislabeled_rate_estimate']*100:.1f}% > 10%,建议人工复核全部数据",
            "reason": "Reddit 弱监督标签噪声较高,影响模型泛化",
        })
    if quality["label_balance_ratio"] < 0.8:
        recs.append({
            "priority": "low",
            "action": f"类别不平衡(比率 {quality['label_balance_ratio']:.2f}),训练时保持 class_weight='balanced'",
            "reason": "不平衡数据需要加权或重采样",
        })
    if not recs:
        recs.append({
            "priority": "low",
            "action": "数据质量良好,无需特殊处理",
            "reason": "所有审计项通过",
        })

    # 保存报告
    AUDIT_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info("=" * 60)
    logger.info("D2 审计完成,报告已保存: %s", AUDIT_REPORT_PATH)
    logger.info("=" * 60)
    logger.info("摘要:")
    logger.info("  样本数: %d", report["summary"]["n_total_samples"])
    logger.info("  精确重复: %d", report["summary"]["n_exact_duplicates"])
    logger.info("  近重复对: %d", report["summary"]["n_near_duplicate_pairs"])
    logger.info("  疑似误标: %d (%.1f%%)", report["summary"]["n_suspected_mislabeled"],
                report["summary"]["mislabeled_rate_estimate"] * 100)
    logger.info("  划分泄露风险: %s (%d issues)", report["summary"]["split_leakage_risk"],
                report["summary"]["split_leakage_issues"])
    logger.info("  建议: %d 条", len(recs))


if __name__ == "__main__":
    main()
