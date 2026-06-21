"""v1.26 Phase 3: Routing Stability Evaluation.

Tests the four routing paths (structured/lite/anxiety_only/insufficient)
with both synthetic and real test cases to verify routing correctness.

Output:
  routing_stability_report.md
  routing_distribution_snapshot.csv
  routing_edge_cases.csv
  routing_policy_v1_26.json
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).resolve().parent
TOP_ROOT = Path(__file__).resolve().parents[4]

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

EXPECTED_STRUCTURED_FIELDS = [
    "age", "gender", "cgpa", "sleep_duration",
    "exercise_frequency", "social_support", "stress_level",
    "anxiety", "family_history", "panic_attack",
    "treatment_seeking", "academic_pressure",
    "financial_pressure", "study_year",
]


def verify_routing_info(ri: dict | None, path_name: str, expected_family: str) -> list[str]:
    issues: list[str] = []
    if ri is None:
        issues.append(f"{path_name}: routing_info is None")
        return issues
    for field in ["selected_model_id", "selected_model_family", "routing_reason",
                  "feature_coverage_ratio", "prediction_confidence_band"]:
        if field not in ri:
            issues.append(f"{path_name}: missing field '{field}' in routing_info")
    actual_family = ri.get("selected_model_family")
    if actual_family != expected_family:
        issues.append(f"{path_name}: expected family='{expected_family}', got '{actual_family}'")
    return issues


async def main() -> None:
    from app.core.model_engine import ModelEngine
    engine = ModelEngine()

    test_cases: list[dict] = []

    test_cases.append({
        "name": "full_structured",
        "expected_family": "structured",
        "expected_band": "high",
        "features": {
            "age": 22, "gender": 1, "cgpa": 3.2, "sleep_duration": 7,
            "exercise_frequency": 3, "social_support": 4, "stress_level": 6,
            "anxiety": 8, "family_history": 0, "panic_attack": 1,
            "treatment_seeking": 0, "academic_pressure": 7,
            "financial_pressure": 5, "study_year": 3,
            "gad7_score": 15, "phq9_score": 18,
            "audio_transcript": "失眠睡不着考试压力大心情差" * 5,
        },
    })

    test_cases.append({
        "name": "full_structured_no_text",
        "expected_family": "structured",
        "expected_band": "high",
        "features": {
            "age": 22, "gender": 1, "cgpa": 3.2, "sleep_duration": 7,
            "exercise_frequency": 3, "social_support": 4, "stress_level": 6,
            "anxiety": 8, "family_history": 0, "panic_attack": 1,
            "treatment_seeking": 0, "academic_pressure": 7,
            "financial_pressure": 5, "study_year": 3,
            "gad7_score": 15, "phq9_score": 18,
        },
    })

    test_cases.append({
        "name": "lite_gad7_text",
        "expected_family": "lite",
        "expected_band": "medium",
        "features": {
            "gad7_score": 15,
            "audio_transcript": "失眠睡不着考试压力大心情差很难过" * 3,
        },
    })

    test_cases.append({
        "name": "anxiety_only",
        "expected_family": "anxiety_only",
        "expected_band": "low",
        "features": {"gad7_score": 15},
    })

    test_cases.append({
        "name": "insufficient",
        "expected_family": "insufficient",
        "expected_band": None,
        "features": {},
    })

    # Edge case: text too short
    test_cases.append({
        "name": "lite_short_text_fallback",
        "expected_family": "anxiety_only",
        "expected_band": "low",
        "features": {"gad7_score": 15, "audio_transcript": "a"},
    })

    # Edge case: text exactly 20 chars
    test_cases.append({
        "name": "lite_text_20_chars",
        "expected_family": "lite",
        "expected_band": "medium",
        "features": {"gad7_score": 15, "audio_transcript": "失眠睡不着考试压力太大心情很差非常难过啊"},
    })

    # Edge case: text 19 chars
    test_cases.append({
        "name": "lite_text_19_chars",
        "expected_family": "anxiety_only",
        "expected_band": "low",
        "features": {"gad7_score": 15, "audio_transcript": "失眠睡不着考试压力"},
    })

    all_issues: list[str] = []
    family_counts: dict[str, int] = {"structured": 0, "lite": 0, "anxiety_only": 0, "insufficient": 0}
    edge_cases: list[dict] = []

    for tc in test_cases:
        result = await engine.predict_structured(tc["features"])
        ri = result.get("routing_info")
        issues = verify_routing_info(ri, tc["name"], tc["expected_family"])
        all_issues.extend(issues)

        actual_family = ri.get("selected_model_family") if ri else None
        actual_band = ri.get("prediction_confidence_band") if ri else None

        if actual_family:
            family_counts[actual_family] = family_counts.get(actual_family, 0) + 1

        if actual_family != tc["expected_family"]:
            edge_cases.append({
                "name": tc["name"],
                "expected_family": tc["expected_family"],
                "actual_family": actual_family,
                "actual_band": actual_band,
                "coverage": ri.get("feature_coverage_ratio") if ri else None,
            })

        status = "PASS" if not issues else "FAIL"
        logger.info("[%s] %s → family=%s band=%s", status, tc["name"], actual_family, actual_band)

    # Real data samples
    logger.info("Testing with real mmpsy samples …")
    struct_path = TOP_ROOT / "data" / "raw" / "mmpsy_structured_features.csv"
    if struct_path.exists():
        df_struct = pd.read_csv(struct_path)
        sample = df_struct.head(20).to_dict(orient="records")
        for i, row in enumerate(sample):
            row_clean = {k: v for k, v in row.items() if not (isinstance(v, float) and np.isnan(v))}
            n_expected = sum(1 for f in EXPECTED_STRUCTURED_FIELDS if f in row_clean)
            result = await engine.predict_structured(row_clean)
            ri = result.get("routing_info")
            family = ri.get("selected_model_family") if ri else "unknown"
            family_counts[family] = family_counts.get(family, 0) + 1
    else:
        logger.warning("mmpsy_structured_features.csv not found — skipping real data test")

    dist_df = pd.DataFrame([
        {"family": k, "count": v, "ratio": round(v / sum(family_counts.values()), 3) if sum(family_counts.values()) > 0 else 0}
        for k, v in family_counts.items()
    ])
    dist_df.to_csv(SCRIPT_DIR / "routing_distribution_snapshot.csv", index=False)

    edge_df = pd.DataFrame(edge_cases)
    if not edge_df.empty:
        edge_df.to_csv(SCRIPT_DIR / "routing_edge_cases.csv", index=False)

    policy = {
        "routing_thresholds": {"feature_coverage": 0.80, "lite_min_text_length": 20},
        "routes": ["structured", "lite", "anxiety_only", "insufficient"],
        "notes": [
            "structured route requires >=80% of 14 expected structured fields",
            "lite route requires GAD-7 + text >=20 chars",
            "anxiety_only route is GAD-7 only fallback (heuristic GAD-7 × 1.29)",
            "insufficient route means no usable input features",
        ],
    }
    with open(SCRIPT_DIR / "routing_policy_v1_26.json", "w", encoding="utf-8") as f:
        json.dump(policy, f, indent=2, ensure_ascii=False)

    ok = len(all_issues) == 0
    report_lines = [
        "# v1.26 Routing Stability Report",
        "",
        f"- Test cases: {len(test_cases)}",
        f"- Issues found: {len(all_issues)}",
        f"- Result: {'✅ STABLE' if ok else '⚠️ ISSUES FOUND'}",
        "",
        "## Family Distribution",
    ]
    for _, d_row in dist_df.iterrows():
        report_lines.append(f"- {d_row['family']}: {d_row['count']} ({d_row['ratio']})")
    report_lines.append("")
    if all_issues:
        report_lines.append("## Issues")
        for issue in all_issues:
            report_lines.append(f"- {issue}")
    if edge_cases:
        report_lines.append("")
        report_lines.append("## Edge Cases")
        for ec in edge_cases:
            report_lines.append(f"- {ec['name']}: expected {ec['expected_family']}, actual {ec['actual_family']}")

    with open(SCRIPT_DIR / "routing_stability_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    if not ok:
        logger.error("Routing stability check found %d issues.", len(all_issues))
        sys.exit(1)

    logger.info("Routing stability evaluation PASSED.")


if __name__ == "__main__":
    asyncio.run(main())
