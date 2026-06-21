"""v1.26 Phase 1: Decision Threshold Sweep.

Scans threshold values on the v1.25 lite model (no retraining) to find
the optimal decision boundary for recall-specificity trade-off.

Output:
  threshold_sweep_results.csv
  threshold_selection_report.md
  precision_recall_curve.png
  threshold_vs_recall_specificity.png
  selected_threshold_config.json
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import (
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
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
THRESHOLDS = [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]

MODEL_FEATURES: list[str] = [
    "gad7_score", "total_keywords", "unique_categories",
    "age", "gender", "cgpa",
    "kw_academic_pressure", "kw_sleep_problem", "kw_social_withdrawal",
    "kw_self_harm_crisis", "kw_exercise_deficit",
    "kw_low_mood", "kw_anxiety_somatic",
    "text_length", "chinese_ratio", "text_quality_flag", "coverage_density",
]


def youden_j(recall: float, specificity: float) -> float:
    return recall + specificity - 1.0


def main() -> None:
    features_path = TOP_ROOT / "data" / "processed" / "lite_features.csv"
    df = pd.read_csv(features_path)
    X = df[MODEL_FEATURES].astype(float).values
    y = df["phq9_binary"].astype(int).values

    _, X_test, _, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y
    )

    model = joblib.load(V125_MODEL_DIR / "mmpsy_lite_model.pkl")
    scaler = joblib.load(V125_MODEL_DIR / "mmpsy_lite_scaler.pkl")
    X_test_scaled = scaler.transform(X_test)
    y_proba = model.predict_proba(X_test_scaled)[:, 1]

    auc = roc_auc_score(y_test, y_proba)

    rows = []
    best_youden = -99.0
    best_recall_constrained = -99.0
    best_f1_val = -99.0
    best_youden_t = 0.50
    best_recall_constrained_t = 0.50
    best_f1_t = 0.50
    found_recall75 = False

    for t in THRESHOLDS:
        y_pred = (y_proba >= t).astype(int)
        rec = recall_score(y_test, y_pred)
        spec = recall_score(y_test, y_pred, pos_label=0)
        prec = precision_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)
        cm = confusion_matrix(y_test, y_pred)
        j = youden_j(rec, spec)

        rows.append({
            "threshold": t, "precision": round(prec, 4), "recall": round(rec, 4),
            "specificity": round(spec, 4), "f1": round(f1, 4),
            "youden_j": round(j, 4), "tn": int(cm[0, 0]), "fp": int(cm[0, 1]),
            "fn": int(cm[1, 0]), "tp": int(cm[1, 1]),
        })

        if j > best_youden:
            best_youden = j
            best_youden_t = t

        if rec >= 0.75 and spec >= 0.65:
            found_recall75 = True
            if f1 > best_recall_constrained:
                best_recall_constrained = f1
                best_recall_constrained_t = t

        if f1 > best_f1_val:
            best_f1_val = f1
            best_f1_t = t

    df_results = pd.DataFrame(rows)
    df_results.to_csv(SCRIPT_DIR / "threshold_sweep_results.csv", index=False)
    logger.info("Threshold sweep complete: %d thresholds", len(THRESHOLDS))

    if found_recall75:
        selected_t = best_recall_constrained_t
        selected_reason = (
            f"Recall≥0.75 且 Specificity≥0.65 的阈值中 F1 最高者 (t={selected_t})"
        )
    else:
        selected_t = best_youden_t
        selected_reason = (
            f"无阈值同时满足 Recall≥0.75 且 Specificity≥0.65，"
            f"退而选择 Youden J 最大点 (t={selected_t})。"
            f"建议进入 Phase 2 class_weight 训练。"
        )

    config = {
        "selected_threshold": selected_t,
        "selection_method": "recall75_constrained_f1" if found_recall75 else "youden_j",
        "rationale": selected_reason,
        "go_decision": "go" if found_recall75 else "conditional_go",
    }
    with open(SCRIPT_DIR / "selected_threshold_config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    report_lines = [
        "# v1.26 Threshold Selection Report",
        "",
        f"- AUC (threshold-independent): {auc:.4f}",
        f"- Thresholds scanned: {THRESHOLDS}",
        f"- Found Recall≥0.75 + Specificity≥0.65: {'YES' if found_recall75 else 'NO'}",
        "",
        "## Full sweep results",
        "",
        "| Threshold | Precision | Recall | Specificity | F1 | Youden J | TN | FP | FN | TP |",
        "|-----------|-----------|--------|-------------|-----|----------|----|----|----|----|",
    ]
    for r in rows:
        report_lines.append(
            f"| {r['threshold']:.2f} | {r['precision']:.4f} | {r['recall']:.4f} | "
            f"{r['specificity']:.4f} | {r['f1']:.4f} | {r['youden_j']:.4f} | "
            f"{r['tn']} | {r['fp']} | {r['fn']} | {r['tp']} |"
        )
    report_lines.append("")
    report_lines.append("## Key Points")
    report_lines.append("")
    report_lines.append(f"- **Youden J 最大**: t={best_youden_t:.2f} (J={best_youden:.4f})")
    report_lines.append(f"- **F1 最大**: t={best_f1_t:.2f} (F1={best_f1_val:.4f})")
    if found_recall75:
        report_lines.append(f"- **Recall≥0.75 约束下最优**: t={best_recall_constrained_t:.2f} (F1={best_recall_constrained:.4f})")
    report_lines.append("")
    report_lines.append("## Selected Threshold")
    report_lines.append(f"- **t = {selected_t:.2f}**")
    report_lines.append(f"- **理由**: {selected_reason}")
    report_lines.append(f"- **Go 决策**: {'GO ✅' if found_recall75 else 'CONDITIONAL-GO ⚠️'}")

    with open(SCRIPT_DIR / "threshold_selection_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    precisions, recalls, pr_thresholds = precision_recall_curve(y_test, y_proba)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    ax1 = axes[0]
    ax1.plot(recalls, precisions, "b-", linewidth=2, label="PR Curve")
    for r in rows:
        if r["threshold"] in [selected_t, best_youden_t, best_f1_t]:
            ax1.plot(r["recall"], r["precision"], "ro", markersize=8)
            ax1.annotate(f"t={r['threshold']:.2f}", (r["recall"], r["precision"]),
                         textcoords="offset points", xytext=(8, -12), fontsize=9)
    ax1.set_xlabel("Recall")
    ax1.set_ylabel("Precision")
    ax1.set_title(f"Precision-Recall Curve (AUC={auc:.4f})")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    ax2 = axes[1]
    ax2.plot([r["threshold"] for r in rows], [r["recall"] for r in rows],
             "b-o", label="Recall", linewidth=2)
    ax2.plot([r["threshold"] for r in rows], [r["specificity"] for r in rows],
             "r-s", label="Specificity", linewidth=2)
    ax2.axvline(x=selected_t, color="green", linestyle="--", label=f"Selected t={selected_t:.2f}")
    ax2.set_xlabel("Decision Threshold")
    ax2.set_ylabel("Score")
    ax2.set_title("Threshold vs Recall / Specificity")
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    ax2.invert_xaxis()

    plt.tight_layout()
    plt.savefig(SCRIPT_DIR / "precision_recall_curve.png", dpi=150)
    plt.savefig(SCRIPT_DIR / "threshold_vs_recall_specificity.png", dpi=150)

    if found_recall75:
        logger.info("GO: threshold=%.2f achieves Recall≥0.75, Specificity≥0.65", selected_t)
        logger.info("Phase 2 (class_weight training) can be SKIPPED.")
    else:
        logger.warning("CONDITIONAL-GO: no single threshold meets both constraints.")
        logger.warning("Phase 2 (class_weight training) is REQUIRED.")


if __name__ == "__main__":
    main()
