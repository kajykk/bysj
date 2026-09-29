"""D2 清洗执行: 剔除精确重复样本,生成 v2 数据集.

基于 d2_text_data_audit.json 的审计结果:
    - 剔除 81 个精确重复样本(53 组,保留每组首条)
    - 0 标签冲突,无需处理冲突
    - 保留原始列结构(clean_text, is_depression)
    - 生成 depression_dataset_reddit_cleaned_v2.csv
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [D2-CLEAN] %(message)s")
logger = logging.getLogger("D2-CLEAN")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_CSV = PROJECT_ROOT / "datasets" / "text" / "depression_dataset_reddit_cleaned.csv"
OUTPUT_CSV = PROJECT_ROOT / "datasets" / "text" / "depression_dataset_reddit_cleaned_v2.csv"
AUDIT_REPORT = PROJECT_ROOT / "model_assessment" / "d2_text_data_audit.json"


def normalize_text_for_hash(text: str) -> str:
    text = str(text).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def text_fingerprint(text: str) -> str:
    return hashlib.sha256(normalize_text_for_hash(text).encode("utf-8")).hexdigest()


def main() -> None:
    logger.info("=" * 60)
    logger.info("D2 清洗执行: 剔除精确重复")
    logger.info("=" * 60)

    # 加载原始数据
    df = pd.read_csv(INPUT_CSV)
    logger.info("原始样本数: %d", len(df))

    # 加载审计报告
    with open(AUDIT_REPORT, "r", encoding="utf-8") as f:
        audit = json.load(f)

    n_expected_dups = audit["summary"]["n_exact_duplicates"]
    logger.info("预期剔除精确重复: %d 个", n_expected_dups)

    # 计算文本指纹
    df["_text_hash"] = df["clean_text"].apply(text_fingerprint)

    # 剔除精确重复(保留首条)
    before = len(df)
    df_clean = df.drop_duplicates(subset=["_text_hash"], keep="first").reset_index(drop=True)
    after = len(df_clean)
    removed = before - after

    logger.info("清洗后样本数: %d (剔除 %d)", after, removed)

    if removed != n_expected_dups:
        logger.warning("剔除数 %d 与预期 %d 不一致,请检查", removed, n_expected_dups)

    # 移除临时列
    df_clean = df_clean.drop(columns=["_text_hash"])

    # 保存 v2 数据集
    df_clean.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    logger.info("已保存: %s", OUTPUT_CSV)

    # 生成清洗摘要
    summary = {
        "cleaned_at": pd.Timestamp.now().isoformat(),
        "input_file": str(INPUT_CSV.relative_to(PROJECT_ROOT)),
        "output_file": str(OUTPUT_CSV.relative_to(PROJECT_ROOT)),
        "before_samples": before,
        "after_samples": after,
        "removed_duplicates": removed,
        "label_distribution_before": df["is_depression"].value_counts().to_dict(),
        "label_distribution_after": df_clean["is_depression"].value_counts().to_dict(),
        "dedup_strategy": "保留每组首条(keep=first)",
        "audit_report_reference": str(AUDIT_REPORT.relative_to(PROJECT_ROOT)),
    }

    summary_path = PROJECT_ROOT / "model_assessment" / "d2_clean_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info("清洗摘要已保存: %s", summary_path)
    logger.info("=" * 60)
    logger.info("D2 清洗完成")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
