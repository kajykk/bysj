"""ROUND_46 model-card metrics, calibration, DCA, conformal helpers.

Pure functions only. Calibration/DCA primitives are imported from
v1_33/calibration_lib.py so point estimates and bootstrap use one implementation.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
    roc_curve,
)

_CALIB_DIR = Path(__file__).resolve().parents[1] / "v1_33"
if str(_CALIB_DIR) not in sys.path:
    sys.path.insert(0, str(_CALIB_DIR))

from calibration_lib import (  # noqa: E402
    calibration_slope_intercept as _calibration_slope_intercept,
    decision_curve,
    expected_calibration_error,
    reliability_table,
)

EPS = 1e-12


def _as_arrays(y, p) -> tuple[np.ndarray, np.ndarray]:
    y_arr = np.asarray(y, dtype=np.float64).ravel()
    p_arr = np.asarray(p, dtype=np.float64).ravel()
    assert y_arr.shape == p_arr.shape, f"y/p shape mismatch: {y_arr.shape} vs {p_arr.shape}"
    assert np.all(np.isfinite(y_arr)), "y contains non-finite values"
    assert np.all(np.isfinite(p_arr)), "p contains non-finite values"
    return y_arr, np.clip(p_arr, EPS, 1.0 - EPS)


def ppv_npv_at_prevalence(sensitivity: float, specificity: float, prevalence: float) -> dict:
    """Bayes reweighting; prevalence is the deployment positive rate, not the test rate."""
    sens = float(sensitivity)
    spec = float(specificity)
    prev = float(prevalence)
    denom_ppv = sens * prev + (1.0 - spec) * (1.0 - prev)
    denom_npv = spec * (1.0 - prev) + (1.0 - sens) * prev
    ppv = sens * prev / denom_ppv if denom_ppv > 0 else float("nan")
    npv = spec * (1.0 - prev) / denom_npv if denom_npv > 0 else float("nan")
    return {"ppv": float(ppv), "npv": float(npv)}


def brier_skill_score(y, p) -> float:
    y_arr, p_arr = _as_arrays(y, p)
    if y_arr.size == 0:
        return float("nan")
    prev = float(y_arr.mean())
    baseline = prev * (1.0 - prev)
    if baseline <= 0:
        return float("nan")
    return float(1.0 - brier_score_loss(y_arr, p_arr) / baseline)


def _core_metrics(y: np.ndarray, p: np.ndarray, threshold: float) -> dict:
    pred = p >= threshold
    pos = y == 1.0
    tp = float(np.sum(pred & pos))
    fp = float(np.sum(pred & ~pos))
    fn = float(np.sum(~pred & pos))
    tn = float(np.sum(~pred & ~pos))
    n = tp + fp + fn + tn
    sens = tp / (tp + fn) if (tp + fn) else float("nan")
    spec = tn / (tn + fp) if (tn + fp) else float("nan")
    ppv = tp / (tp + fp) if (tp + fp) else float("nan")
    npv = tn / (tn + fn) if (tn + fn) else float("nan")
    alert_rate = (tp + fp) / n if n else float("nan")
    f1 = 2.0 * tp / (2.0 * tp + fp + fn) if (2.0 * tp + fp + fn) else 0.0
    accuracy = (tp + tn) / n if n else float("nan")
    balanced = 0.5 * (sens + spec) if np.isfinite(sens) and np.isfinite(spec) else float("nan")
    return {
        "n": int(n),
        "threshold": float(threshold),
        "tp": int(tp),
        "fp": int(fp),
        "fn": int(fn),
        "tn": int(tn),
        "positive_rate": float(y.mean()) if n else float("nan"),
        "alert_rate": float(alert_rate),
        "alerts_per_1000": float(alert_rate * 1000.0),
        "sensitivity": float(sens),
        "specificity": float(spec),
        "ppv": float(ppv),
        "npv": float(npv),
        "f1": float(f1),
        "accuracy": float(accuracy),
        "balanced_accuracy": float(balanced),
    }


def _discrimination(y: np.ndarray, p: np.ndarray) -> dict:
    if y.size == 0 or len(np.unique(y)) < 2:
        return {"auroc": float("nan"), "auprc": float("nan")}
    return {
        "auroc": float(roc_auc_score(y, p)),
        "auprc": float(average_precision_score(y, p)),
    }


def sens_at_fixed_specificity(y, p, target_specificity: float = 0.90) -> dict:
    y_arr, p_arr = _as_arrays(y, p)
    if len(np.unique(y_arr)) < 2:
        return {"target_specificity": target_specificity, "threshold": float("nan"), "sensitivity": float("nan")}
    fpr, tpr, thresholds = roc_curve(y_arr, p_arr)
    valid = np.where((1.0 - fpr) >= target_specificity - 1e-12)[0]
    idx = int(valid[-1]) if valid.size else 0
    return {
        "target_specificity": float(target_specificity),
        "achieved_specificity": float(1.0 - fpr[idx]),
        "threshold": float(thresholds[idx]) if np.isfinite(thresholds[idx]) else float("nan"),
        "sensitivity": float(tpr[idx]),
    }


def spec_at_fixed_sensitivity(y, p, target_sensitivity: float = 0.90) -> dict:
    y_arr, p_arr = _as_arrays(y, p)
    if len(np.unique(y_arr)) < 2:
        return {"target_sensitivity": target_sensitivity, "threshold": float("nan"), "specificity": float("nan")}
    fpr, tpr, thresholds = roc_curve(y_arr, p_arr)
    idx = int(np.searchsorted(tpr, target_sensitivity, side="left"))
    idx = min(idx, len(tpr) - 1)
    return {
        "target_sensitivity": float(target_sensitivity),
        "achieved_sensitivity": float(tpr[idx]),
        "threshold": float(thresholds[idx]) if np.isfinite(thresholds[idx]) else float("nan"),
        "specificity": float(1.0 - fpr[idx]),
    }


def risk_level_distribution(p, cuts: list[float] | tuple[float, ...]) -> dict:
    p_arr = np.asarray(p, dtype=np.float64).ravel()
    levels = np.zeros(p_arr.size, dtype=np.int64)
    for cut in cuts:
        levels += (p_arr >= float(cut)).astype(np.int64)
    counts = np.bincount(levels, minlength=5)
    return {
        "cuts": [float(c) for c in cuts],
        "counts": [int(x) for x in counts],
        "rates": [float(x) / max(p_arr.size, 1) for x in counts],
    }


def model_card(
    y,
    p,
    *,
    threshold: float = 0.5,
    cuts: list[float] | tuple[float, ...] = (0.25, 0.45, 0.65, 0.85),
    target_prevalences: tuple[float, ...] = (0.10, 0.15, 0.20, 0.30),
    n_bins: int = 10,
) -> dict:
    y_arr, p_arr = _as_arrays(y, p)
    core = _core_metrics(y_arr, p_arr, threshold)
    disc = _discrimination(y_arr, p_arr)
    prev = float(y_arr.mean()) if y_arr.size else float("nan")
    ppv_npv = {
        f"{prev_target:.2f}": ppv_npv_at_prevalence(core["sensitivity"], core["specificity"], prev_target)
        for prev_target in target_prevalences
    }
    calib = _calibration_slope_intercept(y_arr, p_arr)
    return {
        **core,
        **disc,
        "auprc_definition": "sklearn average_precision_score (step-weighted); baseline = positive_rate",
        "auprc_prevalence_baseline": prev,
        "brier": float(brier_score_loss(y_arr, p_arr)) if y_arr.size else float("nan"),
        "brier_skill": brier_skill_score(y_arr, p_arr),
        "ece": float(expected_calibration_error(y_arr, p_arr, n_bins)),
        "calibration_slope": float(calib["slope"]),
        "calibration_intercept": float(calib["intercept"]),
        "sens_at_90spec": sens_at_fixed_specificity(y_arr, p_arr, 0.90),
        "spec_at_90sens": spec_at_fixed_sensitivity(y_arr, p_arr, 0.90),
        "ppv_npv_at_prevalence": ppv_npv,
        "risk_levels": risk_level_distribution(p_arr, cuts),
        "reliability": reliability_table(y_arr, p_arr, n_bins),
    }


def _bootstrap_core(y: np.ndarray, p: np.ndarray, threshold: float) -> dict:
    core = _core_metrics(y, p, threshold)
    disc = _discrimination(y, p)
    return {
        "auroc": disc["auroc"],
        "auprc": disc["auprc"],
        "brier": float(brier_score_loss(y, p)) if len(np.unique(y)) >= 2 else float("nan"),
        "f1": core["f1"],
        "sensitivity": core["sensitivity"],
        "specificity": core["specificity"],
        "ppv": core["ppv"],
        "npv": core["npv"],
        "alert_rate": core["alert_rate"],
    }


def bootstrap_metrics(
    y,
    p,
    *,
    threshold: float = 0.5,
    groups=None,
    B: int = 2000,
    seed: int = 42,
) -> dict:
    """Percentile bootstrap. Group resampling is used whenever cluster IDs are available."""
    y_arr, p_arr = _as_arrays(y, p)
    rng = np.random.RandomState(seed)
    keys = ("auroc", "auprc", "brier", "f1", "sensitivity", "specificity", "ppv", "npv", "alert_rate")
    samples: dict[str, list[float]] = {k: [] for k in keys}
    group_row = None
    n_groups = 0
    if groups is not None:
        groups_arr = np.asarray(groups)
        uniq, inverse = np.unique(groups_arr, return_inverse=True)
        n_groups = len(uniq)
        group_row = inverse.astype(np.int64)
    n = y_arr.size
    for _ in range(B):
        if group_row is None:
            idx = rng.randint(0, n, n)
        else:
            pick = rng.randint(0, n_groups, n_groups)
            cnt = np.bincount(pick, minlength=n_groups)
            idx = np.repeat(np.arange(n), cnt[group_row])
        yb, pb = y_arr[idx], p_arr[idx]
        if len(np.unique(yb)) < 2:
            continue
        m = _bootstrap_core(yb, pb, threshold)
        for k in keys:
            samples[k].append(m[k])
    out = {}
    for k in keys:
        arr = np.asarray(samples[k], dtype=np.float64)
        arr = arr[np.isfinite(arr)]
        if arr.size == 0:
            out[k] = {"ci95": [float("nan"), float("nan")], "bootstrap_n": 0}
        else:
            out[k] = {
                "ci95": [float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))],
                "bootstrap_n": int(arr.size),
            }
    out["_meta"] = {
        "B": int(B),
        "seed": int(seed),
        "resampling": "group" if group_row is not None else "row",
        "n_groups": int(n_groups) if group_row is not None else None,
    }
    return out


def bootstrap_threshold_metrics(
    y,
    p,
    thresholds,
    *,
    groups=None,
    B: int = 2000,
    seed: int = 42,
) -> dict:
    """Percentile CIs for operating-point metrics at several fixed thresholds.

    Resamples rows (or groups) once per replicate and evaluates every threshold on
    the same replicate, so the reported CIs are comparable across cuts.
    """
    y_arr, p_arr = _as_arrays(y, p)
    t_arr = np.asarray(thresholds, dtype=np.float64).ravel()
    rng = np.random.RandomState(seed)
    keys = (
        "sensitivity",
        "specificity",
        "ppv",
        "npv",
        "alert_rate",
        "net_benefit",
        "ppv_at_prev_0.15",
        "npv_at_prev_0.15",
    )
    samples = {f"{t:.2f}": {k: [] for k in keys} for t in t_arr}
    group_row = None
    n_groups = 0
    if groups is not None:
        groups_arr = np.asarray(groups)
        uniq, inverse = np.unique(groups_arr, return_inverse=True)
        n_groups = len(uniq)
        group_row = inverse.astype(np.int64)
    n = y_arr.size
    for _ in range(B):
        if group_row is None:
            idx = rng.randint(0, n, n)
        else:
            pick = rng.randint(0, n_groups, n_groups)
            cnt = np.bincount(pick, minlength=n_groups)
            idx = np.repeat(np.arange(n), cnt[group_row])
        yb, pb = y_arr[idx], p_arr[idx]
        if len(np.unique(yb)) < 2:
            continue
        for t in t_arr:
            core = _core_metrics(yb, pb, t)
            tp, fp, fn, tn = core["tp"], core["fp"], core["fn"], core["tn"]
            net_benefit = tp / max(tp + fp + fn + tn, 1) - (fp / max(tp + fp + fn + tn, 1)) * (
                t / (1.0 - t)
            )
            bayes = ppv_npv_at_prevalence(core["sensitivity"], core["specificity"], 0.15)
            vals = {
                **core,
                "net_benefit": net_benefit,
                "ppv_at_prev_0.15": bayes["ppv"],
                "npv_at_prev_0.15": bayes["npv"],
            }
            slot = samples[f"{t:.2f}"]
            for k in keys:
                slot[k].append(vals[k])

    out = {}
    for t_key, slot in samples.items():
        entry = {}
        for k in keys:
            arr = np.asarray(slot[k], dtype=np.float64)
            arr = arr[np.isfinite(arr)]
            entry[k] = {
                "ci95": (
                    [float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))]
                    if arr.size
                    else [float("nan"), float("nan")]
                ),
                "bootstrap_n": int(arr.size),
            }
        out[t_key] = entry
    out["_meta"] = {
        "B": int(B),
        "seed": int(seed),
        "resampling": "group" if group_row is not None else "row",
        "n_groups": int(n_groups) if group_row is not None else None,
    }
    return out


def at_risk_cut(y, p, cut: float, target_prevalences: tuple[float, ...] = (0.15,)) -> dict:
    y_arr, p_arr = _as_arrays(y, p)
    core = _core_metrics(y_arr, p_arr, cut)
    return {
        **core,
        "ppv_npv_at_prevalence": {
            f"{prev:.2f}": ppv_npv_at_prevalence(core["sensitivity"], core["specificity"], prev)
            for prev in target_prevalences
        },
    }


def operating_point_candidates(
    y,
    p,
    *,
    target_prevalences: tuple[float, ...] = (0.15,),
    target_sensitivity: float = 0.90,
    target_ppv: float = 0.50,
) -> dict:
    """Pick screening/triage/Youden operating points from the ROC curve."""
    y_arr, p_arr = _as_arrays(y, p)
    if len(np.unique(y_arr)) < 2:
        return {"status": "not_evaluable"}
    fpr, tpr, thresholds = roc_curve(y_arr, p_arr)
    prev = float(y_arr.mean())
    rows = []
    for i in range(len(thresholds)):
        if not np.isfinite(thresholds[i]):
            continue
        sens = float(tpr[i])
        spec = float(1.0 - fpr[i])
        ppvs = {
            f"{target:.2f}": ppv_npv_at_prevalence(sens, spec, target)["ppv"]
            for target in target_prevalences
        }
        rows.append(
            {
                "threshold": float(thresholds[i]),
                "sensitivity": sens,
                "specificity": spec,
                "youden_j": sens + spec - 1.0,
                "ppv_at_prevalence": ppvs,
            }
        )
    if not rows:
        return {"status": "not_evaluable"}

    def _best(candidates, key):
        return max(candidates, key=key) if candidates else None

    screen = _best([r for r in rows if r["sensitivity"] >= target_sensitivity], key=lambda r: r["specificity"])
    triage_key = f"{target_prevalences[0]:.2f}"
    triage = _best(
        [r for r in rows if r["ppv_at_prevalence"].get(triage_key, 0.0) >= target_ppv],
        key=lambda r: r["sensitivity"],
    )
    return {
        "status": "ok",
        "test_prevalence": prev,
        "screening_sens90": screen,
        "triage_ppv50_at_target": triage,
        "youden": _best(rows, key=lambda r: r["youden_j"]),
        "target_prevalences": [float(x) for x in target_prevalences],
    }


def dca(y, p, thresholds=None) -> dict:
    y_arr, p_arr = _as_arrays(y, p)
    if thresholds is None:
        thresholds = np.arange(0.01, 0.99 + 1e-9, 0.01)
    curve = decision_curve(y_arr, p_arr, thresholds)
    t = curve["thresholds"]
    nb = curve["net_benefit_model"]
    nb_all = curve["net_benefit_treat_all"]

    def ranges(mask) -> list[list[float]]:
        if not np.any(mask):
            return []
        out: list[list[float]] = []
        start = float(t[mask][0])
        prev = start
        for cur in t[mask][1:]:
            if cur - prev > 0.0100001:
                out.append([round(start, 2), round(float(prev), 2)])
                start = float(cur)
            prev = float(cur)
        out.append([round(start, 2), round(float(prev), 2)])
        return out

    return {
        "thresholds": [float(x) for x in t],
        "net_benefit_model": [float(x) for x in nb],
        "net_benefit_treat_all": [float(x) for x in nb_all],
        "net_benefit_treat_none": [0.0 for _ in t],
        "model_beats_treat_none_ranges": ranges(nb > 0),
        "model_beats_treat_all_ranges": ranges(nb > nb_all),
        "prevalence": float(y_arr.mean()),
    }


def fit_platt(y, p) -> dict:
    y_arr, p_arr = _as_arrays(y, p)
    calib = _calibration_slope_intercept(y_arr, p_arr)
    return {"slope": float(calib["slope"]), "intercept": float(calib["intercept"])}


def apply_platt(p, slope: float, intercept: float) -> np.ndarray:
    p_arr = np.clip(np.asarray(p, dtype=np.float64).ravel(), EPS, 1.0 - EPS)
    logit = np.log(p_arr / (1.0 - p_arr))
    return 1.0 / (1.0 + np.exp(-(intercept + slope * logit)))


def wilson_ci(k: int, n: int, z: float = 1.959963984540054) -> list[float]:
    if n <= 0:
        return [float("nan"), float("nan")]
    phat = k / n
    denom = 1.0 + z * z / n
    centre = (phat + z * z / (2.0 * n)) / denom
    half = z * math.sqrt(phat * (1.0 - phat) / n + z * z / (4.0 * n * n)) / denom
    return [max(0.0, centre - half), min(1.0, centre + half)]


def conformal_binary(y_cal, p_cal, y_test, p_test, alpha: float = 0.10) -> dict:
    """Split conformal for a binary label. Scores are 1 - p(true label)."""
    yc, pc = _as_arrays(y_cal, p_cal)
    yt, pt = _as_arrays(y_test, p_test)
    cal_scores = np.where(yc == 1.0, 1.0 - pc, pc)
    n = cal_scores.size
    k = int(math.ceil((n + 1) * (1.0 - alpha)))
    q = 1.0 if k > n else float(np.sort(cal_scores)[k - 1])
    include_pos = (1.0 - pt) <= q + 1e-12
    include_neg = pt <= q + 1e-12
    covered = np.where(yt == 1.0, include_pos, include_neg)
    set_size = include_pos.astype(np.int64) + include_neg.astype(np.int64)
    n_test = int(yt.size)
    n_cov = int(covered.sum())
    return {
        "alpha": float(alpha),
        "nominal_coverage": float(1.0 - alpha),
        "n_cal": int(n),
        "n_test": n_test,
        "q": float(q),
        "coverage": float(n_cov / n_test) if n_test else float("nan"),
        "coverage_wilson95": wilson_ci(n_cov, n_test),
        "mean_set_size": float(set_size.mean()) if n_test else float("nan"),
        "singleton_rate": float(np.mean(set_size == 1)) if n_test else float("nan"),
        "empty_rate": float(np.mean(set_size == 0)) if n_test else float("nan"),
        "both_rate": float(np.mean(set_size == 2)) if n_test else float("nan"),
        "abstention_rate": float(np.mean(set_size != 1)) if n_test else float("nan"),
    }


def _group_split(y, groups, rng: np.random.RandomState, test_frac: float = 0.5):
    groups_arr = np.asarray(groups)
    uniq = np.unique(groups_arr)
    labels = {}
    for g in uniq:
        vals = y[groups_arr == g]
        labels[g] = int(round(float(vals.mean()))) if vals.size else 0
    cal_groups, test_groups = [], []
    for label in (0, 1):
        bucket = np.array([g for g in uniq if labels[g] == label], dtype=object)
        rng.shuffle(bucket)
        n_test = max(1, int(round(len(bucket) * test_frac))) if len(bucket) > 1 else 0
        test_groups.extend(bucket[:n_test].tolist())
        cal_groups.extend(bucket[n_test:].tolist())
    cal_set, test_set = set(cal_groups), set(test_groups)
    cal_mask = np.array([g in cal_set for g in groups_arr])
    test_mask = np.array([g in test_set for g in groups_arr])
    return cal_mask, test_mask


def conformal_repeated_group_splits(
    y,
    p,
    groups,
    *,
    alpha: float = 0.10,
    n_repeats: int = 50,
    seed: int = 42,
) -> dict:
    """Repeated group-level 50/50 splits; reports mean and 2.5/97.5 percentile coverage."""
    y_arr, p_arr = _as_arrays(y, p)
    rng = np.random.RandomState(seed)
    rows = []
    for _ in range(n_repeats):
        cal_mask, test_mask = _group_split(y_arr, groups, rng)
        if not cal_mask.any() or not test_mask.any():
            continue
        res = conformal_binary(
            y_arr[cal_mask], p_arr[cal_mask], y_arr[test_mask], p_arr[test_mask], alpha
        )
        rows.append(res)
    cov = np.array([r["coverage"] for r in rows], dtype=np.float64)
    size = np.array([r["mean_set_size"] for r in rows], dtype=np.float64)
    abst = np.array([r["abstention_rate"] for r in rows], dtype=np.float64)
    return {
        "alpha": float(alpha),
        "nominal_coverage": float(1.0 - alpha),
        "n_repeats": int(len(rows)),
        "coverage_mean": float(cov.mean()) if cov.size else float("nan"),
        "coverage_p2_5": float(np.percentile(cov, 2.5)) if cov.size else float("nan"),
        "coverage_p97_5": float(np.percentile(cov, 97.5)) if cov.size else float("nan"),
        "mean_set_size": float(size.mean()) if size.size else float("nan"),
        "abstention_rate_mean": float(abst.mean()) if abst.size else float("nan"),
    }


def subgroup_metrics(
    y,
    p,
    mask,
    *,
    threshold: float = 0.5,
    cuts: list[float] | tuple[float, ...] = (0.25, 0.45, 0.65, 0.85),
    target_prevalences: tuple[float, ...] = (0.15,),
) -> dict:
    y_arr, p_arr = _as_arrays(y, p)
    mask_arr = np.asarray(mask, dtype=bool)
    y_sub, p_sub = y_arr[mask_arr], p_arr[mask_arr]
    if y_sub.size == 0:
        return {"n": 0}
    card = model_card(
        y_sub,
        p_sub,
        threshold=threshold,
        cuts=cuts,
        target_prevalences=target_prevalences,
    )
    card.pop("reliability", None)
    return card


def equalized_odds_gap(y, p, subgroups: dict, threshold: float = 0.5) -> dict:
    y_arr, p_arr = _as_arrays(y, p)
    tpr, fpr, ppv, alert = {}, {}, {}, {}
    for name, mask in subgroups.items():
        mask_arr = np.asarray(mask, dtype=bool)
        if not mask_arr.any():
            continue
        m = _core_metrics(y_arr[mask_arr], p_arr[mask_arr], threshold)
        tpr[name] = m["sensitivity"]
        fpr[name] = 1.0 - m["specificity"]
        ppv[name] = m["ppv"]
        alert[name] = m["alert_rate"]
    finite = lambda d: [v for v in d.values() if np.isfinite(v)]  # noqa: E731
    return {
        "tpr": tpr,
        "fpr": fpr,
        "ppv": ppv,
        "alert_rate": alert,
        "tpr_gap": float(max(finite(tpr)) - min(finite(tpr))) if len(finite(tpr)) > 1 else 0.0,
        "fpr_gap": float(max(finite(fpr)) - min(finite(fpr))) if len(finite(fpr)) > 1 else 0.0,
        "ppv_gap": float(max(finite(ppv)) - min(finite(ppv))) if len(finite(ppv)) > 1 else 0.0,
        "alert_rate_gap": float(max(finite(alert)) - min(finite(alert))) if len(finite(alert)) > 1 else 0.0,
    }
