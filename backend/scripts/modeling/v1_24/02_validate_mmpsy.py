"""v1.24 Phase 2: Validate v1.23 on mmpsy structured features.

Runs constrained external validation: applies the v1.23 pipeline to mmpsy
derived features, computes metrics against phq9_binary ground truth,
and generates a 3-feature subset baseline for comparison.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import cross_val_score
from sklearn.calibration import calibration_curve
from scipy.stats import pearsonr, spearmanr

PROJECT_ROOT = Path(__file__).resolve().parents[4]

COLOR_PRIMARY = "#409eff"
COLOR_REFERENCE = "#c0c4cc"
FIG_DPI = 150


def main() -> None:
    features_path = PROJECT_ROOT / "data" / "processed" / "mmpsy_structured_features.csv"
    model_path = (
        PROJECT_ROOT
        / "backend"
        / "models"
        / "v1.23_external_lr"
        / "model.pkl"
    )
    raw_path = PROJECT_ROOT / "data" / "external" / "mmpsy_scores.csv"

    docs_dir = (
        PROJECT_ROOT
        / "docs"
        / "planning"
        / "v1.24-mmpsy-external-consistency-and-score-stability"
    )
    docs_dir.mkdir(parents=True, exist_ok=True)

    df_features = pd.read_csv(features_path)
    pipeline = joblib.load(model_path)
    feature_names = list(pipeline.feature_names_in_)

    X = df_features[feature_names]
    df_raw = pd.read_csv(raw_path)
    y_true = df_raw["phq9_binary"].values

    y_prob = pipeline.predict_proba(X)[:, 1]
    y_pred = pipeline.predict(X)

    # -- main metrics --
    auc = float(roc_auc_score(y_true, y_prob))
    prec, rec, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="binary", zero_division=0
    )
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    spec = float(tn / (tn + fp)) if (tn + fp) > 0 else 0.0

    # -- correlations --
    phq9_scores = df_raw["phq9_score"].values
    gad7_scores = df_raw["gad7_score"].values
    pear_r, pear_p = pearsonr(y_prob, phq9_scores)
    spear_rho, spear_p = spearmanr(y_prob, gad7_scores)

    # -- high-risk recall --
    high_mask = y_true == 1
    high_recall = float(y_pred[high_mask].mean()) if high_mask.sum() > 0 else 0.0

    # -- 3-feature subset baseline --
    subset_cols = ["stress_level", "anxiety", "panic_attack"]
    X_3 = df_features[subset_cols].values
    try:
        cv_scores = cross_val_score(
            LogisticRegression(solver="liblinear", random_state=42),
            X_3,
            y_true,
            cv=5,
            scoring="roc_auc",
        )
        auc_3f = float(cv_scores.mean())
    except Exception:
        auc_3f = float("nan")

    auc_gap = round(auc - auc_3f, 4) if not np.isnan(auc_3f) else float("nan")

    # -- feature coverage --
    derived_count = sum(
        1 for c in feature_names
        if f"{c}_source" in df_features.columns and df_features[f"{c}_source"].iloc[0] == "derived"
    )
    coverage_pct = round(derived_count / len(feature_names) * 100, 1)

    # ---- save metrics JSON ----
    metrics = {
        "dataset": "mmpsy",
        "samples": len(df_features),
        "feature_coverage_pct": coverage_pct,
        "constrained": True,
        "auc": auc,
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "specificity": spec,
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "pearson_r": round(float(pear_r), 4),
        "pearson_p": round(float(pear_p), 6),
        "spearman_rho": round(float(spear_rho), 4),
        "spearman_p": round(float(spear_p), 6),
        "high_risk_recall": round(high_recall, 4),
        "subset_3feature_auc": round(auc_3f, 4),
        "auc_gap_12vs3": auc_gap,
    }
    (docs_dir / "mmpsy_external_validation_metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # ---- charts ----
    fpr, tpr, _ = roc_curve(y_true, y_prob)
    plt.figure(figsize=(6, 5))
    plt.plot(fpr, tpr, color=COLOR_PRIMARY, lw=2, label=f"AUC = {auc:.4f}")
    plt.plot([0, 1], [0, 1], color=COLOR_REFERENCE, lw=1, linestyle="--")
    plt.xlim([0.0, 1.0])
    plt.ylim([0.0, 1.05])
    plt.xlabel("False Positive Rate")
    plt.ylabel("True Positive Rate")
    plt.title("mmpsy Constrained External Validation — ROC")
    plt.legend(loc="lower right")
    plt.tight_layout()
    plt.savefig(docs_dir / "mmpsy_roc_curve.png", dpi=FIG_DPI)
    plt.close()

    prob_true, prob_pred = calibration_curve(y_true, y_prob, n_bins=10)
    plt.figure(figsize=(6, 5))
    plt.plot(prob_pred, prob_true, marker="o", color=COLOR_PRIMARY, lw=2, label="v1.23 on mmpsy")
    plt.plot([0, 1], [0, 1], color=COLOR_REFERENCE, lw=1, linestyle="--", label="Perfect")
    plt.xlim([0.0, 1.0])
    plt.ylim([0.0, 1.0])
    plt.xlabel("Mean Predicted Probability")
    plt.ylabel("Fraction of Positives")
    plt.title("mmpsy Constrained External Validation — Calibration")
    plt.legend(loc="lower right")
    plt.tight_layout()
    plt.savefig(docs_dir / "mmpsy_calibration_curve.png", dpi=FIG_DPI)
    plt.close()

    # ---- report ----
    gap_note = ""
    if not np.isnan(auc_gap):
        if auc_gap > 0.01:
            gap_note = " (imputed features may provide weak signal)"
        elif auc_gap < -0.01:
            gap_note = " (imputed features may introduce noise → regression-to-mean)"
        else:
            gap_note = " (imputed features contribute negligibly)"

    constrained_note = (
        f"⚠️ This is a **constrained external validation**. "
        f"Only {derived_count}/{len(feature_names)} ({coverage_pct}%) features "
        f"were rule-derived from mmpsy fields; the remaining "
        f"{len(feature_names) - derived_count} were filled with training-set medians."
    )

    report = f"""# mmpsy Constrained External Validation Report

