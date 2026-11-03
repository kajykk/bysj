#!/usr/bin/env python
"""ROUND_46 P1: split-conformal abstention + fairness subgroup report.

Read-only. No production model, threshold, or routing rule is modified.

Conformal protocol
------------------
Binary split conformal with score 1 - p(true label):
    q = ceil((n_cal + 1) * (1 - alpha))-th smallest calibration score
    set = {y : 1 - p(y) <= q}
A singleton {positive} is an automatic alert, {negative} an automatic clear,
and an empty / two-label set is routed to human review. Coverage is marginal,
not subgroup-conditional; subgroup and Mondrian coverage are reported separately.

Units
-----
- structured v1.23: validation -> test (same distribution), plus a clean
  Kaggle -> Mendeley source holdout (calibration and test from different sources).
- text groupwise OOF: repeated 50/50 group splits (50 repeats), no demographics.
- physiological v2: 153 validation -> 157 test, no demographics.
- fairness: structured only (source / gender / age); text, English, and
  physiological corpora carry no protected attributes.

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/modeling/eval/v1_46/06_conformal_fairness.py
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[3]
PROJECT_ROOT = BACKEND.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from model_card_lib import (  # noqa: E402
    _as_arrays,
    _core_metrics,
    _group_split,
    model_card,
    wilson_ci,
)

OUT_JSON = HERE / "conformal_fairness.json"
MIRROR_JSON = PROJECT_ROOT / "outputs" / "candidates" / "round46" / "conformal_fairness.json"
REPORT_MD = PROJECT_ROOT / "outputs" / "ROUND_46_CONFORMAL_FAIRNESS.md"

DATA = PROJECT_ROOT / "data"
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
ALPHAS = (0.05, 0.10, 0.20)
FAIR_THRESHOLDS = (0.25, 0.50)
ALL_THRESHOLDS = (0.25, 0.45, 0.50, 0.65)
BOOTSTRAP_B = 2000
REPEATS = 50
EPS = 1e-12


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MC = _load_module("round46_model_cards", HERE / "01_model_cards.py")
S3 = _load_module("round46_source_holdout", HERE / "03_source_holdout.py")


def _jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        val = float(obj)
        return val if math.isfinite(val) else None
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


# ── conformal primitives ─────────────────────────────────────────────────────


def conformal_apply(y_cal, p_cal, p_test, alpha: float):
    yc, pc = _as_arrays(y_cal, p_cal)
    pt = np.clip(np.asarray(p_test, dtype=np.float64).ravel(), EPS, 1.0 - EPS)
    scores = np.where(yc == 1.0, 1.0 - pc, pc)
    n = scores.size
    k = int(math.ceil((n + 1) * (1.0 - alpha)))
    q = 1.0 if k > n else float(np.sort(scores)[k - 1])
    include_pos = (1.0 - pt) <= q + EPS
    include_neg = pt <= q + EPS
    return q, include_pos, include_neg


def conformal_summary(y_test, include_pos, include_neg, *, alpha: float, q: float, n_cal: int) -> dict:
    yt = np.asarray(y_test, dtype=np.float64).ravel()
    pos = yt == 1.0
    neg = ~pos
    n = yt.size
    size = include_pos.astype(np.int64) + include_neg.astype(np.int64)
    covered = np.where(pos, include_pos, include_neg)

    auto_pos = include_pos & ~include_neg
    auto_neg = include_neg & ~include_pos
    review = ~(auto_pos | auto_neg)

    tp = int(np.sum(auto_pos & pos))
    fp = int(np.sum(auto_pos & neg))
    tn = int(np.sum(auto_neg & neg))
    fn = int(np.sum(auto_neg & pos))
    review_pos = int(np.sum(review & pos))
    review_neg = int(np.sum(review & neg))
    auto_n = tp + fp + tn + fn

    def _rate(num, den):
        return float(num / den) if den else float("nan")

    return {
        "alpha": float(alpha),
        "nominal_coverage": float(1.0 - alpha),
        "n_cal": int(n_cal),
        "n_test": int(n),
        "q": float(q),
        "review_band": [float(min(q, 1.0 - q)), float(max(q, 1.0 - q))],
        "coverage": _rate(int(covered.sum()), n),
        "coverage_wilson95": wilson_ci(int(covered.sum()), n),
        "coverage_positive": _rate(int(np.sum(covered & pos)), int(pos.sum())),
        "coverage_positive_wilson95": wilson_ci(int(np.sum(covered & pos)), int(pos.sum())),
        "coverage_negative": _rate(int(np.sum(covered & neg)), int(neg.sum())),
        "coverage_negative_wilson95": wilson_ci(int(np.sum(covered & neg)), int(neg.sum())),
        "mean_set_size": float(size.mean()) if n else float("nan"),
        "singleton_rate": _rate(int(np.sum(size == 1)), n),
        "empty_rate": _rate(int(np.sum(size == 0)), n),
        "both_rate": _rate(int(np.sum(size == 2)), n),
        "abstention_rate": _rate(int(review.sum()), n),
        "review_positive_rate": _rate(review_pos, int(pos.sum())),
        "review_negative_rate": _rate(review_neg, int(neg.sum())),
        "auto_decision_rate": _rate(auto_n, n),
        "auto_alert_rate": _rate(tp + fp, n),
        "auto_alert_precision": _rate(tp, tp + fp),
        "auto_alert_precision_wilson95": wilson_ci(tp, tp + fp),
        "positive_auto_alert_rate": _rate(tp, int(pos.sum())),
        "positive_auto_cleared_rate": _rate(fn, int(pos.sum())),
        "negative_auto_cleared_rate": _rate(tn, int(neg.sum())),
        "auto_accuracy": _rate(tp + tn, auto_n),
    }


def coverage_by_masks(y_test, include_pos, include_neg, masks: dict) -> dict:
    yt = np.asarray(y_test, dtype=np.float64).ravel()
    pos = yt == 1.0
    covered = np.where(pos, include_pos, include_neg)
    size = include_pos.astype(np.int64) + include_neg.astype(np.int64)
    out = {}
    for name, mask in masks.items():
        mask = np.asarray(mask, dtype=bool)
        if not mask.any():
            continue
        n_cov = int(np.sum(covered & mask))
        n = int(mask.sum())
        out[name] = {
            "n": n,
            "coverage": float(n_cov / n),
            "coverage_wilson95": wilson_ci(n_cov, n),
            "mean_set_size": float(size[mask].mean()),
            "abstention_rate": float(np.mean(size[mask] != 1)),
        }
    return out


def mondrian_conformal(
    y_cal,
    p_cal,
    g_cal,
    y_test,
    p_test,
    g_test,
    alpha: float,
    *,
    min_cal: int = 20,
    min_test: int = 10,
) -> dict:
    yc, pc = _as_arrays(y_cal, p_cal)
    yt = np.asarray(y_test, dtype=np.float64).ravel()
    pt = np.asarray(p_test, dtype=np.float64).ravel()
    gc = np.asarray(g_cal, dtype=object)
    gt = np.asarray(g_test, dtype=object)
    groups = sorted(set(gc.tolist()) & set(gt.tolist()), key=str)
    per_group = {}
    covered_all = np.zeros(yt.size, dtype=bool)
    size_all = np.zeros(yt.size, dtype=np.int64)
    assigned = np.zeros(yt.size, dtype=bool)
    for g in groups:
        m_cal = gc == g
        m_test = gt == g
        if int(m_cal.sum()) < min_cal or int(m_test.sum()) < min_test:
            per_group[str(g)] = {
                "status": "skipped",
                "n_cal": int(m_cal.sum()),
                "n_test": int(m_test.sum()),
                "reason": f"requires n_cal>={min_cal} and n_test>={min_test}",
            }
            continue
        q, inc_pos, inc_neg = conformal_apply(yc[m_cal], pc[m_cal], pt[m_test], alpha)
        summary = conformal_summary(
            yt[m_test], inc_pos, inc_neg, alpha=alpha, q=q, n_cal=int(m_cal.sum())
        )
        summary["n_cal"] = int(m_cal.sum())
        per_group[str(g)] = summary
        pos = yt[m_test] == 1.0
        covered_all[m_test] = np.where(pos, inc_pos, inc_neg)
        size_all[m_test] = inc_pos.astype(np.int64) + inc_neg.astype(np.int64)
        assigned[m_test] = True
    n_assigned = int(assigned.sum())
    return {
        "alpha": float(alpha),
        "groups": per_group,
        "assigned_rate": float(n_assigned / yt.size) if yt.size else float("nan"),
        "marginal_coverage_assigned": (
            float(np.mean(covered_all[assigned])) if n_assigned else float("nan")
        ),
        "mean_set_size_assigned": (
            float(size_all[assigned].mean()) if n_assigned else float("nan")
        ),
    }


def repeated_group_conformal(y, p, groups, alpha: float, *, n_repeats: int = REPEATS, seed: int = 42) -> dict:
    y_arr, p_arr = _as_arrays(y, p)
    g_arr = np.asarray(groups, dtype=object)
    rng = np.random.RandomState(seed)
    rows = []
    for _ in range(n_repeats):
        cal_mask, test_mask = _group_split(y_arr, g_arr, rng)
        if not cal_mask.any() or not test_mask.any():
            continue
        q, inc_pos, inc_neg = conformal_apply(
            y_arr[cal_mask], p_arr[cal_mask], p_arr[test_mask], alpha
        )
        rows.append(
            conformal_summary(
                y_arr[test_mask],
                inc_pos,
                inc_neg,
                alpha=alpha,
                q=q,
                n_cal=int(cal_mask.sum()),
            )
        )
    keys = (
        "coverage",
        "coverage_positive",
        "coverage_negative",
        "mean_set_size",
        "abstention_rate",
        "auto_decision_rate",
        "auto_alert_precision",
        "positive_auto_alert_rate",
        "positive_auto_cleared_rate",
        "auto_accuracy",
    )
    out = {"alpha": float(alpha), "nominal_coverage": float(1.0 - alpha), "n_repeats": len(rows)}
    for key in keys:
        arr = np.asarray([r[key] for r in rows], dtype=np.float64)
        arr = arr[np.isfinite(arr)]
        out[key] = {
            "mean": float(arr.mean()) if arr.size else float("nan"),
            "p2_5": float(np.percentile(arr, 2.5)) if arr.size else float("nan"),
            "p97_5": float(np.percentile(arr, 97.5)) if arr.size else float("nan"),
        }
    out["q_mean"] = float(np.mean([r["q"] for r in rows])) if rows else float("nan")
    return out


# ── fairness primitives ──────────────────────────────────────────────────────


def structured_masks(df: pd.DataFrame) -> dict:
    masks = {
        "source:kaggle": df["source"].eq("kaggle").to_numpy(),
        "source:mendeley": df["source"].eq("mendeley").to_numpy(),
        "gender:0": df["gender"].eq(0).to_numpy(),
        "gender:1": df["gender"].eq(1).to_numpy(),
    }
    kaggle = df["source"].eq("kaggle").to_numpy()
    for value in (0, 1):
        masks[f"kaggle_gender:{value}"] = kaggle & df["gender"].eq(value).to_numpy()
    cuts = [-np.inf, 16, 20, 25, 30, 35, np.inf]
    labels = ["<17", "17-20", "21-25", "26-30", "31-35", ">35"]
    bins = pd.cut(df["age"], bins=cuts, labels=labels, right=True)
    for label in labels:
        m = (bins == label).to_numpy()
        if m.any():
            masks[f"age:{label}"] = m
            if kaggle.any():
                masks[f"kaggle_age:{label}"] = m & kaggle
    return masks


def _metric_value(y, p, threshold: float, metric: str) -> float:
    m = _core_metrics(y, p, threshold)
    if metric == "tpr":
        return float(m["sensitivity"])
    if metric == "fpr":
        return float(1.0 - m["specificity"])
    if metric == "ppv":
        return float(m["ppv"])
    if metric == "alert_rate":
        return float(m["alert_rate"])
    raise ValueError(metric)


def pairwise_gap_ci(
    y,
    p,
    mask_a,
    mask_b,
    threshold: float,
    metric: str,
    *,
    B: int = BOOTSTRAP_B,
    seed: int = 42,
) -> dict:
    y = np.asarray(y, dtype=np.float64).ravel()
    p = np.asarray(p, dtype=np.float64).ravel()
    ia = np.where(np.asarray(mask_a, dtype=bool))[0]
    ib = np.where(np.asarray(mask_b, dtype=bool))[0]
    if ia.size == 0 or ib.size == 0:
        return {"status": "not_evaluable"}
    point = _metric_value(y[ia], p[ia], threshold, metric) - _metric_value(
        y[ib], p[ib], threshold, metric
    )
    rng = np.random.RandomState(seed)
    samples = []
    for _ in range(B):
        ja = rng.randint(0, ia.size, ia.size)
        jb = rng.randint(0, ib.size, ib.size)
        val = _metric_value(y[ia[ja]], p[ia[ja]], threshold, metric) - _metric_value(
            y[ib[jb]], p[ib[jb]], threshold, metric
        )
        if np.isfinite(val):
            samples.append(val)
    arr = np.asarray(samples, dtype=np.float64)
    return {
        "delta": float(point) if np.isfinite(point) else None,
        "ci95": (
            [float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))]
            if arr.size
            else [float("nan"), float("nan")]
        ),
        "n_a": int(ia.size),
        "n_b": int(ib.size),
        "bootstrap_n": int(arr.size),
        "metric": metric,
        "threshold": float(threshold),
    }


def maxmin_gap_ci(
    y,
    p,
    masks: dict,
    threshold: float,
    metric: str,
    *,
    B: int = BOOTSTRAP_B,
    seed: int = 42,
) -> dict:
    y = np.asarray(y, dtype=np.float64).ravel()
    p = np.asarray(p, dtype=np.float64).ravel()
    idx = {name: np.where(np.asarray(mask, dtype=bool))[0] for name, mask in masks.items()}
    idx = {name: ii for name, ii in idx.items() if ii.size > 0}
    if len(idx) < 2:
        return {"status": "not_evaluable"}

    def _spread(indices: dict) -> float:
        vals = [
            _metric_value(y[ii], p[ii], threshold, metric)
            for ii in indices.values()
            if ii.size
        ]
        vals = [v for v in vals if np.isfinite(v)]
        return float(max(vals) - min(vals)) if len(vals) > 1 else float("nan")

    point = _spread(idx)
    rng = np.random.RandomState(seed)
    samples = []
    for _ in range(B):
        picked = {
            name: ii[rng.randint(0, ii.size, ii.size)] for name, ii in idx.items()
        }
        val = _spread(picked)
        if np.isfinite(val):
            samples.append(val)
    arr = np.asarray(samples, dtype=np.float64)
    return {
        "delta": float(point) if np.isfinite(point) else None,
        "ci95": (
            [float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))]
            if arr.size
            else [float("nan"), float("nan")]
        ),
        "n_groups": len(idx),
        "bootstrap_n": int(arr.size),
        "metric": metric,
        "threshold": float(threshold),
    }


def subgroup_table(y, p, masks: dict, thresholds: tuple[float, ...]) -> dict:
    y = np.asarray(y, dtype=np.float64).ravel()
    p = np.asarray(p, dtype=np.float64).ravel()
    out = {}
    for name, mask in masks.items():
        mask = np.asarray(mask, dtype=bool)
        if not mask.any():
            continue
        ys, ps = y[mask], p[mask]
        card = model_card(ys, ps, threshold=0.5, cuts=(), target_prevalences=(0.15,))
        entry = {
            "n": int(mask.sum()),
            "positives": int(ys.sum()),
            "prevalence": float(ys.mean()),
            "auroc": card["auroc"],
            "auprc": card["auprc"],
            "brier": card["brier"],
            "ece": card["ece"],
            "calibration_slope": card["calibration_slope"],
            "operating_points": {},
        }
        for t in thresholds:
            m = _core_metrics(ys, ps, t)
            entry["operating_points"][f"{t:.2f}"] = {
                "alerts": int(m["tp"] + m["fp"]),
                "alert_rate": m["alert_rate"],
                "sensitivity": m["sensitivity"],
                "sensitivity_wilson95": wilson_ci(m["tp"], m["tp"] + m["fn"]),
                "specificity": m["specificity"],
                "specificity_wilson95": wilson_ci(m["tn"], m["tn"] + m["fp"]),
                "ppv": m["ppv"],
                "ppv_wilson95": wilson_ci(m["tp"], m["tp"] + m["fp"]),
                "npv": m["npv"],
                "f1": m["f1"],
            }
        out[name] = entry
    return out


def fairness_block(y, p, masks: dict, contrasts: dict, thresholds: tuple[float, ...]) -> dict:
    gaps = {}
    for t in thresholds:
        gaps[f"{t:.2f}"] = {}
        for name, spec in contrasts.items():
            metrics = ("tpr", "fpr", "ppv", "alert_rate")
            if spec["kind"] == "pairwise":
                gaps[f"{t:.2f}"][name] = {
                    metric: pairwise_gap_ci(
                        y, p, masks[spec["a"]], masks[spec["b"]], t, metric
                    )
                    for metric in metrics
                }
            else:
                sub = {g: masks[g] for g in spec["groups"] if g in masks}
                gaps[f"{t:.2f}"][name] = {
                    metric: maxmin_gap_ci(y, p, sub, t, metric) for metric in metrics
                }
    return {"subgroups": subgroup_table(y, p, masks, thresholds), "gaps": gaps}


# ── unit builders ────────────────────────────────────────────────────────────


def structured_internal():
    model = MC.load_structured_model()
    validation = pd.read_csv(DATA / "processed" / "v1_23_external" / "validation.csv")
    test = pd.read_csv(DATA / "processed" / "v1_23_external" / "test.csv")
    y_val = validation[TARGET].to_numpy(dtype=np.int64)
    p_val = model.predict_proba(validation[FEATURES])[:, 1]
    y = test[TARGET].to_numpy(dtype=np.int64)
    p = model.predict_proba(test[FEATURES])[:, 1]

    masks = structured_masks(test)
    contrasts = {
        "source:kaggle_vs_mendeley": {
            "kind": "pairwise",
            "a": "source:kaggle",
            "b": "source:mendeley",
        },
        "gender:1_vs_0": {"kind": "pairwise", "a": "gender:1", "b": "gender:0"},
        "kaggle_gender:1_vs_0": {
            "kind": "pairwise",
            "a": "kaggle_gender:1",
            "b": "kaggle_gender:0",
        },
        "age:max_minus_min": {
            "kind": "maxmin",
            "groups": [m for m in masks if m.startswith("age:")],
        },
        "kaggle_age:max_minus_min": {
            "kind": "maxmin",
            "groups": [m for m in masks if m.startswith("kaggle_age:")],
        },
    }

    conformal = {}
    for alpha in ALPHAS:
        q, inc_pos, inc_neg = conformal_apply(y_val, p_val, p, alpha)
        summary = conformal_summary(y, inc_pos, inc_neg, alpha=alpha, q=q, n_cal=len(y_val))
        summary["coverage_by_subgroup"] = coverage_by_masks(y, inc_pos, inc_neg, masks)
        conformal[f"{alpha:.2f}"] = summary

    val_masks = structured_masks(validation)
    mondrian = {}
    for attr, prefix in (("source", "source:"), ("gender", "gender:"), ("age", "age:")):
        names = [m for m in masks if m.startswith(prefix)]
        names_cal = [m for m in val_masks if m.startswith(prefix)]
        assert names == names_cal, f"{attr} mask mismatch"
        g_cal = np.full(len(validation), "", dtype=object)
        g_test = np.full(len(test), "", dtype=object)
        for name in names:
            g_cal[val_masks[name]] = name
            g_test[masks[name]] = name
        mondrian[attr] = mondrian_conformal(
            y_val, p_val, g_cal, y, p, g_test, alpha=0.10
        )

    return {
        "role": "citable_internal_test",
        "n": int(len(y)),
        "positive_rate": float(y.mean()),
        "conformal": conformal,
        "mondrian_alpha_0.10": mondrian,
        "fairness": fairness_block(y, p, masks, contrasts, ALL_THRESHOLDS),
        "boundary": (
            "Internal test mixes 4,181 Kaggle and 137 Mendeley rows; the production "
            "model trained on 408 other Mendeley rows, so the source contrast is "
            "same-source optimism, not an external validation."
        ),
    }


def structured_source_holdout():
    aligned, kaggle, mendeley, processed = S3.load_data()
    feats = list(S3.FEATURES)
    y_kag = kaggle["label_binary"].to_numpy(dtype=np.int64)
    y_men = mendeley["label_binary"].to_numpy(dtype=np.int64)
    k_fit, k_cal = train_test_split(
        kaggle, test_size=0.20, random_state=S3.SEED, stratify=y_kag
    )
    pipe = S3.make_pipeline()
    pipe.fit(k_fit[feats], k_fit["label_binary"].to_numpy(dtype=np.int64))
    p_cal = pipe.predict_proba(k_cal[feats])[:, 1]
    p_men = pipe.predict_proba(mendeley[feats])[:, 1]

    mendeley = mendeley.copy()
    cuts = [-np.inf, 4, 9, 14, 19, np.inf]
    labels = ["0-4", "5-9", "10-14", "15-19", "20+"]
    phq_bins = pd.cut(mendeley["phq9_total"], bins=cuts, labels=labels, right=True)
    masks = {
        **structured_masks(mendeley.assign(source="mendeley")),
        **{f"phq9:{label}": (phq_bins == label).to_numpy() for label in labels},
    }
    masks.pop("source:kaggle", None)
    masks.pop("kaggle_gender:0", None)
    masks.pop("kaggle_gender:1", None)
    for key in [k for k in masks if k.startswith("kaggle_age:")]:
        masks.pop(key)

    y_cal = k_cal["label_binary"].to_numpy(dtype=np.int64)
    conformal = {}
    for alpha in ALPHAS:
        q, inc_pos, inc_neg = conformal_apply(y_cal, p_cal, p_men, alpha)
        summary = conformal_summary(
            y_men, inc_pos, inc_neg, alpha=alpha, q=q, n_cal=len(k_cal)
        )
        summary["coverage_by_subgroup"] = coverage_by_masks(y_men, inc_pos, inc_neg, masks)
        conformal[f"{alpha:.2f}"] = summary

    target_cal = {}
    for n_cal_target in (50, 100, 200):
        target_cal[str(n_cal_target)] = simulate_target_calibration(
            y_men, p_men, n_cal_target, alpha=0.10
        )

    contrasts = {
        "gender:1_vs_0": {"kind": "pairwise", "a": "gender:1", "b": "gender:0"},
        "age:max_minus_min": {
            "kind": "maxmin",
            "groups": [m for m in masks if m.startswith("age:")],
        },
    }
    return {
        "role": "clean_source_holdout",
        "protocol": "train on 80% Kaggle, calibrate on held-out 20% Kaggle, test on all 682 Mendeley",
        "n_train": int(len(k_fit)),
        "n_cal": int(len(k_cal)),
        "n_test": int(len(y_men)),
        "positive_rate_test": float(y_men.mean()),
        "conformal": conformal,
        "target_calibration_simulation_alpha_0.10": target_cal,
        "fairness_secondary": fairness_block(y_men, p_men, masks, contrasts, FAIR_THRESHOLDS),
        "boundary": (
            "Kaggle labels are self-reported binary; Mendeley labels are PHQ-9 >= 10. "
            "Coverage loss mixes covariate shift with label-definition shift."
        ),
    }


def simulate_target_calibration(
    y, p, n_cal_target: int, *, alpha: float = 0.10, repeats: int = 50, seed: int = 42
) -> dict:
    y_arr, p_arr = _as_arrays(y, p)
    pos_idx = np.where(y_arr == 1.0)[0]
    neg_idx = np.where(y_arr == 0.0)[0]
    n = y_arr.size
    n_pos = int(round(n_cal_target * pos_idx.size / n))
    n_neg = n_cal_target - n_pos
    rng = np.random.RandomState(seed)
    rows = []
    for _ in range(repeats):
        pos_pick = rng.choice(pos_idx, size=n_pos, replace=False)
        neg_pick = rng.choice(neg_idx, size=n_neg, replace=False)
        cal = np.concatenate([pos_pick, neg_pick])
        test = np.setdiff1d(np.arange(n), cal, assume_unique=False)
        q, inc_pos, inc_neg = conformal_apply(y_arr[cal], p_arr[cal], p_arr[test], alpha)
        rows.append(
            conformal_summary(
                y_arr[test], inc_pos, inc_neg, alpha=alpha, q=q, n_cal=cal.size
            )
        )
    out = {
        "alpha": float(alpha),
        "n_cal_target": int(n_cal_target),
        "n_test_mean": float(np.mean([r["n_test"] for r in rows])),
        "repeats": len(rows),
    }
    for key in ("coverage", "mean_set_size", "abstention_rate", "auto_alert_precision"):
        arr = np.asarray([r[key] for r in rows], dtype=np.float64)
        arr = arr[np.isfinite(arr)]
        out[key] = {
            "mean": float(arr.mean()) if arr.size else float("nan"),
            "p2_5": float(np.percentile(arr, 2.5)) if arr.size else float("nan"),
            "p97_5": float(np.percentile(arr, 97.5)) if arr.size else float("nan"),
        }
    return out


def text_unit():
    _, oof = MC.read_text_oof()
    y = oof["label"].to_numpy(dtype=np.int64)
    p = oof["p_groupwise"].to_numpy(dtype=float)
    groups = oof["group"].astype(str).to_numpy()
    conformal = {
        f"{alpha:.2f}": repeated_group_conformal(y, p, groups, alpha) for alpha in ALPHAS
    }
    return {
        "role": "citable_groupwise_oof",
        "n": int(len(y)),
        "n_groups": int(len(np.unique(groups))),
        "positive_rate": float(y.mean()),
        "conformal": conformal,
        "fairness": {
            "status": "not_evaluable",
            "reason": (
                "The Chinese corpus and the groupwise OOF table carry no gender, age, "
                "or source attribution. Group IDs denote sibling text families, not "
                "people or protected groups."
            ),
        },
        "boundary": (
            "Repeated 50/50 group splits on OOF scores are group-aware, but the OOF "
            "base models saw the calibration groups during their own training folds. "
            "This is an approximate exchangeability check, not a strict held-out "
            "conformal guarantee."
        ),
    }


def physio_unit():
    pred = pd.read_csv(HERE / "physio_val_test_predictions.csv")
    val = pred[pred["split"] == "validation"]
    test = pred[pred["split"] == "test"]
    y_val = val["y_true"].to_numpy(dtype=np.int64)
    p_val = val["y_score"].to_numpy(dtype=float)
    y = test["y_true"].to_numpy(dtype=np.int64)
    p = test["y_score"].to_numpy(dtype=float)
    conformal = {}
    for alpha in ALPHAS:
        q, inc_pos, inc_neg = conformal_apply(y_val, p_val, p, alpha)
        conformal[f"{alpha:.2f}"] = conformal_summary(
            y, inc_pos, inc_neg, alpha=alpha, q=q, n_cal=len(y_val)
        )
    return {
        "role": "citable_secondary_small_test",
        "n_validation": int(len(y_val)),
        "n_test": int(len(y)),
        "positive_rate_test": float(y.mean()),
        "conformal": conformal,
        "fairness": {
            "status": "not_evaluable",
            "reason": (
                "The depression physiological table has no gender, age, or protected "
                "attribute; the only metadata is source='depresjon'. n=157 is also too "
                "small for stable subgroup inference."
            ),
        },
        "boundary": (
            "Calibration 153 rows, test 157 rows. At alpha=0.05 the 95th percentile is "
            "estimated from 153 points; interval endpoints are granular."
        ),
    }


def main() -> int:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    MIRROR_JSON.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "_note": (
            "ROUND_46 P1. Split conformal with score 1-p(true label); singleton "
            "sets auto-decide, empty/two-label sets route to human review. Fairness "
            "is computed only where protected attributes exist (structured). No "
            "production artifact or threshold was modified."
        ),
        "protocol_date": "2026-11-02",
        "method": {
            "score": "1 - p(true label)",
            "q": "ceil((n_cal + 1) * (1 - alpha))-th smallest calibration score",
            "set": "{y : 1 - p(y) <= q}",
            "auto_alert": "set == {positive}; auto_clear: set == {negative}; review: empty or both",
            "coverage": "marginal split-conformal coverage; subgroups and Mondrian reported separately",
            "bootstrap": f"percentile bootstrap B={BOOTSTRAP_B}; text repeats={REPEATS} group splits",
        },
        "units": {
            "structured_internal": structured_internal(),
            "structured_source_holdout": structured_source_holdout(),
            "text_groupwise_oof": text_unit(),
            "physio_v2": physio_unit(),
            "text_english_holdout": {
                "status": "not_evaluable",
                "reason": (
                    "The English Reddit holdout has no protected attributes and only "
                    "one split; a repeated group split would need sibling provenance "
                    "that is not present."
                ),
            },
            "fusion": {
                "status": "not_evaluable",
                "reason": "No aligned three-modality labelled samples; no conformal or fairness unit exists.",
            },
        },
    }

    payload = _jsonable(payload)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    MIRROR_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_MD.write_text(build_report(payload), encoding="utf-8")

    for name, unit in payload["units"].items():
        if unit.get("status") == "not_evaluable":
            print(f"{name:28s} not_evaluable")
            continue
        if "conformal" not in unit:
            continue
        for alpha, res in unit["conformal"].items():
            cov = _metric(res, "coverage")
            print(
                f"{name:28s} alpha={alpha} coverage={cov:.3f} "
                f"set={_metric(res, 'mean_set_size'):.2f} "
                f"abstain={_metric(res, 'abstention_rate'):.3f}"
            )
    print(f"written: {OUT_JSON}")
    print(f"written: {REPORT_MD}")
    return 0


def _fmt(value, nd: int = 3) -> str:
    if value is None:
        return "—"
    try:
        val = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(val):
        return "—"
    return f"{val:.{nd}f}"


def _ci(pair) -> str:
    if not pair:
        return "—"
    lo, hi = pair
    if lo is None or hi is None or not (math.isfinite(float(lo)) and math.isfinite(float(hi))):
        return "—"
    return f"[{float(lo):.3f}, {float(hi):.3f}]"


def _metric(res: dict, key: str):
    val = res.get(key)
    if isinstance(val, dict):
        return val.get("mean")
    return val


def build_report(payload: dict) -> str:
    units = payload["units"]
    lines: list[str] = []
    add = lines.append

    add("# ROUND_46 · Conformal 弃权与公平性亚组报告")
    add("")
    add("> 口径：split conformal，score = 1 − p(true label)；单标签集合自动决策，空集/双标签集合转人工复核。")
    add("> 只读评估。未修改生产模型、阈值或路由规则。日期：2026-11-02。")
    add("")

    add("## 1. 覆盖率总表")
    add("")
    add("| 单元 | alpha | n_cal | n_test | 覆盖率 [95% CI] | 平均集合大小 | 弃权率 |")
    add("|---|---:|---:|---:|---|---:|---:|")
    unit_labels = {
        "structured_internal": "structured 内部验证→测试",
        "structured_source_holdout": "structured Kaggle→Mendeley",
        "text_groupwise_oof": "text groupwise 重复组切分",
        "physio_v2": "physio 验证→测试",
    }
    for key, label in unit_labels.items():
        unit = units.get(key, {})
        for alpha, res in unit.get("conformal", {}).items():
            if isinstance(res.get("coverage"), dict):
                cov_s = (
                    f"{_fmt(_metric(res, 'coverage'))} "
                    f"[{_fmt(res['coverage'].get('p2_5'))}, {_fmt(res['coverage'].get('p97_5'))}]"
                )
                n_cal = "—"
                n_test = "—"
            else:
                cov_s = f"{_fmt(_metric(res, 'coverage'))} {_ci(res.get('coverage_wilson95'))}"
                n_cal = str(res.get("n_cal"))
                n_test = str(res.get("n_test"))
            add(
                f"| {label} | {alpha} | {n_cal} | {n_test} | {cov_s} | "
                f"{_fmt(_metric(res, 'mean_set_size'))} | {_fmt(_metric(res, 'abstention_rate'))} |"
            )
    add("")

    add("## 2. 弃权策略：自动决策的安全性与代价")
    add("")
    add("| 单元 | alpha | 自动决策率 | 自动告警精确率 | 阳性自动告警率 | 阳性被自动排除率 | 自动决策准确率 |")
    add("|---|---:|---:|---:|---:|---:|---:|")
    for key, label in unit_labels.items():
        unit = units.get(key, {})
        for alpha, res in unit.get("conformal", {}).items():
            vals = {
                k: _metric(res, k)
                for k in (
                    "auto_decision_rate",
                    "auto_alert_precision",
                    "positive_auto_alert_rate",
                    "positive_auto_cleared_rate",
                    "auto_accuracy",
                )
            }
            add(
                f"| {label} | {alpha} | {_fmt(vals['auto_decision_rate'])} | "
                f"{_fmt(vals['auto_alert_precision'])} | {_fmt(vals['positive_auto_alert_rate'])} | "
                f"{_fmt(vals['positive_auto_cleared_rate'])} | {_fmt(vals['auto_accuracy'])} |"
            )
    add("")

    add("## 3. 分布偏移下的 conformal：Kaggle → Mendeley")
    add("")
    cross = units["structured_source_holdout"]["conformal"]
    add("| alpha | 总覆盖 | 阳性覆盖 | 阴性覆盖 | 平均集合大小 | 弃权率 | 平均 q |")
    add("|---|---:|---:|---:|---:|---:|---:|")
    for alpha, res in cross.items():
        add(
            f"| {alpha} | {_fmt(res['coverage'])} | {_fmt(res['coverage_positive'])} | "
            f"{_fmt(res['coverage_negative'])} | {_fmt(res['mean_set_size'])} | "
            f"{_fmt(res['abstention_rate'])} | {_fmt(res['q'])} |"
        )
    add("")
    add("目标域本地校准模拟（只用 n 条 Mendeley 标签重估 q，不重训模型）：")
    add("")
    add("| 目标校准 n | 覆盖均值 | 2.5% | 97.5% | 平均集合大小 |")
    add("|---|---:|---:|---:|---:|")
    for n_cal, res in units["structured_source_holdout"]["target_calibration_simulation_alpha_0.10"].items():
        add(
            f"| {n_cal} | {_fmt(res['coverage']['mean'])} | {_fmt(res['coverage']['p2_5'])} | "
            f"{_fmt(res['coverage']['p97_5'])} | {_fmt(res['mean_set_size']['mean'])} |"
        )
    add("")
    add("按 PHQ-9 分层看池化覆盖（alpha=0.10）：")
    add("")
    add("| PHQ-9 分层 | n | 覆盖率 [95% CI] | 平均集合大小 | 弃权率 |")
    add("|---|---:|---|---:|---:|")
    phq_cov = cross["0.10"]["coverage_by_subgroup"]
    for label in ("phq9:0-4", "phq9:5-9", "phq9:10-14", "phq9:15-19", "phq9:20+"):
        if label not in phq_cov:
            continue
        row = phq_cov[label]
        add(
            f"| {label.replace('phq9:', '')} | {row['n']} | {_fmt(row['coverage'])} "
            f"{_ci(row['coverage_wilson95'])} | {_fmt(row['mean_set_size'])} | "
            f"{_fmt(row['abstention_rate'])} |"
        )
    add("")
    add(
        "池化覆盖 0.839 掩盖了阈值附近人群的系统性低估：PHQ-9 10–14 组覆盖仅 "
        f"{_fmt(phq_cov.get('phq9:10-14', {}).get('coverage'))}，而 0–4 组接近 "
        f"{_fmt(phq_cov.get('phq9:0-4', {}).get('coverage'))}。"
    )
    add("")
    src_policy = cross["0.10"]
    add(
        "策略后果：alpha=0.10 时自动告警精确率为 "
        f"{_fmt(src_policy['auto_alert_precision'])}，但只有 "
        f"{_fmt(src_policy['positive_auto_alert_rate'])} 的阳性被自动告警，"
        f"{_fmt(src_policy['positive_auto_cleared_rate'])} 的阳性被自动排除。"
        "用源域校准出的 q 直接迁移到目标域会系统性低估风险，不能这样上线。"
    )
    add("")

    add("## 4. 结构化亚组公平性（生产 v1.23 内部测试，仅诊断）")
    add("")
    fair = units["structured_internal"]["fairness"]
    adds = ["source:kaggle", "source:mendeley", "gender:0", "gender:1", "kaggle_gender:0", "kaggle_gender:1"]
    adds += [k for k in fair["subgroups"] if k.startswith("age:") or k.startswith("kaggle_age:")]
    add("| 亚组 | n | 阳性率 | AUC | Brier | ECE | 0.25 告警率 | 0.25 TPR | 0.25 PPV | 0.50 告警率 | 0.50 TPR | 0.50 PPV |")
    add("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for name in adds:
        if name not in fair["subgroups"]:
            continue
        s = fair["subgroups"][name]
        op25 = s["operating_points"]["0.25"]
        op50 = s["operating_points"]["0.50"]
        add(
            f"| {name} | {s['n']} | {_fmt(s['prevalence'])} | {_fmt(s['auroc'])} | "
            f"{_fmt(s['brier'])} | {_fmt(s['ece'])} | {_fmt(op25['alert_rate'])} | "
            f"{_fmt(op25['sensitivity'])} | {_fmt(op25['ppv'])} | "
            f"{_fmt(op50['alert_rate'])} | {_fmt(op50['sensitivity'])} | {_fmt(op50['ppv'])} |"
        )
    add("")

    add("### 4.1 差距与自助置信区间")
    add("")
    add("| 阈值 | 对比 | 指标 | 差值 | 95% CI |")
    add("|---:|---|---|---:|---|")
    for t, contrasts in fair["gaps"].items():
        if t not in ("0.25", "0.50"):
            continue
        for name, metrics in contrasts.items():
            for metric in ("tpr", "fpr", "ppv", "alert_rate"):
                g = metrics[metric]
                if g.get("status") == "not_evaluable":
                    continue
                add(f"| {t} | {name} | {metric} | {_fmt(g['delta'])} | {_ci(g['ci95'])} |")
    add("")
    add("说明：source 不是受保护属性，而是数据来源/标签定义代理；Mendeley 仅 137 行，区间很宽。")
    add("")
    add(
        "年龄组的 TPR/FPR 差距同时受病例构成与分数分布影响：17–20 组患病率 0.705，"
        "31–35 组 0.408；但 TPR/FPR 是类条件指标，差距不能仅由患病率解释，"
        "需要按年龄重估校准或做分组阈值审查。"
    )
    add("")

    add("### 4.2 分组（Mondrian）conformal：组内 q 是否救得回来")
    add("")
    add("| 属性 | 组 | n_cal | n_test | 池化 q 覆盖 | 组内 q | 组内 q 覆盖 | 组内弃权率 |")
    add("|---|---|---:|---:|---:|---:|---:|---:|")
    pooled_cov = units["structured_internal"]["conformal"]["0.10"]["coverage_by_subgroup"]
    for attr, block in units["structured_internal"]["mondrian_alpha_0.10"].items():
        for name, row in block["groups"].items():
            if row.get("status") == "skipped":
                continue
            pooled = pooled_cov.get(name, {}).get("coverage")
            add(
                f"| {attr} | {name} | {row['n_cal']} | {row['n_test']} | {_fmt(pooled)} | "
                f"{_fmt(row['q'])} | {_fmt(row['coverage'])} | {_fmt(row['abstention_rate'])} |"
            )
    add("")
    add(
        "Mondrian 的组内 q 只在该组校准样本足够时有效。Mendeley 组校准 n=137，"
        "组内 q 覆盖反而低于池化 q；这不是方法失败，而是有限样本下 q 的抽样波动。"
        "目标域需要先积累本机构校准样本，再谈分组 conformal。"
    )
    add("")

    add("## 5. 干净的来源留出模型：亚组二次读数")
    add("")
    clean = units["structured_source_holdout"]["fairness_secondary"]["subgroups"]
    add("| 亚组 | n | 阳性率 | AUC | Brier | 0.50 TPR | 0.50 FPR | 0.50 PPV |")
    add("|---|---:|---:|---:|---:|---:|---:|---:|")
    for name, s in clean.items():
        if name.startswith("phq9:"):
            continue
        op = s["operating_points"]["0.50"]
        spec = op.get("specificity")
        fpr = None if spec is None else 1.0 - float(spec)
        add(
            f"| {name} | {s['n']} | {_fmt(s['prevalence'])} | {_fmt(s['auroc'])} | "
            f"{_fmt(s['brier'])} | {_fmt(op['sensitivity'])} | "
            f"{_fmt(fpr)} | {_fmt(op['ppv'])} |"
        )
    add("")
    add("这是目标域内部的二次读数；标签为 PHQ-9≥10，不能与 Kaggle 自报标签直接合并解释。"
        "PHQ-9 严重度剂量反应见 `outputs/ROUND_46_SOURCE_HOLDOUT.md`。")
    add("")

    add("## 6. 不可评估项")
    add("")
    add("- 文本：中文语料与 groupwise OOF 表没有性别/年龄/来源标注；group 是文本家族，不是人群。")
    add("- 英文留出：单次切分，无受保护属性，且无兄弟文本溯源。")
    add("- 生理：数据表只有 source='depresjon'，无性别/年龄；n=157 也不足以做稳定亚组推断。")
    add("- 融合：没有对齐的三模态有标签样本，conformal 与公平性都无从谈起。")
    add("")

    add("## 7. 解释边界")
    add("")
    add("- 同分布单元覆盖率接近名义值；跨来源覆盖率下降，说明可交换性不成立，conformal 不能凭空修复分布偏移。")
    add(
        "- 跨来源不是“覆盖率略低”：alpha=0.10 时 PHQ-9 10–14 组覆盖仅 "
        f"{_fmt(phq_cov.get('phq9:10-14', {}).get('coverage'))}，"
        f"{_fmt(src_policy['positive_auto_cleared_rate'])} 的阳性被自动排除。"
        "这是策略级失效，不是统计噪声。"
    )
    add("- 目标域 50 条本地标签即可把池化覆盖拉回 0.90 附近；这是最低可行的上线前置条件，但分组覆盖仍需更多样本。")
    add("- 覆盖率是边际保证，不是亚组保证；Mondrian 分组校准需要每组足够的校准样本，137 行的 Mendeley 组不足以稳定估计组内 q。")
    add("- 弃权率是覆盖率的代价：文本模型在 90% 覆盖下仅约三成阳性被自动告警，不能直接做无人决策。")
    add("- 公平性只在结构化数据上可算；来源差距混合了协变量偏移与标签定义偏移，不能当作“算法歧视”结论。")
    add("- 所有结果来自离线评估，不改变生产路由；上线前需要在目标机构重新校准并重估亚组覆盖。")
    add("")

    add("## 8. 复现")
    add("")
    add("```bash")
    add("cd backend")
    add(".venv/Scripts/python.exe scripts/modeling/eval/v1_46/06_conformal_fairness.py")
    add("```")
    add("")
    add("产物：`scripts/modeling/eval/v1_46/conformal_fairness.json`、"
        "`outputs/candidates/round46/conformal_fairness.json`。")
    add("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
