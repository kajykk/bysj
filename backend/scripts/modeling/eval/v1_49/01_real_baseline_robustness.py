#!/usr/bin/env python
"""ROUND_49: robustness and wear-time confound audit of the real-actigraphy baseline.

Read-only offline evaluation. No production artifact, threshold, runtime
contract, or model is modified.

The ROUND_48 baseline reported two subject-level protocols that disagree
(0.6454 LOSO vs 0.7620 multi-day grouped). This script asks two narrower
questions before any external validation is attempted:

1. How much does the subject-level result move across defensible analysis
   choices (mean vs median aggregation, autocorrelation NaN handling, day
   inclusion)?
2. Is the signal separable from zero-activity days and wear/activity-time
   proxies?

The answer is descriptive. A wide specification range means the ROUND_48 point
estimate is not a stable performance estimate, and a label-related wear proxy
means the signal cannot be called a clean physiological effect. Neither result
upgrades the production physiological unit.

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/modeling/eval/v1_49/01_real_baseline_robustness.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import math
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu, spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[3]
PROJECT_ROOT = BACKEND.parent
ROUND48_PATH = HERE.parent / "v1_48" / "01_real_actigraphy_baseline.py"

OUT_JSON = HERE / "robustness_audit.json"
OUT_CSV = HERE / "specification_curve.csv"
OUT_MIRROR = PROJECT_ROOT / "outputs" / "candidates" / "round49" / "robustness_audit.json"
OUT_REPORT = PROJECT_ROOT / "docs" / "model-evaluation" / "REAL_BASELINE_ROBUSTNESS.md"

SEED = 42
BOOTSTRAP_B = 500
MIN_DAYS = 14
AGGREGATIONS = ("mean", "median")
AUTOCORR_MODES = ("nanmean", "zero", "drop")
DAY_MODES = ("all", "nonzero", "min14")
CONFOUND_FEATURES = (
    "mean_act",
    "zero_day_fraction",
    "mean_active_minutes",
    "mean_zero_minutes",
    "active_mean_act",
    "active_days",
)


def _load_round48():
    spec = importlib.util.spec_from_file_location("round48_baseline", ROUND48_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


R48 = _load_round48()
PRIMARY = list(R48.PRIMARY_FEATURES)


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_active_minutes() -> pd.DataFrame:
    rows: list[dict] = []
    with zipfile.ZipFile(R48.RAW_ZIP) as archive:
        for name in archive.namelist():
            if not (name.startswith("data/condition/") or name.startswith("data/control/")):
                continue
            subject = Path(name).stem
            if not (subject.startswith("condition_") or subject.startswith("control_")):
                continue
            frame = pd.read_csv(io.BytesIO(archive.read(name)), parse_dates=["date"])
            for day, group in frame.groupby(frame["date"].dt.date):
                activity = group["activity"].to_numpy(dtype=np.float64)
                if activity.size != R48.MIN_COMPLETE_MINUTES:
                    continue
                rows.append(
                    {
                        "subject": subject,
                        "day": str(day),
                        "active_minutes": int((activity > 0).sum()),
                        "zero_minutes": int((activity == 0).sum()),
                    }
                )
    out = pd.DataFrame(rows)
    if len(out) != 1029:
        raise AssertionError(f"expected 1029 complete days, got {len(out)}")
    if out.duplicated(["subject", "day"]).any():
        raise AssertionError("duplicate subject-day in active-minute table")
    return out


def subset_days(frame: pd.DataFrame, day_mode: str) -> pd.DataFrame:
    if day_mode == "all":
        return frame
    if day_mode == "nonzero":
        return frame[~frame["all_zero"]].copy()
    if day_mode == "min14":
        counts = frame.groupby("subject").size()
        keep = counts[counts >= MIN_DAYS].index
        return frame[frame["subject"].isin(keep)].copy()
    raise ValueError(day_mode)


def build_subject_table(
    frame: pd.DataFrame,
    features: list[str],
    aggregation: str,
    autocorr_mode: str,
) -> pd.DataFrame:
    work = frame
    if autocorr_mode == "zero" and "autocorrelation_act" in features:
        work = work.copy()
        work["autocorrelation_act"] = work["autocorrelation_act"].fillna(0.0)

    grouped = work.groupby("subject")
    table = grouped.agg(
        label=("label", "first"),
        days=("day", "size"),
        zero_days=("all_zero", "sum"),
        mean_active_minutes=("active_minutes", "mean"),
        mean_zero_minutes=("zero_minutes", "mean"),
    )
    for feature in features:
        if feature in (
            "zero_day_fraction",
            "active_days",
            "active_mean_act",
            "mean_active_minutes",
            "mean_zero_minutes",
        ):
            continue
        if aggregation == "mean":
            table[feature] = grouped[feature].mean()
        elif aggregation == "median":
            table[feature] = grouped[feature].median()
        else:
            raise ValueError(aggregation)
    table = table.reset_index()
    for feature in features:
        if feature in table.columns:
            table[feature] = table[feature].fillna(0.0)

    active = work[~work["all_zero"]].groupby("subject")["mean_act"].mean().rename("active_mean_act")
    table = table.merge(active, on="subject", how="left")
    table["active_mean_act"] = table["active_mean_act"].fillna(0.0)
    table["zero_day_fraction"] = table["zero_days"] / table["days"]
    table["active_days"] = table["days"] - table["zero_days"]
    return table


def _make_model():
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(C=1.0, max_iter=2000, solver="lbfgs"),
    )


def _bootstrap_auc(y: np.ndarray, score: np.ndarray, b: int = BOOTSTRAP_B) -> dict:
    rng = np.random.default_rng(SEED)
    aucs: list[float] = []
    for _ in range(b):
        idx = rng.integers(0, len(y), len(y))
        yy = y[idx]
        ss = score[idx]
        if len(np.unique(yy)) < 2:
            continue
        aucs.append(float(roc_auc_score(yy, ss)))
    return {
        "b": int(b),
        "seed": SEED,
        "valid_resamples": int(len(aucs)),
        "auc_95ci": [float(np.percentile(aucs, 2.5)), float(np.percentile(aucs, 97.5))] if aucs else None,
    }


def loso_model(table: pd.DataFrame, features: list[str]) -> dict:
    X = table[features].to_numpy(dtype=float)
    y = table["label"].to_numpy(dtype=int)
    oof = np.zeros(len(y), dtype=float)
    coefficients: list[np.ndarray] = []
    for i in range(len(y)):
        train = np.arange(len(y)) != i
        model = _make_model()
        model.fit(X[train], y[train])
        oof[i] = float(model.predict_proba(X[i : i + 1])[0, 1])
        coefficients.append(np.asarray(model.named_steps["logisticregression"].coef_[0], dtype=float))
    coef_matrix = np.asarray(coefficients)
    metrics = R48.metrics(y, oof)
    return {
        "features": features,
        "n_subjects": int(len(y)),
        "metrics": metrics,
        "bootstrap": _bootstrap_auc(y, oof),
        "coefficients": {
            feature: {
                "mean_standardized": float(coef_matrix[:, idx].mean()),
                "negative_folds": int((coef_matrix[:, idx] < 0).sum()),
                "n_folds": int(len(y)),
            }
            for idx, feature in enumerate(features)
        },
    }


def _oof_scores(table: pd.DataFrame, features: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    X = table[features].to_numpy(dtype=float)
    y = table["label"].to_numpy(dtype=int)
    subject = table["subject"].to_numpy()
    oof = np.zeros(len(y), dtype=float)
    for i in range(len(y)):
        train = np.arange(len(y)) != i
        model = _make_model()
        model.fit(X[train], y[train])
        oof[i] = float(model.predict_proba(X[i : i + 1])[0, 1])
    return subject, y, oof


def influence_check(frame: pd.DataFrame) -> dict:
    definitions = {
        "primary4_mean_nanmean": ("mean", "nanmean", PRIMARY),
        "best_mean_zero": ("mean", "zero", PRIMARY),
        "wear_proxies_only": (
            "mean",
            "nanmean",
            ["zero_day_fraction", "mean_active_minutes", "active_days"],
        ),
        "primary4_plus_wear": (
            "mean",
            "nanmean",
            PRIMARY + ["zero_day_fraction", "mean_active_minutes", "active_days"],
        ),
    }
    exclusions = {
        "all": [],
        "exclude_control_3": ["control_3"],
        "exclude_control_32": ["control_32"],
        "exclude_control_31": ["control_31"],
        "exclude_top3": ["control_3", "control_32", "control_31"],
    }
    out: dict[str, dict] = {}
    for name, (aggregation, autocorr_mode, features) in definitions.items():
        table = build_subject_table(frame, features, aggregation, autocorr_mode)
        subject, y, oof = _oof_scores(table, features)
        out[name] = {}
        for label, excluded in exclusions.items():
            keep = ~np.isin(subject, excluded) if excluded else np.ones(len(y), dtype=bool)
            out[name][label] = {
                "n_subjects": int(keep.sum()),
                "auc": float(roc_auc_score(y[keep], oof[keep])),
            }
    return out


def univariate(table: pd.DataFrame, column: str) -> dict:
    y = table["label"].to_numpy(dtype=int)
    score = table[column].to_numpy(dtype=float)
    auc = float(roc_auc_score(y, score))
    condition = table.loc[table["label"] == 1, column].to_numpy(dtype=float)
    control = table.loc[table["label"] == 0, column].to_numpy(dtype=float)
    return {
        "auc_raw": auc,
        "auc_oriented": float(max(auc, 1.0 - auc)),
        "direction": "higher value -> condition" if auc >= 0.5 else "higher value -> control",
        "bootstrap": _bootstrap_auc(y, score),
        "condition_mean": float(condition.mean()),
        "condition_sd": float(condition.std(ddof=1)),
        "control_mean": float(control.mean()),
        "control_sd": float(control.std(ddof=1)),
        "mannwhitney_p": float(mannwhitneyu(condition, control, alternative="two-sided").pvalue),
    }


def spec_id(aggregation: str, autocorr_mode: str, day_mode: str) -> str:
    return f"{aggregation}__{autocorr_mode}__{day_mode}"


def run_spec(frame: pd.DataFrame, spec: dict) -> dict:
    subset = subset_days(frame, spec["day_mode"])
    features = [
        feature for feature in PRIMARY if not (spec["autocorr_mode"] == "drop" and feature == "autocorrelation_act")
    ]
    table = build_subject_table(
        subset,
        features,
        spec["aggregation"],
        spec["autocorr_mode"],
    )
    result = loso_model(table, features)
    return {
        "spec_id": spec_id(spec["aggregation"], spec["autocorr_mode"], spec["day_mode"]),
        "aggregation": spec["aggregation"],
        "autocorr_mode": spec["autocorr_mode"],
        "day_mode": spec["day_mode"],
        "features": features,
        "n_subjects": int(len(table)),
        "n_days": int(len(subset)),
        "n_positive_subjects": int(table["label"].sum()),
        "n_zero_days": int(subset["all_zero"].sum()),
        "auc": result["metrics"]["auc"],
        "auc_95ci": result["bootstrap"]["auc_95ci"],
        "auprc": result["metrics"]["auprc"],
        "brier": result["metrics"]["brier"],
        "mean_predicted": result["metrics"]["mean_predicted"],
        "calibration_slope": result["metrics"]["calibration_slope"],
    }


def _factor_summary(rows: list[dict], key: str) -> dict:
    levels = sorted({row[key] for row in rows})
    out = {}
    for level in levels:
        aucs = [row["auc"] for row in rows if row[key] == level]
        out[level] = {
            "n_specs": len(aucs),
            "auc_mean": float(np.mean(aucs)),
            "auc_min": float(np.min(aucs)),
            "auc_max": float(np.max(aucs)),
        }
    return out


def summarize_specs(rows: list[dict]) -> dict:
    aucs = np.asarray([row["auc"] for row in rows], dtype=float)
    ci_lows = np.asarray([row["auc_95ci"][0] for row in rows], dtype=float)
    ci_highs = np.asarray([row["auc_95ci"][1] for row in rows], dtype=float)
    slopes = np.asarray([row["calibration_slope"] for row in rows], dtype=float)
    best = max(rows, key=lambda row: row["auc"])
    worst = min(rows, key=lambda row: row["auc"])
    return {
        "n_specs": int(len(rows)),
        "auc_min": float(aucs.min()),
        "auc_median": float(np.median(aucs)),
        "auc_max": float(aucs.max()),
        "auc_range": float(aucs.max() - aucs.min()),
        "calibration_slope_min": float(slopes.min()),
        "calibration_slope_max": float(slopes.max()),
        "ci_lower_gt_0_5": int((ci_lows > 0.5).sum()),
        "ci_covers_0_5": int(((ci_lows <= 0.5) & (ci_highs >= 0.5)).sum()),
        "auc_ge_0_60": int((aucs >= 0.60).sum()),
        "auc_ge_0_65": int((aucs >= 0.65).sum()),
        "auc_ge_0_70": int((aucs >= 0.70).sum()),
        "auc_lt_0_60": int((aucs < 0.60).sum()),
        "best_spec": best["spec_id"],
        "best_spec_auc": best["auc"],
        "worst_spec": worst["spec_id"],
        "worst_spec_auc": worst["auc"],
        "by_aggregation": _factor_summary(rows, "aggregation"),
        "by_autocorr_mode": _factor_summary(rows, "autocorr_mode"),
        "by_day_mode": _factor_summary(rows, "day_mode"),
    }


def main() -> int:
    frame, _scores, partial_days = R48.load_days()
    active = load_active_minutes()
    frame = frame.merge(
        active,
        on=["subject", "day"],
        how="left",
        validate="one_to_one",
    )
    if frame["active_minutes"].isna().any():
        raise AssertionError("active-minute table does not cover every complete day")
    if int((frame["active_minutes"] + frame["zero_minutes"]).ne(1440).sum()) != 0:
        raise AssertionError("active + zero minutes do not sum to 1440")

    specs = [
        {
            "aggregation": aggregation,
            "autocorr_mode": autocorr_mode,
            "day_mode": day_mode,
        }
        for aggregation in AGGREGATIONS
        for autocorr_mode in AUTOCORR_MODES
        for day_mode in DAY_MODES
    ]
    spec_rows = [run_spec(frame, spec) for spec in specs]
    spec_summary = summarize_specs(spec_rows)

    base_table = build_subject_table(
        frame,
        PRIMARY,
        "mean",
        "nanmean",
    )
    univariate_rows = {column: univariate(base_table, column) for column in CONFOUND_FEATURES}

    base_models = {
        "mean_act_only": loso_model(base_table, ["mean_act"]),
        "zero_day_fraction_only": loso_model(base_table, ["zero_day_fraction"]),
        "mean_active_minutes_only": loso_model(base_table, ["mean_active_minutes"]),
        "active_mean_act_only": loso_model(base_table, ["active_mean_act"]),
        "mean_act_plus_zero_fraction": loso_model(base_table, ["mean_act", "zero_day_fraction"]),
        "mean_act_plus_active_minutes": loso_model(base_table, ["mean_act", "mean_active_minutes"]),
        "wear_proxies_only": loso_model(
            base_table,
            ["zero_day_fraction", "mean_active_minutes", "active_days"],
        ),
        "mean_act_plus_wear_proxies": loso_model(
            base_table,
            ["mean_act", "zero_day_fraction", "mean_active_minutes"],
        ),
    }

    correlations = {}
    for left, right in (
        ("zero_day_fraction", "mean_act"),
        ("mean_active_minutes", "mean_act"),
        ("mean_zero_minutes", "mean_act"),
        ("zero_day_fraction", "active_mean_act"),
    ):
        result = spearmanr(base_table[left], base_table[right])
        correlations[f"{left}__{right}"] = {
            "spearman_rho": float(result.statistic),
            "p_value": float(result.pvalue),
        }

    zero_day_subjects = (
        base_table.loc[base_table["zero_days"] > 0, ["subject", "label", "days", "zero_days"]]
        .sort_values(["zero_days", "subject"], ascending=[False, True])
        .head(8)
        .to_dict("records")
    )
    zero_day_by_group = {
        "condition_subjects_with_zero_day": int(((base_table["label"] == 1) & (base_table["zero_days"] > 0)).sum()),
        "control_subjects_with_zero_day": int(((base_table["label"] == 0) & (base_table["zero_days"] > 0)).sum()),
        "condition_zero_days": int(base_table.loc[base_table["label"] == 1, "zero_days"].sum()),
        "control_zero_days": int(base_table.loc[base_table["label"] == 0, "zero_days"].sum()),
        "condition_mean_complete_days": float(base_table.loc[base_table["label"] == 1, "days"].mean()),
        "control_mean_complete_days": float(base_table.loc[base_table["label"] == 0, "days"].mean()),
        "condition_median_complete_days": float(base_table.loc[base_table["label"] == 1, "days"].median()),
        "control_median_complete_days": float(base_table.loc[base_table["label"] == 0, "days"].median()),
        "condition_mean_active_days": float(base_table.loc[base_table["label"] == 1, "active_days"].mean()),
        "control_mean_active_days": float(base_table.loc[base_table["label"] == 0, "active_days"].mean()),
    }

    influence = influence_check(frame)
    mean_act_auc = base_models["mean_act_only"]["metrics"]["auc"]
    adjusted_auc = base_models["mean_act_plus_zero_fraction"]["metrics"]["auc"]
    active_mean_auc = base_models["active_mean_act_only"]["metrics"]["auc"]
    zero_fraction_auc = univariate_rows["zero_day_fraction"]["auc_raw"]

    spec_verdict = (
        f"18 个规范网格的受试者级 LOSO AUC 范围 {spec_summary['auc_min']:.4f}–"
        f"{spec_summary['auc_max']:.4f}（中位 {spec_summary['auc_median']:.4f}）；"
        f"{spec_summary['ci_lower_gt_0_5']}/18 个规范的 95% CI 下界高于 0.5，"
        f"{spec_summary['ci_covers_0_5']}/18 个覆盖 0.5，"
        f"{spec_summary['auc_ge_0_65']}/18 个达到 0.65。"
        "ROUND_48 的 0.6454 只是该网格中的一个点，不是稳健性能估计。"
    )
    confound_verdict = (
        f"零活动日比例单变量 AUC={zero_fraction_auc:.4f}"
        f"（{'病例更高' if zero_fraction_auc >= 0.5 else '对照更高'}）；"
        f"mean_act 单变量模型 AUC={mean_act_auc:.4f}，"
        f"加入零活动日比例后={adjusted_auc:.4f}；"
        f"仅用 active_mean_act 的模型 AUC={active_mean_auc:.4f}。"
        "零活动日/活动分钟代理与标签相关，且方向并不一致（病例全零日更少、"
        "但活动日内的零活动分钟更多），无法把信号解释为干净的生理效应。"
    )
    overall_verdict = (
        "真实 actigraphy 在 Depresjon 上有可检出但脆弱的组间信号；"
        "规范选择可把受试者级 AUC 从约 0.59 拉到 0.74，且佩戴/零活动代理与标签纠缠。"
        "因此 ROUND_48 不能升级为稳定的真实生理性能证据，更不能进入生产；"
        "Phase 1 的外部队列必须带佩戴元数据并预注册处理规则。"
    )

    payload = {
        "round": "ROUND_49",
        "status": "descriptive_offline_robustness_audit_not_production",
        "external_validation": False,
        "production_changed": False,
        "input": {
            "round48_script": ROUND48_PATH.relative_to(PROJECT_ROOT).as_posix(),
            "round48_script_sha256": _sha256(ROUND48_PATH),
            "round48_json": (
                PROJECT_ROOT / "backend" / "scripts" / "modeling" / "eval" / "v1_48" / "real_actigraphy_baseline.json"
            )
            .relative_to(PROJECT_ROOT)
            .as_posix(),
        },
        "dataset": {
            "n_subjects": int(frame["subject"].nunique()),
            "n_complete_days": int(len(frame)),
            "n_partial_days_excluded": int(partial_days),
            "n_zero_days": int(frame["all_zero"].sum()),
            "positive_days": int(frame["label"].sum()),
            "note": (
                "Same Depresjon complete-day table as ROUND_48, merged with "
                "per-day active/zero minute counts from the raw per-subject files."
            ),
        },
        "design": {
            "spec_grid": {
                "aggregation": list(AGGREGATIONS),
                "autocorr_mode": list(AUTOCORR_MODES),
                "day_mode": list(DAY_MODES),
                "n_specs": len(spec_rows),
            },
            "analysis_unit": "subject-level leave-one-subject-out; scaler fit inside each fold",
            "bootstrap": f"{BOOTSTRAP_B} subject-level resamples, seed {SEED}",
            "confound_features": list(CONFOUND_FEATURES),
            "note": (
                "Autocorr modes: nanmean skips undefined days; zero fills them "
                "with 0 before aggregation; drop removes the feature. Day modes: "
                "all complete days; nonzero excludes all-zero days; min14 keeps "
                "subjects with at least 14 complete days."
            ),
        },
        "results": {
            "specification_curve": spec_rows,
            "specification_summary": spec_summary,
            "confound_univariate": univariate_rows,
            "confound_models": base_models,
            "confound_correlations": correlations,
            "zero_day_distribution": zero_day_by_group,
            "zero_day_subjects_top": zero_day_subjects,
            "influence_check": influence,
        },
        "interpretation": {
            "spec_verdict": spec_verdict,
            "confound_verdict": confound_verdict,
            "overall_verdict": overall_verdict,
            "allowed_claims": [
                "在 Depresjon 上，真实 actigraphy 的受试者级 AUC 对可辩护的聚合方式与日纳入规则敏感。",
                "零活动日与活动分钟代理与标签相关，因此该基线不能当作干净的生理信号。",
                "ROUND_49 不提升生产生理单元的证据等级，也不修改任何工件。",
            ],
            "forbidden_claims": [
                "ROUND_48 的 0.6454 或 0.7620 是稳定的真实生理性能估计。",
                "真实 actigraphy 基线已获外部验证或已可用于生产。",
                "佩戴代理模型具有临床意义；它们只是数据质量与活动模式的诊断。",
                "这些结果适用于消费级可穿戴、普通成人或临床诊断。",
            ],
        },
        "sanity_checks": {
            "n_subjects_55": bool(frame["subject"].nunique() == 55),
            "n_complete_days_1029": bool(len(frame) == 1029),
            "active_minutes_complete": bool((frame["active_minutes"] + frame["zero_minutes"] == 1440).all()),
            "n_specs_18": bool(len(spec_rows) == 18),
            "all_spec_aucs_finite": bool(all(math.isfinite(row["auc"]) for row in spec_rows)),
            "csv_sha256": None,
        },
        "artifacts": {
            "specification_curve_csv": OUT_CSV.relative_to(PROJECT_ROOT).as_posix(),
            "report": OUT_REPORT.relative_to(PROJECT_ROOT).as_posix(),
        },
    }

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(spec_rows).to_csv(OUT_CSV, index=False)
    csv_sha = _sha256(OUT_CSV)
    payload["sanity_checks"]["csv_sha256"] = csv_sha
    payload = _finite(payload)
    text = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False)
    OUT_JSON.write_text(text, encoding="utf-8")
    OUT_MIRROR.parent.mkdir(parents=True, exist_ok=True)
    OUT_MIRROR.write_text(text, encoding="utf-8")
    OUT_REPORT.write_text(render_report(payload), encoding="utf-8")

    print("[real_baseline_robustness]")
    print(
        f"  subjects={payload['dataset']['n_subjects']} days={payload['dataset']['n_complete_days']} "
        f"zero_days={payload['dataset']['n_zero_days']} partial_excluded={partial_days}"
    )
    print(
        f"  specs={spec_summary['n_specs']} AUC={spec_summary['auc_min']:.4f}-"
        f"{spec_summary['auc_max']:.4f} median={spec_summary['auc_median']:.4f} "
        f"ci>0.5={spec_summary['ci_lower_gt_0_5']}/18"
    )
    print(
        f"  zero_fraction univariate AUC={zero_fraction_auc:.4f} "
        f"mean_act={mean_act_auc:.4f} mean_act+zero={adjusted_auc:.4f} "
        f"active_mean_act={active_mean_auc:.4f}"
    )
    print(f"  -> {OUT_JSON.relative_to(PROJECT_ROOT)}")
    print(f"  -> {OUT_CSV.relative_to(PROJECT_ROOT)}")
    print(f"  -> {OUT_REPORT.relative_to(PROJECT_ROOT)}")
    return 0


def _fmt(value, digits: int = 4) -> str:
    return "NA" if value is None else f"{value:.{digits}f}"


def render_report(payload: dict) -> str:
    dataset = payload["dataset"]
    results = payload["results"]
    summary = results["specification_summary"]
    univariate_rows = results["confound_univariate"]
    models = results["confound_models"]
    correlations = results["confound_correlations"]
    zero_dist = results["zero_day_distribution"]
    top_zero = results["zero_day_subjects_top"]
    influence = results["influence_check"]
    primary_influence_aucs = [row["auc"] for row in influence["primary4_mean_nanmean"].values()]
    wear_influence_aucs = [row["auc"] for row in influence["wear_proxies_only"].values()]
    interpretation = payload["interpretation"]

    lines = [
        "# Depresjon 真实 actigraphy 基线的稳健性与佩戴混杂（ROUND_49）",
        "",
        "> 本文件由 `backend/scripts/modeling/eval/v1_49/01_real_baseline_robustness.py` 生成。",
        "> 只读离线评估，**没有修改生产模型、工件、阈值或运行时**。",
        "> **这不是外部验证，也不是生产替换。**",
        "",
        "## 0. 结论先行",
        "",
        f"- 18 个规范网格的受试者级 LOSO AUC：**{summary['auc_min']:.4f}–"
        f"{summary['auc_max']:.4f}**（中位 {summary['auc_median']:.4f}）；"
        f"95% CI 下界高于 0.5 的规范 {summary['ci_lower_gt_0_5']}/18，"
        f"覆盖 0.5 的 {summary['ci_covers_0_5']}/18。",
        f"- ROUND_48 的 0.6454 只是网格中的一个点；"
        f"最好规范 {summary['best_spec']} = {summary['best_spec_auc']:.4f}，"
        f"最差规范 {summary['worst_spec']} = {summary['worst_spec_auc']:.4f}。",
        f"- 零活动日比例单变量 AUC {univariate_rows['zero_day_fraction']['auc_raw']:.4f}，"
        f"mean_act 单变量模型 AUC {models['mean_act_only']['metrics']['auc']:.4f}，"
        f"加入零活动日比例后 {models['mean_act_plus_zero_fraction']['metrics']['auc']:.4f}。",
        "- 零活动日/活动分钟代理与标签相关，方向不一致：病例全零日更少，"
        "但活动日内的零活动分钟更多；**不能把信号解释为干净的生理效应**。",
        f"- 仅用佩戴代理的 LOSO 模型 AUC {models['wear_proxies_only']['metrics']['auc']:.4f}，"
        "高于 ROUND_48 主口径 0.6454，也高于其多日聚合 0.7620；"
        "这是数据质量混杂的强信号。",
        f"- 记录时长也与标签相关：病例平均 {zero_dist['condition_mean_complete_days']:.1f} "
        f"个完整日，对照 {zero_dist['control_mean_complete_days']:.1f}；"
        "`active_days` 与 `min14` 规范部分反映佩戴依从性，不是纯活动量。",
        "- 结论：ROUND_48 的真实 actigraphy 信号是**脆弱的、与佩戴/活动模式纠缠的**；"
        "不升级证据等级，不进入生产，Phase 1 外部队列必须带佩戴元数据并预注册规则。",
        "- **ROUND_50 后续审计（2026-11-02）**：ROUND_48 的日级多日聚合次口径"
        "（0.7620 ± 0.0093）另有 9 个规范：预注册 `day__zero__all` 精确复现，"
        "但受试者级 AUC 范围为 0.6565–0.7620，0.7620 是网格最大值；日级口径在 "
        "9/9 配对中高于本报告的受试者级 LOSO（差值 +0.0187 到 +0.0789），"
        "校准斜率 3.23–4.28。0.7620 也不是稳健单点引用；见 "
        "`docs/model-evaluation/REAL_BASELINE_PROTOCOL_ROBUSTNESS.md`。",
        "",
        "## 1. 数据与设计",
        "",
        "| 项目 | 值 |",
        "|---|---|",
        f"| 受试者 | {dataset['n_subjects']} |",
        f"| 完整日 | {dataset['n_complete_days']}（阳性日 {dataset['positive_days']}） |",
        f"| 全零完整日 | {dataset['n_zero_days']} |",
        f"| 非完整日（排除） | {dataset['n_partial_days_excluded']} |",
        f"| 规范网格 | 聚合 {', '.join(payload['design']['spec_grid']['aggregation'])} × "
        f"自相关处理 {', '.join(payload['design']['spec_grid']['autocorr_mode'])} × "
        f"日纳入 {', '.join(payload['design']['spec_grid']['day_mode'])} = "
        f"{summary['n_specs']} 个规范 |",
        "",
        f"- 分析单位：{payload['design']['analysis_unit']}。",
        f"- Bootstrap：{payload['design']['bootstrap']}。",
        f"- 缺失处理：{payload['design']['note']}",
        "",
        "## 2. 规范曲线",
        "",
        "| 规范 | 特征数 | 受试者 | 日 | AUC | 95% CI | Brier |",
        "|---|---:|---:|---:|---:|---|---:|",
    ]
    for row in results["specification_curve"]:
        lines.append(
            f"| `{row['spec_id']}` | {len(row['features'])} | {row['n_subjects']} | "
            f"{row['n_days']} | {row['auc']:.4f} | "
            f"[{row['auc_95ci'][0]:.4f}, {row['auc_95ci'][1]:.4f}] | "
            f"{row['brier']:.4f} |"
        )

    lines += [
        "",
        "### 2.1 因子汇总",
        "",
        "| 因子 | 水平 | 规范数 | AUC 均值 | AUC 最小 | AUC 最大 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for factor, label in (
        ("by_aggregation", "聚合"),
        ("by_autocorr_mode", "自相关处理"),
        ("by_day_mode", "日纳入"),
    ):
        for level, row in summary[factor].items():
            lines.append(
                f"| {label} | {level} | {row['n_specs']} | {row['auc_mean']:.4f} | "
                f"{row['auc_min']:.4f} | {row['auc_max']:.4f} |"
            )

    lines += [
        "",
        "`mean__nanmean__all` 的点估计与 ROUND_48 主口径相同（0.6454）；"
        "本表 CI 由 500 次 bootstrap 得到，ROUND_48 用 2000 次，故区间端点略有差异。",
        "",
        "最敏感的两个选择是**自相关缺失处理**和**日纳入规则**："
        "把未定义自相关填 0 的平均 AUC 最高（0.6658 vs nanmean 0.6429、drop 0.6577）；"
        "限制 ≥14 天后平均 AUC 最低（0.6218），剔除零活动日的影响方向不一致"
        "（均值 0.6646，但部分规范上升、部分下降）。这说明 ROUND_48 的 0.6454 不是稳健点估计。",
        "",
        "18 个规范共享同一批 55 名受试者，不是独立样本；范围描述的是**分析选择敏感性**，"
        "不是抽样分布。`autocorr_mode=drop` 同时改变缺失处理与特征数（4→3），"
        "因此该因子的汇总不能单独解释为「删掉自相关特征」的效应。"
        f"各规范的校准斜率范围 {summary['calibration_slope_min']:.3f}–"
        f"{summary['calibration_slope_max']:.3f}，在 55 人样本上不足以形成校准结论。",
        "",
        "主口径仍是 ROUND_48 预注册的 `mean__nanmean__all`（0.6454）；其余 17 个规范"
        "只用于报告敏感性，**不得事后挑选最大值 0.7364 作为性能估计**。",
        "",
        "## 3. 零活动日与佩戴代理",
        "",
        "### 3.1 单变量读数（受试者级，4 特征主口径的受试者表）",
        "",
        "| 变量 | AUC（原始方向） | AUC（定向） | 方向 | 病例均值 | 对照均值 | Mann-Whitney p |",
        "|---|---:|---:|---|---:|---:|---:|",
    ]
    for column, row in univariate_rows.items():
        lines.append(
            f"| `{column}` | {row['auc_raw']:.4f} | {row['auc_oriented']:.4f} | "
            f"{row['direction']} | {row['condition_mean']:.4f} | "
            f"{row['control_mean']:.4f} | {row['mannwhitney_p']:.4f} |"
        )

    lines += [
        "",
        "`mean_zero_minutes` 与 `mean_active_minutes` 互补（合计 1440 分钟），"
        "两者不是独立证据；6 个单变量检验未做多重比较校正，p 值只作描述。",
        "",
        f"分组分布：病例 {zero_dist['condition_subjects_with_zero_day']} 人有全零日"
        f"（共 {zero_dist['condition_zero_days']} 天），"
        f"对照 {zero_dist['control_subjects_with_zero_day']} 人有全零日"
        f"（共 {zero_dist['control_zero_days']} 天）。",
        "",
        f"记录时长本身也与标签相关：病例平均 {zero_dist['condition_mean_complete_days']:.1f} "
        f"个完整日（中位 {zero_dist['condition_median_complete_days']:.1f}），"
        f"对照平均 {zero_dist['control_mean_complete_days']:.1f}"
        f"（中位 {zero_dist['control_median_complete_days']:.1f}）。"
        f"`active_days` 的差异（病例 {zero_dist['condition_mean_active_days']:.1f} vs "
        f"对照 {zero_dist['control_mean_active_days']:.1f}）至少部分是记录时长/佩戴依从性差异；"
        "`min14` 规范因此同时改变样本构成，不能当作纯质量过滤。",
        "",
        "### 3.2 多变量 LOSO 模型",
        "",
        "| 模型 | 特征 | AUC | 95% CI | Brier | 系数方向（负向折数） |",
        "|---|---|---:|---|---:|---|",
    ]
    for name, row in models.items():
        coef_text = "; ".join(
            f"`{feature}` {value['mean_standardized']:+.3f} ({value['negative_folds']}/{value['n_folds']} 折为负)"
            for feature, value in row["coefficients"].items()
        )
        lines.append(
            f"| {name} | {', '.join(row['features'])} | {row['metrics']['auc']:.4f} | "
            f"[{row['bootstrap']['auc_95ci'][0]:.4f}, "
            f"{row['bootstrap']['auc_95ci'][1]:.4f}] | "
            f"{row['metrics']['brier']:.4f} | {coef_text} |"
        )

    lines += [
        "",
        "单特征 LOSO 模型 AUC 与 §3.1 的单变量 AUC 不必相等：每折标准化参数与截距不同，"
        "把各折的 out-of-fold 概率拼起来后，跨折排序会改变。两者只用于方向一致性检查，"
        "不能互相替代。",
        "",
        "`zero_day_fraction` 与 `mean_active_minutes` / `active_days` 是**数据质量/佩戴代理**，"
        "不是临床特征；把它们加入模型只能说明信号与这些代理纠缠，不能说明模型可用。",
        "",
        "### 3.3 相关性",
        "",
        "| 变量对 | Spearman ρ | p |",
        "|---|---:|---:|",
    ]
    for name, row in correlations.items():
        lines.append(f"| `{name}` | {row['spearman_rho']:.4f} | {row['p_value']:.4f} |")

    lines += [
        "",
        "### 3.4 全零日最多的受试者",
        "",
        "| 受试者 | 标签 | 完整日 | 全零日 |",
        "|---|---:|---:|---:|",
    ]
    for row in top_zero:
        lines.append(f"| `{row['subject']}` | {row['label']} | {row['days']} | {row['zero_days']} |")

    lines += [
        "",
        "全零日集中在少数对照受试者，且病例在活动日内有更多零活动分钟；"
        "没有佩戴/非佩戴标志时，无法区分「完全不活动」「设备未戴」和「睡眠/休息」。",
        "",
        "### 3.5 排除高零活动日受试者",
        "",
        "| 模型 | 全部 | 排除 control_3 | 排除 control_32 | 排除 control_31 | 排除三者 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, rows in influence.items():
        lines.append(
            f"| {name} | {rows['all']['auc']:.4f} | "
            f"{rows['exclude_control_3']['auc']:.4f} | "
            f"{rows['exclude_control_32']['auc']:.4f} | "
            f"{rows['exclude_control_31']['auc']:.4f} | "
            f"{rows['exclude_top3']['auc']:.4f} |"
        )

    lines += [
        "",
        "排除对象按全零日数预先指定（control_3、control_32、control_31 为全零日最多的三名受试者）。"
        f"排除后主口径仍在 {min(primary_influence_aucs):.3f}–{max(primary_influence_aucs):.3f}，"
        f"佩戴代理模型仍在 {min(wear_influence_aucs):.3f}–{max(wear_influence_aucs):.3f}；"
        f"最好规范从 {influence['best_mean_zero']['all']['auc']:.4f} "
        f"降到 {influence['best_mean_zero']['exclude_top3']['auc']:.4f}，仍落在网格范围内。"
        "结论不是由单一受试者驱动，但也不能消除佩戴混杂。",
        "",
        "## 4. 解释边界",
        "",
        "**允许的表述**",
        "",
    ]
    for item in interpretation["allowed_claims"]:
        lines.append(f"- {item}")
    lines += [
        "",
        "**禁止的表述**",
        "",
    ]
    for item in interpretation["forbidden_claims"]:
        lines.append(f"- {item}")

    lines += [
        "",
        "## 5. 复现",
        "",
        "```bash",
        "cd backend",
        ".venv/Scripts/python.exe scripts/modeling/eval/v1_49/01_real_baseline_robustness.py",
        "```",
        "",
        f"- 规范明细：`{OUT_CSV.relative_to(PROJECT_ROOT).as_posix()}`。",
        f"- JSON：`{OUT_JSON.relative_to(PROJECT_ROOT).as_posix()}`；"
        f"镜像：`{OUT_MIRROR.relative_to(PROJECT_ROOT).as_posix()}`。",
        f"- 全部随机过程固定 seed={SEED}；bootstrap {BOOTSTRAP_B} 次。",
        "",
        "## 6. 对 Phase 1 的含义",
        "",
        "1. 真实 actigraphy 的 ROUND_48 读数不能作为稳定性能估计；"
        "外部评估必须同时报告规范曲线，而不是只报一个最佳数字。",
        "2. 外部队列必须提供佩戴/非佩戴或有效佩戴时长；没有它，零活动日与疾病活动度无法分离。",
        "3. 处理规则（自相关缺失、零活动日、聚合方式）应在看外部标签前预注册，否则规范选择本身会变成隐性调参。",
        "4. 这些结果仍不支持普通人群、消费级可穿戴或临床诊断用途，也不改变生产单元证据等级。",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