{constrained_note}

## Key Metrics

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Binary AUC | {auc:.4f} | ≥ 0.80 | {"✅" if auc >= 0.80 else "⚠️"} |
| Recall (Sensitivity) | {rec:.4f} | ≥ 0.70 | {"✅" if rec >= 0.70 else "⚠️"} |
| Specificity | {spec:.4f} | ≥ 0.60 | {"✅" if spec >= 0.60 else "⚠️"} |
| F1 Score | {f1:.4f} | — | — |
| High-Risk Recall | {high_recall:.4f} | ≥ 0.75 | {"✅" if high_recall >= 0.75 else "⚠️"} |
| Pearson r (vs PHQ-9) | {pear_r:.4f} | ≥ 0.50 | {"✅" if pear_r >= 0.50 else "⚠️"} |
| Spearman ρ (vs GAD-7) | {spear_rho:.4f} | ≥ 0.50 | {"✅" if spear_rho >= 0.50 else "⚠️"} |

## Confusion Matrix

|  | Predicted Negative | Predicted Positive |
|--|-------------------|-------------------|
| Actual Negative | TN = {tn} | FP = {fp} |
| Actual Positive | FN = {fn} | TP = {tp} |

## Subset Baseline (3 derived features only)

| Metric | Value |
|--------|-------|
| 3-feature 5-fold CV AUC | {auc_3f:.4f} |
| AUC gap (12f − 3f) | {auc_gap:.4f}{gap_note} |

## Figures

![ROC Curve](mmpsy_roc_curve.png)
![Calibration Curve](mmpsy_calibration_curve.png)
"""

    (docs_dir / "mmpsy_external_validation_report.md").write_text(report, encoding="utf-8")

    print(f"AUC: {auc:.4f}")
    print(f"Recall: {rec:.4f}  Specificity: {spec:.4f}  F1: {f1:.4f}")
    print(f"Pearson r: {pear_r:.4f}  Spearman rho: {spear_rho:.4f}")
    print(f"High-risk recall: {high_recall:.4f}")
    print(f"3-feature AUC: {auc_3f:.4f}  Gap: {auc_gap}")
    print(f"Reports saved to: {docs_dir}")


if __name__ == "__main__":
    main()
