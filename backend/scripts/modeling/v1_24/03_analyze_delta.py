"""v1.24 Phase 3: Delta distribution analysis.

Analyzes the delta (v123_risk - v120_risk) distribution across the
training dataset (N=4318) to identify systematic score shifts and
inform Score Adapter piecewise segment selection.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[4]


def df_to_md(df: pd.DataFrame) -> str:
    cols = df.columns.tolist()
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    rows = []
    for _, row in df.iterrows():
        vals = [str(v) for v in row]
        rows.append("| " + " | ".join(vals) + " |")
    return "\n".join([header, sep] + rows)


def fmt_num(x: float, precision: int = 2) -> str:
    return f"{x:.{precision}f}"


def main() -> None:
    delta_path = (
        PROJECT_ROOT
        / "backend"
        / "models"
        / "v1.23_external_lr"
        / "model_delta_samples.csv"
    )
    docs_dir = (
        PROJECT_ROOT
        / "docs"
        / "planning"
        / "v1.24-mmpsy-external-consistency-and-score-stability"
    )
    docs_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(delta_path)
    delta = df["delta_v123_v120"].values
    abs_delta = np.abs(delta)
    N = len(df)

    # ============================================================
    # Level 1 — Global statistics
    # ============================================================
    mean_d = float(np.mean(delta))
    mean_abs = float(np.mean(abs_delta))
    std_d = float(np.std(delta, ddof=1))
    quantiles = np.quantile(delta, [0.10, 0.25, 0.50, 0.75, 0.90])

    thresholds = [15, 20, 30, 40]
    exceed_counts = {t: int((abs_delta > t).sum()) for t in thresholds}
    exceed_pcts = {t: round(exceed_counts[t] / N * 100, 1) for t in thresholds}

    # ============================================================
    # Level 2 — By v1.20 risk level
    # ============================================================
    v120_bins = [0, 18, 35, 55, 72, 100]
    v120_labels = ["low", "mild", "moderate", "high", "severe"]
    df["risk_level"] = pd.cut(
        df["v120_risk"], bins=v120_bins, labels=v120_labels, right=False
    )
    risk_grouped = (
        df.groupby("risk_level", observed=False)["delta_v123_v120"]
        .agg(["count", "mean", "std"])
        .reset_index()
    )
    risk_grouped.columns = ["risk_level", "count", "mean", "std"]
    risk_grouped["abs_mean"] = risk_grouped["mean"].abs()

    # ============================================================
    # Level 3 — By stress_level & anxiety bins (PHQ-9/GAD-7 proxy)
    # ============================================================
    # stress_level ranges 0-5 (original feature). Bin for severity.
    stress_bins = [0, 0.93, 1.85, 2.78, 3.70, 5.19]
    stress_labels = ["0-4", "5-9", "10-14", "15-19", "20+"]
    df["stress_bin"] = pd.cut(
        df["stress_level"], bins=stress_bins, labels=stress_labels, right=False
    )
    stress_grouped = (
        df.groupby("stress_bin", observed=False)["delta_v123_v120"]
        .agg(["count", "mean", "std"])
        .reset_index()
    )
    stress_grouped.columns = ["phq9_proxy_bin", "count", "mean", "std"]
    stress_grouped["abs_mean"] = stress_grouped["mean"].abs()

    anxiety_bins = [0, 1.19, 2.38, 3.57, 4.76, 6.0]
    anxiety_labels = ["0-4", "5-9", "10-14", "15-20", "21+"]
    df["anxiety_bin"] = pd.cut(
        df["anxiety"], bins=anxiety_bins, labels=anxiety_labels, right=False
    )
    anxiety_grouped = (
        df.groupby("anxiety_bin", observed=False)["delta_v123_v120"]
        .agg(["count", "mean", "std"])
        .reset_index()
    )
    anxiety_grouped.columns = ["gad7_proxy_bin", "count", "mean", "std"]
    anxiety_grouped["abs_mean"] = anxiety_grouped["mean"].abs()

    # ============================================================
    # Level 4 — By demographics
    # ============================================================
    age_bins = [0, 18, 21, 24, 100]
    age_labels = ["<=18", "19-21", "22-24", "25+"]
    df["age_group"] = pd.cut(
        df["age"], bins=age_bins, labels=age_labels, right=True
    )
    age_grouped = (
        df.groupby("age_group", observed=False)["delta_v123_v120"]
        .agg(["count", "mean", "std"])
        .reset_index()
    )
    age_grouped.columns = ["age_group", "count", "mean", "std"]
    age_grouped["abs_mean"] = age_grouped["mean"].abs()

    gender_grouped = (
        df.groupby("gender")["delta_v123_v120"]
        .agg(["count", "mean", "std"])
        .reset_index()
    )
    gender_grouped.columns = ["gender", "count", "mean", "std"]
    gender_grouped["abs_mean"] = gender_grouped["mean"].abs()

    if "source" in df.columns:
        source_grouped = (
            df.groupby("source")["delta_v123_v120"]
            .agg(["count", "mean", "std"])
            .reset_index()
        )
        source_grouped.columns = ["source", "count", "mean", "std"]
        source_grouped["abs_mean"] = source_grouped["mean"].abs()
    else:
        source_grouped = pd.DataFrame(
            columns=["source", "count", "mean", "std", "abs_mean"]
        )

    # ============================================================
    # Level 5 — Extreme cases
    # ============================================================
    extreme_30 = df[abs_delta > 30].copy()
    extreme_40 = df[abs_delta > 40].copy()
    n_extreme_30 = len(extreme_30)
    n_extreme_40 = len(extreme_40)

    low_to_high = df[(df["v120_risk"] <= 18) & (df["v123_risk"] >= 55)]
    high_to_low = df[(df["v120_risk"] >= 55) & (df["v123_risk"] <= 18)]
    n_low_to_high = len(low_to_high)
    n_high_to_low = len(high_to_low)

    # extreme_30 risk level distribution
    extreme_risk_dist = (
        extreme_30.groupby("risk_level", observed=False)
        .size()
        .reset_index(name="count")
    )
    extreme_risk_dist["pct"] = round(
        extreme_risk_dist["count"] / n_extreme_30 * 100, 1
    )

    # ============================================================
    # Level 6 — Quintile segment recommendation
    # ============================================================
    df["quintile"] = pd.qcut(
        df["v120_risk"], q=5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"]
    )
    quintile_grouped = (
        df.groupby("quintile", observed=False)
        .agg(
            score_min=("v120_risk", "min"),
            score_max=("v120_risk", "max"),
            mean_delta=("delta_v123_v120", "mean"),
            delta_std=("delta_v123_v120", "std"),
            count=("delta_v123_v120", "count"),
        )
        .reset_index()
    )
    quintile_grouped["score_range"] = (
        quintile_grouped["score_min"].astype(int).astype(str)
        + "-"
        + quintile_grouped["score_max"].astype(int).astype(str)
    )
    quintile_grouped["abs_mean_delta"] = quintile_grouped["mean_delta"].abs()

    # ============================================================
    # Feature group split (depression_binary)
    # ============================================================
    feat_grouped = (
        df.groupby("depression_binary")["delta_v123_v120"]
        .agg(["count", "mean", "std"])
        .reset_index()
    )
    feat_grouped.columns = ["depression_binary", "count", "mean", "std"]
    feat_grouped["abs_mean"] = feat_grouped["mean"].abs()
    feat_grouped["label"] = feat_grouped["depression_binary"].map(
        {0: "non_depressed", 1: "depressed"}
    )

    # ============================================================
    # Save CSVs
    # ============================================================
    # risk_grouped with score_range for Adapter
    risk_out = risk_grouped.copy()
    risk_boundaries = list(zip(v120_bins[:-1], v120_bins[1:]))
    risk_out["score_range"] = [
        f"{lo}-{hi - 1}" for lo, hi in risk_boundaries
    ]
    risk_out = risk_out.rename(columns={"mean": "actual_mean_delta"})
    risk_out[["risk_level", "score_range", "count", "actual_mean_delta", "std", "abs_mean"]].to_csv(
        docs_dir / "delta_by_risk_group.csv", index=False
    )

    feat_grouped.to_csv(docs_dir / "delta_by_feature_group.csv", index=False)

    quintile_out = quintile_grouped.rename(
        columns={"mean_delta": "actual_mean_delta"}
    )
    quintile_out[["quintile", "score_range", "count", "actual_mean_delta", "delta_std"]].to_csv(
        docs_dir / "delta_quintile_segments.csv", index=False
    )

    extreme_cols = [
        "source",
        "age",
        "gender",
        "stress_level",
        "anxiety",
        "v120_risk",
        "v123_risk",
        "delta_v123_v120",
        "risk_level",
    ]
    available_ext_cols = [c for c in extreme_cols if c in extreme_30.columns]
    extreme_30[available_ext_cols].to_csv(
        docs_dir / "extreme_delta_cases.csv", index=False
    )

    # ============================================================
    # Generate report
    # ============================================================
    quant_str = " | ".join(
        f"P{p} = {fmt_num(quantiles[i])}"
        for i, p in enumerate([10, 25, 50, 75, 90])
    )

    exceed_rows = "\n".join(
        f"| |delta| > {t} | {exceed_counts[t]} | {exceed_pcts[t]}% |"
        for t in thresholds
    )

    report = f"""# v1.24 Delta Distribution Analysis Report

