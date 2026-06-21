"""v1.25 Phase 1: Lite Feature Construction.

Builds 20-dimensional feature vectors from mmpsy raw data using only
GAD-7, text keywords, and demographic defaults (NO phq9_score as input).

Output:
  data/processed/lite_features.csv (1275 x 20)
  lite_feature_report.md (keyword coverage statistics)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[4]

KEYWORD_CATEGORIES: dict[str, list[str]] = {
    "academic_pressure": [
        "挂科", "退学", "考研", "论文", "毕业", "导师",
        "考试", "成绩", "作业", "学习", "背书", "中考", "高考",
        "学业", "老师", "周测",
    ],
    "sleep_problem": [
        "失眠", "熬夜", "早醒", "嗜睡", "噩梦",
        "睡不着", "睡不好", "多梦", "彻夜难眠", "整夜没睡",
    ],
    "social_withdrawal": [
        "独处", "回避", "不想说话", "孤僻",
        "不想见人", "不想出门", "孤立", "一个人",
    ],
    "self_harm_crisis": [
        "自残", "自杀", "想死", "割腕", "安眠药",
        "不想活", "活不下去", "死了算了", "结束生命",
        "跳楼", "上吊",
    ],
    "exercise_deficit": [
        "不运动", "躺着", "不出门", "宅",
    ],
    "low_mood": [
        "难过", "绝望", "空虚", "麻木", "没意义",
        "低落", "沮丧", "郁闷", "痛苦", "没意思",
    ],
    "anxiety_somatic": [
        "心慌", "胸闷", "发抖", "出汗", "窒息",
        "紧张", "不安", "害怕", "担心",
    ],
}

DEMO_DEFAULTS = {"age": 25.0, "gender": 1, "cgpa": 3.1}


def chinese_ratio(text: str) -> float:
    chinese = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    return chinese / max(len(text), 1)


def check_text_quality(text: str) -> int:
    length = len(text)
    cr = chinese_ratio(text)
    if length < 20:
        return 0
    if cr < 0.30:
        return 1
    return 2


def extract_keywords(text: str) -> dict:
    result: dict = {
        "keyword_counts": {},
        "total_keywords": 0,
        "crisis_weighted": 0,
    }
    for cat, keywords in KEYWORD_CATEGORIES.items():
        count = sum(text.count(kw) for kw in keywords)
        if cat == "self_harm_crisis":
            count *= 2
            result["crisis_weighted"] = count
        result["keyword_counts"][cat] = count
        result["total_keywords"] += count
    result["unique_categories"] = sum(
        1 for v in result["keyword_counts"].values() if v > 0
    )
    return result


def main() -> None:
    mmpsy_path = PROJECT_ROOT / "data" / "external" / "mmpsy_scores.csv"
    if not mmpsy_path.exists():
        print(f"ERROR: mmpsy_scores.csv not found at {mmpsy_path}")
        sys.exit(1)

    df = pd.read_csv(mmpsy_path)
    print(f"Loaded mmpsy_scores.csv: {len(df)} rows")

    features_list: list[dict] = []
    for _, row in df.iterrows():
        text = str(row["audio_transcript"])
        kw = extract_keywords(text)
        quality = check_text_quality(text)
        length = len(text)

        features: dict = {
            "user_id": row["user_id"],
            "gad7_score": float(row["gad7_score"]),
            "phq9_score": float(row["phq9_score"]),  # 对照列，不作为模型输入
            "phq9_binary": int(row["phq9_binary"]),
            "age": DEMO_DEFAULTS["age"],
            "gender": DEMO_DEFAULTS["gender"],
            "cgpa": DEMO_DEFAULTS["cgpa"],
            "total_keywords": kw["total_keywords"],
            "unique_categories": kw["unique_categories"],
            "text_length": length,
            "chinese_ratio": round(chinese_ratio(text), 4),
            "text_quality_flag": quality,
            "crisis_weighted": kw["crisis_weighted"],
            "coverage_density": round(
                kw["total_keywords"] / max(length, 1) * 100, 2
            ),
        }
        for cat in KEYWORD_CATEGORIES:
            features[f"kw_{cat}"] = kw["keyword_counts"].get(cat, 0)

        features_list.append(features)

    df_out = pd.DataFrame(features_list)

    output_path = PROJECT_ROOT / "data" / "processed" / "lite_features.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(output_path, index=False, encoding="utf-8")
    print(f"Saved lite_features.csv: {len(df_out)} rows x {len(df_out.columns)} cols")

    # Feature report
    output_dir = (
        PROJECT_ROOT / "docs" / "planning" / "v1.25-mmpsy-lite-risk-model"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "lite_feature_report.md"

    flag_counts = df_out["text_quality_flag"].value_counts().sort_index()
    q_labels = {0: "text too short (<20)", 1: "non-chinese (<30%)", 2: "normal"}

    lines: list[str] = [
        "# v1.25 Phase 1: Lite Feature Report",
        "",
        f"> Generated: {pd.Timestamp.now().isoformat(timespec='seconds')}",
        f"> Samples: {len(df_out)}",
        f"> Features: {len(df_out.columns)} columns",
        "",
        "## 1. Text Quality Distribution",
        "",
        "| Flag | Description | Count | Ratio |",
        "|---|---|---|---|",
    ]
    for flag in sorted(q_labels):
        cnt = flag_counts.get(flag, 0)
        ratio = cnt / len(df_out) * 100
        lines.append(
            f"| {flag} | {q_labels[flag]} | {cnt} | {round(ratio, 2)}% |"
        )
    lines.append("")

    lines.append("## 2. Keyword Category Coverage")
    lines.append("")
    lines.append("| Category | Hit Count | Hit Rate (%) | Mean Count |")
    lines.append("|---|---|---|---|")
    for cat in KEYWORD_CATEGORIES:
        col = f"kw_{cat}"
        hit = (df_out[col] > 0).sum()
        rate = hit / len(df_out) * 100
        mean_cnt = df_out[col].mean()
        lines.append(
            f"| {cat} | {hit} | {round(rate, 2)} | {round(mean_cnt, 2)} |"
        )
    lines.append("")

    lines.append("## 3. Keyword Density Statistics")
    lines.append("")
    total_kw = df_out["total_keywords"]
    unique_cat = df_out["unique_categories"]
    density = df_out["coverage_density"]

    lines.append("| Metric | Mean | Median | P10 | P90 | Min | Max |")
    lines.append("|---|---|---|---|---|---|---|")

    for name, series in [
        ("total_keywords", total_kw),
        ("unique_categories", unique_cat),
        ("coverage_density", density),
    ]:
        mean_v = series.mean()
        median_v = series.median()
        p10 = series.quantile(0.10)
        p90 = series.quantile(0.90)
        min_v = series.min()
        max_v = series.max()
        lines.append(
            f"| {name} | {round(mean_v, 2)} | {round(median_v, 2)} | "
            f"{round(p10, 2)} | {round(p90, 2)} | {round(min_v, 2)} | "
            f"{round(max_v, 2)} |"
        )

    lines.append("")
    lines.append("## 4. Text Length Distribution")
    lines.append("")

    text_len = df_out["text_length"]
    lines.append(f"- Mean: {round(text_len.mean(), 1)} characters")
    lines.append(f"- Median: {round(text_len.median(), 1)} characters")
    lines.append(f"- Min: {int(text_len.min())} / Max: {int(text_len.max())} characters")

    lines.append("")
    zero_kw = (total_kw == 0).sum()
    lines.append(f"**Samples with zero keywords**: {zero_kw} ({round(zero_kw / len(df_out) * 100, 2)}%)")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Feature report written to: {report_path}")


if __name__ == "__main__":
    main()
