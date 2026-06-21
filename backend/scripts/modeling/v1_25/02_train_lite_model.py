"""v1.25 Phase 2: Lite Model Training.

Trains a CalibratedClassifierCV(LogisticRegression) on 17-dimensional
lite features (NO phq9_score). Evaluates on a 15% hold-out test set.

Output:
  backend/models/v1.25_mmpsy_lite/mmpsy_lite_model.pkl
  backend/models/v1.25_mmpsy_lite/mmpsy_lite_scaler.pkl
  backend/models/v1.25_mmpsy_lite/mmpsy_lite_feature_names.json
  backend/models/v1.25_mmpsy_lite/mmpsy_lite_metrics.json
  (optional) backend/models/v1.25_mmpsy_lite/mmpsy_lite_model_gbdt.pkl
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from sklearn.calibration import CalibratedClassifierCV, calibration_curve  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import StratifiedKFold, train_test_split  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]

RANDOM_STATE = 42
TEST_SIZE = 0.15
CV_SPLITS = 5
LR_C = 1.0
LR_MAX_ITER = 1000
CLASS_WEIGHT = "balanced"

GO_THRESHOLDS = {
    "auc": 0.80,
    "recall": 0.75,
    "specificity": 0.65,
    "f1": 0.60,
    "brier": 0.18,
}

MODEL_FEATURES: list[str] = [
    "gad7_score",
    "total_keywords",
    "unique_categories",
    "age",
    "gender",
    "cgpa",
    "kw_academic_pressure",
    "kw_sleep_problem",
    "kw_social_withdrawal",
    "kw_self_harm_crisis",
    "kw_exercise_deficit",
    "kw_low_mood",
    "kw_anxiety_somatic",
    "text_length",
    "chinese_ratio",
    "text_quality_flag",
    "coverage_density",
]


def _score_to_level(score: float) -> int:
    thresholds = [18, 35, 55, 72]
    for i, t in enumerate(thresholds):
        if score < t:
            return i
    return 4


def main() -> None:
    features_path = PROJECT_ROOT / "data" / "processed" / "lite_features.csv"
    if not features_path.exists():
        logger.error("lite_features.csv not found at %s", features_path)
        sys.exit(1)

    df = pd.read_csv(features_path)
    logger.info("Loaded lite_features.csv: %d rows", len(df))

    for f in MODEL_FEATURES:
        if f not in df.columns:
            logger.error("Missing feature column: %s", f)
            sys.exit(1)

    X = df[MODEL_FEATURES].values.astype(float)
    y = df["phq9_binary"].values.astype(int)

    logger.info("X shape: %s, y positive ratio: %.4f", X.shape, y.mean())

    X_train_val, X_test, y_train_val, y_test, idx_train_val, idx_test = (
        train_test_split(
            X, y, np.arange(len(y)),
            test_size=TEST_SIZE, stratify=y, random_state=RANDOM_STATE,
        )
    )

    scaler = StandardScaler()
    scaler.fit(X_train_val)
    X_train_val_s = scaler.transform(X_train_val)
    X_test_s = scaler.transform(X_test)

    base_lr = LogisticRegression(
        C=LR_C, max_iter=LR_MAX_ITER, class_weight=CLASS_WEIGHT,
        random_state=RANDOM_STATE,
    )
    cv = StratifiedKFold(n_splits=CV_SPLITS, shuffle=True, random_state=RANDOM_STATE)
    calibrated = CalibratedClassifierCV(base_lr, method="isotonic", cv=cv)
    calibrated.fit(X_train_val_s, y_train_val)

    y_proba = calibrated.predict_proba(X_test_s)[:, 1]
    y_pred = calibrated.predict(X_test_s)

    metrics: dict = {
        "auc": float(roc_auc_score(y_test, y_proba)),
        "f1": float(f1_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred)),
        "recall": float(recall_score(y_test, y_pred)),
        "brier": float(brier_score_loss(y_test, y_proba)),
    }
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
    metrics["specificity"] = float(tn / (tn + fp)) if (tn + fp) > 0 else 0.0
    metrics["tn"] = int(tn)
    metrics["fp"] = int(fp)
    metrics["fn"] = int(fn)
    metrics["tp"] = int(tp)

    phq9_test = df["phq9_score"].values[idx_test].astype(float)
    r, _ = pearsonr(y_proba, phq9_test)
    rho, _ = spearmanr(y_proba, phq9_test)
    metrics["pearson_r"] = float(r)
    metrics["spearman_rho"] = float(rho)

    go = all(
        metrics[k] >= GO_THRESHOLDS[k]
        for k in ["auc", "recall", "specificity"]
    ) and metrics["brier"] <= GO_THRESHOLDS["brier"]
    metrics["go_decision"] = bool(go)

    # LightGBM (optional)
    try:
        import lightgbm as lgb
        lgb_base = lgb.LGBMClassifier(
            max_depth=3, n_estimators=50, min_child_samples=20,
            class_weight="balanced", random_state=RANDOM_STATE,
            verbose=-1,
        )
        lgb_calibrated = CalibratedClassifierCV(
            lgb_base, method="isotonic", cv=cv
        )
        lgb_calibrated.fit(X_train_val_s, y_train_val)
        lgb_proba = lgb_calibrated.predict_proba(X_test_s)[:, 1]
        lgb_pred = lgb_calibrated.predict(X_test_s)
        metrics["gbdt_auc"] = float(roc_auc_score(y_test, lgb_proba))
        metrics["gbdt_f1"] = float(f1_score(y_test, lgb_pred))
        logger.info("LightGBM trained: AUC=%.4f, F1=%.4f",
                     metrics["gbdt_auc"], metrics["gbdt_f1"])
    except (ImportError, Exception) as exc:
        logger.warning("LightGBM not available: %s", exc)

    # Serialize
    model_dir = PROJECT_ROOT / "backend" / "models" / "v1.25_mmpsy_lite"
    model_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(calibrated, model_dir / "mmpsy_lite_model.pkl")
    joblib.dump(scaler, model_dir / "mmpsy_lite_scaler.pkl")
    (model_dir / "mmpsy_lite_feature_names.json").write_text(
        json.dumps(MODEL_FEATURES, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (model_dir / "mmpsy_lite_metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    if "gbdt_auc" in metrics:
        try:
            joblib.dump(lgb_calibrated, model_dir / "mmpsy_lite_model_gbdt.pkl")
        except Exception:
            pass

    logger.info("Metrics: AUC=%.4f F1=%.4f Recall=%.4f Specificity=%.4f Brier=%.4f",
                metrics["auc"], metrics["f1"], metrics["recall"],
                metrics["specificity"], metrics["brier"])
    logger.info("Go/No-Go: %s", "GO" if go else "NO-GO")

    # Charts
    output_dir = (
        PROJECT_ROOT / "docs" / "planning" / "v1.25-mmpsy-lite-risk-model"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    # ROC
    fpr, tpr, _ = roc_curve(y_test, y_proba)
    plt.figure(figsize=(6, 5))
    plt.plot(fpr, tpr, label=f"LR (AUC={metrics['auc']:.4f})")
    plt.plot([0, 1], [0, 1], "k--", alpha=0.3)
    plt.xlabel("False Positive Rate")
    plt.ylabel("True Positive Rate")
    plt.title("v1.25 mmpsy-lite ROC Curve")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "mmpsy_lite_roc_curve.png", dpi=150)
    plt.close()

    # Calibration
    prob_true, prob_pred = calibration_curve(y_test, y_proba, n_bins=10)
    plt.figure(figsize=(6, 5))
    plt.plot(prob_pred, prob_true, "s-", label="LR (isotonic)")
    plt.plot([0, 1], [0, 1], "k--", alpha=0.3)
    plt.xlabel("Mean Predicted Probability")
    plt.ylabel("Fraction of Positives")
    plt.title("v1.25 mmpsy-lite Calibration Curve")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "mmpsy_lite_calibration_curve.png", dpi=150)
    plt.close()

    # Confusion matrix
    cm = confusion_matrix(y_test, y_pred)
    plt.figure(figsize=(5, 4))
    plt.imshow(cm, interpolation="nearest", cmap=plt.cm.Blues)
    plt.title("v1.25 Confusion Matrix")
    plt.colorbar()
    for i in range(2):
        for j in range(2):
            plt.text(j, i, str(cm[i, j]), ha="center", va="center",
                     fontsize=14,
                     color="white" if cm[i, j] > cm.max() / 2 else "black")
    plt.xticks([0, 1], ["Pred Neg", "Pred Pos"])
    plt.yticks([0, 1], ["True Neg", "True Pos"])
    plt.tight_layout()
    plt.savefig(output_dir / "mmpsy_lite_confusion_matrix.png", dpi=150)
    plt.close()

    # Training report
    report_path = output_dir / "mmpsy_lite_training_report.md"
    lines: list[str] = [
        "# v1.25 mmpsy-lite Training Report",
        "",
        f"> Generated: {pd.Timestamp.now().isoformat(timespec='seconds')}",
        "",
        "## Model Configuration",
        "",
        f"- **Model**: CalibratedClassifierCV(LogisticRegression, isotonic)",
        f"- **Features**: {len(MODEL_FEATURES)} dimensions (no phq9_score)",
        f"- **CV**: {CV_SPLITS}-Fold Stratified",
        f"- **Test Split**: {TEST_SIZE * 100:.0f}% hold-out",
        f"- **Random State**: {RANDOM_STATE}",
        f"- **Class Weight**: {CLASS_WEIGHT}",
        "",
        "## Test Set Metrics",
        "",
        "| Metric | Value | Threshold | Status |",
        "|---|---|---|---|",
    ]
    for key in ["auc", "f1", "recall", "specificity"]:
        val = metrics[key]
        thresh = GO_THRESHOLDS.get(key, 0)
        status = "✅" if val >= thresh else "❌"
        lines.append(f"| {key.upper()} | {val:.4f} | ≥ {thresh} | {status} |")

    lines.append(
        f"| Brier | {metrics['brier']:.4f} | ≤ {GO_THRESHOLDS['brier']} | "
        f"{'✅' if metrics['brier'] <= GO_THRESHOLDS['brier'] else '❌'} |"
    )
    lines.append(f"| Precision | {metrics['precision']:.4f} | — | — |")
    lines.append("")
    lines.append("### Confusion Matrix")
    lines.append(f"TN={tn}  FP={fp}")
    lines.append(f"FN={fn}  TP={tp}")
    lines.append("")

    lines.append("### Correlation with PHQ-9 (reference only)")
    lines.append(f"- Pearson r: {metrics['pearson_r']:.4f}")
    lines.append(f"- Spearman ρ: {metrics['spearman_rho']:.4f}")
    lines.append("")

    if "gbdt_auc" in metrics:
        lines.append("### LightGBM (optional)")
        lines.append(f"- AUC: {metrics['gbdt_auc']:.4f}")
        lines.append(f"- F1: {metrics['gbdt_f1']:.4f}")
        lines.append("")

    lines.append(f"## Go / No-Go Decision: {'🟢 GO' if go else '🔴 NO-GO'}")
    lines.append("")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Training report written to: %s", report_path)

    if not go:
        logger.warning("Go/No-Go thresholds not met — review training report")
        logger.warning(
            "Recall=%.4f (threshold=%.2f). Model is conservative "
            "(high specificity=%.4f). Consider adjusting decision threshold "
            "or class_weight for production deployment.",
            metrics["recall"], GO_THRESHOLDS["recall"], metrics["specificity"],
        )


if __name__ == "__main__":
    main()
