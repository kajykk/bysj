#!/usr/bin/env python
"""ROUND_46 P0: unified model cards for structured / text / physiological.

Read-only evaluation. No production artifact, threshold, or model is modified.
Fusion is explicitly marked not_evaluable: the repository has no aligned
three-modality labelled sample.

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/modeling/eval/v1_46/01_model_cards.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold, train_test_split

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[3]
PROJECT_ROOT = BACKEND.parent
for path in (BACKEND, HERE, PROJECT_ROOT / "scripts" / "ml_training"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from model_card_lib import (  # noqa: E402
    apply_platt,
    at_risk_cut,
    bootstrap_metrics,
    dca,
    equalized_odds_gap,
    fit_platt,
    model_card,
    operating_point_candidates,
    subgroup_metrics,
)

DATA = PROJECT_ROOT / "data"
OUT_DIR = PROJECT_ROOT / "outputs" / "candidates" / "round46"
OUT_JSON = HERE / "model_cards.json"
OUT_MIRROR = OUT_DIR / "model_cards.json"

FEATURES = [
    "age",
    "gender",
    "cgpa",
    "stress_level",
    "sleep_duration",
    "social_support",
    "financial_pressure",
    "family_history",
    "academic_pressure",
    "exercise_frequency",
    "anxiety",
    "panic_attack",
]
TARGET = "depression_binary"
STRUCTURED_CUTS = [0.25, 0.45, 0.65, 0.85]
TEXT_CUTS = [0.20, 0.40, 0.60, 0.80]
PHYSIO_CUTS = [0.35, 0.55, 0.75, 0.90]
BOOTSTRAP_B = 5000


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_structured_model():
    model = joblib.load(BACKEND / "models" / "v1.23_external_lr" / "model.pkl")
    for item in model.named_steps["preprocessor"].transformers_:
        transformer = item[1]
        imputer = getattr(transformer, "named_steps", {}).get("imputer")
        if imputer is not None and not hasattr(imputer, "_fill_dtype") and hasattr(imputer, "_fit_dtype"):
            imputer._fill_dtype = imputer._fit_dtype
    return model


def threshold_table(y, p, cuts, thresholds_extra=()):
    observed = float(np.mean(y))
    rows = {}
    for cut in list(cuts) + [x for x in thresholds_extra if x not in cuts]:
        rows[f"{cut:.2f}"] = at_risk_cut(y, p, cut, target_prevalences=(0.15, round(observed, 4)))
    return rows


def structured_card():
    model = load_structured_model()
    test = pd.read_csv(DATA / "processed" / "v1_23_external" / "test.csv")
    validation = pd.read_csv(DATA / "processed" / "v1_23_external" / "validation.csv")
    features = list(model.feature_names_in_)
    assert features == FEATURES, f"unexpected production features: {features}"
    y = test[TARGET].to_numpy()
    p = model.predict_proba(test[features])[:, 1]
    y_val = validation[TARGET].to_numpy()
    p_val = model.predict_proba(validation[features])[:, 1]

    card = model_card(y, p, threshold=0.5, cuts=STRUCTURED_CUTS, target_prevalences=(0.10, 0.15, 0.20, 0.30))
    boot = bootstrap_metrics(y, p, threshold=0.5, B=BOOTSTRAP_B, seed=42)
    dca_curve = dca(y, p)

    platt = fit_platt(y_val, p_val)
    p_cal = apply_platt(p, platt["slope"], platt["intercept"])
    cal_card = model_card(y, p_cal, threshold=0.5, cuts=STRUCTURED_CUTS, target_prevalences=(0.10, 0.15, 0.20, 0.30))
    cal_boot = bootstrap_metrics(y, p_cal, threshold=0.5, B=BOOTSTRAP_B, seed=42)
    cal_dca = dca(y, p_cal)

    subgroups = {}
    subgroup_masks = {
        "source:kaggle": test["source"].to_numpy() == "kaggle",
        "source:mendeley": test["source"].to_numpy() == "mendeley",
        "gender:0": test["gender"].to_numpy() == 0,
        "gender:1": test["gender"].to_numpy() == 1,
    }
    age_bins = pd.cut(test["age"], bins=[16, 20, 25, 30, 35], labels=["17-20", "21-25", "26-30", "31-35"])
    for label in age_bins.cat.categories:
        subgroup_masks[f"age:{label}"] = (age_bins == label).to_numpy()
    for name, mask in subgroup_masks.items():
        if not mask.any():
            continue
        entry = subgroup_metrics(y, p, mask, threshold=0.5, cuts=STRUCTURED_CUTS, target_prevalences=(0.15,))
        if mask.sum() >= 100 and len(np.unique(y[mask])) == 2:
            entry["bootstrap"] = bootstrap_metrics(
                y[mask], p[mask], threshold=0.5, B=2000, seed=42
            )
        subgroups[name] = entry

    source_gap = equalized_odds_gap(
        y,
        p,
        {"kaggle": subgroup_masks["source:kaggle"], "mendeley": subgroup_masks["source:mendeley"]},
        threshold=0.5,
    )
    gender_gap = equalized_odds_gap(
        y,
        p,
        {"gender:0": subgroup_masks["gender:0"], "gender:1": subgroup_masks["gender:1"]},
        threshold=0.5,
    )

    return {
        "role": "citable_internal_test",
        "source": "data/processed/v1_23_external/test.csv",
        "source_sha256": sha256(DATA / "processed" / "v1_23_external" / "test.csv"),
        "validation_source": "data/processed/v1_23_external/validation.csv",
        "validation_sha256": sha256(DATA / "processed" / "v1_23_external" / "validation.csv"),
        "model": "models/v1.23_external_lr/model.pkl",
        "model_sha256": sha256(BACKEND / "models" / "v1.23_external_lr" / "model.pkl"),
        "n": int(len(y)),
        "positive_rate": float(y.mean()),
        "card": card,
        "bootstrap": boot,
        "dca": dca_curve,
        "threshold_table": threshold_table(y, p, STRUCTURED_CUTS, thresholds_extra=(0.50,)),
        "operating_points": operating_point_candidates(y, p, target_prevalences=(0.15,)),
        "calibration_candidate": {
            "method": "Platt on validation split, applied to test (no test fit)",
            "platt": platt,
            "card": cal_card,
            "bootstrap": cal_boot,
            "dca": cal_dca,
            "delta_brier": float(cal_card["brier"] - card["brier"]),
            "delta_ece": float(cal_card["ece"] - card["ece"]),
        },
        "subgroups": subgroups,
        "fairness_gaps_at_0.5": {"source": source_gap, "gender": gender_gap},
    }


def read_text_oof():
    path = BACKEND / "scripts" / "modeling" / "v1_27" / "groupwise_oof_predictions.csv"
    df = pd.read_csv(path)
    return path, df


def crossfit_group_platt(y, p, groups):
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)
    calibrated = np.full(len(y), np.nan)
    for train_idx, test_idx in splitter.split(np.zeros(len(y)), y, groups=groups):
        platt = fit_platt(y[train_idx], p[train_idx])
        calibrated[test_idx] = apply_platt(p[test_idx], platt["slope"], platt["intercept"])
    assert np.isfinite(calibrated).all()
    return calibrated


def text_card():
    oof_path, oof = read_text_oof()
    y = oof["label"].to_numpy(dtype=int)
    p = oof["p_groupwise"].to_numpy(dtype=float)
    groups = oof["group"].astype(str).to_numpy()
    card = model_card(y, p, threshold=0.5, cuts=TEXT_CUTS, target_prevalences=(0.10, 0.15, 0.2163, 0.30))
    boot = bootstrap_metrics(y, p, threshold=0.5, groups=groups, B=3000, seed=42)
    dca_curve = dca(y, p)
    p_cal = crossfit_group_platt(y, p, groups)
    cal_card = model_card(y, p_cal, threshold=0.5, cuts=TEXT_CUTS, target_prevalences=(0.10, 0.15, 0.2163, 0.30))
    cal_boot = bootstrap_metrics(y, p_cal, threshold=0.5, groups=groups, B=3000, seed=42)
    cal_dca = dca(y, p_cal)

    leaky = model_card(
        y,
        oof["p_textwise"].to_numpy(dtype=float),
        threshold=0.5,
        cuts=TEXT_CUTS,
        target_prevalences=(0.15,),
    )

    return {
        "role": "citable_groupwise_oof",
        "source": "backend/scripts/modeling/v1_27/groupwise_oof_predictions.csv",
        "source_sha256": sha256(oof_path),
        "n": int(len(y)),
        "positive_rate": float(y.mean()),
        "n_groups": int(len(np.unique(groups))),
        "card": card,
        "bootstrap": boot,
        "dca": dca_curve,
        "threshold_table": threshold_table(y, p, TEXT_CUTS, thresholds_extra=(0.30, 0.50)),
        "operating_points": operating_point_candidates(y, p, target_prevalences=(0.15,)),
        "calibration_candidate": {
            "method": "5-fold StratifiedGroupKFold cross-fitted Platt on OOF probabilities",
            "card": cal_card,
            "bootstrap": cal_boot,
            "dca": cal_dca,
            "delta_brier": float(cal_card["brier"] - card["brier"]),
            "delta_ece": float(cal_card["ece"] - card["ece"]),
        },
        "leaky_textwise_contrast": {
            "role": "not_citable",
            "why": "text-level OOF lets sibling variants cross folds; it is the leakage-inflated protocol.",
            "card": leaky,
            "delta_auroc_vs_groupwise": float(leaky["auroc"] - card["auroc"]),
            "delta_f1_vs_groupwise": float(leaky["f1"] - card["f1"]),
        },
    }


def text_english_holdout():
    en_path = PROJECT_ROOT / "datasets" / "text" / "depression_dataset_reddit_cleaned.csv"
    en = pd.read_csv(en_path)
    en = en.dropna(subset=["clean_text", "is_depression"]).copy()
    from data_utils import clean_text  # noqa: PLC0415

    en["text"] = en["clean_text"].astype(str).map(clean_text)
    en["label"] = pd.to_numeric(en["is_depression"], errors="coerce").fillna(0).astype(int)
    en = en[en["label"].isin([0, 1])].drop_duplicates(subset=["text"]).reset_index(drop=True)
    _, holdout = train_test_split(en, test_size=0.2, random_state=42, stratify=en["label"])
    model = joblib.load(BACKEND / "models" / "text" / "improved_bilingual_model.pkl")
    tfidf = joblib.load(BACKEND / "models" / "text" / "improved_bilingual_tfidf.pkl")
    p = model.predict_proba(tfidf.transform(holdout["text"].astype(str)))[:, 1]
    y = holdout["label"].to_numpy(dtype=int)
    card = model_card(y, p, threshold=0.5, cuts=TEXT_CUTS, target_prevalences=(0.10, 0.20, 0.30, 0.4915))
    return {
        "role": "citable_cross_lingual_holdout",
        "source": "datasets/text/depression_dataset_reddit_cleaned.csv (20% stratified holdout, seed=42)",
        "source_sha256": sha256(en_path),
        "model": "models/text/improved_bilingual_model.pkl + improved_bilingual_tfidf.pkl",
        "n": int(len(y)),
        "positive_rate": float(y.mean()),
        "card": card,
        "bootstrap": bootstrap_metrics(y, p, threshold=0.5, B=BOOTSTRAP_B, seed=42),
        "dca": dca(y, p),
        "threshold_table": threshold_table(y, p, TEXT_CUTS, thresholds_extra=(0.30, 0.50)),
        "operating_points": operating_point_candidates(y, p, target_prevalences=(0.20,)),
        "boundary": "Same Reddit domain as training, not a clinical or new-population external validation.",
    }


def load_eval01():
    path = BACKEND / "scripts" / "modeling" / "eval" / "v1_29" / "01_reproducible_eval.py"
    spec = importlib.util.spec_from_file_location("round29_eval01", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def physio_predictions():
    from app.ml.data_loader import load_depresjon_data  # noqa: PLC0415
    from app.ml.feature_engineering import engineer_features  # noqa: PLC0415
    from app.ml.model_loader import load_cleaner, load_feature_names, load_model, load_scaler  # noqa: PLC0415

    eval01 = load_eval01()
    df = load_depresjon_data()
    y = df["depression_label"].to_numpy(dtype=np.int64)
    tri, vai, tei = eval01.split_indices(y)
    eval01._assert_split_matches(y, tri, vai, tei)
    feats = load_feature_names()
    cleaner = load_cleaner()
    scaler = load_scaler()
    model = load_model()

    def score(idx):
        cleaned = cleaner.transform(df.iloc[idx])
        engineered = engineer_features(cleaned)
        x = engineered[feats].values.astype(np.float32)
        return np.asarray(model.predict_proba(scaler.transform(x))).reshape(-1)

    p_val, p_test = score(vai), score(tei)
    existing = pd.read_csv(BACKEND / "models" / "artifacts" / "physiological_optimized" / "test_predictions.csv")
    existing = existing.sort_values("row_index")
    order = np.argsort(tei)
    max_abs_diff = float(np.max(np.abs(existing["y_score"].to_numpy() - p_test[order])))
    predictions = pd.DataFrame(
        {
            "split": ["validation"] * len(vai) + ["test"] * len(tei),
            "row_index": np.concatenate([vai, tei]),
            "y_true": np.concatenate([y[vai], y[tei]]),
            "y_score": np.concatenate([p_val, p_test]),
        }
    )
    predictions.to_csv(HERE / "physio_val_test_predictions.csv", index=False)
    return df, y, vai, tei, p_val, p_test, feats, max_abs_diff, existing


def physio_card():
    df, y, vai, tei, p_val, p_test, feats, max_abs_diff, existing = physio_predictions()
    y_test = y[tei]
    card = model_card(y_test, p_test, threshold=0.5, cuts=PHYSIO_CUTS, target_prevalences=(0.15, 0.35, 0.50))
    boot = bootstrap_metrics(y_test, p_test, threshold=0.5, B=BOOTSTRAP_B, seed=42)
    dca_curve = dca(y_test, p_test)
    platt = fit_platt(y[vai], p_val)
    p_cal = apply_platt(p_test, platt["slope"], platt["intercept"])
    cal_card = model_card(y_test, p_cal, threshold=0.5, cuts=PHYSIO_CUTS, target_prevalences=(0.15, 0.35, 0.50))
    return {
        "role": "citable_secondary_small_test",
        "source": "depresjon_physiological.csv current version, deterministic 719/153/157 split",
        "n_total": int(len(y)),
        "n_validation": int(len(vai)),
        "n_test": int(len(tei)),
        "positive_rate_test": float(y_test.mean()),
        "feature_names": feats,
        "production_predictions_reproduced": bool(max_abs_diff < 1e-6),
        "max_abs_diff_vs_artifact_csv": max_abs_diff,
        "auprc_artifact_metrics_json": 0.8919268523615607,
        "auprc_definition_gap": round(
            card["auprc"] - 0.8919268523615607, 6
        ),
        "auprc_gap_note": (
            "metrics.json records a custom step integral using precision[:-1] "
            "(v1_29/04 auprc_score); standard sklearn average_precision_score on the "
            "same 157 predictions is higher. Definition difference only, same predictions."
        ),
        "card": card,
        "bootstrap": boot,
        "dca": dca_curve,
        "threshold_table": threshold_table(y_test, p_test, PHYSIO_CUTS, thresholds_extra=(0.50,)),
        "operating_points": operating_point_candidates(y_test, p_test, target_prevalences=(0.15,)),
        "calibration_candidate": {
            "method": "Platt on 153 validation rows, applied to 157 test rows (exploratory only)",
            "platt": platt,
            "card": cal_card,
            "delta_brier": float(cal_card["brier"] - card["brier"]),
            "delta_ece": float(cal_card["ece"] - card["ece"]),
        },
        "boundary": "n=157; bootstrap CI is wide. Do not cite as a stable external-validation estimate.",
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    units = {
        "structured_v1_23": structured_card(),
        "text_groupwise_oof": text_card(),
        "text_english_holdout": text_english_holdout(),
        "physio_v2_current_split": physio_card(),
        "fusion": {
            "status": "not_evaluable",
            "reason": "No aligned three-modality labelled samples exist; modality datasets come from different populations.",
            "existing_rule_level_analysis": "backend/scripts/modeling/eval/v1_37/fusion_ablation.json",
            "boundary": "Do not infer fusion performance, modality contribution, or DCA from synthetic score grids.",
        },
    }
    payload = {
        "_note": (
            "ROUND_46 P0 model cards. Structured is a single internal test split; text is "
            "sibling-aware groupwise OOF (the only citable Chinese text generalization "
            "protocol); physiological is a 157-row deterministic split; English is a "
            "cross-lingual holdout from the same Reddit domain. No production artifact "
            "or threshold was modified."
        ),
        "protocol_date": "2026-11-02",
        "metrics": {
            "auroc": "threshold-free ranking; 0.5 baseline",
            "auprc": "sklearn average_precision_score; compare with positive_rate baseline, not 0.5",
            "auprc_artifact_discrepancy": (
                "physiological metrics.json 0.8919 uses a custom precision[:-1] step integral; "
                "standard AP on identical predictions is 0.8961 (definition only)"
            ),
            "brier": "mean((p-y)^2); report brier_skill versus prevalence-only baseline",
            "calibration": "Platt slope/intercept on logit(p); ideal slope=1, intercept=0",
            "dca": "net_benefit(t) = TP/n - FP/n * t/(1-t)",
            "ppv_npv": "Bayes reweighted to stated prevalence; test prevalence is not deployment prevalence",
            "bootstrap": f"percentile bootstrap, B={BOOTSTRAP_B} for main units; text resamples groups",
        },
        "units": units,
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_MIRROR.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    for name, unit in units.items():
        if unit.get("status") == "not_evaluable":
            print(f"{name:28s} not_evaluable")
            continue
        card = unit["card"]
        print(
            f"{name:28s} n={card['n']:5d} prev={card['positive_rate']:.3f} "
            f"auc={card['auroc']:.4f} auprc={card['auprc']:.4f} brier={card['brier']:.4f} "
            f"ece={card['ece']:.4f} slope={card['calibration_slope']:.3f}"
        )
    print(f"written: {OUT_JSON}")
    print(f"written: {OUT_MIRROR}")


if __name__ == "__main__":
    main()
