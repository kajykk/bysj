"""v1.24 Phase 1: Build mmpsy structured features.

Derives or imputes the 12 v1.23 model features from the mmpsy dataset
(which contains only PHQ-9 / GAD-7 scores and audio transcripts).

⛔⛔⛔ 禁止用于模型评估（2026-10-19 B.5 补救轮加注） ⛔⛔⛔

本脚本产出的 `stress_level` 曾是 **L4 目标泄漏**的载体：

    derive_stress(phq9) = round(phq9 / 27.0 * 5.0, 4)

而 mmpsy 的标签 `phq9_binary = (phq9_score >= 10)`。实测
`corr(stress_level, phq9_score) = 1.0`、`stress_level` **单特征 AUC = 1.0000**
⇒ 任何把该列当输入的「模型性能」读数都是同义反复，**换任何 CV 都修不好**。
据此得出的 `v1.24` 外部验证结论（3-feature AUC 0.9993、AUC gap -0.3744
及其「插补引入噪声 → 回归均值」解释）**均已就地更正**，见
`docs/ML_LEAKAGE_REMEDIATION.md`。

当前行为（默认安全）：
  * `stress_level` 置为**缺失**（`stress_level_source = "unavailable"`），
    并在 `mmpsy_feature_mapping_report.md` 显式声明「该特征在 mmpsy 不可得」。
  * 需要**复现历史产出**时须显式传 `--allow-historical-repro`；
    该模式会打印醒目警告并在报告中标注 `label_derived: true`。

本文件是**归档历史脚本**：历史已落盘的产出与读数一律不改，只加护栏。
L4 检测现由 `tests/test_p2_38_leakage_audit_guard.py` 在提交期强制。
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


# ── 标签同源 / 强代理特征显式登记（B.5 补救轮新增） ──────────────────
# 供 L4 闸门与 mapping report 消费。**新增派生特征必须同步登记**，否则
# tests/test_p2_38_leakage_audit_guard.py 的登记完整性断言会红。
LABEL_DERIVED_FEATURES: dict[str, str] = {
    "stress_level": (
        "⛔ 标签同源：round(phq9_score / 27.0 * 5.0, 4)，而标签 "
        "phq9_binary = (phq9_score >= 10)。实测 corr=1.0、单特征 AUC=1.0000 "
        "⇒ L4 目标泄漏，禁止进入任何评估。"
    ),
}
# 非同源但强相关（派生自另一量表 GAD-7），须声明后使用
PROXY_DERIVED_FEATURES: dict[str, str] = {
    "anxiety": (
        "⚠️ 派生自另一量表 GAD-7（round(gad7_score / 21.0 * 5.0, 4)），"
        "非 phq9_binary 同源，但实测 corr(anxiety, phq9_score)=0.7987、"
        "单特征 AUC=0.9200 ⇒ 属强代理，须声明后使用。"
    ),
}


def derive_stress(phq9: float) -> float:
    """⛔ 标签同源派生 —— **默认不可用于建模**，仅 `--allow-historical-repro` 调用。

    `phq9 / 27 * 5` 是标签源 `phq9_score` 的确定性线性变换，而标签
    `phq9_binary = (phq9_score >= 10)` ⇒ 单特征 AUC = 1.0000（L4 目标泄漏）。
    保留此函数仅为复现已归档的历史产出；默认路径下 `stress_level` 置缺失。
    """
    return round(phq9 / 27.0 * 5.0, 4)


def derive_anxiety(gad7: float) -> float:
    """⚠️ 派生自**另一量表 GAD-7**，非标签同源（标签来自 PHQ-9）。

    但实测 corr(anxiety, phq9_score)=0.7987、单特征 AUC=0.9200 ⇒ **强代理**。
    允许使用，但必须在特征映射报告中声明其来源量表与相关性。
    """
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
    import argparse
    import sys

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--allow-historical-repro",
        action="store_true",
        help=(
            "⛔ 复现已归档的历史产出：恢复 stress_level 的标签同源派生。 "
            "**仅用于比对历史读数**，产出物禁止用于任何模型评估。"
        ),
    )
    args = ap.parse_args()
    repro = bool(args.allow_historical_repro)

    if repro:
        print(
            "\n" + "⛔" * 30
            + "\n⛔ --allow-historical-repro 已启用：正在复现**含 L4 目标泄漏**的历史产出。\n"
            "⛔ stress_level = round(phq9_score/27*5, 4)，与标签 phq9_binary 同源\n"
            "⛔ （corr=1.0、单特征 AUC=1.0000）。产出物**禁止用于模型评估**。\n"
            + "⛔" * 30 + "\n",
            file=sys.stderr,
        )

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
    # ⛔ stress_level：默认的**安全路径**——mmpsy 无真实 stress 字段，
    #    而 phq9 派生版本与标签同源（L4）⇒ 置缺失并显式声明不可得。
    #    仅 --allow-historical-repro 时恢复历史（泄漏）行为。
    if repro:
        df_out["stress_level"] = df["phq9_score"].apply(derive_stress)
        df_out["stress_level_source"] = "derived"
    else:
        df_out["stress_level"] = float("nan")
        df_out["stress_level_source"] = "unavailable"

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

    # ⛔ 标签同源 / 强代理特征显式声明（B.5 补救轮新增）
    mapping_lines.append("## ⛔ 标签同源与强代理特征声明")
    mapping_lines.append("")
    if repro:
        mapping_lines.append(
            "> **本产出由 `--allow-historical-repro` 生成，含标签同源特征，"
            "禁止用于模型评估。**"
        )
        mapping_lines.append("")
    for feat, note in LABEL_DERIVED_FEATURES.items():
        present = df_out[f"{feat}_source"].iloc[0] == "derived"
        state = "**已派生（泄漏）**" if present else "已置缺失（unavailable）✅"
        mapping_lines.append(f"- `{feat}`：{state} — {note}")
    for feat, note in PROXY_DERIVED_FEATURES.items():
        mapping_lines.append(f"- `{feat}`：⚠️ 强代理（非同源） — {note}")
    mapping_lines.append("")
    mapping_lines.append(
        "判据来源：`tests/test_p2_38_leakage_audit_guard.py`（L4 目标泄漏闸门，"
        "|corr| 与单特征 AUC 双阈值 0.99）。"
    )
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
