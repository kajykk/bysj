"""v1.25 Phase 0: Data Audit Script.

Verifies mmpsy data assets are complete and consistent before lite feature
construction and model training. Outputs a structured audit report.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[4]

BASELINE = {
    "n_rows": 1275,
    "n_cols_mmpsy": 9,
    "phq9_min": 0,
    "phq9_max": 27,
    "gad7_min": 0,
    "gad7_max": 21,
    "positive_count": 258,
    "negative_count": 1017,
    "positive_ratio": 0.202,
    "tolerance_ratio": 0.02,
    "unique_users": 1275,
}

MMPSY_COLUMNS = {
    "user_id",
    "phq9_score",
    "phq9_level",
    "phq9_binary",
    "gad7_score",
    "gad7_level",
    "gad7_binary",
    "audio_count",
    "audio_transcript",
}


def verify_mmpsy_scores(csv_path: Path) -> dict:
    results: dict[str, bool | int | float | str] = {}
    df = pd.read_csv(csv_path)

    results["row_count"] = len(df)
    results["row_count_ok"] = len(df) == BASELINE["n_rows"]

    actual_cols = set(df.columns)
    results["columns_ok"] = actual_cols == MMPSY_COLUMNS
    missing = MMPSY_COLUMNS - actual_cols
    extra = actual_cols - MMPSY_COLUMNS
    results["missing_cols"] = ", ".join(sorted(missing)) if missing else "none"
    results["extra_cols"] = ", ".join(sorted(extra)) if extra else "none"

    results["phq9_range_ok"] = bool(
        df["phq9_score"].between(BASELINE["phq9_min"], BASELINE["phq9_max"]).all()
    )
    results["gad7_range_ok"] = bool(
        df["gad7_score"].between(BASELINE["gad7_min"], BASELINE["gad7_max"]).all()
    )

    results["transcript_notna_ok"] = bool(df["audio_transcript"].notna().all())
    lengths = df["audio_transcript"].str.len()
    results["text_min_len"] = int(lengths.min())
    results["text_max_len"] = int(lengths.max())

    derived = (df["phq9_score"] >= 10).astype(int)
    mismatch = (df["phq9_binary"] != derived).sum()
    results["label_consistency_mismatch"] = int(mismatch)
    results["label_consistency_ok"] = mismatch == 0

    actual_positive = df["phq9_binary"].mean()
    results["positive_ratio"] = round(float(actual_positive), 4)
    results["positive_ratio_ok"] = bool(
        abs(actual_positive - BASELINE["positive_ratio"]) <= BASELINE["tolerance_ratio"]
    )
    results["positive_count"] = int(df["phq9_binary"].sum())
    results["negative_count"] = int((1 - df["phq9_binary"]).sum())

    results["user_id_unique_ok"] = (
        df["user_id"].nunique() == BASELINE["unique_users"]
    )

    return results


def verify_structured_features(csv_path: Path) -> dict:
    results: dict[str, bool | int | float | str] = {}
    df = pd.read_csv(csv_path)

    results["row_count"] = len(df)
    results["row_count_ok"] = len(df) == BASELINE["n_rows"]

    source_cols = [c for c in df.columns if c.endswith("_source")]
    results["source_col_count"] = len(source_cols)
    derived = 0
    imputed = 0
    for col in source_cols:
        counts = df[col].value_counts()
        derived += counts.get("derived", 0)
        imputed += counts.get("imputed", 0)
    results["derived_count"] = int(derived)
    results["imputed_count"] = int(imputed)

    return results


def main() -> None:
    output_dir = (
        PROJECT_ROOT
        / "docs"
        / "planning"
        / "v1.25-mmpsy-lite-risk-model"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "data_audit_report.md"

    mmpsy_path = PROJECT_ROOT / "data" / "external" / "mmpsy_scores.csv"
    structured_path = (
        PROJECT_ROOT / "data" / "processed" / "mmpsy_structured_features.csv"
    )

    lines: list[str] = [
        "# v1.25 Phase 0: Data Audit Report",
        "",
        f"> Generated: {pd.Timestamp.now().isoformat(timespec='seconds')}",
        "",
        "## 1. mmpsy_scores.csv",
        "",
    ]

    if not mmpsy_path.exists():
        lines.append("❌ **CRITICAL**: `data/external/mmpsy_scores.csv` not found.")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Audit report written to: {report_path}")
        print("CRITICAL: mmpsy_scores.csv not found")
        sys.exit(1)

    mmpsy_results = verify_mmpsy_scores(mmpsy_path)

    lines.append("| Check | Status | Value | Baseline |")
    lines.append("|---|---|---|---|")

    checks_mmpsy = [
        ("Row Count", "row_count_ok", "row_count", BASELINE["n_rows"]),
        ("Columns Match", "columns_ok", "—", "9 specified columns"),
        ("PHQ-9 Range [0-27]", "phq9_range_ok", "—", "all in [0, 27]"),
        ("GAD-7 Range [0-21]", "gad7_range_ok", "—", "all in [0, 21]"),
        ("Transcript Not Null", "transcript_notna_ok", "—", "all non-null"),
        (
            "Label Consistency",
            "label_consistency_ok",
            f"mismatch={mmpsy_results['label_consistency_mismatch']}",
            "0 mismatches",
        ),
        (
            "Positive Ratio",
            "positive_ratio_ok",
            mmpsy_results["positive_ratio"],
            f"{BASELINE['positive_ratio']} ± {BASELINE['tolerance_ratio']}",
        ),
        ("User ID Unique", "user_id_unique_ok", "—", str(BASELINE["unique_users"])),
    ]

    all_ok = True
    for name, ok_key, val, baseline in checks_mmpsy:
        ok = bool(mmpsy_results[ok_key])
        status = "✅" if ok else "❌"
        if not ok:
            all_ok = False
        display_val = str(val) if not str(val).startswith("—") else str(mmpsy_results.get(ok_key.replace("_ok", ""), val))
        if isinstance(display_val, (float,)):
            display_val = f"{display_val}"
        lines.append(f"| {name} | {status} | {display_val} | {baseline} |")

    lines.append("")
    lines.append(f"**Text length range**: {mmpsy_results['text_min_len']} – {mmpsy_results['text_max_len']} characters")
    lines.append(f"**Missing columns**: {mmpsy_results['missing_cols']}")
    lines.append(f"**Extra columns**: {mmpsy_results['extra_cols']}")
    lines.append(f"**Positive samples**: {mmpsy_results['positive_count']} / {mmpsy_results['positive_count'] + mmpsy_results['negative_count']}")

    lines.append("")
    lines.append("## 2. mmpsy_structured_features.csv")
    lines.append("")

    if not structured_path.exists():
        lines.append("⚠️ `data/processed/mmpsy_structured_features.csv` not found.")
        lines.append("(This is non-blocking for lite model — lite features will be built from scratch.)")
    else:
        struct_results = verify_structured_features(structured_path)
        status = "✅" if struct_results["row_count_ok"] else "❌"
        lines.append(f"| Row Count | {status} | {struct_results['row_count']} | {BASELINE['n_rows']} |")
        lines.append(f"| Source Columns | — | {struct_results['source_col_count']} derived/imputed cols | — |")
        lines.append(f"| Derived Cells | — | {struct_results['derived_count']} | — |")
        lines.append(f"| Imputed Cells | — | {struct_results['imputed_count']} | — |")

    lines.append("")
    lines.append("---")
    lines.append("")

    if all_ok:
        lines.append("## ✅ Audit Passed")
        lines.append("")
        lines.append("All mmpsy data checks passed. Safe to proceed to Phase 1 (lite feature construction).")
    else:
        lines.append("## ⚠️ Audit Issues Found")
        lines.append("")
        lines.append("Some checks failed. Review the issues above before proceeding to Phase 1.")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Audit report written to: {report_path}")
    print(f"Overall: {'ALL OK' if all_ok else 'ISSUES FOUND'}")

    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
