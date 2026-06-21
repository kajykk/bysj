"""v1.25 Phase 3: Ablation Study.

Runs 5 feature configurations through 5-Fold CV to isolate the contribution
of GAD-7 vs text keywords vs demographics. Uses Bootstrap AUC difference
test for pairwise comparisons with Bonferroni correction.

Output:
  docs/planning/v1.25-mmpsy-lite-risk-model/ablation_results.json
  docs/planning/v1.25-mmpsy-lite-risk-model/ablation_report.md
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    confusion_matrix,
    f1_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
RANDOM_STATE = 42
CV_SPLITS = 5
ALPHA = 0.05
ALPHA_CORRECTED = 0.005
N_BOOTSTRAP = 1000


def compute_bootstrap_p(
    df: pd.DataFrame,
    features_a: list[str],
    features_b: list[str],
    y: np.ndarray,
    n_bootstrap: int = N_BOOTSTRAP,
) -> float:
    """Bootstrap AUC difference test.

    H0: AUC(B) >= AUC(A)
    H1: AUC(A) > AUC(B)
    """
    Xa = df[features_a].values.astype(float)
    Xb = df[features_b].values.astype(float)
    n = len(y)

    cv = StratifiedKFold(n_splits=CV_SPLITS, shuffle=True, random_state=RANDOM_STATE)

    diff_observed = []
    for train_idx, val_idx in cv.split(Xa, y):
        scaler_a = StandardScaler().fit(Xa[train_idx])
        scaler_b = StandardScaler().fit(Xb[train_idx])
        Xa_val = scaler_a.transform(Xa[val_idx])
        Xb_val = scaler_b.transform(Xb[val_idx])
        model_a = LogisticRegression(
            C=1.0, max_iter=1000, class_weight="balanced", random_state=RANDOM_STATE
        ).fit(scaler_a.transform(Xa[train_idx]), y[train_idx])
        model_b = LogisticRegression(
            C=1.0, max_iter=1000, class_weight="balanced", random_state=RANDOM_STATE
        ).fit(scaler_b.transform(Xb[train_idx]), y[train_idx])
        auc_a = roc_auc_score(y[val_idx], model_a.predict_proba(Xa_val)[:, 1])
        auc_b = roc_auc_score(y[val_idx], model_b.predict_proba(Xb_val)[:, 1])
        diff_observed.append(auc_a - auc_b)

    diff_observed = np.array(diff_observed)

    rng = np.random.RandomState(RANDOM_STATE + 7)
    diff_bootstrap = []
    for _ in range(n_bootstrap):
        idx = rng.choice(n, n, replace=True)
        y_boot = y[idx]

        fold_diffs = []
        for train_idx, val_idx in cv.split(Xa, y_boot):
            scaler_a = StandardScaler().fit(Xa[train_idx])
            scaler_b = StandardScaler().fit(Xb[train_idx])
            Xa_val = scaler_a.transform(Xa[val_idx])
            Xb_val = scaler_b.transform(Xb[val_idx])
            model_a = LogisticRegression(
                C=1.0, max_iter=1000, class_weight="balanced", random_state=RANDOM_STATE
            ).fit(scaler_a.transform(Xa[train_idx]), y_boot[train_idx])
            model_b = LogisticRegression(
                C=1.0, max_iter=1000, class_weight="balanced", random_state=RANDOM_STATE
            ).fit(scaler_b.transform(Xb[train_idx]), y_boot[train_idx])
            auc_a = roc_auc_score(y_boot[val_idx], model_a.predict_proba(Xa_val)[:, 1])
            auc_b = roc_auc_score(y_boot[val_idx], model_b.predict_proba(Xb_val)[:, 1])
            fold_diffs.append(auc_a - auc_b)
        diff_bootstrap.append(np.mean(fold_diffs))

    diff_bootstrap = np.array(diff_bootstrap)
    p = max(1e-4, float((diff_bootstrap < 0).mean()))
    return p


def main() -> None:
    features_path = PROJECT_ROOT / "data" / "processed" / "lite_features.csv"
    if not features_path.exists():
        logger.error("lite_features.csv not found")
        sys.exit(1)

    df = pd.read_csv(features_path)

    feature_names_path = (
        PROJECT_ROOT
        / "backend"
        / "models"
        / "v1.25_mmpsy_lite"
        / "mmpsy_lite_feature_names.json"
    )
    if feature_names_path.exists():
        MODEL_FEATURES = json.loads(feature_names_path.read_text(encoding="utf-8"))
    else:
        MODEL_FEATURES = [
            "gad7_score", "total_keywords", "unique_categories",
            "age", "gender", "cgpa",
            "kw_academic_pressure", "kw_sleep_problem",
            "kw_social_withdrawal", "kw_self_harm_crisis",
            "kw_exercise_deficit", "kw_low_mood", "kw_anxiety_somatic",
            "text_length", "chinese_ratio",
            "text_quality_flag", "coverage_density",
        ]

    ab_configs = [
        {
            "id": "A",
            "name": "PHQ-9 Only (upper bound)",
            "features": ["phq9_score"],
        },
        {
            "id": "B",
            "name": "GAD-7 Only (anxiety baseline)",
            "features": ["gad7_score"],
        },
        {
            "id": "C",
            "name": "Text Keywords Only",
            "features": [
                "kw_academic_pressure", "kw_sleep_problem", "kw_social_withdrawal",
                "kw_self_harm_crisis", "kw_exercise_deficit", "kw_low_mood",
                "kw_anxiety_somatic", "total_keywords", "unique_categories",
            ],
        },
        {
            "id": "D",
            "name": "GAD-7 + Text (v1.25 core)",
            "features": [
                "gad7_score",
                "kw_academic_pressure", "kw_sleep_problem", "kw_social_withdrawal",
                "kw_self_harm_crisis", "kw_exercise_deficit", "kw_low_mood",
                "kw_anxiety_somatic", "total_keywords", "unique_categories",
            ],
        },
        {
            "id": "E",
            "name": "GAD-7 + Text + Demo (v1.25 full)",
            "features": MODEL_FEATURES,
        },
    ]

    y = df["phq9_binary"].values.astype(int)
    cv = StratifiedKFold(n_splits=CV_SPLITS, shuffle=True, random_state=RANDOM_STATE)

    results: dict = {}
    for cfg in ab_configs:
        cfg_id = cfg["id"]
        X = df[cfg["features"]].values.astype(float)

        folds_auc, folds_f1, folds_recall, folds_spec = [], [], [], []
        for train_idx, val_idx in cv.split(X, y):
            scaler = StandardScaler().fit(X[train_idx])
            X_train = scaler.transform(X[train_idx])
            X_val = scaler.transform(X[val_idx])

            model = LogisticRegression(
                C=1.0, max_iter=1000, class_weight="balanced",
                random_state=RANDOM_STATE,
            ).fit(X_train, y[train_idx])

            y_proba = model.predict_proba(X_val)[:, 1]
            y_pred = model.predict(X_val)

            folds_auc.append(roc_auc_score(y[val_idx], y_proba))
            folds_f1.append(f1_score(y[val_idx], y_pred))
            folds_recall.append(recall_score(y[val_idx], y_pred))
            tn, fp, fn, tp = confusion_matrix(y[val_idx], y_pred).ravel()
            spec = tn / (tn + fp) if (tn + fp) > 0 else 0.0
            folds_spec.append(spec)

        results[cfg_id] = {
            "name": cfg["name"],
            "features": cfg["features"],
            "metrics": {
                "auc": {"mean": round(float(np.mean(folds_auc)), 4),
                        "std": round(float(np.std(folds_auc)), 4)},
                "f1": {"mean": round(float(np.mean(folds_f1)), 4),
                       "std": round(float(np.std(folds_f1)), 4)},
                "recall": {"mean": round(float(np.mean(folds_recall)), 4),
                           "std": round(float(np.std(folds_recall)), 4)},
                "specificity": {"mean": round(float(np.mean(folds_spec)), 4),
                                "std": round(float(np.std(folds_spec)), 4)},
            },
        }

    comparisons = [("D", "B"), ("E", "B"), ("D", "C"), ("E", "C")]
    for a_id, b_id in comparisons:
        cfg_a = next(c for c in ab_configs if c["id"] == a_id)
        cfg_b = next(c for c in ab_configs if c["id"] == b_id)
        p = compute_bootstrap_p(df, cfg_a["features"], cfg_b["features"], y)
        sig = p < ALPHA_CORRECTED
        results[f"{a_id}_vs_{b_id}"] = {
            "p_value": round(float(p), 6),
            "alpha_corrected": ALPHA_CORRECTED,
            "significant": bool(sig),
        }
        logger.info("Bootstrap %s vs %s: p=%.6f sig=%s", a_id, b_id, p, sig)

    output_dir = (
        PROJECT_ROOT / "docs" / "planning" / "v1.25-mmpsy-lite-risk-model"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save JSON
    json_path = output_dir / "ablation_results.json"
    json_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Generate report
    report_path = output_dir / "ablation_report.md"
    lines: list[str] = [
        "# v1.25 Phase 3: Ablation Study Report",
        "",
        f"> Generated: {pd.Timestamp.now().isoformat(timespec='seconds')}",
        f"> CV: {CV_SPLITS}-Fold Stratified | Random State: {RANDOM_STATE}",
        "",
        "## 1. Per-Configuration Metrics (CV Mean ± Std)",
        "",
        "| ID | Config | AUC | F1 | Recall | Specificity |",
        "|---|---|---|---|---|---|",
    ]
    for cfg in ab_configs:
        m = results[cfg["id"]]["metrics"]
        lines.append(
            f"| {cfg['id']} | {cfg['name']} | "
            f"{m['auc']['mean']:.4f}±{m['auc']['std']:.4f} | "
            f"{m['f1']['mean']:.4f}±{m['f1']['std']:.4f} | "
            f"{m['recall']['mean']:.4f}±{m['recall']['std']:.4f} | "
            f"{m['specificity']['mean']:.4f}±{m['specificity']['std']:.4f} |"
        )
    lines.append("")

    lines.append("## 2. Pairwise Bootstrap Tests")
    lines.append("")
    lines.append(f"> α' = {ALPHA_CORRECTED} (Bonferroni: {ALPHA}/{len(comparisons)})")
    lines.append("")
    lines.append("| Comparison | p-value | α' | Significant |")
    lines.append("|---|---|---|---|")
    for comp_key, comp_data in results.items():
        if comp_key.startswith("D_") or comp_key.startswith("E_"):
            sig_mark = "✅" if comp_data["significant"] else "❌"
            lines.append(
                f"| {comp_key.replace('_', ' vs ')} | "
                f"{comp_data['p_value']} | {comp_data['alpha_corrected']} | "
                f"{sig_mark} |"
            )
    lines.append("")

    best_config = max(
        ab_configs, key=lambda c: results[c["id"]]["metrics"]["auc"]["mean"]
    )
    lines.append(f"**Best Config**: {best_config['id']} — {best_config['name']}")
    lines.append(f"**AUC**: {results[best_config['id']]['metrics']['auc']['mean']:.4f}")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Ablation report written to: %s", report_path)

    best_auc = results[best_config["id"]]["metrics"]["auc"]["mean"]
    logger.info(
        "Best: %s AUC=%.4f | D vs B p=%.6f | E vs B p=%.6f",
        best_config["id"], best_auc,
        results.get("D_vs_B", {}).get("p_value", float("nan")),
        results.get("E_vs_B", {}).get("p_value", float("nan")),
    )


if __name__ == "__main__":
    main()
