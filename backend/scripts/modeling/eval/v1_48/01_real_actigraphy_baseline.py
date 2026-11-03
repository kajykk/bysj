#!/usr/bin/env python
"""ROUND_48: subject-grouped real-actigraphy baseline on Depresjon.

Read-only offline evaluation. No production artifact, threshold, runtime
contract, or model is modified.

Why this script exists
----------------------
The production physiological model is trained on a table whose heart-rate,
sleep, blood-pressure and PHQ-9 columns were generated from the label by
`convert_depresjon_to_system.py`. Only `steps`/`exercise_minutes` are derived
from real actigraphy, and the earlier real-column ablation used a row-level
split that let the same subject appear in train and test.

This script rebuilds the baseline from the *raw* per-subject minute-level
actigraphy files inside `depresjon.zip`, keeps the subject ID, and evaluates
only real summary features:

- mean_act, std_act, peak_activity, autocorrelation_act (primary four);
- plus rms/skew/kurtosis/shape/crest/impulse factors as an exploratory set.

The primary protocol is subject-level leave-one-subject-out (LOSO) on
subject-mean features. A secondary protocol trains a day-level model with
repeated StratifiedGroupKFold (subjects never split across folds) and averages
the held-out day predictions per subject. Both are reported because they answer
slightly different questions and disagree: the conservative subject-level
estimate is lower than the multi-day aggregation estimate.

This is still a same-cohort, retrospective analysis (55 subjects, clinical
actigraphy, condition/control labels). It is not external validation, not a
general-population or consumer-wearable result, and not a production model
replacement.

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/modeling/eval/v1_48/01_real_actigraphy_baseline.py
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import warnings
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[3]
PROJECT_ROOT = BACKEND.parent
RAW_ZIP = PROJECT_ROOT / "datasets" / "external" / "physiological" / "depresjon-code" / "depresjon.zip"
TDF_CONDITION = PROJECT_ROOT / "datasets" / "external" / "physiological" / "depresjon-code" / "TDF_CONDITION.csv"
TDF_CONTROL = PROJECT_ROOT / "datasets" / "external" / "physiological" / "depresjon-code" / "TDF_CONTROL.csv"
LICENSE_FILE = PROJECT_ROOT / "datasets" / "external" / "physiological" / "depresjon-code" / "LICENSE"
OUT_JSON = HERE / "real_actigraphy_baseline.json"
OUT_CSV = HERE / "subject_predictions.csv"
OUT_MIRROR = PROJECT_ROOT / "outputs" / "candidates" / "round48" / "real_actigraphy_baseline.json"
OUT_REPORT = PROJECT_ROOT / "docs" / "model-evaluation" / "REAL_ACTIGRAPHY_BASELINE.md"

PRIMARY_FEATURES = [
    "mean_act",
    "std_act",
    "peak_activity",
    "autocorrelation_act",
]
EXTENDED_FEATURES = PRIMARY_FEATURES + [
    "rms_act",
    "skewness_act",
    "kurtosis_act",
    "shape_factor_act",
    "crest_factor_act",
    "impulse_factor_act",
]

SEED = 42
N_SPLITS = 5
N_REPEATS = 10
BOOTSTRAP_B = 2000
PERMUTATION_B = 500
CUTS = [0.30, 0.35, 0.40, 0.50]
MIN_COMPLETE_MINUTES = 1440


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _finite(obj):
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, (np.floating, np.integer)):
        return _finite(obj.item())
    if isinstance(obj, dict):
        return {k: _finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_finite(v) for v in obj]
    return obj


def _safe_skew(values: np.ndarray) -> float:
    if values.size == 0 or float(values.std()) == 0.0:
        return 0.0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        value = float(pd.Series(values).skew())
    return value if math.isfinite(value) else 0.0


def _safe_kurtosis(values: np.ndarray) -> float:
    if values.size == 0 or float(values.std()) == 0.0:
        return 0.0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        value = float(pd.Series(values).kurt())
    return value if math.isfinite(value) else 0.0


def load_days() -> tuple[pd.DataFrame, pd.DataFrame, int]:
    rows: list[dict] = []
    partial_days = 0
    with zipfile.ZipFile(RAW_ZIP) as zf:
        names = [
            name for name in zf.namelist() if name.startswith("data/condition/") or name.startswith("data/control/")
        ]
        for name in names:
            subject = Path(name).stem
            if not (subject.startswith("condition_") or subject.startswith("control_")):
                continue
            frame = pd.read_csv(
                io.BytesIO(zf.read(name)),
                parse_dates=["date"],
            )
            for day, group in frame.groupby(frame["date"].dt.date):
                activity = group["activity"].to_numpy(dtype=np.float64)
                if activity.size != MIN_COMPLETE_MINUTES:
                    partial_days += 1
                    continue
                mean_act = float(activity.mean())
                std_act = float(activity.std(ddof=1))
                peak_activity = float(activity.max())
                if float(activity.std()) == 0.0:
                    autocorrelation = float("nan")
                else:
                    autocorrelation = float(np.corrcoef(activity[:-1], activity[1:])[0, 1])
                rms_act = float(np.sqrt(np.mean(activity * activity)))
                rows.append(
                    {
                        "subject": subject,
                        "day": str(day),
                        "label": int(subject.startswith("condition_")),
                        "mean_act": mean_act,
                        "std_act": std_act,
                        "peak_activity": peak_activity,
                        "autocorrelation_act": autocorrelation,
                        "rms_act": rms_act,
                        "skewness_act": _safe_skew(activity),
                        "kurtosis_act": _safe_kurtosis(activity),
                        "shape_factor_act": rms_act / mean_act if mean_act else float("nan"),
                        "crest_factor_act": peak_activity / rms_act if rms_act else float("nan"),
                        "impulse_factor_act": peak_activity / mean_act if mean_act else float("nan"),
                    }
                )
        scores = pd.read_csv(io.BytesIO(zf.read("data/scores.csv")))
    frame = pd.DataFrame(rows)
    frame["all_zero"] = (frame["mean_act"] == 0.0) & (frame["peak_activity"] == 0.0)
    frame = frame.sort_values(["subject", "day"]).reset_index(drop=True)
    return frame, scores, partial_days


def validate_against_tdf(frame: pd.DataFrame) -> dict:
    condition = pd.read_csv(TDF_CONDITION, parse_dates=["date"])
    control = pd.read_csv(TDF_CONTROL, parse_dates=["date"])
    tdf = pd.concat([condition, control], ignore_index=True)
    tdf["day"] = tdf["date"].dt.date.astype(str)

    raw_key: dict[tuple, list[dict]] = defaultdict(list)
    for record in frame.to_dict("records"):
        key = (
            record["day"],
            round(float(record["mean_act"]), 6),
            int(record["peak_activity"]),
        )
        raw_key[key].append(record)

    matched: list[tuple[dict, dict]] = []
    ambiguous: list[tuple[dict, list[dict]]] = []
    unmatched: list[dict] = []
    for record in tdf.to_dict("records"):
        key = (
            record["day"],
            round(float(record["mean_act"]), 6),
            int(record["peak_activity"]),
        )
        candidates = raw_key.get(key, [])
        if not candidates:
            unmatched.append(record)
        elif len(candidates) == 1:
            matched.append((record, candidates[0]))
        else:
            ambiguous.append((record, candidates))

    def _values(record: dict) -> tuple:
        return (
            round(float(record["mean_act"]), 6),
            round(float(record["std_act"]), 6),
            int(record["peak_activity"]),
        )

    ambiguous_consistent = True
    compared: list[tuple[dict, dict]] = list(matched)
    for tdf_record, candidates in ambiguous:
        if len({_values(candidate) for candidate in candidates}) != 1:
            ambiguous_consistent = False
        compared.extend((tdf_record, candidate) for candidate in candidates)

    diffs = {"mean_act": [], "std_act": [], "peak_activity": [], "autocorrelation_act": []}
    label_mismatches = 0
    for tdf_record, raw_record in compared:
        diffs["mean_act"].append(abs(float(tdf_record["mean_act"]) - float(raw_record["mean_act"])))
        diffs["std_act"].append(abs(float(tdf_record["std_act"]) - float(raw_record["std_act"])))
        diffs["peak_activity"].append(abs(float(tdf_record["peak_activity"]) - float(raw_record["peak_activity"])))
        if math.isfinite(float(tdf_record["autocorrelation_act"])) and math.isfinite(
            float(raw_record["autocorrelation_act"])
        ):
            diffs["autocorrelation_act"].append(
                abs(float(tdf_record["autocorrelation_act"]) - float(raw_record["autocorrelation_act"]))
            )
        tdf_label = 1 if tdf_record["Label"] == "condition" else 0
        if tdf_label != int(raw_record["label"]):
            label_mismatches += 1

    ambiguous_zero_rows = sum(
        1 for record, _ in ambiguous if float(record["mean_act"]) == 0.0 and float(record["peak_activity"]) == 0.0
    )
    return {
        "tdf_rows": int(len(tdf)),
        "matched_rows": int(len(matched)),
        "ambiguous_rows": int(len(ambiguous)),
        "unmatched_rows": int(len(unmatched)),
        "ambiguous_zero_rows": int(ambiguous_zero_rows),
        "ambiguous_consistent": bool(ambiguous_consistent),
        "label_mismatches": int(label_mismatches),
        "max_abs_diff_mean_act": float(max(diffs["mean_act"])) if diffs["mean_act"] else None,
        "max_abs_diff_std_act": float(max(diffs["std_act"])) if diffs["std_act"] else None,
        "max_abs_diff_peak_activity": float(max(diffs["peak_activity"])) if diffs["peak_activity"] else None,
        "max_abs_diff_autocorrelation_act": float(max(diffs["autocorrelation_act"]))
        if diffs["autocorrelation_act"]
        else None,
        "autocorrelation_compared_rows": int(len(diffs["autocorrelation_act"])),
        "note": (
            "TDF rows do not carry subject IDs. 996/1029 rows match one raw day "
            "uniquely on date + mean + peak. The remaining 33 TDF rows share their "
            "key with 2-3 raw days: 31 are all-zero days from control_1/31/32, and "
            "2 are the identical control_6/control_7 rows on 2003-04-12. All "
            "ambiguous candidates have identical feature values and labels, so the "
            "raw per-subject files (which retain the subject ID for all 1029 "
            "complete days) remain the source of truth; TDF is only a definition "
            "check."
        ),
    }


def subject_mean_table(frame: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    table = frame.groupby("subject").agg(label=("label", "first"), days=("day", "size"))
    for feature in features:
        table[feature] = frame.groupby("subject")[feature].mean()
    table = table.reset_index()
    for feature in features:
        table[feature] = table[feature].fillna(0.0)
    return table


def _fit_predict(X_train, y_train, X_test) -> np.ndarray:
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(C=1.0, max_iter=2000, solver="lbfgs"),
    )
    model.fit(X_train, y_train)
    return model.predict_proba(X_test)[:, 1]


def _ece(y: np.ndarray, p: np.ndarray, bins: int = 5) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    index = np.digitize(p, edges[1:-1])
    ece = 0.0
    for bin_id in range(bins):
        mask = index == bin_id
        if mask.any():
            ece += abs(float(y[mask].mean()) - float(p[mask].mean())) * float(mask.mean())
    return float(ece)


def _calibration_slope(y: np.ndarray, p: np.ndarray) -> tuple[float, float]:
    clipped = np.clip(p, 1e-6, 1.0 - 1e-6)
    logit = np.log(clipped / (1.0 - clipped)).reshape(-1, 1)
    model = LogisticRegression(C=1e6, max_iter=1000)
    model.fit(logit, y)
    return float(model.coef_[0, 0]), float(model.intercept_[0])


def metrics(y, p) -> dict:
    y = np.asarray(y, dtype=int)
    p = np.asarray(p, dtype=float)
    slope, intercept = _calibration_slope(y, p)
    return {
        "n": int(len(y)),
        "positives": int(y.sum()),
        "prevalence": float(y.mean()),
        "auc": float(roc_auc_score(y, p)),
        "auprc": float(average_precision_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "mean_predicted": float(p.mean()),
        "calibration_ece_5bin": _ece(y, p, 5),
        "calibration_slope": slope,
        "calibration_intercept": intercept,
    }


def threshold_table(y, p) -> dict:
    y = np.asarray(y, dtype=int)
    p = np.asarray(p, dtype=float)
    out = {}
    for cut in CUTS:
        pred = p >= cut
        tp = int(((pred == 1) & (y == 1)).sum())
        fp = int(((pred == 1) & (y == 0)).sum())
        fn = int(((pred == 0) & (y == 1)).sum())
        tn = int(((pred == 0) & (y == 0)).sum())
        out[f"{cut:.2f}"] = {
            "threshold": cut,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "sensitivity": tp / (tp + fn) if tp + fn else None,
            "specificity": tn / (tn + fp) if tn + fp else None,
            "ppv": tp / (tp + fp) if tp + fp else None,
            "npv": tn / (tn + fn) if tn + fn else None,
            "alert_rate": (tp + fp) / len(y),
        }
    return out


def bootstrap_subject_metrics(y, p, b: int = BOOTSTRAP_B) -> dict:
    y = np.asarray(y, dtype=int)
    p = np.asarray(p, dtype=float)
    rng = np.random.default_rng(SEED)
    aucs: list[float] = []
    briers: list[float] = []
    auprcs: list[float] = []
    for _ in range(b):
        idx = rng.integers(0, len(y), len(y))
        yy = y[idx]
        pp = p[idx]
        if len(np.unique(yy)) < 2:
            continue
        aucs.append(float(roc_auc_score(yy, pp)))
        briers.append(float(brier_score_loss(yy, pp)))
        auprcs.append(float(average_precision_score(yy, pp)))
    return {
        "bootstrap_b": int(b),
        "seed": SEED,
        "valid_resamples": int(len(aucs)),
        "auc_95ci": [float(np.percentile(aucs, 2.5)), float(np.percentile(aucs, 97.5))] if aucs else None,
        "brier_95ci": [float(np.percentile(briers, 2.5)), float(np.percentile(briers, 97.5))] if briers else None,
        "auprc_95ci": [float(np.percentile(auprcs, 2.5)), float(np.percentile(auprcs, 97.5))] if auprcs else None,
    }


def loso_predictions(X, y) -> np.ndarray:
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=int)
    oof = np.zeros(len(y), dtype=float)
    for i in range(len(y)):
        train = np.arange(len(y)) != i
        oof[i] = float(_fit_predict(X[train], y[train], X[i : i + 1])[0])
    return oof


def repeated_grouped_cv(X, y, groups, repeats: int = N_REPEATS) -> dict:
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=int)
    groups = np.asarray(groups)
    day_aucs: list[float] = []
    day_auprcs: list[float] = []
    day_briers: list[float] = []
    subject_aucs: list[float] = []
    day_sum = np.zeros(len(y), dtype=float)
    day_count = np.zeros(len(y), dtype=int)
    subject_predictions: dict[str, list[float]] = defaultdict(list)

    for repeat_seed in range(SEED, SEED + repeats):
        cv = StratifiedGroupKFold(
            n_splits=N_SPLITS,
            shuffle=True,
            random_state=repeat_seed,
        )
        oof = np.zeros(len(y), dtype=float)
        for train_idx, test_idx in cv.split(X, y, groups):
            if set(groups[train_idx]) & set(groups[test_idx]):
                raise AssertionError("subject leaked across grouped CV folds")
            oof[test_idx] = _fit_predict(X[train_idx], y[train_idx], X[test_idx])
        day_aucs.append(float(roc_auc_score(y, oof)))
        day_auprcs.append(float(average_precision_score(y, oof)))
        day_briers.append(float(brier_score_loss(y, oof)))
        day_sum += oof
        day_count += 1

        by_subject = pd.DataFrame({"subject": groups, "label": y, "p": oof})
        subject_frame = by_subject.groupby("subject").agg(
            label=("label", "first"),
            p=("p", "mean"),
        )
        subject_aucs.append(float(roc_auc_score(subject_frame["label"], subject_frame["p"])))
        for subject, probability in subject_frame["p"].items():
            subject_predictions[subject].append(float(probability))

    if np.any(day_count != repeats):
        raise AssertionError("not every day received one prediction per repeat")

    subject_pooled = pd.DataFrame(
        [(subject, float(np.mean(values))) for subject, values in subject_predictions.items()],
        columns=["subject", "p"],
    ).sort_values("subject")
    subject_pooled["label"] = subject_pooled["subject"].str.startswith("condition_").astype(int)
    day_pooled = day_sum / day_count
    return {
        "n_splits": N_SPLITS,
        "n_repeats": repeats,
        "day_auc_mean": float(np.mean(day_aucs)),
        "day_auc_sd": float(np.std(day_aucs)),
        "day_auc_range": [float(min(day_aucs)), float(max(day_aucs))],
        "day_auc_pooled": float(roc_auc_score(y, day_pooled)),
        "day_auprc_mean": float(np.mean(day_auprcs)),
        "day_brier_mean": float(np.mean(day_briers)),
        "subject_auc_mean": float(np.mean(subject_aucs)),
        "subject_auc_sd": float(np.std(subject_aucs)),
        "subject_auc_range": [float(min(subject_aucs)), float(max(subject_aucs))],
        "subject_metrics_pooled": metrics(subject_pooled["label"], subject_pooled["p"]),
        "subject_bootstrap": bootstrap_subject_metrics(subject_pooled["label"], subject_pooled["p"]),
        "thresholds_pooled": threshold_table(subject_pooled["label"], subject_pooled["p"]),
        "subject_pooled": subject_pooled,
        "per_repeat_day_auc": day_aucs,
        "per_repeat_subject_auc": subject_aucs,
    }


def repeated_naive_cv(X, y, groups, repeats: int = N_REPEATS) -> dict:
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=int)
    groups = np.asarray(groups)
    day_aucs: list[float] = []
    subject_aucs: list[float] = []
    subject_predictions: dict[str, list[float]] = defaultdict(list)

    for repeat_seed in range(SEED, SEED + repeats):
        cv = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=repeat_seed)
        oof = np.zeros(len(y), dtype=float)
        for train_idx, test_idx in cv.split(X, y):
            oof[test_idx] = _fit_predict(X[train_idx], y[train_idx], X[test_idx])
        day_aucs.append(float(roc_auc_score(y, oof)))

        by_subject = pd.DataFrame({"subject": groups, "label": y, "p": oof})
        subject_frame = by_subject.groupby("subject").agg(
            label=("label", "first"),
            p=("p", "mean"),
        )
        subject_aucs.append(float(roc_auc_score(subject_frame["label"], subject_frame["p"])))
        for subject, probability in subject_frame["p"].items():
            subject_predictions[subject].append(float(probability))

    subject_pooled = pd.DataFrame(
        [(subject, float(np.mean(values))) for subject, values in subject_predictions.items()],
        columns=["subject", "p"],
    ).sort_values("subject")
    subject_pooled["label"] = subject_pooled["subject"].str.startswith("condition_").astype(int)
    return {
        "n_splits": N_SPLITS,
        "n_repeats": repeats,
        "day_auc_mean": float(np.mean(day_aucs)),
        "day_auc_sd": float(np.std(day_aucs)),
        "subject_auc_mean": float(np.mean(subject_aucs)),
        "subject_auc_sd": float(np.std(subject_aucs)),
        "subject_metrics_pooled": metrics(subject_pooled["label"], subject_pooled["p"]),
        "subject_pooled": subject_pooled,
    }


def loso_subject_result(X, y, subjects) -> dict:
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=int)
    oof = loso_predictions(X, y)
    return {
        "n_subjects": int(len(y)),
        "n_positives": int(y.sum()),
        "metrics": metrics(y, oof),
        "bootstrap": bootstrap_subject_metrics(y, oof),
        "thresholds": threshold_table(y, oof),
        "predictions": dict(zip(subjects, oof.tolist())),
    }


def permutation_test_loso(X, y, observed_auc: float, b: int = PERMUTATION_B) -> dict:
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=int)
    rng = np.random.default_rng(SEED)
    count = 0
    aucs: list[float] = []
    for _ in range(b):
        permuted = rng.permutation(y)
        oof = loso_predictions(X, permuted)
        auc = float(roc_auc_score(permuted, oof))
        aucs.append(auc)
        if auc >= observed_auc:
            count += 1
    return {
        "metric": "subject_level_auc",
        "n_permutations": int(b),
        "seed": SEED,
        "observed": float(observed_auc),
        "permuted_mean": float(np.mean(aucs)),
        "permuted_sd": float(np.std(aucs)),
        "permuted_95ci": [float(np.percentile(aucs, 2.5)), float(np.percentile(aucs, 97.5))],
        "p_value_one_sided": float((1 + count) / (1 + b)),
    }


def permutation_test_grouped(X, y, groups, observed_auc: float, b: int = PERMUTATION_B) -> dict:
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=int)
    groups = np.asarray(groups)
    subjects = sorted(set(groups))
    subject_labels = pd.DataFrame({"subject": groups, "label": y}).groupby("subject")["label"].first()
    base_labels = subject_labels.loc[subjects].to_numpy()
    rng = np.random.default_rng(SEED)
    count = 0
    aucs: list[float] = []
    for _ in range(b):
        permuted_subject_labels = rng.permutation(base_labels)
        mapping = dict(zip(subjects, permuted_subject_labels))
        permuted_day_labels = np.array([mapping[subject] for subject in groups])
        repeat_aucs: list[float] = []
        for repeat_seed in range(SEED, SEED + N_REPEATS):
            cv = StratifiedGroupKFold(
                n_splits=N_SPLITS,
                shuffle=True,
                random_state=repeat_seed,
            )
            oof = np.zeros(len(permuted_day_labels), dtype=float)
            for train_idx, test_idx in cv.split(X, permuted_day_labels, groups):
                oof[test_idx] = _fit_predict(
                    X[train_idx],
                    permuted_day_labels[train_idx],
                    X[test_idx],
                )
            by_subject = pd.DataFrame({"subject": groups, "label": permuted_day_labels, "p": oof})
            subject_frame = by_subject.groupby("subject").agg(
                label=("label", "first"),
                p=("p", "mean"),
            )
            repeat_aucs.append(float(roc_auc_score(subject_frame["label"], subject_frame["p"])))
        auc = float(np.mean(repeat_aucs))
        aucs.append(auc)
        if auc >= observed_auc:
            count += 1
    return {
        "metric": "subject_level_auc_after_multiday_aggregation",
        "n_permutations": int(b),
        "seed": SEED,
        "n_repeats_per_permutation": N_REPEATS,
        "observed": float(observed_auc),
        "permuted_mean": float(np.mean(aucs)),
        "permuted_sd": float(np.std(aucs)),
        "permuted_95ci": [float(np.percentile(aucs, 2.5)), float(np.percentile(aucs, 97.5))],
        "p_value_one_sided": float((1 + count) / (1 + b)),
    }


def demographics_control(table: pd.DataFrame, scores: pd.DataFrame) -> dict:
    merged = table.merge(
        scores[["number", "gender", "age"]],
        left_on="subject",
        right_on="number",
        how="left",
    )
    age_parts = merged["age"].astype(str).str.extract(r"(\d+)-(\d+)").astype(float)
    merged["age_mid"] = age_parts.mean(axis=1)
    merged["age_mid"] = merged["age_mid"].fillna(merged["age_mid"].median())
    merged["gender"] = pd.to_numeric(merged["gender"], errors="coerce")
    merged["gender"] = merged["gender"].fillna(merged["gender"].median())
    oof = loso_predictions(merged[["gender", "age_mid"]].to_numpy(), merged["label"].to_numpy())
    return {
        "features": ["gender", "age_mid"],
        "note": "Age bin midpoint and encoded gender only; no actigraphy. Negative control, not a model.",
        "metrics": metrics(merged["label"], oof),
    }


def univariate_subject_auc(table: pd.DataFrame) -> dict:
    out = {}
    for feature in PRIMARY_FEATURES:
        auc = float(roc_auc_score(table["label"], table[feature]))
        out[feature] = {
            "auc_direction_not_flipped": auc,
            "auc_if_inverted": float(1.0 - auc),
            "direction": "higher value -> higher label" if auc >= 0.5 else "higher value -> lower label",
        }
    return out


def madrs_correlation(subject_pooled: pd.DataFrame, scores: pd.DataFrame) -> dict:
    merged = subject_pooled.merge(
        scores[["number", "madrs1", "madrs2"]],
        left_on="subject",
        right_on="number",
        how="left",
    )
    condition = merged[merged["subject"].str.startswith("condition_")]
    out = {"n_condition": int(len(condition)), "note": "Exploratory; controls have no MADRS."}
    for column in ("madrs1", "madrs2"):
        pair = condition[[column, "p"]].dropna()
        if len(pair) >= 3 and pair[column].nunique() > 1 and pair["p"].nunique() > 1:
            result = spearmanr(pair[column], pair["p"])
            out[column] = {
                "n": int(len(pair)),
                "spearman_rho": float(result.statistic),
                "p_value": float(result.pvalue),
            }
        else:
            out[column] = {"n": int(len(pair)), "spearman_rho": None, "p_value": None}
    return out


def sensitivity_excluding_zero_days(frame: pd.DataFrame) -> dict:
    nonzero = frame[~frame["all_zero"]].copy()
    X = nonzero[PRIMARY_FEATURES].fillna(0.0).to_numpy(dtype=float)
    y = nonzero["label"].to_numpy(dtype=int)
    groups = nonzero["subject"].to_numpy()
    result = repeated_grouped_cv(X, y, groups)
    return {
        "definition": "exclude 70 all-zero complete days; same 4 features and repeated grouped CV",
        "n_days": int(len(nonzero)),
        "n_subjects": int(nonzero["subject"].nunique()),
        "subject_auc_mean": result["subject_auc_mean"],
        "subject_auc_sd": result["subject_auc_sd"],
        "subject_metrics_pooled": result["subject_metrics_pooled"],
        "day_auc_pooled": result["day_auc_pooled"],
    }


def sensitivity_min_days(frame: pd.DataFrame, minimum: int = 14) -> dict:
    counts = frame.groupby("subject").size()
    keep = set(counts[counts >= minimum].index)
    subset = frame[frame["subject"].isin(keep)].copy()
    X = subset[PRIMARY_FEATURES].fillna(0.0).to_numpy(dtype=float)
    y = subset["label"].to_numpy(dtype=int)
    groups = subset["subject"].to_numpy()
    result = repeated_grouped_cv(X, y, groups)
    return {
        "definition": f"keep subjects with at least {minimum} complete days",
        "n_days": int(len(subset)),
        "n_subjects": int(subset["subject"].nunique()),
        "n_subjects_dropped": int(frame["subject"].nunique() - len(keep)),
        "subject_auc_mean": result["subject_auc_mean"],
        "subject_auc_sd": result["subject_auc_sd"],
        "subject_metrics_pooled": result["subject_metrics_pooled"],
        "day_auc_pooled": result["day_auc_pooled"],
    }


def main() -> int:
    if not RAW_ZIP.exists():
        raise SystemExit(f"raw Depresjon zip not found: {RAW_ZIP}")

    frame, scores, partial_days = load_days()
    if len(frame) != 1029:
        raise AssertionError(f"expected 1029 complete days, got {len(frame)}")
    if frame["subject"].nunique() != 55:
        raise AssertionError("expected 55 subjects")
    if int(frame["label"].sum()) != 359:
        raise AssertionError("expected 359 positive days")

    tdf_validation = validate_against_tdf(frame)
    if tdf_validation["matched_rows"] != 996:
        raise AssertionError("TDF validation row count changed")
    if tdf_validation["ambiguous_rows"] != 33 or tdf_validation["unmatched_rows"] != 0:
        raise AssertionError("TDF ambiguous/unmatched rows changed")
    if not tdf_validation["ambiguous_consistent"]:
        raise AssertionError("TDF ambiguous candidates disagree on feature values")
    if tdf_validation["label_mismatches"] != 0:
        raise AssertionError("subject label disagrees with TDF label")
    for key in (
        "max_abs_diff_mean_act",
        "max_abs_diff_std_act",
        "max_abs_diff_peak_activity",
        "max_abs_diff_autocorrelation_act",
    ):
        value = tdf_validation[key]
        if value is not None and value > 1e-8:
            raise AssertionError(f"{key} too large: {value}")

    subject4 = subject_mean_table(frame, PRIMARY_FEATURES)
    subject10 = subject_mean_table(frame, EXTENDED_FEATURES)

    X_primary = frame[PRIMARY_FEATURES].fillna(0.0).to_numpy(dtype=float)
    y_day = frame["label"].to_numpy(dtype=int)
    groups = frame["subject"].to_numpy()

    primary = loso_subject_result(
        subject4[PRIMARY_FEATURES].to_numpy(dtype=float),
        subject4["label"].to_numpy(dtype=int),
        subject4["subject"].tolist(),
    )
    secondary = repeated_grouped_cv(X_primary, y_day, groups)
    naive = repeated_naive_cv(X_primary, y_day, groups)

    extended_primary = loso_subject_result(
        subject10[EXTENDED_FEATURES].to_numpy(dtype=float),
        subject10["label"].to_numpy(dtype=int),
        subject10["subject"].tolist(),
    )
    extended_secondary = repeated_grouped_cv(
        frame[EXTENDED_FEATURES].fillna(0.0).to_numpy(dtype=float),
        y_day,
        groups,
    )

    permutation_primary = permutation_test_loso(
        subject4[PRIMARY_FEATURES].to_numpy(dtype=float),
        subject4["label"].to_numpy(dtype=int),
        primary["metrics"]["auc"],
    )
    permutation_secondary = permutation_test_grouped(
        X_primary,
        y_day,
        groups,
        secondary["subject_auc_mean"],
    )

    demographics = demographics_control(subject4, scores)
    univariate = univariate_subject_auc(subject4)
    madrs = madrs_correlation(secondary["subject_pooled"], scores)
    sensitivity_zero = sensitivity_excluding_zero_days(frame)
    sensitivity_days = sensitivity_min_days(frame, 14)

    prediction_table = subject4.merge(
        subject10[["subject"] + [column for column in EXTENDED_FEATURES if column not in PRIMARY_FEATURES]],
        on="subject",
        how="left",
    )
    prediction_table = prediction_table.merge(
        scores[["number", "gender", "age", "madrs1", "madrs2"]],
        left_on="subject",
        right_on="number",
        how="left",
    )
    prediction_table = prediction_table.drop(columns=["number"])
    prediction_table["p_subject_mean_loso"] = prediction_table["subject"].map(primary["predictions"])
    prediction_table["p_grouped_multiday"] = prediction_table["subject"].map(
        secondary["subject_pooled"].set_index("subject")["p"]
    )
    prediction_table["p_naive_rowlevel"] = prediction_table["subject"].map(
        naive["subject_pooled"].set_index("subject")["p"]
    )
    prediction_table = prediction_table.sort_values("subject").reset_index(drop=True)
    prediction_table.to_csv(OUT_CSV, index=False)
    csv_sha = _sha256(OUT_CSV)

    for result in (secondary, naive, extended_secondary):
        result.pop("subject_pooled")

    subject_days = frame.groupby("subject").size()
    dataset = {
        "raw_zip": str(RAW_ZIP.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "raw_zip_sha256": _sha256(RAW_ZIP),
        "tdf_condition_sha256": _sha256(TDF_CONDITION),
        "tdf_control_sha256": _sha256(TDF_CONTROL),
        "license_file": str(LICENSE_FILE.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "license_note": (
            "The in-repo depresjon-code LICENSE is MIT and covers the code "
            "repository; the Depresjon data itself has no separate license file "
            "in this repository, so redistribution/citation must follow the "
            "original dataset terms."
        ),
        "n_subjects": int(frame["subject"].nunique()),
        "n_condition_subjects": int(scores["number"].str.startswith("condition_").sum()),
        "n_control_subjects": int(scores["number"].str.startswith("control_").sum()),
        "n_complete_days": int(len(frame)),
        "n_partial_days_excluded": int(partial_days),
        "n_all_zero_complete_days": int(frame["all_zero"].sum()),
        "positive_days": int(frame["label"].sum()),
        "day_prevalence": float(frame["label"].mean()),
        "subject_days_min": int(subject_days.min()),
        "subject_days_max": int(subject_days.max()),
        "subject_days_median": float(subject_days.median()),
        "label_source": "raw file directory: data/condition/* vs data/control/*",
        "evaluation_type": "same-cohort retrospective baseline; not external validation",
    }

    features = {
        "primary": PRIMARY_FEATURES,
        "extended_exploratory": EXTENDED_FEATURES,
        "definitions": {
            "mean_act": "mean of 1440 minute-level activity values for a complete day",
            "std_act": "sample standard deviation (ddof=1) of the 1440 values",
            "peak_activity": "maximum minute-level activity value",
            "autocorrelation_act": "lag-1 Pearson correlation of consecutive minute values; undefined on constant days",
            "extended": "rms/skewness/kurtosis/shape/crest/impulse factors recomputed from the same minute series",
        },
        "missing_handling": (
            "autocorrelation is undefined on constant days "
            f"({int(frame['autocorrelation_act'].isna().sum())} days). Day-level "
            "models fill it with 0.0; subject-mean models average available values "
            "and fill an all-missing subject with 0.0."
        ),
        "tdf_validation": tdf_validation,
    }

    design = {
        "primary_subject_mean_loso": (
            "Aggregate each subject's complete days to the mean of the four real "
            "features, then leave one subject out; scaler and logistic regression "
            "fit on the other 54 subjects only."
        ),
        "secondary_grouped_multiday": (
            "Train a day-level logistic regression with 5-fold StratifiedGroupKFold "
            "(subjects never split across folds), repeat 10 times, then average "
            "held-out day probabilities per subject."
        ),
        "naive_leakage_comparison": (
            "Same 5-fold repeated CV but with StratifiedKFold on days, which lets "
            "days from one subject appear in both train and test; used only to "
            "quantify optimism from subject leakage."
        ),
        "extended_exploratory": "10 features, both protocols; not a production candidate.",
        "bootstrap": f"{BOOTSTRAP_B} subject-level resamples, seed {SEED}",
        "permutation": f"{PERMUTATION_B} subject-label permutations, seed {SEED}",
    }

    sanity_checks = {
        "n_subjects_55": bool(frame["subject"].nunique() == 55),
        "n_complete_days_1029": bool(len(frame) == 1029),
        "positive_days_359": bool(int(frame["label"].sum()) == 359),
        "tdf_matched_996": bool(tdf_validation["matched_rows"] == 996),
        "tdf_ambiguous_33_consistent": bool(
            tdf_validation["ambiguous_rows"] == 33
            and tdf_validation["ambiguous_consistent"]
            and tdf_validation["unmatched_rows"] == 0
        ),
        "tdf_label_mismatches_0": bool(tdf_validation["label_mismatches"] == 0),
        "grouped_folds_disjoint": True,
        "all_primary_metrics_finite": bool(
            all(math.isfinite(float(primary["metrics"][key])) for key in ("auc", "auprc", "brier"))
            and all(math.isfinite(float(secondary["subject_metrics_pooled"][key])) for key in ("auc", "auprc", "brier"))
        ),
        "csv_sha256": csv_sha,
    }

    payload = {
        "round": "ROUND_48",
        "status": "descriptive_offline_real_actigraphy_baseline_not_production",
        "external_validation": False,
        "production_changed": False,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": dataset,
        "features": features,
        "design": design,
        "results": {
            "primary_subject_mean_loso_4feat": primary,
            "secondary_grouped_multiday_4feat": secondary,
            "naive_rowlevel_4feat": naive,
            "extended_subject_mean_loso_10feat": extended_primary,
            "extended_grouped_multiday_10feat": extended_secondary,
            "permutation_primary_loso": permutation_primary,
            "permutation_secondary_grouped": permutation_secondary,
            "demographics_only_control": demographics,
            "univariate_subject_auc": univariate,
            "madrs_correlation": madrs,
            "sensitivity_excluding_zero_days": sensitivity_zero,
            "sensitivity_min_14_days": sensitivity_days,
        },
        "artifacts": {
            "subject_predictions_csv": OUT_CSV.relative_to(PROJECT_ROOT).as_posix(),
            "subject_predictions_sha256": csv_sha,
            "report": OUT_REPORT.relative_to(PROJECT_ROOT).as_posix(),
        },
        "sanity_checks": sanity_checks,
        "interpretation": {
            "why_not_external_validation": [
                "Same Depresjon cohort used for both the original label and this baseline; no independent cohort.",
                "55 subjects, clinical actigraphy, condition/control labels; not general population or consumer wearables.",
                "Retrospective complete-day summaries; no prospective prediction of onset or relapse.",
            ],
            "allowed_claims": [
                "On Depresjon, a subject-grouped real-actigraphy-only baseline reaches the reported AUC.",
                "The conservative subject-mean LOSO estimate and the multi-day grouped estimate differ; report both and do not treat either as a stable clinical performance estimate.",
                "The dominant univariate signal is lower mean activity; MADRS severity is not tracked by this baseline.",
            ],
            "forbidden_claims": [
                "This baseline is externally validated or ready for production.",
                "This baseline can be compared directly with the synthetic-feature production AUC 0.9451.",
                "These numbers apply to consumer wearables, general adults, or clinical diagnosis.",
                "The 10-feature exploratory model should replace the production model.",
            ],
        },
    }

    payload = _finite(payload)
    text = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False)
    OUT_JSON.write_text(text, encoding="utf-8")
    OUT_MIRROR.parent.mkdir(parents=True, exist_ok=True)
    OUT_MIRROR.write_text(text, encoding="utf-8")
    OUT_REPORT.write_text(render_report(payload), encoding="utf-8")

    print("[real_actigraphy_baseline]")
    print(
        f"  subjects={dataset['n_subjects']} days={dataset['n_complete_days']} "
        f"positives={dataset['positive_days']} partial_excluded={dataset['n_partial_days_excluded']}"
    )
    print(
        "  primary subject-mean LOSO 4feat: "
        f"AUC={primary['metrics']['auc']:.4f} "
        f"CI={primary['bootstrap']['auc_95ci']} "
        f"Brier={primary['metrics']['brier']:.4f} "
        f"perm_p={permutation_primary['p_value_one_sided']:.4f}"
    )
    print(
        "  secondary grouped multiday 4feat: "
        f"subjectAUC={secondary['subject_auc_mean']:.4f}"
        f"±{secondary['subject_auc_sd']:.4f} "
        f"pooled={secondary['subject_metrics_pooled']['auc']:.4f} "
        f"dayAUC={secondary['day_auc_mean']:.4f}"
        f"±{secondary['day_auc_sd']:.4f} "
        f"perm_p={permutation_secondary['p_value_one_sided']:.4f}"
    )
    print(f"  naive row-level 4feat: subjectAUC={naive['subject_auc_mean']:.4f}±{naive['subject_auc_sd']:.4f}")
    print(
        "  extended 10feat: "
        f"subject-mean AUC={extended_primary['metrics']['auc']:.4f} "
        f"grouped subjectAUC={extended_secondary['subject_auc_mean']:.4f}"
    )
    print(f"  -> {OUT_JSON.relative_to(PROJECT_ROOT)}")
    print(f"  -> {OUT_CSV.relative_to(PROJECT_ROOT)}")
    print(f"  -> {OUT_REPORT.relative_to(PROJECT_ROOT)}")
    return 0


def render_report(payload: dict) -> str:
    dataset = payload["dataset"]
    features = payload["features"]
    results = payload["results"]
    primary = results["primary_subject_mean_loso_4feat"]
    secondary = results["secondary_grouped_multiday_4feat"]
    naive = results["naive_rowlevel_4feat"]
    extended_primary = results["extended_subject_mean_loso_10feat"]
    extended_secondary = results["extended_grouped_multiday_10feat"]
    perm_primary = results["permutation_primary_loso"]
    perm_secondary = results["permutation_secondary_grouped"]
    demographics = results["demographics_only_control"]
    univariate = results["univariate_subject_auc"]
    madrs = results["madrs_correlation"]
    sens_zero = results["sensitivity_excluding_zero_days"]
    sens_days = results["sensitivity_min_14_days"]
    tdf = features["tdf_validation"]

    def fmt(value, digits=4):
        return "NA" if value is None else f"{value:.{digits}f}"

    lines = [
        "# Depresjon 真实 actigraphy 分组基线（ROUND_48）",
        "",
        "> 本文件由 `backend/scripts/modeling/eval/v1_48/01_real_actigraphy_baseline.py` 生成。",
        "> 只读离线评估，**没有修改生产模型、工件、阈值或运行时**。",
        "> **这不是外部验证，也不是生产替换。**",
        ">",
        "> **ROUND_49 更新（2026-11-02）**：本报告的 0.6454 对分析规范敏感",
        "> （18 个规范的受试者级 LOSO AUC 为 0.5855–0.7364），且与零活动日/记录时长代理纠缠",
        "> （仅佩戴代理的 LOSO AUC 为 0.7921）。引用本报告前必须同时阅读",
        "> `docs/model-evaluation/REAL_BASELINE_ROBUSTNESS.md`；0.6454 不是稳健性能估计。",
        ">",
        "> **ROUND_50 更新（2026-11-02）**：多日聚合次口径的 0.7620 也已做 9 规范审计；",
        "> 预注册规范精确复现，但 9 规范受试者级 AUC 为 0.6565–0.7620，0.7620 是网格最大值，",
        "> 不是稳健协议估计；日级与受试者级 LOSO 回答不同问题，不能互相替代。见",
        "> `docs/model-evaluation/REAL_BASELINE_PROTOCOL_ROBUSTNESS.md`。",
        "",
        "## 0. 结论先行",
        "",
        f"- 数据：{dataset['n_subjects']} 名受试者（{dataset['n_condition_subjects']} 例 / "
        f"{dataset['n_control_subjects']} 对照），{dataset['n_complete_days']} 个完整日；"
        f"排除 {dataset['n_partial_days_excluded']} 个非 1440 分钟日。",
        f"- 保守主口径（受试者均值 + LOSO，4 个真实特征）：AUC **{primary['metrics']['auc']:.4f}** "
        f"[{primary['bootstrap']['auc_95ci'][0]:.4f}, {primary['bootstrap']['auc_95ci'][1]:.4f}]，"
        f"Brier {primary['metrics']['brier']:.4f}；置换检验 p={perm_primary['p_value_one_sided']:.4f}。",
        f"- 多日聚合次口径（日级分组 CV + 受试者聚合，4 个真实特征）：受试者级 AUC "
        f"**{secondary['subject_auc_mean']:.4f} ± {secondary['subject_auc_sd']:.4f}**，"
        f"合并 OOF 为 {secondary['subject_metrics_pooled']['auc']:.4f}；"
        f"置换检验 p={perm_secondary['p_value_one_sided']:.4f}。",
        "- 两个口径不一致，说明估计依赖「是否把同一天的预测聚合成多日平均」；不能只挑其中较大的一个对外报告。",
        "- 真实 actigraphy 在本队列有可检出的组间信号（两种受试者级口径均高于 0.5）；"
        "生产 MLP 的 0.9451 是合成特征读数，特征来源、标签与协议不同，不能并列比较。",
        "",
        "## 1. 数据与来源",
        "",
        "| 项目 | 值 |",
        "|---|---|",
        f"| 原始压缩包 | `{dataset['raw_zip']}` |",
        f"| ZIP SHA-256 | `{dataset['raw_zip_sha256']}` |",
        f"| TDF_CONDITION SHA-256 | `{dataset['tdf_condition_sha256']}` |",
        f"| TDF_CONTROL SHA-256 | `{dataset['tdf_control_sha256']}` |",
        f"| 受试者 | {dataset['n_subjects']}（{dataset['n_condition_subjects']} 例 / {dataset['n_control_subjects']} 对照） |",
        f"| 完整日 | {dataset['n_complete_days']}；阳性日 {dataset['positive_days']}（{dataset['day_prevalence']:.4f}） |",
        f"| 受试者天数 | {dataset['subject_days_min']}–{dataset['subject_days_max']}（中位 {dataset['subject_days_median']:.0f}） |",
        f"| 非完整日（排除） | {dataset['n_partial_days_excluded']} |",
        f"| 全零完整日 | {dataset['n_all_zero_complete_days']} |",
        f"| 标签来源 | {dataset['label_source']} |",
        f"| 许可 | {dataset['license_note']} |",
        "",
        "### 1.1 与 TDF 的一致性校验",
        "",
        f"- TDF 共 {tdf['tdf_rows']} 行；按「日期 + mean_act + peak_activity」唯一匹配 "
        f"{tdf['matched_rows']} 行；键重复但候选值一致的歧义行 {tdf['ambiguous_rows']} 行；"
        f"完全未匹配 {tdf['unmatched_rows']} 行。",
        f"- 歧义行中全零日 {tdf['ambiguous_zero_rows']} 行，来自 control_1/31/32 的共享零活动日；"
        "另有 2 行是 control_6/control_7 在 2003-04-12 的完全相同日；"
        f"全部候选特征/标签一致：{tdf['ambiguous_consistent']}。",
        f"- 匹配行标签冲突：{tdf['label_mismatches']}。",
        f"- `mean_act` 最大绝对差 {tdf['max_abs_diff_mean_act']:.3e}；"
        f"`std_act` {tdf['max_abs_diff_std_act']:.3e}；"
        f"`peak_activity` {tdf['max_abs_diff_peak_activity']:.3e}；"
        f"`autocorrelation_act` {tdf['max_abs_diff_autocorrelation_act']:.3e} "
        f"（{tdf['autocorrelation_compared_rows']} 行可比）。",
        f"- {tdf['note']}",
        "",
        "## 2. 特征与评估设计",
        "",
        f"- 主特征（4 个）：{', '.join(f'`{f}`' for f in features['primary'])}。",
        f"- 探索特征（10 个）：{', '.join(f'`{f}`' for f in features['extended_exploratory'])}。",
        f"- 缺失处理：{features['missing_handling']}",
        f"- 主口径：{payload['design']['primary_subject_mean_loso']}",
        f"- 次口径：{payload['design']['secondary_grouped_multiday']}",
        f"- 泄漏对照：{payload['design']['naive_leakage_comparison']}",
        f"- Bootstrap：{payload['design']['bootstrap']}；置换：{payload['design']['permutation']}",
        "",
        "## 3. 结果",
        "",
        "| 口径 | 分析单位 | n | AUC | 95% CI / 重复 SD | AUPRC | Brier | 平均预测 |",
        "|---|---|---:|---|---:|---:|---:|---:|",
        f"| 主口径：受试者均值 LOSO，4 特征 | 受试者 | {primary['n_subjects']} | "
        f"{primary['metrics']['auc']:.4f} | "
        f"[{primary['bootstrap']['auc_95ci'][0]:.4f}, {primary['bootstrap']['auc_95ci'][1]:.4f}] | "
        f"{primary['metrics']['auprc']:.4f} | {primary['metrics']['brier']:.4f} | "
        f"{primary['metrics']['mean_predicted']:.4f} |",
        f"| 次口径：日级分组 + 多日聚合，4 特征 | 受试者 | {secondary['subject_metrics_pooled']['n']} | "
        f"{secondary['subject_auc_mean']:.4f} | "
        f"±{secondary['subject_auc_sd']:.4f}（重复） | "
        f"{secondary['subject_metrics_pooled']['auprc']:.4f} | "
        f"{secondary['subject_metrics_pooled']['brier']:.4f} | "
        f"{secondary['subject_metrics_pooled']['mean_predicted']:.4f} |",
        f"| 次口径的日级读数 | 日 | {dataset['n_complete_days']} | "
        f"{secondary['day_auc_mean']:.4f} ± {secondary['day_auc_sd']:.4f} | — | "
        f"{secondary['day_auprc_mean']:.4f} | {secondary['day_brier_mean']:.4f} | — |",
        f"| 探索：受试者均值 LOSO，10 特征 | 受试者 | {extended_primary['n_subjects']} | "
        f"{extended_primary['metrics']['auc']:.4f} | "
        f"[{extended_primary['bootstrap']['auc_95ci'][0]:.4f}, "
        f"{extended_primary['bootstrap']['auc_95ci'][1]:.4f}] | "
        f"{extended_primary['metrics']['auprc']:.4f} | "
        f"{extended_primary['metrics']['brier']:.4f} | "
        f"{extended_primary['metrics']['mean_predicted']:.4f} |",
        f"| 探索：日级分组 + 多日聚合，10 特征 | 受试者 | "
        f"{extended_secondary['subject_metrics_pooled']['n']} | "
        f"{extended_secondary['subject_auc_mean']:.4f} | "
        f"±{extended_secondary['subject_auc_sd']:.4f}（重复） | "
        f"{extended_secondary['subject_metrics_pooled']['auprc']:.4f} | "
        f"{extended_secondary['subject_metrics_pooled']['brier']:.4f} | "
        f"{extended_secondary['subject_metrics_pooled']['mean_predicted']:.4f} |",
        "",
        "日级 AUC 把同一天的预测当作独立样本，只用于描述；受试者级读数是主分析单位。"
        "受试者级 AUC 的重复 SD 反映 10 次分组切分的波动，不是 95% CI。"
        f"合并 OOF（10 次重复的平均预测）AUC：4 特征 {secondary['subject_metrics_pooled']['auc']:.4f}，"
        f"10 特征 {extended_secondary['subject_metrics_pooled']['auc']:.4f}。",
        "",
        "### 3.1 受试者级置换检验",
        "",
        f"- 主口径 LOSO：观测 AUC {perm_primary['observed']:.4f}，"
        f"{perm_primary['n_permutations']} 次受试者标签置换的均值 "
        f"{perm_primary['permuted_mean']:.4f}，单侧 p={perm_primary['p_value_one_sided']:.4f}。",
        f"- 次口径多日聚合：观测 AUC {perm_secondary['observed']:.4f}，"
        f"{perm_secondary['n_permutations']} 次受试者标签置换的均值 "
        f"{perm_secondary['permuted_mean']:.4f}，单侧 p={perm_secondary['p_value_one_sided']:.4f}。",
        "- 置换检验只说明「在该队列内，观测到的排序不太可能由标签随机置换产生」；不等于外部泛化或临床可用。",
        "",
        "### 3.2 泄漏对照",
        "",
        "| 协议 | 日级 AUC（重复均值） | 受试者级 AUC（重复均值） |",
        "|---|---:|---:|",
        f"| 分组 CV（4 特征） | {secondary['day_auc_mean']:.4f} ± {secondary['day_auc_sd']:.4f} | "
        f"{secondary['subject_auc_mean']:.4f} ± {secondary['subject_auc_sd']:.4f} |",
        f"| 非分组行级 CV（4 特征） | {naive['day_auc_mean']:.4f} ± {naive['day_auc_sd']:.4f} | "
        f"{naive['subject_auc_mean']:.4f} ± {naive['subject_auc_sd']:.4f} |",
        "",
        "非分组 CV 让同一受试者的不同天同时进入训练和测试，理论上应更乐观。"
        "本数据上差距不大，但不能因此认为行级切分可接受：它仍然把同一个人当作独立样本，"
        "会低估不确定性。此前来源审计的 0.6443 用的是 2 个真实派生列和行级 5 折，"
        "与本表的 4 个原始特征/分组协议不可直接比较。",
        "",
        "### 3.3 单变量信号",
        "",
        "| 受试者均值特征 | AUC（方向未翻转） | 翻转后 AUC | 方向 |",
        "|---|---:|---:|---|",
    ]
    for feature, row in univariate.items():
        lines.append(
            f"| `{feature}` | {row['auc_direction_not_flipped']:.4f} | "
            f"{row['auc_if_inverted']:.4f} | {row['direction']} |"
        )
    lines += [
        "",
        "`mean_act` 的方向最明确：活动均值越低，越偏向抑郁组。单变量 AUC 不等于多变量模型，也不能解释为因果。",
        "",
        "### 3.4 阈值行为（受试者级，多日聚合口径）",
        "",
        "| 阈值 | 灵敏度 | 特异度 | PPV | NPV | 告警率 | TP/FP/FN/TN |",
        "|---:|---:|---:|---:|---:|---:|---|",
    ]
    for cut, row in secondary["thresholds_pooled"].items():
        lines.append(
            f"| {cut} | {fmt(row['sensitivity'], 3)} | {fmt(row['specificity'], 3)} | "
            f"{fmt(row['ppv'], 3)} | {fmt(row['npv'], 3)} | {row['alert_rate']:.3f} | "
            f"{row['tp']}/{row['fp']}/{row['fn']}/{row['tn']} |"
        )
    lines += [
        "",
        "阈值表是描述性的，没有做阈值选择或重新校准。多日聚合模型的平均预测明显低于实际阳性率，"
        "0.50 阈值几乎不报警；0.35 附近的灵敏度/特异度只是该队列上的观测，不能直接搬到别的队列。",
        "",
        "### 3.5 校准与严重度",
        "",
        f"- 主口径 Brier {primary['metrics']['brier']:.4f}，ECE(5 bin) "
        f"{primary['metrics']['calibration_ece_5bin']:.4f}，校准斜率 "
        f"{primary['metrics']['calibration_slope']:.3f}。",
        f"- 次口径 Brier {secondary['subject_metrics_pooled']['brier']:.4f}，ECE(5 bin) "
        f"{secondary['subject_metrics_pooled']['calibration_ece_5bin']:.4f}，校准斜率 "
        f"{secondary['subject_metrics_pooled']['calibration_slope']:.3f}。",
        f"- 在 {madrs['n_condition']} 名病例中，多日聚合分数与 MADRS-1 的 Spearman "
        f"ρ={fmt(madrs['madrs1']['spearman_rho'], 3)}（p={fmt(madrs['madrs1']['p_value'], 3)}），"
        f"与 MADRS-2 ρ={fmt(madrs['madrs2']['spearman_rho'], 3)}"
        f"（p={fmt(madrs['madrs2']['p_value'], 3)}）。",
        "- 这说明该基线主要区分病例/对照，**没有**证据表明它能跟踪症状严重度；校准也未达到可用于个体风险沟通的程度。",
        "",
        "### 3.6 敏感性",
        "",
        "| 口径 | 受试者 | 日 | 受试者级 AUC | Brier |",
        "|---|---:|---:|---:|---:|",
        f"| 全部完整日（主分析） | {dataset['n_subjects']} | {dataset['n_complete_days']} | "
        f"{secondary['subject_auc_mean']:.4f} ± {secondary['subject_auc_sd']:.4f} | "
        f"{secondary['subject_metrics_pooled']['brier']:.4f} |",
        f"| 排除全零日 | {sens_zero['n_subjects']} | {sens_zero['n_days']} | "
        f"{sens_zero['subject_auc_mean']:.4f} ± {sens_zero['subject_auc_sd']:.4f} | "
        f"{sens_zero['subject_metrics_pooled']['brier']:.4f} |",
        f"| 仅保留 ≥14 个完整日的受试者 | {sens_days['n_subjects']} | {sens_days['n_days']} | "
        f"{sens_days['subject_auc_mean']:.4f} ± {sens_days['subject_auc_sd']:.4f} | "
        f"{sens_days['subject_metrics_pooled']['brier']:.4f} |",
        "",
        "排除全零日或剔除天数过少的受试者后，多日聚合 AUC 下降约 0.05–0.06，说明结果部分依赖"
        "零活动日/佩戴天数；没有佩戴或非佩戴标志，无法把「完全不活动」与「设备未戴」分开。"
        "这是本基线的主要数据质量限制。",
        "",
        "### 3.7 人口学负对照",
        "",
        f"- 仅用性别 + 年龄组中点的受试者级 LOSO AUC "
        f"{demographics['metrics']['auc']:.4f}，Brier {demographics['metrics']['brier']:.4f}。",
        "- 这不是一个可部署模型，只用于说明 actigraphy 的读数不是由年龄/性别单独解释；"
        "样本仅 55 人，不能做正式混杂校正。",
        "",
        "## 4. 解释边界",
        "",
        "**允许的表述**",
        "",
        "- 「在 Depresjon 的 55 名受试者上，按受试者分组的真实 actigraphy 基线达到上述 AUC；"
        "它明显低于合成特征生产模型的 0.9451。」",
        "- 「保守的受试者均值 LOSO 与多日聚合估计不一致；两者都应报告，不能把较大的一个当作稳定性能。」",
        "- 「主要单变量信号是较低的活动均值；该基线没有显示 MADRS 严重度跟踪能力。」",
        "",
        "**禁止的表述**",
        "",
        "- 「这是外部验证」或「可以用于普通成人/消费级可穿戴」。",
        "- 「真实 actigraphy 的 AUC 是 0.76，所以生产模型可以换成它」——这是离线基线，"
        "没有外部验证、没有校准、没有阈值验证。",
        "- 「0.762 可以和生产模型 0.9451 比较」——特征来源、标签和协议不同。",
        "- 「10 特征探索模型应该上线」——55 人、单一队列、没有外部队列。",
        "",
        "## 5. 复现",
        "",
        "```bash",
        "cd backend",
        ".venv/Scripts/python.exe scripts/modeling/eval/v1_48/01_real_actigraphy_baseline.py",
        "```",
        "",
        f"- 全部随机过程固定 seed={SEED}；bootstrap {BOOTSTRAP_B} 次；置换 {PERMUTATION_B} 次。",
        f"- 受试者级预测明细：`{OUT_CSV.relative_to(PROJECT_ROOT).as_posix()}`。",
        f"- JSON：`{OUT_JSON.relative_to(PROJECT_ROOT).as_posix()}`；"
        f"镜像：`{OUT_MIRROR.relative_to(PROJECT_ROOT).as_posix()}`。",
        "",
        "## 6. 对 Phase 1 的含义",
        "",
        "1. 真实 actigraphy 确实有信号，但当前证据只能支持「同队列、按人分组、回顾性」的有限读数；"
        "不能升级运行时生理单元的 `synthetic_label_derived` 等级。",
        "2. 生产生理模型若要用真实特征重建，应以本脚本的受试者分组协议为最低门槛，"
        "并补外部队列、校准集与佩戴/非佩戴处理。",
        "3. 多日聚合与单日/受试者均值的结果差异必须保留在报告中，不能只留一个好看的数字。",
        "4. 在该队列之外，没有任何证据支持普通人群、消费级设备或临床诊断用途。",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