## Level 1 — Global Statistics

| Metric | Value |
|--------|-------|
| N (total samples) | {N} |
| Mean delta | {fmt_num(mean_d)} |
| Mean |delta| | {fmt_num(mean_abs)} |
| Std delta | {fmt_num(std_d)} |
| {quant_str} |

### Exceedance Summary

| Condition | Count | Proportion |
|-----------|-------|------------|
{exceed_rows}

---

## Level 2 — Delta by v1.20 Risk Level

{df_to_md(risk_grouped)}

---

## Level 3 — Delta by Severity Proxy

### By stress_level (PHQ-9 proxy)

> stress_level bins mapped from PHQ-9: stress = phq9 / 27 * 5

{df_to_md(stress_grouped)}

### By anxiety (GAD-7 proxy)

> anxiety bins mapped from GAD-7: anxiety = gad7 / 21 * 5

{df_to_md(anxiety_grouped)}

---

## Level 4 — Delta by Demographics

### By Age Group

{df_to_md(age_grouped)}

### By Gender

{df_to_md(gender_grouped)}

### By Source

{df_to_md(source_grouped) if not source_grouped.empty else "_source column not available_"}

---

## Level 5 — Extreme Cases

| Category | Count | % of Total |
|----------|-------|------------|
| |delta| > 30 | {n_extreme_30} | {fmt_num(n_extreme_30 / N * 100)}% |
| |delta| > 40 | {n_extreme_40} | {fmt_num(n_extreme_40 / N * 100)}% |
| Low → High (v120 ≤ 18, v123 ≥ 55) | {n_low_to_high} | {fmt_num(n_low_to_high / N * 100)}% |
| High → Low (v120 ≥ 55, v123 ≤ 18) | {n_high_to_low} | {fmt_num(n_high_to_low / N * 100)}% |

