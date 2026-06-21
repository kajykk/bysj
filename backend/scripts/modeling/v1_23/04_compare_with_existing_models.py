#!/usr/bin/env python3
"""v1.23 Phase 6: 三模型对比 — 系统比较 v1.20、v1.21、v1.23。

在 align_features 测试集上同时运行三模型，输出分类指标、风险分分布、delta 分析。

输出:
    backend/models/v1.23_external_lr/comparison_metrics.json
    backend/models/v1.23_external_lr/model_delta_samples.csv
    docs/planning/v1.23-external-risk-model-upgrade/MODEL_COMPARISON_REPORT.md
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score, balanced_accuracy_score, confusion_matrix,
    f1_score, precision_score, recall_score, roc_auc_score,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]

V123_FEATURES = [
    "age", "gender", "cgpa", "stress_level", "sleep_duration",
    "social_support", "financial_pressure", "family_history",
    "academic_pressure", "exercise_frequency", "anxiety", "panic_attack",
]
V120_MODEL_PATH = "backend/models/artifacts/structured_v1.20/structured_model_v1.20.pkl"
V121_MODEL_PATH = "backend/models/artifacts/structured_v1.21/model_binary_lr.pkl"
V121_SCALER_PATH = "backend/models/artifacts/structured_v1.21/scaler.pkl"
V123_MODEL_PATH = "backend/models/v1.23_external_lr/model.pkl"

TARGET_COL = "depression_binary"
SOURCE_COL = "source"


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_proba: np.ndarray) -> dict:
    cm = confusion_matrix(y_true, y_pred)
    if len(cm.ravel()) == 4:
        tn, fp, fn, tp = cm.ravel()
    else:
        tn = fp = fn = tp = 0
    return {
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "balanced_accuracy": round(balanced_accuracy_score(y_true, y_pred), 4),
        "precision": round(precision_score(y_true, y_pred, zero_division=0), 4),
        "recall": round(recall_score(y_true, y_pred, zero_division=0), 4),
        "specificity": round(tn / (tn + fp), 4) if (tn + fp) > 0 else 0,
        "f1": round(f1_score(y_true, y_pred, zero_division=0), 4),
        "roc_auc": round(roc_auc_score(y_true, y_proba), 4) if len(np.unique(y_true)) > 1 else None,
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def build_v120_features(df: pd.DataFrame) -> np.ndarray:
    cols = [
        "age", "gender", "study_year", "cgpa", "stress_level",
        "sleep_duration", "social_support", "financial_pressure",
        "family_history", "academic_pressure", "exercise_frequency",
        "anxiety", "panic_attack", "treatment_seeking",
    ]
    data = {}
    for c in cols:
        if c in df.columns:
            vals = df[c].values.astype(float)
        elif c == "study_year":
            vals = np.full(len(df), 2.0)
        elif c == "treatment_seeking":
            vals = np.zeros(len(df))
        else:
            vals = np.zeros(len(df))
        data[c] = vals
    return np.column_stack([data[c] for c in cols])


def build_v121_features(df: pd.DataFrame) -> np.ndarray:
    cols = [
        "age", "gender", "study_year", "cgpa", "stress_level",
        "sleep_duration", "social_support", "financial_pressure",
        "family_history", "academic_pressure", "exercise_frequency",
        "anxiety", "panic_attack", "treatment_seeking",
    ]
    data = {}
    for c in cols:
        if c in df.columns:
            vals = df[c].values.astype(float)
        elif c == "study_year":
            vals = np.full(len(df), 2.0)
        elif c == "treatment_seeking":
            vals = np.zeros(len(df))
        else:
            vals = np.zeros(len(df))
        data[c] = vals
    return np.column_stack([data[c] for c in cols])


def main() -> None:
    parser = argparse.ArgumentParser(description="v1.23 Phase 6: Model Comparison")
    parser.add_argument("--data-dir", default="data/processed/v1_23_external")
    parser.add_argument("--output-dir", default="backend/models/v1.23_external_lr")
    parser.add_argument("--report-dir", default="docs/planning/v1.23-external-risk-model-upgrade")
    args = parser.parse_args()

    data_dir = PROJECT_ROOT / args.data_dir
    output_dir = PROJECT_ROOT / args.output_dir
    report_dir = PROJECT_ROOT / args.report_dir
    v120_path = PROJECT_ROOT / V120_MODEL_PATH
    v121_path = PROJECT_ROOT / V121_MODEL_PATH
    v121_scaler_path = PROJECT_ROOT / V121_SCALER_PATH
    v123_path = PROJECT_ROOT / V123_MODEL_PATH

    df_test = pd.read_csv(data_dir / "test.csv")
    y_test = df_test[TARGET_COL].values
    logger.info("Test samples: %d, pos_rate=%.2f%%", len(df_test), y_test.mean() * 100)

    # v1.20
    if v120_path.exists():
        v120_model = joblib.load(v120_path)
        X_v120 = build_v120_features(df_test)
        v120_proba = v120_model.predict_proba(X_v120)[:, 1]
        v120_pred = v120_model.predict(X_v120)
        v120_risk = v120_proba * 100
        v120_metrics = compute_metrics(y_test, v120_pred, v120_proba)
        logger.info("v1.20 metrics: AUC=%.4f, F1=%.4f", v120_metrics["roc_auc"], v120_metrics["f1"])
    else:
        logger.warning("v1.20 model not found at %s", v120_path)
        v120_proba = v120_risk = v120_metrics = None

    # v1.21
    if v121_path.exists() and v121_scaler_path.exists():
        v121_model = joblib.load(v121_path)
        v121_scaler = joblib.load(v121_scaler_path)
        X_v121 = build_v121_features(df_test)
        try:
            X_v121_scaled = v121_scaler.transform(X_v121)
        except Exception:
            X_v121_scaled = X_v121
        v121_proba = v121_model.predict_proba(X_v121_scaled)[:, 1]
        v121_pred = v121_model.predict(X_v121_scaled)
        v121_risk = v121_proba * 100
        v121_metrics = compute_metrics(y_test, v121_pred, v121_proba)
        logger.info("v1.21 metrics: AUC=%.4f, F1=%.4f", v121_metrics["roc_auc"], v121_metrics["f1"])
    else:
        logger.warning("v1.21 model not found")
        v121_proba = v121_risk = v121_metrics = None

    # v1.23
    v123_model = joblib.load(v123_path)
    X_v123 = df_test[V123_FEATURES]
    v123_proba = v123_model.predict_proba(X_v123)[:, 1]
    v123_pred = v123_model.predict(X_v123)
    v123_risk = v123_proba * 100
    v123_metrics = compute_metrics(y_test, v123_pred, v123_proba)
    logger.info("v1.23 metrics: AUC=%.4f, F1=%.4f", v123_metrics["roc_auc"], v123_metrics["f1"])

    # Delta analysis
    delta_20 = None
    delta_21 = None
    if v120_risk is not None:
        delta_20 = v123_risk - v120_risk
    if v121_risk is not None:
        delta_21 = v123_risk - v121_risk

    comparison = {
        "test_samples": len(df_test),
        "models": {},
    }
    for name, risk, metrics in [
        ("v1.20_synthetic_lr", v120_risk, v120_metrics),
        ("v1.21_real_binary_lr", v121_risk, v121_metrics),
        ("v1.23_external_lr", v123_risk, v123_metrics),
    ]:
        if risk is None:
            continue
        comparison["models"][name] = {
            **metrics,
            "risk_score_stats": {
                "mean": round(float(risk.mean()), 2),
                "median": round(float(np.median(risk)), 2),
                "p25": round(float(np.percentile(risk, 25)), 2),
                "p75": round(float(np.percentile(risk, 75)), 2),
                "p90": round(float(np.percentile(risk, 90)), 2),
                "min": round(float(risk.min()), 2),
                "max": round(float(risk.max()), 2),
            },
        }

    if delta_20 is not None:
        comparison["delta_v123_vs_v120"] = {
            "mean_abs_delta": round(float(np.abs(delta_20).mean()), 2),
            "median_abs_delta": round(float(np.median(np.abs(delta_20))), 2),
            "max_abs_delta": round(float(np.abs(delta_20).max()), 2),
            "delta_gt_15_ratio": round(float((np.abs(delta_20) > 15).mean()), 4),
            "delta_gt_30_ratio": round(float((np.abs(delta_20) > 30).mean()), 4),
            "delta_gt_40_ratio": round(float((np.abs(delta_20) > 40).mean()), 4),
        }
        comparison["delta_v123_vs_v121"] = {
            "mean_abs_delta": round(float(np.abs(delta_21).mean()), 2),
            "median_abs_delta": round(float(np.median(np.abs(delta_21))), 2),
            "max_abs_delta": round(float(np.abs(delta_21).max()), 2),
            "delta_gt_15_ratio": round(float((np.abs(delta_21) > 15).mean()), 4),
            "delta_gt_30_ratio": round(float((np.abs(delta_21) > 30).mean()), 4),
            "delta_gt_40_ratio": round(float((np.abs(delta_21) > 40).mean()), 4),
        }

    delta_df = df_test[["source"] + V123_FEATURES + [TARGET_COL]].copy()
    delta_df["v120_risk"] = v120_risk
    delta_df["v121_risk"] = v121_risk
    delta_df["v123_risk"] = v123_risk
    if delta_20 is not None:
        delta_df["delta_v123_v120"] = delta_20
    if delta_21 is not None:
        delta_df["delta_v123_v121"] = delta_21
    delta_df.to_csv(output_dir / "model_delta_samples.csv", index=False)

    # Typical sample extraction
    typical = {}
    if delta_20 is not None:
        typical["all_low"] = delta_df[(delta_df["v120_risk"] < 20) & (delta_df["v123_risk"] < 20)].head(3)[V123_FEATURES].to_dict("records")
        typical["all_high"] = delta_df[(delta_df["v120_risk"] >= 60) & (delta_df["v123_risk"] >= 60)].head(3)[V123_FEATURES].to_dict("records")
        typical["v120_low_v123_high"] = delta_df[(delta_df["v120_risk"] < 30) & (delta_df["v123_risk"] >= 50)].head(3)[V123_FEATURES].to_dict("records")
        typical["v120_high_v123_low"] = delta_df[(delta_df["v120_risk"] >= 50) & (delta_df["v123_risk"] < 30)].head(3)[V123_FEATURES].to_dict("records")
    comparison["typical_samples"] = typical

    (output_dir / "comparison_metrics.json").write_text(
        json.dumps(comparison, indent=2, ensure_ascii=False, default=str), encoding="utf-8",
    )

    # Report
    lines = [
        "# v1.23 模型对比报告 (MODEL_COMPARISON_REPORT)",
        "",
        "> 日期: 2026-05-02",
        f"> 测试集: {len(df_test)} 样本 (统一 align_features 测试集)",
        "",
        "## 分类性能对比",
        "",
        "| 指标 | v1.20 Synthetic LR | v1.21 Real Binary LR | v1.23 External LR |",
        "|------|-------------------|---------------------|-------------------|",
    ]
    for metric_name in ["roc_auc", "accuracy", "precision", "recall", "f1", "specificity", "balanced_accuracy"]:
        vals = []
        for model_key in ["v1.20_synthetic_lr", "v1.21_real_binary_lr", "v1.23_external_lr"]:
            m = comparison["models"].get(model_key, {})
            v = m.get(metric_name, "N/A") if m else "N/A"
            vals.append(str(v))
        lines.append(f"| {metric_name} | " + " | ".join(vals) + " |")

    lines.extend([
        "",
        "## 风险分分布对比",
        "",
        "| 模型 | 均值 | 中位数 | P25 | P75 | P90 |",
        "|------|------|--------|-----|-----|-----|",
    ])
    for model_key in ["v1.20_synthetic_lr", "v1.21_real_binary_lr", "v1.23_external_lr"]:
        m = comparison["models"].get(model_key, {})
        if not m:
            continue
        stats = m.get("risk_score_stats", {})
        vals = [str(stats.get(k, "N/A")) for k in ["mean", "median", "p25", "p75", "p90"]]
        lines.append(f"| {model_key} | " + " | ".join(vals) + " |")

    if delta_20 is not None:
        d = comparison["delta_v123_vs_v120"]
        lines.extend([
            "",
            "## v1.23 vs v1.20 Delta 分析",
            f"- Mean Abs Delta: **{d['mean_abs_delta']}**",
            f"- Median Abs Delta: {d['median_abs_delta']}",
            f"- Max Abs Delta: {d['max_abs_delta']}",
            f"- |delta| > 15: **{d['delta_gt_15_ratio']:.1%}**",
            f"- |delta| > 30: **{d['delta_gt_30_ratio']:.1%}**",
            f"- |delta| > 40: **{d['delta_gt_40_ratio']:.1%}**",
        ])

    if delta_21 is not None:
        d = comparison["delta_v123_vs_v121"]
        lines.extend([
            "",
            "## v1.23 vs v1.21 Delta 分析",
            f"- Mean Abs Delta: **{d['mean_abs_delta']}**",
            f"- |delta| > 15: {d['delta_gt_15_ratio']:.1%}",
            f"- |delta| > 30: {d['delta_gt_30_ratio']:.1%}",
        ])

    lines.extend([
        "",
        "## 联合评估结论",
    ])

    v123_auc = v123_metrics["roc_auc"]
    v120_auc = v120_metrics["roc_auc"] if v120_metrics else None
    if v120_auc:
        auc_gap = abs(v123_auc - v120_auc)
        lines.append(f"- v1.23 vs v1.20 AUC 差距: {auc_gap:.4f}")
    if delta_20 is not None:
        mabs = comparison["delta_v123_vs_v120"]["mean_abs_delta"]
        gt15 = comparison["delta_v123_vs_v120"]["delta_gt_15_ratio"]
        gt40 = comparison["delta_v123_vs_v120"]["delta_gt_40_ratio"]
        lines.append(f"- 与 v1.20 平均差异: {mabs} (要求 < 15, {'✅' if mabs < 15 else '❌'})")
        lines.append(f"- |delta| > 40 比例: {gt40:.1%} (要求 < 5%, {'✅' if gt40 < 0.05 else '❌'})")

    lines.extend([
        "",
        "> **推荐**: 基于以上对比，判断 v1.23 是否可作为候选实验模型或需进一步调整。",
    ])

    (report_dir / "MODEL_COMPARISON_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    logger.info("Phase 6 complete.")


if __name__ == "__main__":
    main()
