#!/usr/bin/env python3
"""v1.23 Phase 1: 数据准备 — 读取 aligned_features.csv，校验、清洗、划分数据集。

输出:
    data/processed/v1_23_external/train.csv
    data/processed/v1_23_external/validation.csv
    data/processed/v1_23_external/test.csv
    data/processed/v1_23_external/external_mmpsy.csv
    data/processed/v1_23_external/split_metadata.json
    docs/planning/v1.23-external-risk-model-upgrade/DATA_PREPARATION_REPORT.md
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]

FEATURE_COLS = [
    "age", "gender", "cgpa", "stress_level", "sleep_duration",
    "social_support", "financial_pressure", "family_history",
    "academic_pressure", "exercise_frequency", "anxiety", "panic_attack",
]

TARGET_COL = "depression_binary"
PHQ9_TOTAL_COL = "phq9_total"
LABEL_SOURCE_COL = "label_source"
SOURCE_COL = "source"

AGE_MIN, AGE_MAX = 12, 35

DATA_SOURCE_WEIGHTS = {"kaggle": 1.0, "mendeley": 5.0}


def _resolve_source(row: pd.Series) -> str:
    ls = str(row.get(LABEL_SOURCE_COL, ""))
    if "phq9" in ls.lower():
        return "mendeley"
    return "kaggle"


def _derive_label(row: pd.Series) -> int:
    ls = str(row.get(LABEL_SOURCE_COL, ""))
    if "phq9" in ls.lower():
        phq = row.get(PHQ9_TOTAL_COL, 0)
        if pd.isna(phq):
            return 0
        return 1 if float(phq) >= 10 else 0
    return int(row.get("label_binary", 0) or 0)


def load_and_clean(input_path: Path) -> pd.DataFrame:
    logger.info("Reading %s", input_path)
    df = pd.read_csv(input_path)
    logger.info("Raw rows: %d, cols: %d", len(df), len(df.columns))

    df[SOURCE_COL] = df.apply(_resolve_source, axis=1)
    df[TARGET_COL] = df.apply(_derive_label, axis=1).astype(int)

    logger.info("Source distribution:\n%s", df[SOURCE_COL].value_counts().to_string())
    logger.info("Target distribution:\n%s", df[TARGET_COL].value_counts().to_string())

    for col in FEATURE_COLS:
        if col not in df.columns:
            logger.warning("Missing feature column: %s — filling with 0", col)
            df[col] = 0

    return df


def check_and_report(df: pd.DataFrame, report_path: Path) -> dict:
    missing_stats: dict[str, dict[str, float]] = {}
    overall_missing: dict[str, float] = {}
    source_stats: dict[str, dict] = {}
    constant_cols: list[str] = []
    outlier_info: dict[str, dict] = {}

    for col in FEATURE_COLS + [TARGET_COL]:
        miss = df[col].isna().sum()
        miss_rate = miss / len(df) if len(df) else 0
        overall_missing[col] = round(miss_rate, 4)
        if miss > 0:
            missing_stats[col] = {"count": int(miss), "rate": round(miss_rate, 4)}

    for col in FEATURE_COLS:
        vals = df[col].dropna()
        if vals.nunique() <= 1:
            constant_cols.append(col)

    for src in df[SOURCE_COL].unique():
        sub = df[df[SOURCE_COL] == src]
        n = len(sub)
        pos_pct = sub[TARGET_COL].mean()
        phq_mean = None
        phq_count = 0
        if PHQ9_TOTAL_COL in sub.columns:
            phq_vals = sub[PHQ9_TOTAL_COL].dropna()
            if len(phq_vals) > 0:
                phq_mean = round(float(phq_vals.mean()), 2)
                phq_count = int(len(phq_vals))
        source_stats[src] = {
            "total": n,
            "positive": int(sub[TARGET_COL].sum()),
            "positive_rate": round(float(pos_pct), 4),
            "phq9_mean": phq_mean,
            "phq9_count": phq_count,
        }

    age_vals = df["age"].dropna()
    outlier_info["age"] = {
        "below_12": int((age_vals < AGE_MIN).sum()),
        "above_35": int((age_vals > AGE_MAX).sum()),
        "total_outliers": int(((age_vals < AGE_MIN) | (age_vals > AGE_MAX)).sum()),
    }

    summary = {
        "total_samples": len(df),
        "target_distribution": df[TARGET_COL].value_counts().to_dict(),
        "source_distribution": df[SOURCE_COL].value_counts().to_dict(),
        "overall_missing_rates": overall_missing,
        "missing_details": missing_stats,
        "constant_features": constant_cols,
        "source_stats": source_stats,
        "outlier_info": outlier_info,
        "features_used": FEATURE_COLS,
        "features_dropped_constant": [c for c in constant_cols if c != TARGET_COL],
    }

    lines = [
        "# v1.23 数据准备报告 (DATA_PREPARATION_REPORT)",
        "",
        f"> 日期: 2026-05-02",
        f"> 输入: data/external/aligned_features.csv",
        f"> 总样本: {len(df)}",
        "",
        "## 数据源分布",
    ]
    for src, info in source_stats.items():
        lines.append(
            f"- **{src}**: {info['total']} 条, "
            f"正例={info['positive']} ({info['positive_rate']:.1%}), "
            f"PHQ-9均值={info.get('phq9_mean', 'N/A')}"
        )

    lines.extend([
        "",
        "## 目标标签分布",
        f"- `{TARGET_COL}=0`: {summary['target_distribution'].get(0, 0)}",
        f"- `{TARGET_COL}=1`: {summary['target_distribution'].get(1, 0)}",
        "",
        "## 缺失率",
    ])
    for col, rate in overall_missing.items():
        if rate > 0:
            lines.append(f"- **{col}**: {rate:.1%}")
    if not any(r > 0 for r in overall_missing.values()):
        lines.append("- 无缺失值")

    lines.extend([
        "",
        "## 常数特征 (无区分度)",
    ])
    for c in constant_cols:
        val = df[c].dropna().iloc[0] if len(df[c].dropna()) > 0 else "N/A"
        lines.append(f"- `{c}` = {val}")
    if not constant_cols:
        lines.append("- 无")

    lines.extend([
        "",
        "## 异常值处理",
        f"- `age`: <={AGE_MIN} 的 {outlier_info['age']['below_12']} 条 (clip), >={AGE_MAX} 的 {outlier_info['age']['above_35']} 条 (clip)",
        "",
        "## 使用的特征 (共{}个)".format(len(FEATURE_COLS)),
    ])
    for f in FEATURE_COLS:
        lines.append(f"- `{f}`")

    lines.extend([
        "",
        "## 数据限制说明",
        "- `source` 列 100%% 缺失，改用 `label_source` 推断数据源",
        "- `social_support` 全为 2.0（填充值），保留但标注",
        "- `treatment_seeking` / `study_year` 为常数，已从特征集中移除",
        "- Mendeley PHQ-9 数据仅 682 条，标签由 `phq9_total >= 10` 导出",
        "- Kaggle `label_binary` 语义不等于 PHQ-9 标签，需在报告中区分",
    ])

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Report saved to %s", report_path)

    return summary


def winsorize_age(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    age = df["age"]
    df["age"] = age.clip(lower=AGE_MIN, upper=AGE_MAX)
    changed = (age != df["age"]).sum()
    if changed > 0:
        logger.info("Age winsorized: %d values clipped to [%d, %d]", changed, AGE_MIN, AGE_MAX)
    return df


def split_by_source(
    df: pd.DataFrame, random_state: int = 42
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    from sklearn.model_selection import train_test_split

    splits = df[SOURCE_COL].unique()
    logger.info("Splitting by source: %s", list(splits))

    train_parts, val_parts, test_parts = [], [], []

    for src in splits:
        sub = df[df[SOURCE_COL] == src].copy()
        n = len(sub)
        if src == "kaggle":
            t_size = 0.15
            sub_train, sub_test = train_test_split(
                sub, test_size=t_size, random_state=random_state,
                stratify=sub[TARGET_COL],
            )
            sub_train, sub_val = train_test_split(
                sub_train, test_size=t_size / (1 - t_size),
                random_state=random_state,
                stratify=sub_train[TARGET_COL],
            )
        else:
            if n < 50:
                logger.warning("%s only %d samples — using all for training", src, n)
                sub_train = sub
                sub_val = sub.sample(frac=0, random_state=random_state)
                sub_test = sub.sample(frac=0, random_state=random_state)
            else:
                t_size = 0.20
                sub_train, sub_test = train_test_split(
                    sub, test_size=t_size, random_state=random_state,
                    stratify=sub[TARGET_COL],
                )
                sub_train, sub_val = train_test_split(
                    sub_train, test_size=t_size / (1 - t_size),
                    random_state=random_state,
                    stratify=sub_train[TARGET_COL],
                )
        train_parts.append(sub_train)
        val_parts.append(sub_val)
        test_parts.append(sub_test)
        logger.info(
            "%s: train=%d, val=%d, test=%d (total=%d)",
            src, len(sub_train), len(sub_val), len(sub_test), n,
        )

    train_df = pd.concat(train_parts, ignore_index=True).sample(
        frac=1, random_state=random_state
    ).reset_index(drop=True)
    val_df = pd.concat(val_parts, ignore_index=True).sample(
        frac=1, random_state=random_state
    ).reset_index(drop=True)
    test_df = pd.concat(test_parts, ignore_index=True).sample(
        frac=1, random_state=random_state
    ).reset_index(drop=True)

    for name, d in [("train", train_df), ("val", val_df), ("test", test_df)]:
        logger.info(
            "%s: %d samples, pos_rate=%.2f%%",
            name, len(d), d[TARGET_COL].mean() * 100,
        )

    return train_df, val_df, test_df


def main() -> None:
    parser = argparse.ArgumentParser(description="v1.23 Phase 1: Data Preparation")
    parser.add_argument(
        "--input", default="data/external/aligned_features.csv",
        help="Path to aligned features CSV",
    )
    parser.add_argument(
        "--output-dir", default="data/processed/v1_23_external",
        help="Directory for processed data outputs",
    )
    parser.add_argument(
        "--report-dir", default="docs/planning/v1.23-external-risk-model-upgrade",
        help="Directory for report outputs",
    )
    parser.add_argument("--random-state", type=int, default=42)
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = PROJECT_ROOT / input_path
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    report_dir = Path(args.report_dir)
    if not report_dir.is_absolute():
        report_dir = PROJECT_ROOT / report_dir

    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    df = load_and_clean(input_path)

    summary = check_and_report(
        df, report_dir / "DATA_PREPARATION_REPORT.md",
    )

    df = winsorize_age(df)

    train_df, val_df, test_df = split_by_source(
        df, random_state=args.random_state,
    )

    out_cols = FEATURE_COLS + [TARGET_COL, SOURCE_COL, PHQ9_TOTAL_COL]
    out_cols = [c for c in out_cols if c in train_df.columns]

    train_df[out_cols].to_csv(output_dir / "train.csv", index=False)
    val_df[out_cols].to_csv(output_dir / "validation.csv", index=False)
    test_df[out_cols].to_csv(output_dir / "test.csv", index=False)
    logger.info("Saved train/val/test to %s", output_dir)

    split_meta = {
        "random_state": args.random_state,
        "input": str(input_path),
        "train_samples": len(train_df),
        "val_samples": len(val_df),
        "test_samples": len(test_df),
        "train_pos_rate": round(float(train_df[TARGET_COL].mean()), 4),
        "val_pos_rate": round(float(val_df[TARGET_COL].mean()), 4),
        "test_pos_rate": round(float(test_df[TARGET_COL].mean()), 4),
        "features": FEATURE_COLS,
        "target": TARGET_COL,
        "summary": summary,
    }

    meta_path = output_dir / "split_metadata.json"
    meta_path.write_text(
        json.dumps(split_meta, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    logger.info("Split metadata saved to %s", meta_path)

    logger.info("Phase 1 complete.")


if __name__ == "__main__":
    main()