### Extreme case risk-level distribution (|delta| > 30)

{df_to_md(extreme_risk_dist)}

---

## Level 6 — Quintile Segment Recommendation

{df_to_md(quintile_grouped[["quintile", "score_range", "count", "mean_delta", "delta_std", "abs_mean_delta"]])}

---

## Output Files

| File | Description |
|------|-------------|
| `delta_by_risk_group.csv` | Delta statistics grouped by v1.20 risk level |
| `delta_by_feature_group.csv` | Delta statistics grouped by depression_binary |
| `extreme_delta_cases.csv` | Samples with |delta| > 30 |
"""

    (docs_dir / "delta_distribution_report.md").write_text(report, encoding="utf-8")

    print(f"Delta analysis complete (N={N})")
    print(f"Mean Abs Delta: {mean_abs:.2f}")
    print(f"  |d| > 15: {exceed_pcts[15]}%")
    print(f"  |d| > 20: {exceed_pcts[20]}%")
    print(f"  |d| > 30: {exceed_pcts[30]}%")
    print(f"  |d| > 40: {exceed_pcts[40]}%")
    print(f"Extreme cases (|d|>30): {n_extreme_30}")
    print(f"Low→High flips: {n_low_to_high}  High→Low flips: {n_high_to_low}")
    print(f"Reports saved to: {docs_dir}")


if __name__ == "__main__":
    main()
