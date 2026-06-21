"""v1.26 Phase 0: Baseline Reproduction.

Loads the v1.25 lite model and reproduces test-set metrics to verify
that results are stable and reproducible before optimization.

Output:
  v1_26_baseline_metrics.json
  v1_26_baseline_reproduction_report.md
  v1_25_test_split_snapshot.csv
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TOP_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_DIR = Path(__file__).resolve().parent
RANDOM_STATE = 42
TEST_SIZE = 0.15

V125_MODEL_DIR = PROJECT_ROOT / "models" / "v1.25_mmpsy_lite"

MODEL_FEATURES: list[str] = [
    "gad7_score", "total_keywords", "unique_categories",
    "age", "gender", "cgpa",
    "kw_academic_pressure", "kw_sleep_problem", "kw_social_withdrawal",
    "kw_self_harm_crisis", "kw_exercise_deficit",
    "kw_low_mood", "kw_anxiety_somatic",
    "text_length", "chinese_ratio", "text_quality_flag", "coverage_density",
]

V125_METRICS = {
    "auc": 0.9380,
    "recall": 0.6667,
    "specificity": 0.9673,
    "f1": 0.7429,
    "precision": 0.8387,
    "brier": 0.0710,
}

TOLERANCE = {"auc": 0.01, "recall": 0.03, "specificity": 0.03, "f1": 0.05, "precision": 0.05, "brier": 0.02}


def main() -> None:
    features_path = TOP_ROOT / "data" / "processed" / "lite_features.csv"
    if not features_path.exists():
        logger.error("lite_features.csv not found at %s", features_path)
        sys.exit(1)

    model_path = V125_MODEL_DIR / "mmpsy_lite_model.pkl"
    scaler_path = V125_MODEL_DIR / "mmpsy_lite_scaler.pkl"
    for p, label in [(model_path, "model"), (scaler_path, "scaler")]:
        if not p.exists():
            logger.warning("%s not found at %s — skipping loaded-model check", label, p)

    logger.info("Loading lite_features.csv …")
    df = pd.read_csv(features_path)

    for col in MODEL_FEATURES:
        if col not in df.columns:
            logger.error("Missing feature column: %s", col)
            sys.exit(1)

    X = df[MODEL_FEATURES].astype(float).values
    y = df["phq9_binary"].astype(int).values
    user_ids = df["user_id"].values

    logger.info("Splitting: test_size=%.2f, random_state=%d, stratify=phq9_binary", TEST_SIZE, RANDOM_STATE)
    _, X_test, _, y_test, _, ids_test = train_test_split(
        X, y, user_ids, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y
    )
    n_test = len(y_test)
    n_pos = y_test.sum()
    logger.info("Test set: %d samples, positive rate = %d/%d = %.1f%%", n_test, n_pos, n_test, 100 * n_pos / n_test)

    snapshot_path = SCRIPT_DIR / "v1_25_test_split_snapshot.csv"
    pd.DataFrame({"user_id": ids_test, "phq9_binary": y_test}).to_csv(snapshot_path, index=False)
    logger.info("Saved test-split snapshot → %s", snapshot_path)

    logger.info("Loading v1.25 model + scaler …")
    model = joblib.load(model_path)
    scaler = joblib.load(scaler_path)

    X_test_scaled = scaler.transform(X_test)
    y_proba = model.predict_proba(X_test_scaled)[:, 1]
    y_pred = model.predict(X_test_scaled)

    metrics = {
        "auc": round(float(roc_auc_score(y_test, y_proba)), 4),
        "recall": round(float(recall_score(y_test, y_pred)), 4),
        "specificity": round(float(recall_score(y_test, y_pred, pos_label=0)), 4),
        "f1": round(float(f1_score(y_test, y_pred)), 4),
        "precision": round(float(precision_score(y_test, y_pred)), 4),
        "brier": round(float(brier_score_loss(y_test, y_proba)), 4),
    }

    metrics["confusion_matrix"] = confusion_matrix(y_test, y_pred).tolist()

    comparison = []
    all_ok = True
    for k, v125_val in V125_METRICS.items():
        v126_val = metrics[k]
        delta = abs(v126_val - v125_val)
        tol = TOLERANCE[k]
        ok = delta <= tol
        if not ok:
            all_ok = False
        comparison.append({
            "metric": k, "v1_25": v125_val, "v1_26_repro": v126_val,
            "delta": round(delta, 4), "tolerance": tol, "pass": ok,
        })

    logger.info("Metrics: %s", json.dumps(metrics, indent=2))

    metrics_path = SCRIPT_DIR / "v1_26_baseline_metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump({"metrics": metrics, "comparison": comparison, "all_pass": all_ok}, f, indent=2, ensure_ascii=False)
    logger.info("Saved metrics → %s", metrics_path)

    report_lines = [
        "# v1.26 Baseline Reproduction Report",
        "",
        f"- Test samples: {n_test}",
        f"- Positive rate: {n_pos}/{n_test} = {100*n_pos/n_test:.1f}%",
        "",
        "| Metric | v1.25 | v1.26 Reproduced | Delta | Tolerance | Pass |",
        "|--------|-------|-----------------|-------|-----------|------|",
    ]
    for c in comparison:
        report_lines.append(
            f"| {c['metric']} | {c['v1_25']} | {c['v1_26_repro']} | {c['delta']} | {c['tolerance']} | {'✅' if c['pass'] else '❌'} |"
        )
    report_lines.append("")
    report_lines.append(f"**Overall**: {'✅ ALL PASS' if all_ok else '❌ DEVIATION DETECTED — review required'}")

    report_path = SCRIPT_DIR / "v1_26_baseline_reproduction_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    logger.info("Saved report → %s", report_path)

    if not all_ok:
        logger.error("Baseline reproduction failed — deviation exceeds tolerance.")
        sys.exit(1)

    logger.info("Baseline reproduction PASSED. Ready for Phase 1 threshold sweep.")


if __name__ == "__main__":
    main()
