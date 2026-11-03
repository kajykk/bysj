#!/usr/bin/env python
"""ROUND_46 P0-3: structured source-held-out validation + feature ablation.

Why this exists
---------------
The production v1.23 structured model was trained on Kaggle + 408 Mendeley rows.
Its internal test contains 137 different Mendeley rows, so "cross-source" reads
from that test are contaminated by same-source training. This script builds a
clean source-held-out candidate: train on all Kaggle, test on all 682 Mendeley.

It also quantifies:
- the production model's same-source optimism (seen 408 vs unseen 137 rows);
- whether dropping redundant / target-constant features helps transfer;
- correlation between predicted probability and PHQ-9 total (an ordinal severity
  signal never used as a training label for the Kaggle model);
- the reverse direction (Mendeley -> Kaggle), as a low-power stress test.

Boundary: Kaggle labels are self-reported binary; Mendeley labels are PHQ-9 >= 10.
The source shift therefore conflates covariate shift and label-definition shift.
Neither direction is a prospective external validation.

Read-only. No model artifact, threshold, or production behavior is modified.

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/modeling/eval/v1_46/03_source_holdout.py
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[3]
PROJECT_ROOT = BACKEND.parent
for path in (BACKEND, HERE, PROJECT_ROOT / "scripts" / "ml_training"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from model_card_lib import (  # noqa: E402
    _core_metrics,
    _discrimination,
    apply_platt,
    at_risk_cut,
    bootstrap_metrics,
    fit_platt,
    model_card,
)


def _load_model_cards_module():
    spec = importlib.util.spec_from_file_location("round46_model_cards", HERE / "01_model_cards.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


MC = _load_model_cards_module()

FEATURES = list(MC.FEATURES)
DATA = PROJECT_ROOT / "data"
OUT_JSON = HERE / "source_holdout.json"
MIRROR_JSON = PROJECT_ROOT / "outputs" / "candidates" / "round46" / "source_holdout.json"
REPORT_MD = PROJECT_ROOT / "outputs" / "ROUND_46_SOURCE_HOLDOUT.md"

BOOTSTRAP_MAIN = 5000
BOOTSTRAP_AUX = 2000
PAIRED_B = 2000
SEED = 42

ABLATIONS: dict[str, list[str]] = {
    "full_12": FEATURES,
    "drop_social_support": [f for f in FEATURES if f != "social_support"],
    "drop_stress_duplicate": [f for f in FEATURES if f != "stress_level"],
    "drop_anxiety": [f for f in FEATURES if f != "anxiety"],
    "drop_anxiety_and_duplicate": [
        f for f in FEATURES if f not in ("stress_level", "anxiety")
    ],
    "drop_target_constant": [
        f for f in FEATURES if f not in ("social_support", "family_history", "panic_attack", "cgpa")
    ],
    "minimal_7": [
        f
        for f in FEATURES
        if f
        not in ("social_support", "family_history", "panic_attack", "cgpa", "stress_level")
    ],
}


def _finite(obj):
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_finite(v) for v in obj]
    if isinstance(obj, (np.floating, np.integer)):
        return _finite(obj.item())
    return obj


def make_pipeline() -> Pipeline:
    """Same preprocessing + LR hyperparameters as production v1.23."""
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(C=1.0, max_iter=2000, random_state=SEED),
            ),
        ]
    )


def fit_predict(train: pd.DataFrame, test: pd.DataFrame, features: list[str], label_col: str):
    pipe = make_pipeline()
    pipe.fit(train[features], train[label_col].to_numpy(dtype=np.int64))
    return pipe, pipe.predict_proba(test[features])[:, 1]


def evaluate(y, p, *, bootstrap_B: int = BOOTSTRAP_AUX) -> dict:
    card = model_card(y, p, threshold=0.5, cuts=(), target_prevalences=(0.15,))
    boot = bootstrap_metrics(y, p, threshold=0.5, B=bootstrap_B, seed=SEED)
    return {"card": card, "bootstrap": boot}


def paired_delta(
    y,
    p_a,
    p_b,
    *,
    B: int = PAIRED_B,
    seed: int = SEED,
) -> dict:
    """Paired percentile bootstrap for metric differences on identical rows."""
    y = np.asarray(y, dtype=np.float64)
    p_a = np.asarray(p_a, dtype=np.float64)
    p_b = np.asarray(p_b, dtype=np.float64)
    rng = np.random.RandomState(seed)
    keys = ("auroc", "auprc", "brier", "f1")
    samples = {k: [] for k in keys}
    n = y.size

    def _metrics(yb, pa, pb):
        disc_a, disc_b = _discrimination(yb, pa), _discrimination(yb, pb)
        core_a, core_b = _core_metrics(yb, pa, 0.5), _core_metrics(yb, pb, 0.5)
        return {
            "auroc": disc_a["auroc"] - disc_b["auroc"],
            "auprc": disc_a["auprc"] - disc_b["auprc"],
            "brier": brier_score_loss(yb, pa) - brier_score_loss(yb, pb),
            "f1": core_a["f1"] - core_b["f1"],
        }

    point = _metrics(y, p_a, p_b)
    for _ in range(B):
        idx = rng.randint(0, n, n)
        yb = y[idx]
        if len(np.unique(yb)) < 2:
            continue
        vals = _metrics(yb, p_a[idx], p_b[idx])
        for k in keys:
            if math.isfinite(vals[k]):
                samples[k].append(vals[k])
    out = {}
    for k in keys:
        arr = np.asarray(samples[k], dtype=np.float64)
        out[k] = {
            "delta_point": point[k],
            "ci95": [float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))]
            if arr.size
            else [float("nan"), float("nan")],
            "bootstrap_n": int(arr.size),
        }
    return out


def smd_table(kaggle: pd.DataFrame, mendeley: pd.DataFrame) -> dict:
    out = {}
    for col in FEATURES:
        a, b = kaggle[col], mendeley[col]
        sd = pd.concat([a, b]).std(ddof=0)
        out[col] = {
            "kaggle_mean": float(a.mean()),
            "mendeley_mean": float(b.mean()),
            "kaggle_nunique": int(a.nunique()),
            "mendeley_nunique": int(b.nunique()),
            "smd": float((a.mean() - b.mean()) / sd) if sd > 0 else None,
        }
    return out


def load_data():
    aligned = pd.read_csv(DATA / "external" / "aligned_features.csv")
    aligned["source"] = aligned["label_source"].map(
        {"self_reported_binary": "kaggle", "phq9_total": "mendeley"}
    )
    assert aligned["source"].notna().all()
    kaggle = aligned[aligned["source"] == "kaggle"].reset_index(drop=True)
    mendeley = aligned[aligned["source"] == "mendeley"].reset_index(drop=True)
    assert len(kaggle) == 27870 and len(mendeley) == 682

    processed = {}
    for split in ("train", "test"):
        processed[split] = pd.read_csv(
            DATA / "processed" / "v1_23_external" / f"{split}.csv"
        )
    return aligned, kaggle, mendeley, processed


def main() -> int:
    aligned, kaggle, mendeley, processed = load_data()
    internal_train, internal_test = processed["train"], processed["test"]
    y_int = internal_test["depression_binary"].to_numpy(dtype=np.int64)
    y_men = mendeley["label_binary"].to_numpy(dtype=np.int64)
    y_kag = kaggle["label_binary"].to_numpy(dtype=np.int64)

    # ── 1) source shift / label shift ──
    label_shift = {
        "kaggle": {
            "n": int(len(kaggle)),
            "positive_rate": float(y_kag.mean()),
            "label_source": "self-reported binary",
        },
        "mendeley": {
            "n": int(len(mendeley)),
            "positive_rate": float(y_men.mean()),
            "label_source": "PHQ-9 >= 10",
            "phq9_total_mean": float(mendeley["phq9_total"].mean()),
            "phq9_total_sd": float(mendeley["phq9_total"].std(ddof=0)),
        },
        "absolute_prevalence_gap": abs(float(y_kag.mean() - y_men.mean())),
    }
    shift = smd_table(kaggle, mendeley)
    redundancy = {
        "stress_equals_academic_fraction": float(
            (aligned["stress_level"] == aligned["academic_pressure"]).mean()
        ),
        "anxiety_stress_pearson": float(aligned["anxiety"].corr(aligned["stress_level"])),
        "social_support_nunique": int(aligned["social_support"].nunique()),
        "mendeley_family_history_nunique": int(mendeley["family_history"].nunique()),
        "mendeley_panic_attack_nunique": int(mendeley["panic_attack"].nunique()),
        "mendeley_cgpa_nunique": int(mendeley["cgpa"].nunique()),
        "mendeley_duplicate_feature_vectors": int(
            mendeley[FEATURES].round(6).duplicated().sum()
        ),
        "kaggle_duplicate_feature_vectors": int(kaggle[FEATURES].round(6).duplicated().sum()),
        "cross_source_exact_feature_vectors": 0,
    }
    kg_keys = set(kaggle[FEATURES].round(6).astype(str).agg("|".join, axis=1))
    men_keys = set(mendeley[FEATURES].round(6).astype(str).agg("|".join, axis=1))
    redundancy["cross_source_exact_feature_vectors"] = int(len(kg_keys & men_keys))

    # ── 2) main protocols with full features ──
    # internal (fresh fit, must reproduce production-like internal test)
    _, p_internal = fit_predict(internal_train, internal_test, FEATURES, "depression_binary")

    # same-source Kaggle random holdout (isolates source shift from sample size)
    k_train, k_test = train_test_split(
        kaggle, test_size=0.20, random_state=SEED, stratify=y_kag
    )
    _, p_kag_holdout = fit_predict(k_train, k_test, FEATURES, "label_binary")

    # clean source holdout: all Kaggle -> all Mendeley
    pipe_src, p_men_clean = fit_predict(kaggle, mendeley, FEATURES, "label_binary")

    # reverse stress test: all Mendeley -> all Kaggle
    _, p_kag_from_men = fit_predict(mendeley, kaggle, FEATURES, "label_binary")

    main_protocols = {
        "internal_test_4318": {
            "design": "train on processed train (Kaggle+Mendeley), test on processed test",
            "n_test": int(len(internal_test)),
            "positive_rate_test": float(y_int.mean()),
            **evaluate(y_int, p_internal, bootstrap_B=BOOTSTRAP_MAIN),
        },
        "kaggle_random_holdout": {
            "design": "train on 80% Kaggle, test on held-out 20% Kaggle (same label source)",
            "n_train": int(len(k_train)),
            "n_test": int(len(k_test)),
            "positive_rate_test": float(k_test["label_binary"].mean()),
            **evaluate(k_test["label_binary"].to_numpy(dtype=np.int64), p_kag_holdout),
        },
        "kaggle_to_mendeley_clean": {
            "design": "train on ALL Kaggle, test on ALL Mendeley; no Mendeley in training",
            "n_train": int(len(kaggle)),
            "n_test": int(len(mendeley)),
            "positive_rate_test": float(y_men.mean()),
            **evaluate(y_men, p_men_clean, bootstrap_B=BOOTSTRAP_MAIN),
        },
        "mendeley_to_kaggle_reverse": {
            "design": "train on ALL Mendeley (682), test on ALL Kaggle; reverse stress test",
            "n_train": int(len(mendeley)),
            "n_test": int(len(kaggle)),
            "positive_rate_test": float(y_kag.mean()),
            **evaluate(y_kag, p_kag_from_men, bootstrap_B=BOOTSTRAP_AUX),
        },
    }

    threshold_transfer = {
        "design": "clean Kaggle-only model scored on all Mendeley; thresholds are fixed, not tuned on target",
        "mean_predicted_probability": float(p_men_clean.mean()),
        "observed_positive_rate": float(y_men.mean()),
        "rows": {
            f"{cut:.2f}": at_risk_cut(y_men, p_men_clean, cut, target_prevalences=(0.15,))
            for cut in (0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.65, 0.85)
        },
        "note": (
            "At the internal 0.5 threshold the source-shifted model under-alerts: mean predicted "
            "probability is below the observed Mendeley prevalence. This is a transfer/calibration "
            "symptom, not evidence for changing production thresholds."
        ),
    }

    # calibration transport: Platt fit on a Kaggle validation fold, applied to Mendeley
    k_fit, k_cal = train_test_split(
        kaggle, test_size=0.20, random_state=SEED, stratify=y_kag
    )
    _, p_cal_fit = fit_predict(k_fit, k_cal, FEATURES, "label_binary")
    platt = fit_platt(k_cal["label_binary"].to_numpy(dtype=np.int64), p_cal_fit)
    _, p_men_80 = fit_predict(k_fit, mendeley, FEATURES, "label_binary")
    p_men_cal = apply_platt(p_men_80, platt["slope"], platt["intercept"])
    cal_raw = evaluate(y_men, p_men_80, bootstrap_B=BOOTSTRAP_AUX)
    cal_after = evaluate(y_men, p_men_cal, bootstrap_B=BOOTSTRAP_AUX)
    calibration_transport = {
        "design": "train on 80% Kaggle; Platt on held-out 20% Kaggle; evaluate both on all Mendeley",
        "platt": platt,
        "raw": cal_raw["card"],
        "source_calibrated": cal_after["card"],
        "delta_brier": cal_after["card"]["brier"] - cal_raw["card"]["brier"],
        "delta_ece": cal_after["card"]["ece"] - cal_raw["card"]["ece"],
        "note": "Source-side calibration cannot fix target covariate/label shift; this measures how far it helps.",
    }

    # ── 3) ablation under internal and source-held-out protocols ──
    internal_ablation = {}
    source_ablation = {}
    source_predictions = {"full_12": p_men_clean}
    internal_predictions = {"full_12": p_internal}
    for name, feats in ABLATIONS.items():
        if name != "full_12":
            _, p_int = fit_predict(
                internal_train, internal_test, feats, "depression_binary"
            )
            _, p_src = fit_predict(kaggle, mendeley, feats, "label_binary")
            internal_predictions[name] = p_int
            source_predictions[name] = p_src
        internal_ablation[name] = {
            "n_features": len(feats),
            "features": feats,
            **evaluate(y_int, internal_predictions[name], bootstrap_B=BOOTSTRAP_AUX),
        }
        source_ablation[name] = {
            "n_features": len(feats),
            "features": feats,
            **evaluate(y_men, source_predictions[name], bootstrap_B=BOOTSTRAP_AUX),
        }

    paired_source = {}
    paired_internal = {}
    for name in ABLATIONS:
        if name == "full_12":
            continue
        paired_source[name] = paired_delta(
            y_men, source_predictions[name], p_men_clean
        )
        paired_internal[name] = paired_delta(
            y_int, internal_predictions[name], p_internal
        )

    # ── 4) production contamination contrast ──
    prod_model = MC.load_structured_model()
    men_in_train = internal_train[internal_train["source"] == "mendeley"].reset_index(drop=True)
    men_in_test = internal_test[internal_test["source"] == "mendeley"].reset_index(drop=True)
    p_prod_men_train = prod_model.predict_proba(men_in_train[FEATURES])[:, 1]
    p_prod_men_test = prod_model.predict_proba(men_in_test[FEATURES])[:, 1]
    y_men_train = men_in_train["depression_binary"].to_numpy(dtype=np.int64)
    y_men_test = men_in_test["depression_binary"].to_numpy(dtype=np.int64)

    # clean model predictions on the same rows
    p_clean_men_train = pipe_src.predict_proba(men_in_train[FEATURES])[:, 1]
    p_clean_men_test = pipe_src.predict_proba(men_in_test[FEATURES])[:, 1]

    contamination = {
        "production_train_mendeley_408": {
            "design": "production model on 408 Mendeley rows it was trained on (in-sample)",
            **evaluate(y_men_train, p_prod_men_train, bootstrap_B=BOOTSTRAP_MAIN),
        },
        "production_test_mendeley_137": {
            "design": "production model on 137 Mendeley rows from its internal test (unseen rows, seen source)",
            **evaluate(y_men_test, p_prod_men_test, bootstrap_B=BOOTSTRAP_MAIN),
        },
        "clean_kaggle_only_all_682": {
            "design": "clean Kaggle-only model on all 682 Mendeley rows",
            **evaluate(y_men, p_men_clean, bootstrap_B=BOOTSTRAP_MAIN),
        },
        "production_vs_clean_on_test_137": {
            "n": int(len(y_men_test)),
            "paired_delta_production_minus_clean": paired_delta(
                y_men_test, p_prod_men_test, p_clean_men_test
            ),
        },
        "production_vs_clean_on_train_408": {
            "n": int(len(y_men_train)),
            "paired_delta_production_minus_clean": paired_delta(
                y_men_train, p_prod_men_train, p_clean_men_train
            ),
        },
        "note": (
            "Production was trained on 408 Mendeley rows. Its 137-row Mendeley test is not a "
            "clean cross-source read because the source was present in training; the clean "
            "Kaggle-only model is the source-held-out reference."
        ),
    }

    # ── 5) PHQ-9 severity correlation (clean model) ──
    phq = mendeley["phq9_total"].to_numpy(dtype=np.float64)
    sev = mendeley["phq9_severity"].astype(str)
    pearson_r = float(pearsonr(p_men_clean, phq)[0])
    spearman_r = float(spearmanr(p_men_clean, phq)[0])
    rng = np.random.RandomState(SEED)
    boot_r = {"pearson": [], "spearman": []}
    for _ in range(BOOTSTRAP_AUX):
        idx = rng.randint(0, len(phq), len(phq))
        if len(np.unique(phq[idx])) < 2:
            continue
        boot_r["pearson"].append(pearsonr(p_men_clean[idx], phq[idx])[0])
        boot_r["spearman"].append(spearmanr(p_men_clean[idx], phq[idx])[0])
    auc_by_cut = {}
    for cut in (5, 10, 15, 20):
        y_cut = (phq >= cut).astype(np.int64)
        if len(np.unique(y_cut)) < 2:
            auc_by_cut[str(cut)] = None
            continue
        auc_by_cut[str(cut)] = {
            "positive_rate": float(y_cut.mean()),
            "auroc": float(roc_auc_score(y_cut, p_men_clean)),
        }
    by_severity = {}
    for category, group in mendeley.assign(p=p_men_clean).groupby("phq9_severity"):
        by_severity[str(category)] = {
            "n": int(len(group)),
            "phq9_mean": float(group["phq9_total"].mean()),
            "mean_predicted_probability": float(group["p"].mean()),
        }
    phq9 = {
        "n": int(len(phq)),
        "pearson_r": pearson_r,
        "spearman_r": spearman_r,
        "pearson_r_ci95": [float(np.percentile(boot_r["pearson"], 2.5)), float(np.percentile(boot_r["pearson"], 97.5))],
        "spearman_r_ci95": [float(np.percentile(boot_r["spearman"], 2.5)), float(np.percentile(boot_r["spearman"], 97.5))],
        "bootstrap_B": BOOTSTRAP_AUX,
        "auc_by_phq9_cut": auc_by_cut,
        "auc_by_phq9_cut_note": "10 is the Mendeley label definition; other cuts are exploratory.",
        "by_severity": by_severity,
        "note": "PHQ-9 total was never used as a training label in the Kaggle-only model.",
    }

    # ── 6) verdict ──
    src = main_protocols["kaggle_to_mendeley_clean"]["card"]
    internal = main_protocols["internal_test_4318"]["card"]
    kag_hold = main_protocols["kaggle_random_holdout"]["card"]
    reverse = main_protocols["mendeley_to_kaggle_reverse"]["card"]
    best_source = max(
        source_ablation.items(),
        key=lambda kv: (kv[1]["card"]["auroc"] or 0.0),
    )
    verdict = (
        f"内部测试 AUC={internal['auroc']:.4f} / Brier={internal['brier']:.4f}；"
        f"同源 Kaggle 留出 AUC={kag_hold['auroc']:.4f} / Brier={kag_hold['brier']:.4f}；"
        f"干净跨来源 Kaggle→Mendeley AUC={src['auroc']:.4f} / Brier={src['brier']:.4f} "
        f"（n={src['n']}, 阳性率={src['positive_rate']:.3f}）；"
        f"反向 Mendeley→Kaggle AUC={reverse['auroc']:.4f}。"
        f"跨来源消融最佳特征集为 `{best_source[0]}`（{best_source[1]['n_features']} 特征，"
        f"AUC={best_source[1]['card']['auroc']:.4f}，Brier={best_source[1]['card']['brier']:.4f}）。"
        "结构化模型的诚实泛化读数应以干净跨来源口径为主，内部测试读数不得单独外推。"
    )

    payload = {
        "_note": (
            "ROUND_46 P0-3 structured source-held-out validation and ablation. Read-only; "
            "no production artifact or threshold modified. Kaggle labels are self-reported "
            "binary; Mendeley labels are PHQ-9 >= 10, so source shift conflates covariate "
            "and label-definition shift. Internal test is not a clean cross-source read "
            "because production trained on 408 Mendeley rows."
        ),
        "data": {
            "aligned_features": str((DATA / "external" / "aligned_features.csv").relative_to(PROJECT_ROOT)),
            "features": FEATURES,
            "label_shift": label_shift,
            "source_shift_smd": shift,
            "redundancy_and_overlap": redundancy,
        },
        "protocols": {
            "internal": "train on data/processed/v1_23_external/train.csv, test on test.csv",
            "kaggle_random_holdout": "80/20 stratified random split within Kaggle",
            "source_held_out": "train on all 27,870 Kaggle, test on all 682 Mendeley",
            "reverse": "train on all 682 Mendeley, test on all 27,870 Kaggle",
        },
        "main_protocols": main_protocols,
        "threshold_transfer": threshold_transfer,
        "calibration_transport": calibration_transport,
        "ablation": {
            "feature_sets": {k: v for k, v in ABLATIONS.items()},
            "internal": internal_ablation,
            "source_held_out": source_ablation,
            "paired_delta_vs_full_internal": paired_internal,
            "paired_delta_vs_full_source": paired_source,
            "paired_delta_note": (
                "Positive AUROC/AUPRC/F1 = ablation better; negative Brier = ablation better. "
                "CI covers test-sampling uncertainty only (models fit once)."
            ),
        },
        "production_contamination": contamination,
        "phq9_severity": phq9,
        "verdict": verdict,
    }
    cleaned = _finite(payload)
    OUT_JSON.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")
    MIRROR_JSON.parent.mkdir(parents=True, exist_ok=True)
    MIRROR_JSON.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")
    REPORT_MD.write_text(render_report(cleaned), encoding="utf-8")

    print("[source_holdout]")
    for name, unit in main_protocols.items():
        c = unit["card"]
        print(
            f"  {name:32s} n={c['n']:6d} prev={c['positive_rate']:.3f} "
            f"auc={c['auroc']:.4f} brier={c['brier']:.4f} "
            f"ece={c['ece']:.4f} slope={c['calibration_slope']:.3f} f1={c['f1']:.4f}"
        )
    for name, unit in source_ablation.items():
        c = unit["card"]
        print(f"  src-ablation {name:28s} p={unit['n_features']:2d} auc={c['auroc']:.4f} brier={c['brier']:.4f}")
    print(f"  PHQ9 Pearson={phq9['pearson_r']:.4f} Spearman={phq9['spearman_r']:.4f}")
    for name, d in contamination.items():
        if isinstance(d, dict) and "card" in d:
            print(
                f"  contamination {name:36s} n={d['card']['n']:5d} "
                f"auc={d['card']['auroc']:.4f} brier={d['card']['brier']:.4f}"
            )
    print(f"  -> {OUT_JSON.relative_to(PROJECT_ROOT)}")
    print(f"  -> {REPORT_MD.relative_to(PROJECT_ROOT)}")
    return 0


def _ci(boot: dict, key: str) -> str:
    entry = boot.get(key)
    if not entry:
        return "n/a"
    lo, hi = entry["ci95"]
    if lo is None or hi is None:
        return "n/a"
    return f"{lo:.3f}-{hi:.3f}"


def render_report(payload: dict) -> str:
    data = payload["data"]
    ls = data["label_shift"]
    protocols = payload["main_protocols"]
    ablation = payload["ablation"]
    contamination = payload["production_contamination"]
    phq = payload["phq9_severity"]
    lines = [
        "# ROUND_46 结构化来源留出验证与消融（P0-3）",
        "",
        "本文件由 `backend/scripts/modeling/eval/v1_46/03_source_holdout.py` 生成。",
        "只读评估，**没有修改生产模型、工件或阈值**。",
        "",
        "## 为什么必须做来源留出",
        "",
        "生产 v1.23 结构化模型在训练时见过 408 条 Mendeley；其内部测试里的 137 条 Mendeley",
        "不是干净跨来源读数。本脚本用「全部 27,870 条 Kaggle 训练 → 全部 682 条 Mendeley 测试」",
        "构造干净的来源留出实验，并用「生产模型在见过的 408 条 vs 未见过的 137 条」量化同源乐观偏差。",
        "",
        "## 标签与协变量偏移（先于指标）",
        "",
        f"- Kaggle：n={ls['kaggle']['n']}，阳性率 {ls['kaggle']['positive_rate']:.4f}，标签={ls['kaggle']['label_source']}",
        f"- Mendeley：n={ls['mendeley']['n']}，阳性率 {ls['mendeley']['positive_rate']:.4f}，标签={ls['mendeley']['label_source']}，"
        f"PHQ-9 均值 {ls['mendeley']['phq9_total_mean']:.2f} ± {ls['mendeley']['phq9_total_sd']:.2f}",
        f"- 阳性率绝对差：{ls['absolute_prevalence_gap']:.4f}",
        "",
        "| 特征 | Kaggle 均值 | Mendeley 均值 | Kaggle 取值数 | Mendeley 取值数 | SMD |",
        "|---|---|---|---|---|---|",
    ]
    for col, row in data["source_shift_smd"].items():
        smd = "n/a" if row["smd"] is None else f"{row['smd']:+.3f}"
        lines.append(
            f"| `{col}` | {row['kaggle_mean']:.3f} | {row['mendeley_mean']:.3f} "
            f"| {row['kaggle_nunique']} | {row['mendeley_nunique']} | {smd} |"
        )
    red = data["redundancy_and_overlap"]
    lines += [
        "",
        f"- `stress_level == academic_pressure` 比例：{red['stress_equals_academic_fraction']:.4f}",
        f"- `anxiety` 与 `stress_level` 相关：{red['anxiety_stress_pearson']:.4f}",
        f"- `social_support` 全表取值数：{red['social_support_nunique']}",
        f"- Mendeley 中 `family_history` / `panic_attack` / `cgpa` 取值数："
        f"{red['mendeley_family_history_nunique']} / {red['mendeley_panic_attack_nunique']} / {red['mendeley_cgpa_nunique']}",
        f"- 跨来源完全相同的特征向量：{red['cross_source_exact_feature_vectors']} 条",
        "",
        "**结论先行：** 迁移方向不是单纯的人群变化——标签定义也从「自报二分类」变成「PHQ-9≥10」；",
        "并且 Mendeley 的 `family_history`、`panic_attack` 恒为 0，`cgpa` 恒为 3.0。",
        "因此跨来源读数应理解为「Kaggle 自报 → Mendeley PHQ-9」的联合迁移，不能只归因于人群差异。",
        "",
        "## 主协议结果",
        "",
        "| 协议 | n_test | 阳性率 | AUC [95%CI] | AUPRC | Brier | ECE | 校准斜率 | F1 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, unit in protocols.items():
        c = unit["card"]
        b = unit["bootstrap"]
        lines.append(
            f"| `{name}` | {c['n']} | {c['positive_rate']:.3f} "
            f"| {c['auroc']:.4f} [{_ci(b, 'auroc')}] | {c['auprc']:.4f} "
            f"| {c['brier']:.4f} [{_ci(b, 'brier')}] | {c['ece']:.4f} "
            f"| {c['calibration_slope']:.3f} | {c['f1']:.4f} [{_ci(b, 'f1')}] |"
        )

    tt = payload["threshold_transfer"]
    lines += [
        "",
        "## 阈值迁移（干净 Kaggle-only 模型 → Mendeley）",
        "",
        f"- 平均预测概率 {tt['mean_predicted_probability']:.4f}，Mendeley 实际阳性率 "
        f"{tt['observed_positive_rate']:.4f}：模型在目标域系统性低估风险。",
        "- 阈值固定、未在目标域调参；0.5 只是内部二元参考，不是生产唯一决策点。",
        "",
        "| 阈值 | 灵敏度 | 特异度 | PPV | NPV | 告警/千 | F1 |",
        "|---|---|---|---|---|---|---|",
    ]
    for cut, row in tt["rows"].items():
        lines.append(
            f"| {cut} | {row['sensitivity']:.3f} | {row['specificity']:.3f} "
            f"| {row['ppv']:.3f} | {row['npv']:.3f} | {row['alerts_per_1000']:.0f} "
            f"| {row['f1']:.3f} |"
        )
    lines += [
        "",
        "内部常用的 0.5 在目标域只报出约一半阳性（灵敏度约 0.51）；生产 mild 切点 0.25 下",
        "灵敏度约 0.77、特异度约 0.78。该对比说明「跨来源后需要重新校准/重新选点」，",
        "**不构成变更生产阈值的授权**。",
        "",
        "## 生产模型的同源乐观偏差",
        "",
        "| 读数 | n | AUC | Brier | ECE | 说明 |",
        "|---|---|---|---|---|---|",
    ]
    for name, unit in contamination.items():
        if not isinstance(unit, dict) or "card" not in unit:
            continue
        c = unit["card"]
        lines.append(
            f"| `{name}` | {c['n']} | {c['auroc']:.4f} | {c['brier']:.4f} | {c['ece']:.4f} | {unit['design']} |"
        )
    pv = contamination["production_vs_clean_on_test_137"]["paired_delta_production_minus_clean"]
    pv_train = contamination["production_vs_clean_on_train_408"]["paired_delta_production_minus_clean"]
    lines += [
        "",
        f"- 同 137 条未见过 Mendeley：生产 − 干净模型的 AUC 差 = "
        f"{pv['auroc']['delta_point']:+.4f} [{pv['auroc']['ci95'][0]:+.4f}, {pv['auroc']['ci95'][1]:+.4f}]；"
        f"Brier 差 = {pv['brier']['delta_point']:+.4f} "
        f"[{pv['brier']['ci95'][0]:+.4f}, {pv['brier']['ci95'][1]:+.4f}]。",
        f"- 同 408 条训练内 Mendeley：生产 − 干净模型的 AUC 差 = "
        f"{pv_train['auroc']['delta_point']:+.4f} "
        f"[{pv_train['auroc']['ci95'][0]:+.4f}, {pv_train['auroc']['ci95'][1]:+.4f}]；"
        f"Brier 差 = {pv_train['brier']['delta_point']:+.4f} "
        f"[{pv_train['brier']['ci95'][0]:+.4f}, {pv_train['brier']['ci95'][1]:+.4f}]。",
        "",
        "Brier 差为负表示生产模型更好；但在训练内 408 条上「更好」主要是同源/同人泄漏，",
        "不能作为跨来源能力证据。",
        "",
        "## 特征消融",
        "",
        "### 干净跨来源（Kaggle→Mendeley，n=682）",
        "",
        "| 特征集 | 特征数 | AUC | Brier | ECE | 校准斜率 | F1 | ΔAUC vs full [95%CI] | ΔBrier vs full [95%CI] |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, unit in ablation["source_held_out"].items():
        c = unit["card"]
        paired = ablation["paired_delta_vs_full_source"].get(name)
        if paired:
            dauc = paired["auroc"]
            dbrier = paired["brier"]
            dauc_s = f"{dauc['delta_point']:+.4f} [{dauc['ci95'][0]:+.4f}, {dauc['ci95'][1]:+.4f}]"
            dbrier_s = f"{dbrier['delta_point']:+.4f} [{dbrier['ci95'][0]:+.4f}, {dbrier['ci95'][1]:+.4f}]"
        else:
            dauc_s = dbrier_s = "reference"
        lines.append(
            f"| `{name}` | {unit['n_features']} | {c['auroc']:.4f} | {c['brier']:.4f} "
            f"| {c['ece']:.4f} | {c['calibration_slope']:.3f} | {c['f1']:.4f} "
            f"| {dauc_s} | {dbrier_s} |"
        )
    lines += [
        "",
        "### 内部测试（n=4318，对照）",
        "",
        "| 特征集 | 特征数 | AUC | Brier | ECE | 校准斜率 | F1 | ΔAUC vs full | ΔBrier vs full |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, unit in ablation["internal"].items():
        c = unit["card"]
        paired = ablation["paired_delta_vs_full_internal"].get(name)
        if paired:
            dauc = paired["auroc"]["delta_point"]
            dbrier = paired["brier"]["delta_point"]
            dauc_s = f"{dauc:+.4f}"
            dbrier_s = f"{dbrier:+.4f}"
        else:
            dauc_s = dbrier_s = "reference"
        lines.append(
            f"| `{name}` | {unit['n_features']} | {c['auroc']:.4f} | {c['brier']:.4f} "
            f"| {c['ece']:.4f} | {c['calibration_slope']:.3f} | {c['f1']:.4f} "
            f"| {dauc_s} | {dbrier_s} |"
        )
    lines += [
        "",
        "Δ 的 95%CI 为配对 bootstrap（同一批测试行重采样，B=2000，seed=42）；",
        "只覆盖测试抽样不确定性，不覆盖训练集抽样或模型选择不确定性。",
        "",
        "## 校准迁移（源侧 Platt → 目标）",
        "",
        f"- 设计：{payload['calibration_transport']['design']}",
        f"- Platt：slope={payload['calibration_transport']['platt']['slope']:.4f}, "
        f"intercept={payload['calibration_transport']['platt']['intercept']:.4f}",
        f"- 目标域 Brier：raw {payload['calibration_transport']['raw']['brier']:.4f} → "
        f"calibrated {payload['calibration_transport']['source_calibrated']['brier']:.4f} "
        f"(Δ {payload['calibration_transport']['delta_brier']:+.4f})",
        f"- 目标域 ECE：raw {payload['calibration_transport']['raw']['ece']:.4f} → "
        f"calibrated {payload['calibration_transport']['source_calibrated']['ece']:.4f} "
        f"(Δ {payload['calibration_transport']['delta_ece']:+.4f})",
        "",
        "源侧校准不能修复目标域的协变量/标签偏移；它只检验「如果部署时按源验证集校准，会好多少」。",
        "",
        "## PHQ-9 严重度关联（干净 Kaggle-only 模型，n=682）",
        "",
        f"- Pearson r = {phq['pearson_r']:.4f} "
        f"[{phq['pearson_r_ci95'][0]:.4f}, {phq['pearson_r_ci95'][1]:.4f}]；"
        f"Spearman ρ = {phq['spearman_r']:.4f} "
        f"[{phq['spearman_r_ci95'][0]:.4f}, {phq['spearman_r_ci95'][1]:.4f}]",
        "- PHQ-9 总分从未作为 Kaggle-only 模型的训练标签，因此这是独立严重度信号的关联检验。",
        "",
        "| PHQ-9 阈值 | 阳性率 | AUC |",
        "|---|---|---|",
    ]
    for cut, row in phq["auc_by_phq9_cut"].items():
        if row is None:
            lines.append(f"| ≥{cut} | n/a | n/a |")
        else:
            lines.append(f"| ≥{cut} | {row['positive_rate']:.3f} | {row['auroc']:.4f} |")
    lines += [
        "",
        "| PHQ-9 严重度 | n | PHQ-9 均值 | 平均预测概率 |",
        "|---|---|---|---|",
    ]
    for category, row in phq["by_severity"].items():
        lines.append(
            f"| {category} | {row['n']} | {row['phq9_mean']:.2f} | {row['mean_predicted_probability']:.4f} |"
        )
    lines += [
        "",
        "## 判定",
        "",
        payload["verdict"],
        "",
        "## 边界与未做",
        "",
        "1. **不是前瞻性外部验证。** 两个来源都是公开数据集，且标签定义不同；无法替代新医院/新学校/新平台的真实流量验证。",
        "2. **反向 Mendeley→Kaggle 只作压力测试。** 682 条训练、Mendeley 多个特征恒定，反向结果不能与正向对称解读。",
        "3. **没有做阈值变更。** 本报告只给泛化读数与消融证据；生产切点保持 25/45/65/85。",
        "4. **CI 只覆盖测试抽样。** 模型只拟合一次，未做训练集重复抽样/交叉拟合；跨来源 CI 不应被读成「部署区间」。",
        "5. **Mendeley 内部有 201 条重复特征向量**（特征粒度粗，未必是重复个体）；未做聚类 bootstrap，按行重采样可能略窄。",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
