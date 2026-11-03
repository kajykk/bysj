#!/usr/bin/env python
"""ROUND_50: specification robustness of the day-level grouped CV protocol.

Read-only offline evaluation. No production artifact, threshold, runtime
contract, or model is modified.

ROUND_49 audited the subject-mean LOSO protocol behind ROUND_48's 0.6454 and
found an 18-specification range of 0.5855-0.7364. ROUND_48's secondary
protocol - a day-level logistic regression trained with repeated
StratifiedGroupKFold and averaged per subject - reported 0.7620 +/- 0.0093
but was never audited across the same analysis choices.

This script holds the day-level model fixed and varies the two choices that
ROUND_48 and ROUND_49 showed to matter:

- autocorrelation missing handling:
  * zero: fill undefined lag-1 autocorrelation with 0.0 (ROUND_48 default);
  * mean: fit a SimpleImputer(strategy="mean") inside every CV fold;
  * drop: remove the autocorrelation feature entirely.
- day inclusion:
  * all: all 1,029 complete days;
  * nonzero: exclude all-zero complete days (959 days);
  * min14: keep subjects with at least 14 complete days (51 subjects, 978 days).

Each of the 9 specifications uses 5-fold StratifiedGroupKFold (subjects never
split across folds), repeated 10 times (seeds 42-51), then averages held-out
day probabilities per subject. The pre-registered specification is
`day__zero__all`; it must reproduce ROUND_48's 0.7620 +/- 0.0093 exactly.
The other eight are sensitivity analyses, not candidates to cherry-pick.

This remains a same-cohort retrospective analysis of 55 clinical subjects. It
is not external validation, not a general-population or consumer-wearable
result, and not a production model replacement.

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/modeling/eval/v1_50/01_protocol_robustness.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[3]
PROJECT_ROOT = BACKEND.parent

R48_SCRIPT = HERE.parent / "v1_48" / "01_real_actigraphy_baseline.py"
R48_JSON = HERE.parent / "v1_48" / "real_actigraphy_baseline.json"
R49_JSON = HERE.parent / "v1_49" / "robustness_audit.json"

OUT_JSON = HERE / "protocol_robustness.json"
OUT_CSV = HERE / "protocol_specification_curve.csv"
OUT_MIRROR = PROJECT_ROOT / "outputs" / "candidates" / "round50" / "protocol_robustness.json"
OUT_REPORT = PROJECT_ROOT / "docs" / "model-evaluation" / "REAL_BASELINE_PROTOCOL_ROBUSTNESS.md"

PRIMARY_FEATURES = [
    "mean_act",
    "std_act",
    "peak_activity",
    "autocorrelation_act",
]
NO_AUTOCORR_FEATURES = PRIMARY_FEATURES[:-1]

SEED = 42
N_SPLITS = 5
N_REPEATS = 10
BOOTSTRAP_B = 2000
MIN_DAYS = 14
AUTOCORR_MODES = ("zero", "mean", "drop")
DAY_MODES = ("all", "nonzero", "min14")
LOSO_AUTOCORR_MAP = {"zero": "zero", "mean": "nanmean", "drop": "drop"}
PREREGISTERED_SPEC = "day__zero__all"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R48 = _load_module("round48_real_actigraphy_baseline", R48_SCRIPT)
R48_PAYLOAD = json.loads(R48_JSON.read_text(encoding="utf-8"))
R49_PAYLOAD = json.loads(R49_JSON.read_text(encoding="utf-8"))


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


def _fit_predict(X_train, y_train, X_test, autocorr_mode: str) -> np.ndarray:
    steps = []
    if autocorr_mode == "mean":
        steps.append(SimpleImputer(strategy="mean"))
    steps.extend(
        [
            StandardScaler(),
            LogisticRegression(C=1.0, max_iter=2000, solver="lbfgs"),
        ]
    )
    model = make_pipeline(*steps)
    model.fit(X_train, y_train)
    return model.predict_proba(X_test)[:, 1]


def _subject_pooled(
    subject_predictions: dict[str, list[float]],
) -> pd.DataFrame:
    pooled = pd.DataFrame(
        [(subject, float(np.mean(values))) for subject, values in subject_predictions.items()],
        columns=["subject", "p"],
    ).sort_values("subject")
    pooled["label"] = pooled["subject"].str.startswith("condition_").astype(int)
    return pooled


def repeated_grouped_cv(
    X,
    y,
    groups,
    autocorr_mode: str,
    repeats: int = N_REPEATS,
) -> dict:
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
            oof[test_idx] = _fit_predict(
                X[train_idx],
                y[train_idx],
                X[test_idx],
                autocorr_mode,
            )
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

    subject_pooled = _subject_pooled(subject_predictions)
    if len(subject_pooled) != len(set(groups)):
        raise AssertionError("subject aggregation lost a subject")
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
        "subject_metrics_pooled": R48.metrics(subject_pooled["label"], subject_pooled["p"]),
        "subject_bootstrap": R48.bootstrap_subject_metrics(
            subject_pooled["label"],
            subject_pooled["p"],
            b=BOOTSTRAP_B,
        ),
        "subject_pooled": subject_pooled,
        "per_repeat_day_auc": day_aucs,
        "per_repeat_subject_auc": subject_aucs,
    }


def subset_days(frame: pd.DataFrame, day_mode: str) -> tuple[pd.DataFrame, int]:
    if day_mode == "all":
        return frame.copy(), 0
    if day_mode == "nonzero":
        return frame[~frame["all_zero"]].copy(), 0
    if day_mode == "min14":
        counts = frame.groupby("subject").size()
        keep = set(counts[counts >= MIN_DAYS].index)
        subset = frame[frame["subject"].isin(keep)].copy()
        dropped = int(frame["subject"].nunique() - subset["subject"].nunique())
        return subset, dropped
    raise ValueError(day_mode)


def run_spec(frame: pd.DataFrame, autocorr_mode: str, day_mode: str) -> dict:
    subset, dropped = subset_days(frame, day_mode)
    features = NO_AUTOCORR_FEATURES if autocorr_mode == "drop" else PRIMARY_FEATURES
    if autocorr_mode in ("zero", "drop"):
        X = subset[features].fillna(0.0).to_numpy(dtype=float)
    else:
        X = subset[features].to_numpy(dtype=float)
    y = subset["label"].to_numpy(dtype=int)
    groups = subset["subject"].to_numpy()

    result = repeated_grouped_cv(X, y, groups, autocorr_mode)
    result.pop("subject_pooled")
    result.pop("per_repeat_day_auc")
    result.pop("per_repeat_subject_auc")

    loso_id = f"mean__{LOSO_AUTOCORR_MAP[autocorr_mode]}__{day_mode}"
    loso_auc = next(row["auc"] for row in R49_PAYLOAD["results"]["specification_curve"] if row["spec_id"] == loso_id)
    pooled = result["subject_metrics_pooled"]
    return {
        "spec_id": f"day__{autocorr_mode}__{day_mode}",
        "autocorr_mode": autocorr_mode,
        "day_mode": day_mode,
        "features": features,
        "n_features": len(features),
        "n_subjects": int(subset["subject"].nunique()),
        "n_subjects_dropped": dropped,
        "n_days": int(len(subset)),
        "n_positive_days": int(subset["label"].sum()),
        "n_zero_days": int(subset["all_zero"].sum()),
        "n_missing_autocorr": int(subset["autocorrelation_act"].isna().sum()),
        "subject_auc_mean": result["subject_auc_mean"],
        "subject_auc_sd": result["subject_auc_sd"],
        "subject_auc_range": result["subject_auc_range"],
        "pooled_auc": pooled["auc"],
        "pooled_auc_ci": result["subject_bootstrap"]["auc_95ci"],
        "pooled_auprc": pooled["auprc"],
        "pooled_brier": pooled["brier"],
        "calibration_slope": pooled["calibration_slope"],
        "day_auc_mean": result["day_auc_mean"],
        "day_auc_sd": result["day_auc_sd"],
        "day_auc_pooled": result["day_auc_pooled"],
        "day_auprc_mean": result["day_auprc_mean"],
        "day_brier_mean": result["day_brier_mean"],
        "subject_level_loso_spec_id": loso_id,
        "subject_level_loso_auc": loso_auc,
        "delta_vs_loso": result["subject_auc_mean"] - loso_auc,
    }


def summarize(rows: list[dict]) -> dict:
    by_id = {row["spec_id"]: row for row in rows}
    aucs = [row["subject_auc_mean"] for row in rows]
    best = max(rows, key=lambda row: row["subject_auc_mean"])
    worst = min(rows, key=lambda row: row["subject_auc_mean"])
    prereg = by_id[PREREGISTERED_SPEC]
    ranked = sorted(rows, key=lambda row: row["subject_auc_mean"], reverse=True)
    prereg_rank = next(index for index, row in enumerate(ranked, start=1) if row["spec_id"] == PREREGISTERED_SPEC)

    def factor_summary(key: str, values: tuple[str, ...]) -> dict:
        out = {}
        for value in values:
            subset = [row for row in rows if row[key] == value]
            out[value] = {
                "n_specs": len(subset),
                "auc_mean": float(np.mean([row["subject_auc_mean"] for row in subset])),
                "auc_min": float(min(row["subject_auc_mean"] for row in subset)),
                "auc_max": float(max(row["subject_auc_mean"] for row in subset)),
            }
        return out

    deltas = [row["delta_vs_loso"] for row in rows]
    return {
        "n_specs": len(rows),
        "auc_min": float(min(aucs)),
        "auc_median": float(np.median(aucs)),
        "auc_max": float(max(aucs)),
        "auc_range": float(max(aucs) - min(aucs)),
        "ci_lower_gt_0_5": sum(row["pooled_auc_ci"][0] > 0.5 for row in rows),
        "ci_covers_0_5": sum(row["pooled_auc_ci"][0] <= 0.5 <= row["pooled_auc_ci"][1] for row in rows),
        "auc_ge_0_65": sum(value >= 0.65 for value in aucs),
        "auc_ge_0_70": sum(value >= 0.70 for value in aucs),
        "best_spec": best["spec_id"],
        "best_spec_auc": best["subject_auc_mean"],
        "worst_spec": worst["spec_id"],
        "worst_spec_auc": worst["subject_auc_mean"],
        "preregistered_spec": PREREGISTERED_SPEC,
        "preregistered_auc": prereg["subject_auc_mean"],
        "preregistered_rank": prereg_rank,
        "preregistered_is_best": prereg["spec_id"] == best["spec_id"],
        "preregistered_is_worst": prereg["spec_id"] == worst["spec_id"],
        "by_autocorr_mode": factor_summary("autocorr_mode", AUTOCORR_MODES),
        "by_day_mode": factor_summary("day_mode", DAY_MODES),
        "loso_comparison": {
            "loso_auc_min": float(min(row["subject_level_loso_auc"] for row in rows)),
            "loso_auc_median": float(np.median([row["subject_level_loso_auc"] for row in rows])),
            "loso_auc_max": float(max(row["subject_level_loso_auc"] for row in rows)),
            "delta_min": float(min(deltas)),
            "delta_median": float(np.median(deltas)),
            "delta_max": float(max(deltas)),
            "n_day_level_above_loso": sum(delta > 0 for delta in deltas),
            "n_specs": len(deltas),
        },
    }


def reproduction_anchors(rows: list[dict]) -> dict:
    by_id = {row["spec_id"]: row for row in rows}
    secondary = R48_PAYLOAD["results"]["secondary_grouped_multiday_4feat"]
    nonzero = R48_PAYLOAD["results"]["sensitivity_excluding_zero_days"]
    min14 = R48_PAYLOAD["results"]["sensitivity_min_14_days"]

    anchors = {
        "day__zero__all": {
            "round48_key": "secondary_grouped_multiday_4feat",
            "round48_subject_auc_mean": secondary["subject_auc_mean"],
            "round48_subject_auc_sd": secondary["subject_auc_sd"],
            "round48_pooled_auc": secondary["subject_metrics_pooled"]["auc"],
            "round50_subject_auc_mean": by_id["day__zero__all"]["subject_auc_mean"],
            "round50_subject_auc_sd": by_id["day__zero__all"]["subject_auc_sd"],
            "round50_pooled_auc": by_id["day__zero__all"]["pooled_auc"],
        },
        "day__zero__nonzero": {
            "round48_key": "sensitivity_excluding_zero_days",
            "round48_subject_auc_mean": nonzero["subject_auc_mean"],
            "round48_subject_auc_sd": nonzero["subject_auc_sd"],
            "round48_pooled_auc": nonzero["subject_metrics_pooled"]["auc"],
            "round50_subject_auc_mean": by_id["day__zero__nonzero"]["subject_auc_mean"],
            "round50_subject_auc_sd": by_id["day__zero__nonzero"]["subject_auc_sd"],
            "round50_pooled_auc": by_id["day__zero__nonzero"]["pooled_auc"],
        },
        "day__zero__min14": {
            "round48_key": "sensitivity_min_14_days",
            "round48_subject_auc_mean": min14["subject_auc_mean"],
            "round48_subject_auc_sd": min14["subject_auc_sd"],
            "round48_pooled_auc": min14["subject_metrics_pooled"]["auc"],
            "round50_subject_auc_mean": by_id["day__zero__min14"]["subject_auc_mean"],
            "round50_subject_auc_sd": by_id["day__zero__min14"]["subject_auc_sd"],
            "round50_pooled_auc": by_id["day__zero__min14"]["pooled_auc"],
        },
    }

    tolerances = {
        "subject_auc_mean": 1e-12,
        "subject_auc_sd": 1e-12,
        "pooled_auc": 1e-12,
    }
    for spec_id, anchor in anchors.items():
        anchor["checks"] = {}
        for metric, tolerance in tolerances.items():
            expected = anchor[f"round48_{metric}"]
            actual = anchor[f"round50_{metric}"]
            delta = abs(actual - expected)
            anchor["checks"][metric] = {
                "expected": expected,
                "actual": actual,
                "abs_delta": delta,
                "tolerance": tolerance,
                "passed": bool(delta <= tolerance),
            }
        anchor["all_passed"] = bool(all(check["passed"] for check in anchor["checks"].values()))
    if not all(anchor["all_passed"] for anchor in anchors.values()):
        raise AssertionError("ROUND_48 reproduction anchor failed")

    anchors["day__zero__nonzero"]["round48_n_days"] = nonzero["n_days"]
    anchors["day__zero__nonzero"]["round50_n_days"] = by_id["day__zero__nonzero"]["n_days"]
    anchors["day__zero__min14"]["round48_n_days"] = min14["n_days"]
    anchors["day__zero__min14"]["round50_n_days"] = by_id["day__zero__min14"]["n_days"]
    anchors["day__zero__min14"]["round48_n_subjects"] = min14["n_subjects"]
    anchors["day__zero__min14"]["round50_n_subjects"] = by_id["day__zero__min14"]["n_subjects"]
    return anchors


def render_report(payload: dict) -> str:
    dataset = payload["dataset"]
    summary = payload["results"]["specification_summary"]
    rows = payload["results"]["specification_curve"]
    anchors = payload["results"]["reproduction_anchors"]
    loso = summary["loso_comparison"]
    pre_anchor = anchors["day__zero__all"]
    by_spec = {row["spec_id"]: row for row in rows}

    lines = [
        "# 真实 actigraphy 多日聚合口径的规范稳健性（ROUND_50）",
        "",
        "> **证据边界（先读）**：本报告仍是 Depresjon 同一队列（55 名受试者、",
        "> 临床 actigraphy、condition/control 标签）的回顾性分析，不是外部验证，",
        "> 不是普通人群或消费级设备结果，也不改变生产模型、阈值或路由。",
        "> 日级多日聚合与受试者级 LOSO 回答的是不同问题，二者的 AUC 不可当作",
        "> 同一个估计量的两个读数来互相替代。",
        "",
        "## 0. 结论先行",
        "",
        "ROUND_48 的次口径「日级模型 + 重复分组 CV + 受试者内平均」报告",
        f"**{pre_anchor['round48_subject_auc_mean']:.4f} ± "
        f"{pre_anchor['round48_subject_auc_sd']:.4f}**。本报告固定该协议，",
        "只改变自相关缺失处理与日纳入规则，得到 9 个规范：",
        "",
        f"1. **预注册规范 `{PREREGISTERED_SPEC}` 精确复现 ROUND_48**：",
        f"受试者级 AUC 均值 {pre_anchor['round50_subject_auc_mean']:.4f} ± "
        f"{pre_anchor['round50_subject_auc_sd']:.4f}，池化 AUC "
        f"{pre_anchor['round50_pooled_auc']:.4f}，与 ROUND_48 的逐位一致",
        "（差值 < 1e-12）。另外两个零填充规范也精确复现 ROUND_48 的",
        "零活动日剔除与 min14 敏感性读数。",
        f"2. **9 个规范的受试者级 AUC 为 {summary['auc_min']:.4f}–"
        f"{summary['auc_max']:.4f}（中位 {summary['auc_median']:.4f}，"
        f"极差 {summary['auc_range']:.4f}）**。预注册规范排名第 "
        f"{summary['preregistered_rank']}/9；"
        + (
            "它恰好是网格最大值。预注册发生在看结果之前，所以这不是事后"
            "挑选；但把 0.7620 单独引用为「该协议的性能」，在效果上等同于"
            "只报告 9 个可辩护规范中的最大值。"
            if summary["preregistered_is_best"]
            else "它不是网格上端，更说明不能把 0.7620 当作稳健点估计。"
        ),
        f"3. **最差规范是 `{summary['worst_spec']}`（"
        f"{summary['worst_spec_auc']:.4f}），与预注册规范相差 "
        f"{summary['preregistered_auc'] - summary['worst_spec_auc']:.4f}**。",
        "汇总差异更大的是日纳入规则：保留全部日、剔除零活动日、限制 ≥14 天",
        "会把同一个日级协议拉到不同的性能区间。",
        f"4. **与受试者级 LOSO 的同因子对照**：9 对配对中，日级口径有 "
        f"{loso['n_day_level_above_loso']}/9 对高于受试者级 LOSO；",
        f"配对差值 {loso['delta_min']:+.4f} 到 {loso['delta_max']:+.4f}"
        f"（中位 {loso['delta_median']:+.4f}）。"
        + (
            "日级口径在全部 9 对中都更高，但差值本身从最小到最大相差约 "
            f"{loso['delta_max'] - loso['delta_min']:.4f}，说明协议差异的"
            "量级并不稳定。"
            if loso["n_day_level_above_loso"] == loso["n_specs"]
            else "日级口径并非在所有规范下都优于受试者级口径，且两者的差值本身随规范变化。"
        ),
        f"5. **9 个规范中只有 {summary['ci_lower_gt_0_5']}/9 的池化 AUC "
        "95% CI 下界严格大于 0.5；最差规范 "
        f"`{summary['worst_spec']}` 的下界为 "
        f"{min(row['pooled_auc_ci'][0] for row in rows):.4f}，不能排除"
        "「与随机排序无法区分」。",
        "6. **校准斜率在 "
        f"{min(row['calibration_slope'] for row in rows):.2f}–"
        f"{max(row['calibration_slope'] for row in rows):.2f}**，全部远高于 1；"
        "日级池化分数明显过度自信，不能当作临床概率使用。",
        "7. **结论**：0.7620 是**预注册规范的精确读数**，也是 9 规范网格的"
        "最大值；它不是跨规范稳健的性能估计。引用它时必须同时给出 9 规范"
        "范围、日级与受试者级两个协议的区别，以及校准/CI 的限制；",
        "不得事后挑选网格最大值作为性能估计。",
        "",
        "## 1. 数据与设计",
        "",
        "### 1.1 数据",
        "",
        f"- 原始数据：`{dataset['raw_zip']}`（SHA-256 `{dataset['raw_zip_sha256']}`）。",
        f"- {dataset['n_subjects']} 名受试者（"
        f"{dataset['n_condition_subjects']} 例 condition / "
        f"{dataset['n_control_subjects']} 例 control），"
        f"{dataset['n_complete_days']} 个完整 1440 分钟日，"
        f"{dataset['n_partial_days_excluded']} 个不完整日已排除。",
        f"- 阳性日 {dataset['positive_days']}（日阳性率 "
        f"{dataset['day_prevalence']:.4f}）；全零完整日 "
        f"{dataset['n_all_zero_complete_days']}。",
        f"- 自相关在常数日上无定义：{dataset['n_missing_autocorr']} 个日缺失"
        f"（{dataset['n_all_zero_complete_days']} 个全零日 + "
        f"{dataset['n_missing_autocorr'] - dataset['n_all_zero_complete_days']} 个"
        "常数非零日，后者全部来自 control）。",
        "",
        "### 1.2 日级协议（固定不变）",
        "",
        "每个规范都训练同一个日级 logistic regression：",
        "",
        "- 特征：`mean_act`、`std_act`、`peak_activity`、`autocorrelation_act`",
        "（`drop` 规范去掉自相关，剩 3 个特征）；",
        "- 5 折 `StratifiedGroupKFold`，同一受试者的日绝不跨折；",
        "- 重复 10 次（随机种子 42–51），每次产生一套折外日概率；",
        "- 每个受试者取折外日概率的均值，得到受试者级分数；",
        "- 报告 10 次重复的受试者级 AUC 均值 ± 标准差，以及把 10 次重复的",
        "受试者分数再平均后的池化 AUC 与 2,000 次受试者级 bootstrap CI。",
        "",
        "### 1.3 变化的两个因子",
        "",
        "| 因子 | 取值 | 定义 |",
        "|---|---|---|",
        "| 自相关缺失处理 | `zero` | 未定义自相关填 0.0（ROUND_48 默认） |",
        "|  | `mean` | 在每个 CV 折内用训练日均值拟合 `SimpleImputer` |",
        "|  | `drop` | 完全去掉自相关特征（4→3 个特征） |",
        "| 日纳入 | `all` | 全部 1,029 个完整日 |",
        "|  | `nonzero` | 剔除 70 个全零完整日（959 日） |",
        "|  | `min14` | 仅保留至少 14 个完整日的受试者（51 人，978 日） |",
        "",
        "`mean` 的插补器只在训练折上拟合，避免测试折信息进入预处理。",
        "`min14` 的受试者筛选基于完整日计数，与 ROUND_48/49 的定义一致。",
        "",
        "## 2. 九个规范的结果",
        "",
        "| 规范 | 受试者 | 日 | 零活动日 | 自相关缺失 | 受试者 AUC（均值±SD） | 池化 AUC [95% CI] | AUPRC | Brier | 校准斜率 | 日 AUC |",
        "|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|",
    ]

    for row in rows:
        ci_low, ci_high = row["pooled_auc_ci"]
        lines.append(
            f"| `{row['spec_id']}` | {row['n_subjects']} | {row['n_days']} | "
            f"{row['n_zero_days']} | {row['n_missing_autocorr']} | "
            f"{row['subject_auc_mean']:.4f} ± "
            f"{row['subject_auc_sd']:.4f} | {row['pooled_auc']:.4f} "
            f"[{ci_low:.4f}, {ci_high:.4f}] | {row['pooled_auprc']:.4f} | "
            f"{row['pooled_brier']:.4f} | {row['calibration_slope']:.4f} | "
            f"{row['day_auc_mean']:.4f} |"
        )

    lines.extend(
        [
            "",
            "> 注：`nonzero` 规范剔除了全部 70 个全零日，但仍保留 8 个常数非零日，",
            "> 因此其自相关缺失数不是 0；`zero` 把这些日填 0，`mean` 在折内插补，",
            "> `drop` 则完全不用自相关。",
            "",
            "> 注：受试者 AUC 的「均值±SD」是 10 次重复之间的波动，不是受试者",
            "> 抽样标准误；池化 AUC 的 CI 是 2,000 次受试者级 bootstrap，二者",
            "> 含义不同，不能混用。9 个规范共享同一批受试者，区间不是独立样本",
            "> 的抽样分布。",
            "",
            "> 日 AUC 与受试者 AUC 也不是同一评价单位：日 AUC 是单日预测的排序",
            "> 性能，受试者 AUC 是把同一受试者的多日概率平均后的排序性能；后者",
            "> 通常更高，因为平均降低了日级噪声。不能把日 AUC 与受试者 AUC 直接",
            "> 比较，也不能用日 AUC 反推受试者级性能。",
            "",
            "### 2.1 因子汇总",
            "",
            "| 自相关处理 | 规范数 | AUC 均值 | 最小 | 最大 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for mode in AUTOCORR_MODES:
        item = summary["by_autocorr_mode"][mode]
        lines.append(
            f"| `{mode}` | {item['n_specs']} | {item['auc_mean']:.4f} | {item['auc_min']:.4f} | {item['auc_max']:.4f} |"
        )
    lines.extend(
        [
            "",
            "| 日纳入 | 规范数 | AUC 均值 | 最小 | 最大 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for mode in DAY_MODES:
        item = summary["by_day_mode"][mode]
        lines.append(
            f"| `{mode}` | {item['n_specs']} | {item['auc_mean']:.4f} | {item['auc_min']:.4f} | {item['auc_max']:.4f} |"
        )
    lines.extend(
        [
            "",
            "自相关处理的影响小于日纳入规则；`mean` 与 `drop` 也不是「更保守」",
            "或「更先进」的自动替代，它们改变的是可用信息与缺失假设，而不是",
            "同一个量的估计精度。`drop` 还会把特征数从 4 改成 3，因此不能把",
            "它与 `zero`/`mean` 的差异单独解释为「自相关特征的效应」。",
            f"零填充的汇总均值最高（{summary['by_autocorr_mode']['zero']['auc_mean']:.4f}），但并非每个",
            "日纳入档位都最高：`all` 与 `min14` 档位是 zero 最高，`nonzero` 档位",
            "是 drop 略高（"
            f"{by_spec['day__drop__nonzero']['subject_auc_mean']:.4f} vs "
            f"{by_spec['day__zero__nonzero']['subject_auc_mean']:.4f}）。这提示"
            "「未定义自相关填 0」可能携带了与零活动日相关的信号，而不只是一个",
            "中性的缺失默认值。",
            "",
            "### 2.2 与 ROUND_48 的复现锚点",
            "",
            "| 规范 | ROUND_48 对应项 | 受试者 AUC（R48） | 受试者 AUC（R50） | 池化 AUC（R48） | 池化 AUC（R50） | 通过 |",
            "|---|---|---:|---:|---:|---:|---|",
            f"| `day__zero__all` | `secondary_grouped_multiday_4feat` | "
            f"{anchors['day__zero__all']['round48_subject_auc_mean']:.6f} | "
            f"{anchors['day__zero__all']['round50_subject_auc_mean']:.6f} | "
            f"{anchors['day__zero__all']['round48_pooled_auc']:.6f} | "
            f"{anchors['day__zero__all']['round50_pooled_auc']:.6f} | 是 |",
            f"| `day__zero__nonzero` | `sensitivity_excluding_zero_days` | "
            f"{anchors['day__zero__nonzero']['round48_subject_auc_mean']:.6f} | "
            f"{anchors['day__zero__nonzero']['round50_subject_auc_mean']:.6f} | "
            f"{anchors['day__zero__nonzero']['round48_pooled_auc']:.6f} | "
            f"{anchors['day__zero__nonzero']['round50_pooled_auc']:.6f} | 是 |",
            f"| `day__zero__min14` | `sensitivity_min_14_days` | "
            f"{anchors['day__zero__min14']['round48_subject_auc_mean']:.6f} | "
            f"{anchors['day__zero__min14']['round50_subject_auc_mean']:.6f} | "
            f"{anchors['day__zero__min14']['round48_pooled_auc']:.6f} | "
            f"{anchors['day__zero__min14']['round50_pooled_auc']:.6f} | 是 |",
            "",
            "三组锚点的逐项绝对差值都小于 1e-12，说明 ROUND_50 没有重新实现",
            "一个「相似」的协议，而是复用了 ROUND_48 的同一套日级数据、折划分、",
            "模型与聚合逻辑。",
            "",
            "## 3. 与受试者级 LOSO 的对照",
            "",
            "ROUND_49 已在受试者级 LOSO 上审计了 18 个规范，并把主口径固定在",
            "`mean__nanmean__all`（0.6454）。本报告把日级 9 个规范与 ROUND_49",
            "中**同自相关处理、同日纳入规则、同 mean 聚合**的受试者级规范配对：",
            "",
            "| 日级规范 | 日级受试者 AUC | 受试者级规范 | 受试者级 AUC | 差值（日级−受试者级） |",
            "|---|---:|---|---:|---:|",
        ]
    )
    for row in rows:
        lines.append(
            f"| `{row['spec_id']}` | {row['subject_auc_mean']:.4f} | "
            f"`{row['subject_level_loso_spec_id']}` | "
            f"{row['subject_level_loso_auc']:.4f} | "
            f"{row['delta_vs_loso']:+.4f} |"
        )
    lines.extend(
        [
            "",
            "配对差值范围 "
            f"{loso['delta_min']:+.4f} 到 {loso['delta_max']:+.4f}，"
            f"中位 {loso['delta_median']:+.4f}；"
            f"{loso['n_day_level_above_loso']}/9 对为正。",
            "",
            "> 配对说明：`zero` 与 `drop` 在日级和受试者级改变的是同一个特征",
            "> 处理；`mean` 只是概念上对应受试者级的 `nanmean`，日级用训练折",
            "> 均值插补、受试者级用受试者内可用日均值，二者不是同一个估计量。",
            "> 因此 `day__mean__*` 的配对差值不能单独解释为「协议效应」。",
            "",
            (
                "日级协议在全部 9 对中都更高"
                if loso["n_day_level_above_loso"] == loso["n_specs"]
                else "日级协议在多数规范下更高"
            )
            + "，但它不是对受试者级估计的「修正」，而是",
            "一个不同的估计量：日级模型用约 1,000 个日样本训练，学到的是日与",
            "标签的关系，再在受试者内平均；受试者级 LOSO 用 54 个受试者均值训练，",
            "直接评价「留一人」的受试者排序。日级模型能利用受试者内部的日分布，",
            "也可能把记录时长、零活动日比例等佩戴/记录特征当作信号。",
            "",
            "因此不能把 0.7620 与 0.6454 的差值解释为「多日聚合带来的真实增益」；",
            "它同时包含协议差异、日纳入选择和佩戴混杂。ROUND_49 已显示，仅佩戴",
            "代理的受试者级 LOSO AUC 为 0.7921，高于日级预注册规范的 0.7620。",
            "",
            "同样不能把日级 9/9 高于受试者级 LOSO 解释为「日级协议已证明更优」：",
            "两个协议都没有见过测试受试者的任何日（分组 CV 已断言受试者不跨折），",
            "但日级模型用约 1,000 个日样本训练，受试者级 LOSO 每折只用 54 个",
            "受试者均值；日级模型有更多训练行，并通过受试者内平均降低日级噪声。",
            "AUC 差异因此不能归因于单一因素；它可能同时反映训练样本量、目标粒度",
            "和评估聚合方式，而不是「日级模型记住了测试受试者」。二者对应不同的",
            "部署问题，不能只看 AUC 高低。",
            "",
            "## 4. 证据边界",
            "",
            "1. **同一队列、回顾性**：55 名受试者全部来自 Depresjon，标签来自",
            "原始目录的 condition/control 分组；没有独立队列、没有前瞻预测。",
            "2. **不是普通人群或消费级设备**：临床 actigraphy 的 1440 分钟日",
            "汇总，不能外推到手机/手表用户或普通成年人。",
            "3. **不是生产替换**：本报告不训练生产模型、不改阈值、不改路由、",
            "不改人群范围；生产生理单元仍是 13 特征合成管线，证据等级不变。",
            "4. **与 0.9451 不可比**：生产生理 AUC 来自标签驱动的合成特征，",
            "本报告是真实 actigraphy 的同队列基线，两者不是同一数据生成过程。",
            "5. **佩戴/记录混杂仍成立**：ROUND_49 发现病例完整日更少",
            "（15.6 vs 20.9）、活跃日更少；仅用零活动日比例、活动分钟、活跃天数",
            "的代理模型 LOSO AUC 为 0.7921。本报告的日纳入因子会放大或缩小这一",
            "混杂，不能把 9 规范中的较高值当作「真实生理信号」。",
            "6. **校准只作描述**：9 个规范的池化校准斜率为 "
            f"{min(row['calibration_slope'] for row in rows):.2f}–"
            f"{max(row['calibration_slope'] for row in rows):.2f}，全部远高于 1，"
            "说明池化分数明显过度自信。样本只有 55 人，校准斜率不足以形成",
            "临床校准结论，也不能把日级分数当作临床概率使用。",
            "",
            "## 5. 复现",
            "",
            "```bash",
            "cd backend",
            ".venv/Scripts/python.exe scripts/modeling/eval/v1_50/01_protocol_robustness.py",
            "```",
            "",
            "输入与产物：",
            "",
            f"- ROUND_48 脚本：`{payload['input']['round48_script']}`（SHA-256 "
            f"`{payload['input']['round48_script_sha256']}`）。",
            f"- ROUND_48 结果：`{payload['input']['round48_json']}`（SHA-256 "
            f"`{payload['input']['round48_json_sha256']}`）。",
            f"- ROUND_49 结果：`{payload['input']['round49_json']}`（SHA-256 "
            f"`{payload['input']['round49_json_sha256']}`）。",
            f"- 本报告 JSON：`{payload['artifacts']['protocol_robustness_json']}`。",
            f"- 本报告 CSV：`{payload['artifacts']['protocol_specification_curve_csv']}`"
            f"（SHA-256 `{payload['artifacts']['protocol_specification_curve_sha256']}`）。",
            f"- 镜像：`{payload['artifacts']['mirror']}`。",
            "",
            "## 6. Phase 1 的含义",
            "",
            "1. 外部成人/临床队列到位后，日级与受试者级两个协议都应预先注册，",
            "并同时报告；不得只报告较高的那个。",
            "2. 日纳入规则（全部日 / 剔除零活动日 / 最少天数）和自相关缺失处理",
            f"必须在看见结果前固定；否则同一份数据可以产生约 {summary['auc_range']:.2f} 的 AUC 摆动。",
            "3. 外部队列必须提供佩戴/记录元数据（有效佩戴时长、零活动日、",
            "设备型号），否则无法区分生理信号与佩戴行为。",
            "4. 本报告的 9 个规范只用于描述敏感性，不构成模型选择依据；",
            "生产模型、阈值、路由和证据等级均不因本报告改变。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    if not R48_JSON.exists():
        raise SystemExit(f"ROUND_48 result not found: {R48_JSON}")
    if not R49_JSON.exists():
        raise SystemExit(f"ROUND_49 result not found: {R49_JSON}")

    frame, _scores, partial_days = R48.load_days()
    if len(frame) != 1029:
        raise AssertionError(f"expected 1029 complete days, got {len(frame)}")
    if frame["subject"].nunique() != 55:
        raise AssertionError("expected 55 subjects")
    if int(frame["label"].sum()) != 359:
        raise AssertionError("expected 359 positive days")

    rows = [run_spec(frame, autocorr_mode, day_mode) for autocorr_mode in AUTOCORR_MODES for day_mode in DAY_MODES]
    if len(rows) != 9:
        raise AssertionError("expected 9 day-level specifications")
    by_id = {row["spec_id"]: row for row in rows}
    if by_id[PREREGISTERED_SPEC]["n_days"] != 1029:
        raise AssertionError("pre-registered specification lost days")
    if by_id["day__zero__nonzero"]["n_days"] != 959:
        raise AssertionError("nonzero specification lost the wrong number of days")
    if by_id["day__zero__min14"]["n_subjects"] != 51:
        raise AssertionError("min14 specification lost the wrong subjects")

    anchors = reproduction_anchors(rows)
    summary = summarize(rows)

    dataset = {
        "raw_zip": str(R48.RAW_ZIP.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "raw_zip_sha256": _sha256(R48.RAW_ZIP),
        "n_subjects": int(frame["subject"].nunique()),
        "n_condition_subjects": int(R48_PAYLOAD["dataset"]["n_condition_subjects"]),
        "n_control_subjects": int(R48_PAYLOAD["dataset"]["n_control_subjects"]),
        "n_complete_days": int(len(frame)),
        "n_partial_days_excluded": int(partial_days),
        "n_all_zero_complete_days": int(frame["all_zero"].sum()),
        "positive_days": int(frame["label"].sum()),
        "day_prevalence": float(frame["label"].mean()),
        "n_missing_autocorr": int(frame["autocorrelation_act"].isna().sum()),
        "label_source": "raw file directory: data/condition/* vs data/control/*",
        "evaluation_type": "same-cohort retrospective baseline; not external validation",
    }

    design = {
        "protocol": (
            "Day-level logistic regression with 5-fold StratifiedGroupKFold "
            "(subjects never split across folds), repeated 10 times with seeds "
            "42-51; held-out day probabilities averaged per subject."
        ),
        "autocorr_zero": "Fill undefined lag-1 autocorrelation with 0.0.",
        "autocorr_mean": ("SimpleImputer(strategy='mean') fit on training days inside every CV fold."),
        "autocorr_drop": "Remove autocorrelation_act; 3 features.",
        "day_all": "All 1,029 complete days.",
        "day_nonzero": "Exclude 70 all-zero complete days; 959 days.",
        "day_min14": ("Keep subjects with at least 14 complete days; 51 subjects, 978 days."),
        "bootstrap": f"{BOOTSTRAP_B} subject-level resamples, seed {SEED}",
        "preregistered_spec": PREREGISTERED_SPEC,
        "preregistration_note": (
            "day__zero__all is the ROUND_48 secondary protocol. The other eight "
            "specifications are sensitivity analyses and must not be used to "
            "select the maximum AUC as a performance estimate."
        ),
    }

    sanity_checks = {
        "n_subjects_55": bool(frame["subject"].nunique() == 55),
        "n_complete_days_1029": bool(len(frame) == 1029),
        "positive_days_359": bool(int(frame["label"].sum()) == 359),
        "n_specs_9": bool(len(rows) == 9),
        "all_spec_aucs_finite": bool(all(math.isfinite(row["subject_auc_mean"]) for row in rows)),
        "all_reproduction_anchors_passed": bool(all(anchor["all_passed"] for anchor in anchors.values())),
        "csv_sha256": "",
    }

    payload = {
        "round": "ROUND_50",
        "status": "descriptive_offline_protocol_robustness_not_production",
        "external_validation": False,
        "production_changed": False,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input": {
            "round48_script": R48_SCRIPT.relative_to(PROJECT_ROOT).as_posix(),
            "round48_script_sha256": _sha256(R48_SCRIPT),
            "round48_json": R48_JSON.relative_to(PROJECT_ROOT).as_posix(),
            "round48_json_sha256": _sha256(R48_JSON),
            "round49_json": R49_JSON.relative_to(PROJECT_ROOT).as_posix(),
            "round49_json_sha256": _sha256(R49_JSON),
        },
        "dataset": dataset,
        "design": design,
        "results": {
            "specification_curve": rows,
            "specification_summary": summary,
            "reproduction_anchors": anchors,
        },
        "interpretation": {
            "verdict": (
                "The pre-registered day-level specification reproduces ROUND_48 "
                "exactly, but the 9-specification range shows that 0.7620 is the "
                "top of the grid, not a robust protocol estimate. Day inclusion "
                "is the dominant specification factor. "
                + (
                    "The day-level protocol is higher than subject-level LOSO in "
                    f"all {summary['loso_comparison']['n_day_level_above_loso']} "
                    "matched pairs, but the gap ranges from "
                    f"{summary['loso_comparison']['delta_min']:+.4f} to "
                    f"{summary['loso_comparison']['delta_max']:+.4f}, so its "
                    "magnitude is not stable."
                    if summary["loso_comparison"]["n_day_level_above_loso"] == summary["loso_comparison"]["n_specs"]
                    else "The day-level protocol is not uniformly higher than subject-level LOSO."
                )
            ),
            "calibration_warning": (
                "Pooled subject calibration slopes range from "
                f"{min(row['calibration_slope'] for row in rows):.4f} to "
                f"{max(row['calibration_slope'] for row in rows):.4f}; the scores "
                "are strongly overconfident and are not clinical probabilities."
            ),
            "allowed_claims": [
                "On Depresjon, the pre-registered day-level grouped-CV protocol reproduces 0.7620 +/- 0.0093 exactly.",
                "Across 9 defensible day-level specifications, the subject-level "
                "AUC range is reported in full; the range describes analysis "
                "choice sensitivity, not sampling variability.",
                "The day-level protocol and the subject-level LOSO protocol answer "
                "different questions and must both be reported.",
            ],
            "forbidden_claims": [
                "0.7620 is a robust performance estimate for real actigraphy.",
                "The highest specification in the 9-spec grid is the model's performance.",
                "The day-level protocol is externally validated or ready for production.",
                "These numbers apply to consumer wearables, general adults, or clinical diagnosis.",
                "These numbers can be compared directly with the synthetic-feature production AUC 0.9451.",
            ],
        },
        "sanity_checks": sanity_checks,
        "artifacts": {
            "protocol_robustness_json": OUT_JSON.relative_to(PROJECT_ROOT).as_posix(),
            "protocol_specification_curve_csv": OUT_CSV.relative_to(PROJECT_ROOT).as_posix(),
            "mirror": OUT_MIRROR.relative_to(PROJECT_ROOT).as_posix(),
            "report": OUT_REPORT.relative_to(PROJECT_ROOT).as_posix(),
        },
    }

    csv_rows = []
    for row in rows:
        csv_rows.append(
            {
                "spec_id": row["spec_id"],
                "autocorr_mode": row["autocorr_mode"],
                "day_mode": row["day_mode"],
                "n_features": row["n_features"],
                "n_subjects": row["n_subjects"],
                "n_subjects_dropped": row["n_subjects_dropped"],
                "n_days": row["n_days"],
                "n_positive_days": row["n_positive_days"],
                "n_zero_days": row["n_zero_days"],
                "n_missing_autocorr": row["n_missing_autocorr"],
                "subject_auc_mean": row["subject_auc_mean"],
                "subject_auc_sd": row["subject_auc_sd"],
                "subject_auc_min": row["subject_auc_range"][0],
                "subject_auc_max": row["subject_auc_range"][1],
                "pooled_auc": row["pooled_auc"],
                "pooled_auc_ci_lower": row["pooled_auc_ci"][0],
                "pooled_auc_ci_upper": row["pooled_auc_ci"][1],
                "pooled_auprc": row["pooled_auprc"],
                "pooled_brier": row["pooled_brier"],
                "calibration_slope": row["calibration_slope"],
                "day_auc_mean": row["day_auc_mean"],
                "day_auc_sd": row["day_auc_sd"],
                "day_auc_pooled": row["day_auc_pooled"],
                "day_auprc_mean": row["day_auprc_mean"],
                "day_brier_mean": row["day_brier_mean"],
                "subject_level_loso_spec_id": row["subject_level_loso_spec_id"],
                "subject_level_loso_auc": row["subject_level_loso_auc"],
                "delta_vs_loso": row["delta_vs_loso"],
            }
        )
    pd.DataFrame(csv_rows).to_csv(OUT_CSV, index=False)
    csv_sha = _sha256(OUT_CSV)
    sanity_checks["csv_sha256"] = csv_sha
    payload["artifacts"]["protocol_specification_curve_sha256"] = csv_sha

    payload = _finite(payload)
    text = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False)
    OUT_JSON.write_text(text, encoding="utf-8")
    OUT_MIRROR.parent.mkdir(parents=True, exist_ok=True)
    OUT_MIRROR.write_text(text, encoding="utf-8")
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text(render_report(payload), encoding="utf-8")

    print("[protocol_robustness]")
    print(
        f"  subjects={dataset['n_subjects']} days={dataset['n_complete_days']} "
        f"positives={dataset['positive_days']} "
        f"zero_days={dataset['n_all_zero_complete_days']}"
    )
    print(
        f"  pre-registered {PREREGISTERED_SPEC}: "
        f"subjectAUC={by_id[PREREGISTERED_SPEC]['subject_auc_mean']:.4f}"
        f"±{by_id[PREREGISTERED_SPEC]['subject_auc_sd']:.4f} "
        f"pooled={by_id[PREREGISTERED_SPEC]['pooled_auc']:.4f}"
    )
    print(
        f"  9-spec subjectAUC range={summary['auc_min']:.4f}-"
        f"{summary['auc_max']:.4f} median={summary['auc_median']:.4f} "
        f"best={summary['best_spec']} worst={summary['worst_spec']}"
    )
    loso = summary["loso_comparison"]
    print(
        "  day-level vs LOSO pairs: "
        f"{loso['n_day_level_above_loso']}/9 above, delta "
        f"{loso['delta_min']:+.4f}..{loso['delta_max']:+.4f}"
    )
    print(f"  -> {OUT_JSON.relative_to(PROJECT_ROOT)}")
    print(f"  -> {OUT_CSV.relative_to(PROJECT_ROOT)}")
    print(f"  -> {OUT_REPORT.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
