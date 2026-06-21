#!/usr/bin/env python3
"""v1.23 Phase 2: 模型训练 — 训练 v1.23 External LR 候选模型。

支持三种训练设置:
    Setting A: natural — Kaggle+Mendeley 自然比例 (所有样本等权)
    Setting B: weighted — Mendeley 样本权重 5.0 (推荐候选)
    Setting C: mendeley_only — 只用 Mendeley 数据 (验证基线)

输出:
    backend/models/v1.23_external_lr/model.pkl
    backend/models/v1.23_external_lr/preprocessor.pkl
    backend/models/v1.23_external_lr/metrics_train.json
    backend/models/v1.23_external_lr/feature_coefficients.csv
    docs/planning/v1.23-external-risk-model-upgrade/TRAINING_REPORT.md
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, balanced_accuracy_score, confusion_matrix,
    f1_score, precision_score, recall_score, roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

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
MENDELEY_SAMPLE_WEIGHT = 5.0


def load_data(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = pd.read_csv(data_dir / "train.csv")
    val = pd.read_csv(data_dir / "validation.csv")
    logger.info("train=%d, val=%d", len(train), len(val))
    return train, val


def build_pipeline(random_state: int) -> Pipeline:
    num_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])
    preprocessor = ColumnTransformer([
        ("num", num_pipeline, FEATURE_COLS),
    ])
    return Pipeline([
        ("preprocessor", preprocessor),
        ("classifier", LogisticRegression(
            random_state=random_state,
            max_iter=2000,
            solver="lbfgs",
        )),
    ])


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_proba: np.ndarray) -> dict:
    cm = confusion_matrix(y_true, y_pred)
    return {
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "balanced_accuracy": round(balanced_accuracy_score(y_true, y_pred), 4),
        "precision": round(precision_score(y_true, y_pred, zero_division=0), 4),
        "recall": round(recall_score(y_true, y_pred, zero_division=0), 4),
        "f1": round(f1_score(y_true, y_pred, zero_division=0), 4),
        "roc_auc": round(roc_auc_score(y_true, y_proba), 4) if len(np.unique(y_true)) > 1 else None,
        "confusion_matrix": {"tn": int(cm[0][0]), "fp": int(cm[0][1]), "fn": int(cm[1][0]), "tp": int(cm[1][1])},
    }


def train_natural(
    train_df: pd.DataFrame, val_df: pd.DataFrame, random_state: int
) -> dict:
    logger.info("=== Setting A: Natural Ratio ===")
    X_train = train_df[FEATURE_COLS]
    y_train = train_df[TARGET_COL]
    X_val = val_df[FEATURE_COLS]
    y_val = val_df[TARGET_COL]

    pipe = build_pipeline(random_state)
    pipe.fit(X_train, y_train)

    y_pred = pipe.predict(X_val)
    y_proba = pipe.predict_proba(X_val)[:, 1]

    metrics = compute_metrics(y_val, y_pred, y_proba)
    logger.info("Val metrics: %s", json.dumps(metrics, indent=2))

    return {"model": pipe, "metrics_val": metrics, "coef": _get_coef(pipe)}


def train_weighted(
    train_df: pd.DataFrame, val_df: pd.DataFrame, random_state: int
) -> dict:
    logger.info("=== Setting B: Source Weighted (Mendeley x%.1f) ===", MENDELEY_SAMPLE_WEIGHT)
    weights = np.ones(len(train_df))
    mendeley_mask = train_df[SOURCE_COL] == "mendeley"
    weights[mendeley_mask] = MENDELEY_SAMPLE_WEIGHT

    train_source_weights = pd.Series(weights, index=train_df.index)
    train_source_weights = train_source_weights.reindex(train_df.index)

    X_train = train_df[FEATURE_COLS]
    y_train = train_df[TARGET_COL]
    X_val = val_df[FEATURE_COLS]
    y_val = val_df[TARGET_COL]

    pipe = build_pipeline(random_state)
    pipe.set_params(classifier__class_weight=None)
    pipe.fit(X_train, y_train, classifier__sample_weight=train_source_weights.values)

    y_pred = pipe.predict(X_val)
    y_proba = pipe.predict_proba(X_val)[:, 1]

    metrics = compute_metrics(y_val, y_pred, y_proba)
    logger.info("Val metrics: %s", json.dumps(metrics, indent=2))

    return {"model": pipe, "metrics_val": metrics, "coef": _get_coef(pipe)}


def train_mendeley_only(
    train_df: pd.DataFrame, val_df: pd.DataFrame, random_state: int
) -> dict:
    logger.info("=== Setting C: Mendeley Only ===")
    m_train = train_df[train_df[SOURCE_COL] == "mendeley"]
    m_val = val_df[val_df[SOURCE_COL] == "mendeley"]

    if len(m_train) < 10:
        logger.warning("Mendeley training set too small (%d), skipping", len(m_train))
        return {"model": None, "metrics_val": {}, "coef": []}

    X_train = m_train[FEATURE_COLS]
    y_train = m_train[TARGET_COL]
    X_val = m_val[FEATURE_COLS]
    y_val = m_val[TARGET_COL]

    pipe = build_pipeline(random_state)
    pipe.fit(X_train, y_train)

    y_pred = pipe.predict(X_val)
    y_proba = pipe.predict_proba(X_val)[:, 1]

    metrics = compute_metrics(y_val, y_pred, y_proba)
    logger.info("Val metrics (Mendeley): %s", json.dumps(metrics, indent=2))

    return {"model": pipe, "metrics_val": metrics, "coef": _get_coef(pipe)}


def _get_coef(pipe: Pipeline) -> list[dict]:
    model = pipe.named_steps["classifier"]
    coefs = model.coef_[0]
    return sorted(
        [
            {"feature": f, "coefficient": round(float(c), 6), "abs_coef": round(abs(float(c)), 6)}
            for f, c in zip(FEATURE_COLS, coefs)
        ],
        key=lambda x: x["abs_coef"], reverse=True,
    )


def generate_report(results: dict, report_path: Path) -> None:
    lines = [
        "# v1.23 训练报告 (TRAINING_REPORT)",
        "",
        "> 日期: 2026-05-02",
        "> 模型类型: Logistic Regression",
        "> 特征数: {}".format(len(FEATURE_COLS)),
        "> 特征: {}".format(", ".join(FEATURE_COLS)),
        "",
        "## Setting A: 自然比例训练",
    ]
    _append_setting(lines, results.get("natural", {}))

    lines.extend(["", "## Setting B: 数据源加权训练 (推荐候选)", f"Mendeley 权重: {MENDELEY_SAMPLE_WEIGHT}x"])
    _append_setting(lines, results.get("weighted", {}))

    lines.extend(["", "## Setting C: Mendeley-only 验证基线"])
    _append_setting(lines, results.get("mendeley_only", {}))

    lines.extend([
        "",
        "## 特征系数 (Setting B — 推荐候选)",
    ])
    coefs = results.get("weighted", {}).get("coef", [])
    for item in coefs:
        direction = "+" if item["coefficient"] >= 0 else ""
        lines.append(f"- `{item['feature']}`: {direction}{item['coefficient']:.4f}")

    lines.extend([
        "",
        "## 训练可复现命令",
        "```bash",
        "python backend/scripts/modeling/v1_23/01_prepare_external_dataset.py --random-state 42",
        "python backend/scripts/modeling/v1_23/02_train_external_lr.py --random-state 42 --setting weighted",
        "```",
    ])

    report_path.write_text("\n".join(lines), encoding="utf-8")


def _append_setting(lines: list[str], result: dict) -> None:
    if not result or not result.get("metrics_val"):
        lines.append("(未训练)")
        return
    m = result["metrics_val"]
    lines.append(f"- Accuracy: {m.get('accuracy', 'N/A')}")
    lines.append(f"- Balanced Acc: {m.get('balanced_accuracy', 'N/A')}")
    lines.append(f"- Precision: {m.get('precision', 'N/A')}")
    lines.append(f"- Recall: {m.get('recall', 'N/A')}")
    lines.append(f"- F1: {m.get('f1', 'N/A')}")
    lines.append(f"- ROC-AUC: {m.get('roc_auc', 'N/A')}")
    cm = m.get("confusion_matrix", {})
    lines.append(f"- 混淆矩阵: TN={cm.get('tn')}, FP={cm.get('fp')}, FN={cm.get('fn')}, TP={cm.get('tp')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="v1.23 Phase 2: Model Training")
    parser.add_argument("--data-dir", default="data/processed/v1_23_external")
    parser.add_argument("--output-dir", default="backend/models/v1.23_external_lr")
    parser.add_argument("--report-dir", default="docs/planning/v1.23-external-risk-model-upgrade")
    parser.add_argument("--setting", default="weighted",
                        choices=["natural", "weighted", "mendeley_only", "all"])
    parser.add_argument("--random-state", type=int, default=42)
    args = parser.parse_args()

    data_dir = PROJECT_ROOT / args.data_dir
    output_dir = PROJECT_ROOT / args.output_dir
    report_dir = PROJECT_ROOT / args.report_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    train_df, val_df = load_data(data_dir)

    settings_to_run = ["natural", "weighted", "mendeley_only"] if args.setting == "all" else [args.setting]

    results = {}
    train_fns = {
        "natural": train_natural,
        "weighted": train_weighted,
        "mendeley_only": train_mendeley_only,
    }

    for s in settings_to_run:
        fn = train_fns[s]
        results[s] = fn(train_df, val_df, args.random_state)

    selected = results.get(args.setting, results.get("weighted", {}))
    selected_model = selected.get("model")
    if selected_model is not None:
        joblib.dump(selected_model, output_dir / "model.pkl")
        logger.info("Model saved to %s/model.pkl", output_dir)

        metrics_out = {
            "random_state": args.random_state,
            "setting": args.setting,
            "training_samples": len(train_df),
            "val_samples": len(val_df),
            **selected["metrics_val"],
        }
        (output_dir / "metrics_train.json").write_text(
            json.dumps(metrics_out, indent=2, ensure_ascii=False), encoding="utf-8",
        )

        coef_df = pd.DataFrame(selected.get("coef", []))
        coef_df.to_csv(output_dir / "feature_coefficients.csv", index=False)

    generate_report(results, report_dir / "TRAINING_REPORT.md")
    logger.info("Phase 2 complete.")


if __name__ == "__main__":
    main()
