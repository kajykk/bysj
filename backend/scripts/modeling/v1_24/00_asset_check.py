"""v1.24 Phase 0: Asset Check Script.

Verifies all required assets exist and are readable before starting feature
construction and validation. Outputs a structured report to the planning docs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[4]

ASSETS: list[tuple[str, str]] = [
    ("v1.23 model", "backend/models/v1.23_external_lr/model.pkl"),
    ("v1.23 schema", "backend/models/v1.23_external_lr/feature_schema.json"),
    ("v1.23 ext metrics", "backend/models/v1.23_external_lr/external_validation_metrics.json"),
    ("v1.23 metrics", "backend/models/v1.23_external_lr/metrics.json"),
    ("v1.23 delta csv", "backend/models/v1.23_external_lr/model_delta_samples.csv"),
    ("mmpsy raw data", "data/external/mmpsy_scores.csv"),
    ("v1.20 model", "backend/models/artifacts/structured_v1.20/structured_model_v1.20.pkl"),
    ("model registry", "backend/app/core/model_registry.py"),
    ("model engine", "backend/app/core/model_engine.py"),
]

DELTA_CSV_EXPECTED_ROWS = 4318
DELTA_CSV_EXPECTED_MEAN_ABS = 21.29
DELTA_CSV_TOLERANCE = 0.5


def check_asset(name: str, rel_path: str) -> bool:
    abs_path = PROJECT_ROOT / rel_path
    return abs_path.exists() and abs_path.is_file()


def verify_delta_csv(rel_path: str) -> dict[str, object]:
    abs_path = PROJECT_ROOT / rel_path
    df = pd.read_csv(abs_path)

    rows_ok = len(df) == DELTA_CSV_EXPECTED_ROWS
    cols_ok = "delta_v123_v120" in df.columns
    mean_abs = float(df["delta_v123_v120"].abs().mean())

    if rows_ok and cols_ok:
        delta_ok = abs(mean_abs - DELTA_CSV_EXPECTED_MEAN_ABS) <= DELTA_CSV_TOLERANCE
    else:
        delta_ok = False

    return {
        "rows": len(df),
        "rows_ok": rows_ok,
        "cols": len(df.columns),
        "cols_ok": cols_ok,
        "mean_abs_delta": round(mean_abs, 2),
        "delta_ok": delta_ok,
        "ok": rows_ok and cols_ok and delta_ok,
    }


def main() -> None:
    output_dir = (
        PROJECT_ROOT
        / "docs"
        / "planning"
        / "v1.24-mmpsy-external-consistency-and-score-stability"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "asset_check_report.md"

    lines: list[str] = [
        "# v1.24 Phase 0: Asset Check Report",
        "",
        f"> Generated: {pd.Timestamp.now().isoformat(timespec='seconds')}",
        "",
        "| # | Asset | Path | Status | Note |",
        "|---|---|---|---|---|",
    ]

    passed = 0
    total = len(ASSETS)

    for idx, (name, rel_path) in enumerate(ASSETS, start=1):
        ok = check_asset(name, rel_path)
        status = "✅" if ok else "❌"
        note = ""

        if ok and name == "v1.23 delta csv":
            extra = verify_delta_csv(rel_path)
            ok = bool(extra["ok"])
            status = "✅" if ok else "❌"
            rows = extra["rows"]
            cols = extra["cols"]
            mad = extra["mean_abs_delta"]
            note = (
                f"rows={rows} ({'OK' if extra['rows_ok'] else 'EXPECTED ' + str(DELTA_CSV_EXPECTED_ROWS)}), "
                f"cols={cols}, mean_abs_delta={mad} "
                f"({'OK' if extra['delta_ok'] else 'expected ~' + str(DELTA_CSV_EXPECTED_MEAN_ABS)})"
            )

        if ok:
            passed += 1

        lines.append(f"| {idx} | {name} | `{rel_path}` | {status} | {note} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"**Summary**: {passed}/{total} assets verified.")

    if passed == total:
        lines.append("")
        lines.append("✅ All assets ready. Safe to proceed to Phase 1.")
    else:
        lines.append("")
        lines.append(
            f"⚠️ {total - passed} asset(s) missing or incorrect. "
            "Review before proceeding."
        )

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Asset check report written to: {report_path}")
    print(f"Result: {passed}/{total} passed")

    if passed != total:
        sys.exit(1)


if __name__ == "__main__":
    main()
