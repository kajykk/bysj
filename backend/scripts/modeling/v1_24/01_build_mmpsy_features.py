"""v1.24 Phase 1: Build mmpsy structured features.

Derives or imputes the 12 v1.23 model features from the mmpsy dataset
(which contains only PHQ-9 / GAD-7 scores and audio transcripts).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[4]

CRISIS_WORDS = [
    "想死", "不想活", "自杀", "自残", "活不下去", "死了算了", "结束生命",
]

SLEEP_RULES: list[tuple[str, float]] = [
    ("整夜没睡", 0),
    ("彻夜难眠", 0),
    ("失眠", 3),
    ("睡不着", 3),
    ("熬夜", 5),
    ("睡眠不足", 5),
    ("早醒", 5),
    ("睡得好", 8),
    ("入睡", 8),
    ("睡眠", 8),
]

ACADEMIC_WORDS = [
    "考试", "成绩", "作业", "学习", "背书", "中考", "高考", "学业", "老师", "周测",
]

EXERCISE_WORDS = [
    "跑步", "打球", "运动", "散步", "锻炼", "篮球", "足球", "游泳", "健身",
]


def count_keywords(text: str, keywords: list[str]) -> int:
    if pd.isna(text) or not isinstance(text, str):
        return 0
    return sum(text.count(kw) for kw in keywords)


def check_crisis(text: str) -> int:
    if pd.isna(text) or not isinstance(text, str):
        return 0
    for w in CRISIS_WORDS:
        if w in text:
            return 1
    return 0


def derive_sleep_duration(text: str, default: float) -> float:
    if pd.isna(text) or not isinstance(text, str):
        return default
    values: list[float] = []
    for kw, val in SLEEP_RULES:
        if kw in text:
            values.append(val)
    return min(values) if values else default


def derive_stress(phq9: float) -> float:
    return round(phq9 / 27.0 * 5.0, 4)


def derive_anxiety(gad7: float) -> float:
    return round(gad7 / 21.0 * 5.0, 4)


def load_schema_medians() -> dict[str, float]:
    import joblib

    model_path = (
        PROJECT_ROOT
        / "backend"
        / "models"
        / "v1.23_external_lr"
        / "model.pkl"
    )
    pipeline = joblib.load(model_path)
    num_pipe = (
        pipeline.named_steps["preprocessor"]
        .named_transformers_["num"]
    )
    imputer = num_pipe.named_steps["imputer"]
    feature_names = pipeline.feature_names_in_
    medians = dict(zip(feature_names, imputer.statistics_))
    return {k: float(v) for k, v in medians.items()}


def main() -> None:
    mmpsy_path = PROJECT_ROOT / "data" / "external" / "mmpsy_scores.csv"
    output_dir = PROJECT_ROOT / "data" / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "mmpsy_structured_features.csv"

    docs_dir = (
        PROJECT_ROOT
        / "docs"
        / "planning"
        / "v1.24-mmpsy-external-consistency-and-score-stability"
    )
    docs_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(mmpsy_path)
    medians = load_schema_medians()

    df_out = pd.DataFrame(index=df.index)

    # -- imputed features --
    df_out["age"] = medians["age"]
    df_out["gender"] = medians["gender"]
    df_out["cgpa"] = medians["cgpa"]
    df_out["social_support"] = medians["social_support"]
    df_out["financial_pressure"] = medians["financial_pressure"]
    df_out["family_history"] = medians["family_history"]

    df_out["age_source"] = "imputed"
    df_out["gender_source"] = "imputed"
    df_out["cgpa_source"] = "imputed"
    df_out["social_support_source"] = "imputed"
    df_out["financial_pressure_source"] = "imputed"
    df_out["family_history_source"] = "imputed"

    # -- derived features --
    df_out["stress_level"] = df["phq9_score"].apply(derive_stress)
    df_out["stress_level_source"] = "derived"

    df_out["sleep_duration"] = df["audio_transcript"].apply(
        lambda t: derive_sleep_duration(t, medians["sleep_duration"])
    )
    df_out["sleep_duration_source"] = "derived"

    df_out["academic_pressure"] = df["audio_transcript"].apply(
        lambda t: min(count_keywords(t, ACADEMIC_WORDS) * 1.25, 5.0)
    )
    df_out["academic_pressure_source"] = "derived"

    df_out["exercise_frequency"] = df["audio_transcript"].apply(
        lambda t: min(count_keywords(t, EXERCISE_WORDS) / 2.0, 3.0)
    )
    df_out["exercise_frequency_source"] = "derived"

    df_out["anxiety"] = df["gad7_score"].apply(derive_anxiety)
    df_out["anxiety_source"] = "derived"

    df_out["panic_attack"] = df["audio_transcript"].apply(check_crisis)
    df_out["panic_attack_source"] = "derived"

    # -- save --
    feature_order = [
        "age", "gender", "cgpa", "stress_level", "sleep_duration",
        "social_support", "financial_pressure", "family_history",
        "academic_pressure", "exercise_frequency", "anxiety", "panic_attack",
    ]
    source_order = [f"{f}_source" for f in feature_order]
    cols = feature_order + source_order
    df_out = df_out[cols]
    df_out.to_csv(output_path, index=False, encoding="utf-8")

    # -- reports --
    derived_count = sum(
        1 for f in feature_order
        if df_out[f"{f}_source"].iloc[0] == "derived"
    )
    coverage_pct = round(derived_count / len(feature_order) * 100, 1)

    mapping_lines = [
        "# mmpsy Feature Mapping Report",
        "",
        f"**Derived features**: {derived_count}/{len(feature_order)} ({coverage_pct}%)",
        f"**Imputed features**: {len(feature_order) - derived_count}/{len(feature_order)} "
        f"({round(100 - coverage_pct, 1)}%)",
        "",
        "| Feature | Strategy |",
        "|---------|----------|",
    ]
    for f in feature_order:
        strategy = df_out[f"{f}_source"].iloc[0]
        mapping_lines.append(f"| {f} | {strategy} |")
    mapping_lines.append("")
    mapping_lines.append(
        f"⚠️ Feature coverage ({coverage_pct}%) is below the 80% threshold. "
        "External validation will be **constrained**."
    )

    (docs_dir / "mmpsy_feature_mapping_report.md").write_text(
        "\n".join(mapping_lines) + "\n", encoding="utf-8"
    )

    # missingness
    missing_lines = [
        "# mmpsy Missingness Report",
        "",
        f"**Rows**: {len(df_out)}",
        f"**Feature columns**: {len(feature_order)}",
        "",
        "All 12 features are present (no NaN): each feature was either derived "
        "from mmpsy fields or filled with the schema median.",
        "",
        "| Feature | Fill Strategy | Notes |",
        "|---------|--------------|-------|",
    ]
    for f in feature_order:
        strategy = df_out[f"{f}_source"].iloc[0]
        if strategy == "imputed":
            missing_lines.append(
                f"| {f} | median={medians.get(f, '?')} | mmpsy has no equivalent field |"
            )
        else:
            missing_lines.append(f"| {f} | rule-derived | derived from mmpsy fields |")

    (docs_dir / "mmpsy_missingness_report.md").write_text(
        "\n".join(missing_lines) + "\n", encoding="utf-8"
    )

    print(f"Structured features: {output_path}")
    print(f"Rows: {len(df_out)}, Columns: {len(df_out.columns)}")
    print(f"Feature coverage: {derived_count}/{len(feature_order)} ({coverage_pct}%)")
    print(f"Mapping report: {docs_dir / 'mmpsy_feature_mapping_report.md'}")
    print(f"Missingness report: {docs_dir / 'mmpsy_missingness_report.md'}")


if __name__ == "__main__":
    main()
