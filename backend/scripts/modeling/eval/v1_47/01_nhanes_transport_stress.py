#!/usr/bin/env python
"""ROUND_47: NHANES 2017-2018 physiological transport stress test.

Read-only evaluation. No production artifact, threshold, runtime contract, or
model is modified.

This is a **stress test, not external validation**:

- the training label is Depresjon's clinical condition/control split, while
  NHANES uses PHQ-9 total >= 10;
- 5/7 training raw features are label-driven synthetic values, `sleep_quality`
  is a binary "ever sought care" proxy, and exercise is self-reported GPAQ;
- NHANES 2017-2018 has no accelerometer step count, so production defaults
  `steps` to 5000;
- NHANES complex sampling weights (WTMEC2YR) are not applied.

The output is descriptive: it quantifies what happens when the deployed MLP is
fed this cohort. It cannot be used to claim transport performance.

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/modeling/eval/v1_47/01_nhanes_transport_stress.py
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[3]
PROJECT_ROOT = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.ml.data_cleaner import DataCleaner  # noqa: E402
from app.ml.feature_engineering import engineer_features  # noqa: E402
from app.ml.model_loader import (  # noqa: E402
    load_cleaner,
    load_feature_names,
    load_model,
    load_scaler,
)

DATA = PROJECT_ROOT / "data" / "external" / "nhanes" / "nhanes_physiological.csv"
MANIFEST = PROJECT_ROOT / "data" / "external" / "nhanes" / "nhanes_manifest.json"
ARTIFACT_DIR = BACKEND / "models" / "artifacts" / "physiological_optimized"
OUT_JSON = HERE / "nhanes_transport_stress.json"
OUT_MIRROR = PROJECT_ROOT / "outputs" / "candidates" / "round47" / "nhanes_transport_stress.json"
OUT_REPORT = PROJECT_ROOT / "docs" / "model-evaluation" / "NHANES_TRANSPORT_STRESS.md"

FEATURES = [
    "sleep_hours",
    "sleep_quality",
    "exercise_minutes",
    "heart_rate",
    "systolic_bp",
    "diastolic_bp",
    "steps",
]
NHANES_FEATURES = FEATURES[:-1]

# Production defaults from _predict_physiological_sync: absent keys fall back
# to these values; NHANES nulls would be rejected by the HTTP schema.
DEFAULTS = {
    "sleep_hours": 7.0,
    "sleep_quality": 5.0,
    "exercise_minutes": 30.0,
    "heart_rate": 70.0,
    "systolic_bp": 120.0,
    "diastolic_bp": 80.0,
    "steps": 5000.0,
}
CUTS = [0.35, 0.50, 0.55, 0.75, 0.90]
BOOTSTRAP_B = 2000
RANDOM_SEED = 42


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonable(value):
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _load_artifacts():
    return {
        "model": load_model(),
        "scaler": load_scaler(),
        "features": load_feature_names(),
        "cleaner": load_cleaner(),
    }


def _load_cohort() -> pd.DataFrame:
    df = pd.read_csv(DATA)
    required = set(FEATURES) | {"depression_label", "phq9_total", "age", "gender"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise AssertionError(f"NHANES CSV 缺少列: {missing}")

    labelled = df[df["depression_label"].notna()].copy()
    labelled["depression_label"] = labelled["depression_label"].astype(int)
    if not set(labelled["depression_label"].unique()) <= {0, 1}:
        raise AssertionError("depression_label 不是二值")
    return labelled


def _build_raw(df: pd.DataFrame, steps_value: float, complete_case: bool) -> pd.DataFrame:
    raw = df[list(FEATURES)].copy()
    if complete_case:
        raw = raw.dropna(subset=NHANES_FEATURES)
    for col in NHANES_FEATURES:
        raw[col] = raw[col].fillna(DEFAULTS[col])
    raw["steps"] = float(steps_value)
    return raw


def _score_batch(artifacts, raw: pd.DataFrame) -> np.ndarray:
    cleaned = artifacts["cleaner"].transform(raw[FEATURES])
    if len(cleaned) != len(raw):
        raise AssertionError("cleaner 丢弃了样本；本评估输入无缺失，不应发生")
    engineered = engineer_features(cleaned)
    matrix = engineered[artifacts["features"]].to_numpy(dtype=np.float32)
    scaled = artifacts["scaler"].transform(matrix)
    return np.asarray(artifacts["model"].predict_proba(scaled), dtype=float).reshape(-1)


def _production_single(artifacts, row: pd.Series, steps_value: float) -> float:
    data = {
        col: float(row[col])
        for col in NHANES_FEATURES
        if pd.notna(row[col])
    }
    data["steps"] = float(steps_value)
    raw_data = {col: float(data.get(col, DEFAULTS[col])) for col in FEATURES}
    cleaned = artifacts["cleaner"].transform_single(raw_data)
    engineered = engineer_features(pd.DataFrame([cleaned]))
    matrix = np.array(
        [[engineered.iloc[0][f] for f in artifacts["features"]]], dtype=np.float32
    )
    return float(
        np.asarray(artifacts["model"].predict_proba(artifacts["scaler"].transform(matrix)))
        .reshape(-1)[0]
    )


def _confusion(y: np.ndarray, p: np.ndarray, threshold: float) -> dict:
    pred = p >= threshold
    tp = int(np.sum((pred == 1) & (y == 1)))
    fp = int(np.sum((pred == 1) & (y == 0)))
    tn = int(np.sum((pred == 0) & (y == 0)))
    fn = int(np.sum((pred == 0) & (y == 1)))

    def _safe(num: int, den: int):
        return None if den == 0 else float(num / den)

    return {
        "threshold": float(threshold),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "sensitivity": _safe(tp, tp + fn),
        "specificity": _safe(tn, tn + fp),
        "ppv": _safe(tp, tp + fp),
        "npv": _safe(tn, tn + fn),
        "alert_rate": float(pred.mean()),
        "accuracy": _safe(tp + tn, len(y)),
        "f1": _safe(2 * tp, 2 * tp + fp + fn),
    }


def _ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    total = 0.0
    for i in range(bins):
        mask = idx == i
        if not np.any(mask):
            continue
        total += float(mask.mean()) * abs(float(p[mask].mean()) - float(y[mask].mean()))
    return total


def _calibration_slope(y: np.ndarray, p: np.ndarray) -> dict:
    if len(np.unique(y)) < 2:
        return {"slope": None, "intercept": None}
    clipped = np.clip(p, 1e-6, 1 - 1e-6)
    logit = np.log(clipped / (1 - clipped)).reshape(-1, 1)
    model = LogisticRegression(C=1e6, solver="lbfgs", max_iter=1000)
    model.fit(logit, y)
    return {
        "slope": float(model.coef_[0, 0]),
        "intercept": float(model.intercept_[0]),
    }


def _metrics(y: np.ndarray, p: np.ndarray) -> dict:
    if len(np.unique(y)) < 2:
        raise AssertionError("指标计算需要两个类别")
    return {
        "n": int(len(y)),
        "positives": int(y.sum()),
        "prevalence": float(y.mean()),
        "roc_auc": float(roc_auc_score(y, p)),
        "auprc": float(average_precision_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "mean_predicted": float(p.mean()),
        "observed_rate": float(y.mean()),
        "calibration_ece_10bin": float(_ece(y, p)),
        "calibration": _calibration_slope(y, p),
        "thresholds": {f"{cut:.2f}": _confusion(y, p, cut) for cut in CUTS},
    }


def _bootstrap(y: np.ndarray, p: np.ndarray, b: int = BOOTSTRAP_B, seed: int = RANDOM_SEED) -> dict:
    rng = np.random.default_rng(seed)
    aucs: list[float] = []
    briers: list[float] = []
    n = len(y)
    for _ in range(b):
        idx = rng.integers(0, n, n)
        yy = y[idx]
        if len(np.unique(yy)) < 2:
            continue
        pp = p[idx]
        aucs.append(float(roc_auc_score(yy, pp)))
        briers.append(float(brier_score_loss(yy, pp)))

    def _ci(values: list[float]) -> dict:
        if not values:
            return {"low": None, "high": None}
        return {
            "low": float(np.percentile(values, 2.5)),
            "high": float(np.percentile(values, 97.5)),
        }

    return {
        "b": int(b),
        "seed": int(seed),
        "roc_auc_95ci": _ci(aucs),
        "brier_95ci": _ci(briers),
    }


def _subgroup(y: np.ndarray, p: np.ndarray, mask: np.ndarray) -> dict:
    yy = y[mask]
    pp = p[mask]
    out = {
        "n": int(mask.sum()),
        "positives": int(yy.sum()) if len(yy) else 0,
        "prevalence": float(yy.mean()) if len(yy) else None,
        "mean_predicted": float(pp.mean()) if len(pp) else None,
    }
    if len(yy) and len(np.unique(yy)) >= 2:
        out["roc_auc"] = float(roc_auc_score(yy, pp))
        out["threshold_0_50"] = _confusion(yy, pp, 0.50)
    else:
        out["roc_auc"] = None
        out["threshold_0_50"] = None
    return out


def _subgroups(df: pd.DataFrame, y: np.ndarray, p: np.ndarray) -> dict:
    age = pd.to_numeric(df["age"], errors="coerce")
    gender = pd.to_numeric(df["gender"], errors="coerce")
    masks = {
        "age_18_39": (age >= 18) & (age <= 39),
        "age_40_59": (age >= 40) & (age <= 59),
        "age_60_80": (age >= 60) & (age <= 80),
        "gender_1": gender == 1,
        "gender_2": gender == 2,
    }
    return {
        name: _subgroup(y, p, mask.fillna(False).to_numpy())
        for name, mask in masks.items()
    }


def _univariate(df: pd.DataFrame) -> dict:
    out = {}
    for col in NHANES_FEATURES + ["age"]:
        mask = df[col].notna()
        yy = df.loc[mask, "depression_label"].to_numpy()
        if len(yy) < 2 or len(np.unique(yy)) < 2:
            out[col] = {"n": int(mask.sum()), "roc_auc_raw": None}
            continue
        out[col] = {
            "n": int(mask.sum()),
            "roc_auc_raw": float(roc_auc_score(yy, df.loc[mask, col].to_numpy())),
        }
    return out


def _score_distribution(y: np.ndarray, p: np.ndarray) -> dict:
    frame = pd.DataFrame({"score": p, "label": y})
    frame["quintile"] = pd.qcut(frame["score"], 5, labels=False, duplicates="drop")
    rows = {}
    for q, group in frame.groupby("quintile", sort=True):
        rows[str(int(q))] = {
            "n": int(len(group)),
            "score_min": float(group["score"].min()),
            "score_max": float(group["score"].max()),
            "mean_score": float(group["score"].mean()),
            "observed_rate": float(group["label"].mean()),
        }
    return rows


def _variant(artifacts, df: pd.DataFrame, steps_value: float, complete_case: bool) -> dict:
    raw = _build_raw(df, steps_value=steps_value, complete_case=complete_case)
    sub = df.loc[raw.index]
    y = sub["depression_label"].to_numpy()
    p = _score_batch(artifacts, raw)

    phq_mask = sub["phq9_total"].notna().to_numpy()
    rho = None
    if phq_mask.sum() > 2:
        rho = float(
            spearmanr(p[phq_mask], sub.loc[phq_mask, "phq9_total"].to_numpy()).statistic
        )

    return {
        "definition": {
            "steps_value": float(steps_value),
            "complete_case_6": bool(complete_case),
            "default_fill": {k: float(v) for k, v in DEFAULTS.items() if k != "steps"},
        },
        "cohort": {
            "n": int(len(y)),
            "positives": int(y.sum()),
            "prevalence": float(y.mean()),
            "rows_with_any_default_fill": int(
                df.loc[raw.index, NHANES_FEATURES].isna().any(axis=1).sum()
            )
            if not complete_case
            else 0,
        },
        "metrics": _metrics(y, p),
        "bootstrap": _bootstrap(y, p),
        "subgroups": _subgroups(sub, y, p),
        "score_quintiles": _score_distribution(y, p),
        "score_vs_phq9_spearman": rho,
    }


def _fmt(value, digits: int = 4) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _metric_row(name: str, result: dict) -> str:
    m = result["metrics"]
    b = result["bootstrap"]
    auc_ci = f"{_fmt(m['roc_auc'])} [{_fmt(b['roc_auc_95ci']['low'])}, {_fmt(b['roc_auc_95ci']['high'])}]"
    return (
        f"| {name} | {m['n']} | {m['prevalence']:.3f} | {auc_ci} | "
        f"{_fmt(m['auprc'])} | {_fmt(m['brier'])} | {_fmt(m['calibration_ece_10bin'])} | "
        f"{_fmt(m['calibration']['slope'])} | {_fmt(m['mean_predicted'], 3)} |"
    )


def _write_report(payload: dict, path: Path) -> None:
    variants = payload["variants"]
    primary = variants["production_defaults"]
    complete = variants["complete_case_6"]
    sensitivity = variants["steps_training_mean_sensitivity"]
    m = primary["metrics"]
    t35 = m["thresholds"]["0.35"]
    t50 = m["thresholds"]["0.50"]

    lines = [
        "# NHANES 2017-2018 生理外部压力测试（ROUND_47）",
        "",
        "> 本文件由 `backend/scripts/modeling/eval/v1_47/01_nhanes_transport_stress.py` 生成。",
        "> **这不是外部验证。** 这是把生产生理 MLP 直接喂给一个标签定义、特征来源、",
        "> 采集协议都不同的队列，观察会发生什么；结果不能用于声明迁移性能。",
        "",
        "## 0. 结论先行",
        "",
        f"- 主口径（生产默认填充，n={m['n']}）AUC **{_fmt(m['roc_auc'])}** "
        f"[{_fmt(primary['bootstrap']['roc_auc_95ci']['low'])}, "
        f"{_fmt(primary['bootstrap']['roc_auc_95ci']['high'])}]，"
        f"AUPRC {_fmt(m['auprc'])}，Brier {_fmt(m['brier'])}。",
        f"- 平均预测概率 {_fmt(m['mean_predicted'], 3)}，实际阳性率 {_fmt(m['observed_rate'], 3)}；"
        f"校准斜率 {_fmt(m['calibration']['slope'])}，ECE {_fmt(m['calibration_ece_10bin'])}。",
        f"- 0.35 阈值：灵敏度 {_fmt(t35['sensitivity'], 3)}、特异度 {_fmt(t35['specificity'], 3)}、"
        f"PPV {_fmt(t35['ppv'], 3)}；0.50 阈值：灵敏度 {_fmt(t50['sensitivity'], 3)}、"
        f"特异度 {_fmt(t50['specificity'], 3)}、PPV {_fmt(t50['ppv'], 3)}。",
        "- **无论读数高低，都不能写成「模型在 NHANES 上有效/无效」**：训练标签是 Depresjon",
        "  临床分组，NHANES 标签是 PHQ-9≥10；7 个特征中 5 个在训练表里是标签驱动合成，",
        "  NHANES 又完全没有步数列（生产默认 5000）。这些差异与模型能力混在一起，无法分离。",
        "",
        "## 1. 数据与口径",
        "",
        "| 项目 | 值 |",
        "|---|---|",
        f"| 数据文件 | `{payload['dataset']['path']}` |",
        f"| SHA-256 | `{payload['dataset']['sha256']}` |",
        f"| 周期 | {payload['dataset']['cycle']} |",
        f"| 有标签行数 | {primary['cohort']['n']} |",
        f"| 阳性（PHQ-9≥10） | {primary['cohort']['positives']}（{primary['cohort']['prevalence']:.3f}） |",
        f"| 年龄范围 | {payload['dataset']['age_range'][0]}–{payload['dataset']['age_range'][1]} 岁 |",
        "| 抽样权重 | 未应用 WTMEC2YR；以下均为未加权描述统计 |",
        "| 标签 | `depression_label = PHQ-9 total >= 10`（9 项完整才计分） |",
        "| 训练标签 | Depresjon `condition/control`（临床分组，不是 PHQ-9） |",
        "",
        "### 1.1 缺失与默认填充",
        "",
        "| 字段 | 缺失数 | 生产行为 |",
        "|---|---:|---|",
    ]
    for col in NHANES_FEATURES:
        lines.append(
            f"| `{col}` | {payload['dataset']['missing'][col]} | "
            f"缺失键使用默认值 {DEFAULTS[col]:g} |"
        )
    lines.append(
        f"| `steps` | {payload['dataset']['missing']['steps']} | "
        "NHANES 无步数列；生产默认 5000（另一敏感性：训练均值 "
        f"{_fmt(payload['steps_training_mean'], 1)}） |"
    )
    lines += [
        "",
        f"主口径中有 {primary['cohort']['rows_with_any_default_fill']} 行至少一个字段使用默认值。",
        f"完整 6 特征子集 n={complete['cohort']['n']}。",
        "",
        "## 2. 特征映射与不可比点",
        "",
        "| 训练字段 | NHANES 映射 | 可比性 |",
        "|---|---|---|",
        "| `sleep_hours` | SLD012（工作日入睡/起床差，四舍五入 0.5h） | 训练列是标签驱动合成；NHANES 是自报，不可比 |",
        "| `sleep_quality` | SLQ050（1=否 2=是「是否因睡眠问题就医」） | 二值就医代理 vs 训练列「标签分组均值 4/2 + 噪声」（1–5 区间），不可比 |",
        "| `exercise_minutes` | PAD615+630+645+660+675（GPAQ 自报分钟和） | 训练列是真实 actigraphy 峰值的事后缩放；采集方式不同 |",
        "| `heart_rate` | BPXPLS（护士实测 60s 脉搏） | 训练列是标签分组均值+噪声，不可比 |",
        "| `systolic_bp` | BPXSY1（第 1 次听诊读数） | 训练列是标签分组均值+噪声，不可比 |",
        "| `diastolic_bp` | BPXDI1（第 1 次听诊读数） | 训练列由 `systolic_bp` 派生，不可比 |",
        "| `steps` | **无对应列** | 生产默认 5000，属于注入值，不是观测值 |",
        "",
        "## 3. 结果（描述性）",
        "",
        "| 口径 | n | 阳性率 | AUC [95%CI] | AUPRC | Brier | ECE | 校准斜率 | 平均预测 |",
        "|---|---:|---:|---|---:|---:|---:|---:|---:|",
        _metric_row("生产默认填充（主口径）", primary),
        _metric_row("完整 6 特征子集", complete),
        _metric_row("steps=训练均值（敏感性）", sensitivity),
        "",
        "### 3.1 阈值行为（主口径）",
        "",
        "| 阈值 | 灵敏度 | 特异度 | PPV | NPV | 告警率 | TP/FP/FN/TN |",
        "|---:|---:|---:|---:|---:|---:|---|",
    ]
    for cut in CUTS:
        row = m["thresholds"][f"{cut:.2f}"]
        lines.append(
            f"| {cut:.2f} | {_fmt(row['sensitivity'], 3)} | {_fmt(row['specificity'], 3)} | "
            f"{_fmt(row['ppv'], 3)} | {_fmt(row['npv'], 3)} | {_fmt(row['alert_rate'], 3)} | "
            f"{row['tp']}/{row['fp']}/{row['fn']}/{row['tn']} |"
        )
    lines += [
        "",
        "### 3.2 亚组（主口径，未加权）",
        "",
        "| 亚组 | n | 阳性 | AUC | 0.50 灵敏度 | 0.50 特异度 | 平均预测 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in primary["subgroups"].items():
        cut = row.get("threshold_0_50") or {}
        lines.append(
            f"| {name} | {row['n']} | {row['positives']} | {_fmt(row['roc_auc'])} | "
            f"{_fmt(cut.get('sensitivity'), 3)} | {_fmt(cut.get('specificity'), 3)} | "
            f"{_fmt(row['mean_predicted'], 3)} |"
        )
    lines += [
        "",
        "### 3.3 单变量信号（未建模，仅描述）",
        "",
        "| 字段 | n | 原始 AUC（未翻转方向） |",
        "|---|---:|---:|",
    ]
    for name, row in payload["univariate_auc"].items():
        lines.append(f"| `{name}` | {row['n']} | {_fmt(row['roc_auc_raw'])} |")
    lines += [
        "",
        "上表 AUC < 0.5 表示该字段数值越高、阳性越少（方向未翻转）；未做任何单变量建模或阈值选择。",
        "",
        f"生产分数与 PHQ-9 总分的 Spearman ρ（主口径）="
        f"{_fmt(primary['score_vs_phq9_spearman'])}。",
        "",
        "## 4. 解释边界",
        "",
        "**允许的表述**",
        "",
        "- 「把一个训练标签为临床分组、5/7 特征为标签驱动合成、缺少步数的模型，直接用于",
        "  NHANES（PHQ-9≥10）时，得到上述描述性读数。」",
        "- 「该读数不能与 Depresjon 的 AUC 0.9451 并列比较。」",
        "- 「它说明当前生产生理模型没有可用的跨队列迁移证据，Phase 1 必须重做真实特征基线。」",
        "",
        "**禁止的表述**",
        "",
        "- 「模型在 NHANES 上 AUC=x，所以能用于普通成人」。",
        "- 「模型在 NHANES 上接近随机，所以真实生理信号没有用」——两者的标签、特征、",
        "  采集协议同时变化，不能做因果归因。",
        "- 「steps=5000 的默认填充不影响结论」——没有步数观测，无法验证这一点。",
        "",
        "## 5. 复现",
        "",
        "```bash",
        "cd backend",
        ".venv/Scripts/python.exe scripts/modeling/eval/v1_47/01_nhanes_transport_stress.py",
        "```",
        "",
        f"确定性：bootstrap B={BOOTSTRAP_B}，seed={RANDOM_SEED}；"
        f"生产单样本对照最大绝对差 {payload['sanity_check']['max_abs_diff']:.3e}。",
        "",
        "## 6. 对 Phase 1 的含义",
        "",
        "1. NHANES 只能作为压力测试，不能升级生理单元的 `evidence_level`；",
        "2. 真实生理基线必须回到原始 actigraphy 的 `mean_act` / `std_act` / `peak_activity`",
        "   / `autocorrelation` 等真实汇总列，并重新切分、训练、校准；",
        "3. 任何新的外部读数必须同时登记特征来源、标签来源、人群、采集协议与是否参与训练；",
        "4. 在真实特征基线完成前，运行时继续维持 `synthetic_label_derived` 与弃权披露。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    if not DATA.exists():
        raise FileNotFoundError(f"NHANES CSV not found: {DATA}")
    if not MANIFEST.exists():
        raise FileNotFoundError(f"NHANES manifest not found: {MANIFEST}")

    artifacts = _load_artifacts()
    df = _load_cohort()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    steps_index = artifacts["features"].index("steps")
    steps_training_mean = float(artifacts["scaler"].mean_[steps_index])

    primary = _variant(artifacts, df, steps_value=DEFAULTS["steps"], complete_case=False)
    complete = _variant(artifacts, df, steps_value=DEFAULTS["steps"], complete_case=True)
    sensitivity = _variant(
        artifacts, df, steps_value=steps_training_mean, complete_case=False
    )

    raw = _build_raw(df, steps_value=DEFAULTS["steps"], complete_case=False)
    sample = raw.head(20)
    batch_scores = _score_batch(artifacts, sample)
    single_scores = np.array(
        [
            _production_single(artifacts, sample.loc[idx], DEFAULTS["steps"])
            for idx in sample.index
        ]
    )
    max_abs_diff = float(np.max(np.abs(batch_scores - single_scores)))

    payload = {
        "round": "ROUND_47",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "descriptive_stress_test_not_external_validation",
        "external_validation": False,
        "transport_risk": "not_evaluated",
        "dataset": {
            "path": str(DATA.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "sha256": sha256_path(DATA),
            "cycle": manifest.get("source", {}).get("cycle"),
            "license": manifest.get("source", {}).get("license"),
            "age_range": manifest.get("measured", {}).get("age_range"),
            "label_rule": manifest.get("label", {}).get("rule"),
            "label_comparable_to_depresjon": manifest.get("label", {}).get("caveat", {}).get("comparable"),
            "missing": {
                **{
                    col: int(df[col].isna().sum())
                    for col in NHANES_FEATURES
                },
                "steps": int(df["steps"].isna().sum()),
            },
            "schema_gap": manifest.get("schema_gap", []),
        },
        "model": {
            "artifact_dir": str(ARTIFACT_DIR.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "artifact_hashes": {
                name: sha256_path(ARTIFACT_DIR / name)
                for name in (
                    "model.json",
                    "scaler.json",
                    "feature_names.json",
                    "cleaner_stats.json",
                )
            },
            "features": list(artifacts["features"]),
            "defaults": {k: float(v) for k, v in DEFAULTS.items()},
        },
        "steps_training_mean": steps_training_mean,
        "variants": {
            "production_defaults": primary,
            "complete_case_6": complete,
            "steps_training_mean_sensitivity": sensitivity,
        },
        "univariate_auc": _univariate(df),
        "sanity_check": {
            "rows": int(len(sample)),
            "max_abs_diff": max_abs_diff,
            "threshold": 1e-6,
            "passed": bool(max_abs_diff < 1e-6),
        },
        "interpretation": {
            "why_not_external_validation": [
                "训练标签是 Depresjon 临床 condition/control，NHANES 是 PHQ-9>=10",
                "训练表 5/7 原始特征是标签驱动合成；NHANES 是实测/自报，来源不同",
                "steps 在 NHANES 中完全缺失，生产默认 5000 是注入值",
                "sleep_quality 在 NHANES 是就医代理，不是 1-4 睡眠质量量表",
                "NHANES 复杂抽样权重未应用",
                "没有目标域重新校准",
            ],
            "allowed_claims": [
                "描述性地报告生产模型在该队列上的分数与标签一致性",
                "说明当前模型没有可用的跨队列迁移证据",
                "据此要求 Phase 1 重做真实特征基线",
            ],
            "forbidden_claims": [
                "NHANES 读数等于模型在普通成人上的性能",
                "NHANES 接近随机证明真实生理信号无效",
                "steps 默认填充不影响结论",
            ],
        },
    }

    if not payload["sanity_check"]["passed"]:
        raise AssertionError(
            f"批量评分与生产单样本评分不一致：max_abs_diff={max_abs_diff}"
        )

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_MIRROR.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(jsonable(payload), ensure_ascii=False, indent=2) + "\n"
    OUT_JSON.write_text(text, encoding="utf-8")
    OUT_MIRROR.write_text(text, encoding="utf-8")
    _write_report(payload, OUT_REPORT)

    print(f"NHANES 压力测试完成：n={primary['cohort']['n']}")
    print(
        "  主口径 AUC={:.4f} Brier={:.4f} ECE={:.4f} mean_pred={:.3f}".format(
            primary["metrics"]["roc_auc"],
            primary["metrics"]["brier"],
            primary["metrics"]["calibration_ece_10bin"],
            primary["metrics"]["mean_predicted"],
        )
    )
    print(f"  完整 6 特征 n={complete['cohort']['n']}")
    print(f"  生产单样本对照 max_abs_diff={max_abs_diff:.3e}")
    print(f"  写出 {OUT_JSON.relative_to(PROJECT_ROOT)}")
    print(f"  写出 {OUT_REPORT.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
