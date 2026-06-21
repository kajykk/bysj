#!/usr/bin/env python3
"""v1.23 Phase 3: 模型评估 — 测试集全面评估，分数据源报告。

输出:
    backend/models/v1.23_external_lr/metrics_eval.json
    backend/models/v1.23_external_lr/confusion_matrix.json
    backend/models/v1.23_external_lr/roc_curve.csv
    backend/models/v1.23_external_lr/pr_curve.csv
    docs/planning/v1.23-external-risk-model-upgrade/MODEL_EVALUATION_REPORT.md
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
    f1_score, precision_recall_curve, precision_score, recall_score,
    roc_auc_score, roc_curve,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]

FEATURE_COLS = [
    "age", "gender", "cgpa", "stress_level", "sleep_duration",
    "social_support", "financial_pressure", "family_history",
    "academic_pressure", "exercise_frequency", "anxiety", "panic_attack",
]
TARGET_COL = "depression_binary"
SOURCE_COL = "source"


def compute_all_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_proba: np.ndarray, prefix: str = "") -> dict:
    cm = confusion_matrix(y_true, y_pred)
    if len(cm.ravel()) == 4:
        tn, fp, fn, tp = cm.ravel()
    else:
        tn, fp, fn, tp = 0, 0, 0, 0

    specificity = round(tn / (tn + fp), 4) if (tn + fp) > 0 else 0.0
    sensitivity = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0.0

    result = {
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "balanced_accuracy": round(balanced_accuracy_score(y_true, y_pred), 4),
        "precision": round(precision_score(y_true, y_pred, zero_division=0), 4),
        "recall": round(recall_score(y_true, y_pred, zero_division=0), 4),
        "sensitivity": sensitivity,
        "specificity": specificity,
        "f1": round(f1_score(y_true, y_pred, zero_division=0), 4),
        "roc_auc": round(roc_auc_score(y_true, y_proba), 4) if len(np.unique(y_true)) > 1 else None,
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "samples": len(y_true),
        "positive_rate": round(float(y_true.mean()), 4),
    }
    if prefix:
        result = {f"{prefix}_{k}" if k != "samples" else f"{prefix}_samples": v for k, v in result.items()}
    return result


def generate_report(
    overall: dict,
    by_source: dict,
    roc_csv_path: Path,
    pr_csv_path: Path,
    error_samples: pd.DataFrame,
    df_test: pd.DataFrame,
    report_path: Path,
) -> None:
    lines = [
        "# v1.23 模型评估报告 (MODEL_EVALUATION_REPORT)",
        "",
        "> 日期: 2026-05-02",
        "> 模型: v1.23 External LR (Setting B — Source Weighted)",
        "",
        "## 测试集总体指标",
        "",
        "| 指标 | 值 |",
        "|------|-----|",
        f"| 样本数 | {overall['samples']} |",
        f"| 正例比例 | {overall['positive_rate']:.1%} |",
        f"| Accuracy | {overall['accuracy']:.4f} |",
        f"| Balanced Accuracy | {overall['balanced_accuracy']:.4f} |",
        f"| Precision | {overall['precision']:.4f} |",
        f"| Recall (Sensitivity) | {overall['recall']:.4f} |",
        f"| Specificity | {overall['specificity']:.4f} |",
        f"| F1-Score | {overall['f1']:.4f} |",
        f"| ROC-AUC | {overall['roc_auc']:.4f} |",
        "",
        "## 混淆矩阵",
        "",
        "|  | 预测负 | 预测正 |",
        "|------|--------|--------|",
        f"| **实际负** | TN={overall['confusion_matrix']['tn']} | FP={overall['confusion_matrix']['fp']} |",
        f"| **实际正** | FN={overall['confusion_matrix']['fn']} | TP={overall['confusion_matrix']['tp']} |",
        "",
        "## 分数据源评估",
    ]

    for src, src_metrics in by_source.items():
        if src_metrics["samples"] == 0:
            continue
        lines.extend([
            f"### {src}",
            f"- 样本数: {src_metrics['samples']}",
            f"- 正例比例: {src_metrics['positive_rate']:.1%}",
            f"- Accuracy: {src_metrics['accuracy']:.4f}",
            f"- Recall: {src_metrics['recall']:.4f}",
            f"- Specificity: {src_metrics['specificity']:.4f}",
            f"- F1: {src_metrics['f1']:.4f}",
            f"- ROC-AUC: {src_metrics['roc_auc']:.4f}",
        ])

    lines.extend([
        "",
        "## 错误样本分析",
        f"- FP (假阳性): {overall['confusion_matrix']['fp']} — 模型误报高风险",
        f"- FN (假阴性): {overall['confusion_matrix']['fn']} — 模型漏报高风险",
    ])

    if not error_samples.empty:
        fp_samples = error_samples[error_samples["error_type"] == "FP"]
        fn_samples = error_samples[error_samples["error_type"] == "FN"]
        lines.append(f"\n### 假阳性 (FP) 特征均值 (n={len(fp_samples)})")
        for col in FEATURE_COLS:
            if col in fp_samples.columns:
                lines.append(f"- `{col}`: {fp_samples[col].mean():.2f}")
        lines.append(f"\n### 假阴性 (FN) 特征均值 (n={len(fn_samples)})")
        for col in FEATURE_COLS:
            if col in fn_samples.columns:
                lines.append(f"- `{col}`: {fn_samples[col].mean():.2f}")

    lines.extend([
        "",
        "## 验收标准对照",
        "| 标准 | 要求 | 实际 | 状态 |",
        "|------|------|------|------|",
        f"| AUC | >= 0.75 | {overall['roc_auc']:.4f} | {'✅' if overall['roc_auc'] >= 0.75 else '❌'} |",
        f"| Recall | >= 0.70 | {overall['recall']:.4f} | {'✅' if overall['recall'] >= 0.70 else '❌'} |",
        f"| Specificity | >= 0.60 | {overall['specificity']:.4f} | {'✅' if overall['specificity'] >= 0.60 else '❌'} |",
        "",
        "## ROC/PR 曲线数据",
        f"- ROC: `{roc_csv_path}`",
        f"- PR: `{pr_csv_path}`",
    ])

    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="v1.23 Phase 3: Model Evaluation")
    parser.add_argument("--data-dir", default="data/processed/v1_23_external")
    parser.add_argument("--model-dir", default="backend/models/v1.23_external_lr")
    parser.add_argument("--report-dir", default="docs/planning/v1.23-external-risk-model-upgrade")
    args = parser.parse_args()

    data_dir = PROJECT_ROOT / args.data_dir
    model_dir = PROJECT_ROOT / args.model_dir
    report_dir = PROJECT_ROOT / args.report_dir

    model = joblib.load(model_dir / "model.pkl")
    df_test = pd.read_csv(data_dir / "test.csv")

    X_test = df_test[FEATURE_COLS]
    y_test = df_test[TARGET_COL]

    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    overall = compute_all_metrics(y_test, y_pred, y_proba)
    logger.info("Overall metrics: %s", json.dumps(overall, indent=2))

    (model_dir / "metrics_eval.json").write_text(
        json.dumps(overall, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    (model_dir / "confusion_matrix.json").write_text(
        json.dumps(overall["confusion_matrix"], indent=2), encoding="utf-8",
    )

    by_source = {}
    for src in df_test[SOURCE_COL].unique():
        mask = df_test[SOURCE_COL] == src
        if mask.sum() == 0:
            continue
        by_source[src] = compute_all_metrics(
            y_test[mask], y_pred[mask], y_proba[mask],
        )
        logger.info("%s metrics: %s", src, json.dumps(by_source[src], indent=2))

    fpr, tpr, _ = roc_curve(y_test, y_proba)
    roc_df = pd.DataFrame({"fpr": fpr, "tpr": tpr})
    roc_df.to_csv(model_dir / "roc_curve.csv", index=False)

    prec_vals, rec_vals, _ = precision_recall_curve(y_test, y_proba)
    pr_df = pd.DataFrame({"precision": prec_vals, "recall": rec_vals})
    pr_df.to_csv(model_dir / "pr_curve.csv", index=False)

    error_mask = y_pred != y_test
    error_samples = df_test[error_mask].copy()
    error_samples["error_type"] = error_samples.apply(
        lambda r: "FP" if r[TARGET_COL] == 0 and r[TARGET_COL] != y_pred[r.name] else "FN",
        axis=1,
    )

    generate_report(
        overall, by_source,
        model_dir / "roc_curve.csv",
        model_dir / "pr_curve.csv",
        error_samples, df_test,
        report_dir / "MODEL_EVALUATION_REPORT.md",
    )

    logger.info("Phase 3 complete.")
    logger.info(
        "Test: AUC=%.4f, Recall=%.4f, Specificity=%.4f, F1=%.4f",
        overall["roc_auc"], overall["recall"], overall["specificity"], overall["f1"],
    )


if __name__ == "__main__":
    main()
