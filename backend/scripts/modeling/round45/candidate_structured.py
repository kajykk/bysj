#!/usr/bin/env python3
"""ROUND_45 离线候选：结构化特征去重对照。

不写生产工件，只输出到 outputs/candidates/round45/。
固定 v1.23 的 train/validation/test 切分与 Setting B（Mendeley x5）权重，
比较 baseline 12 特征与去重特征集的 test 指标。
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = PROJECT_ROOT / "data" / "processed" / "v1_23_external"
PRODUCTION_MODEL = PROJECT_ROOT / "backend" / "models" / "v1.23_external_lr" / "model.pkl"
OUT_DIR = PROJECT_ROOT / "outputs" / "candidates" / "round45"

BASE_FEATURES = [
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
SOURCE = "source"
MENDELEY_WEIGHT = 5.0

FEATURE_SETS = {
    "baseline_12": BASE_FEATURES,
    "drop_academic_11": [c for c in BASE_FEATURES if c != "academic_pressure"],
    "drop_anxiety_11": [c for c in BASE_FEATURES if c != "anxiety"],
    "drop_both_10": [
        c for c in BASE_FEATURES if c not in ("academic_pressure", "anxiety")
    ],
}


def build_pipeline(features: list[str]) -> Pipeline:
    preprocessor = ColumnTransformer(
        [
            (
                "num",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="median")),
                        ("scaler", StandardScaler()),
                    ]
                ),
                features,
            )
        ]
    )
    return Pipeline(
        [
            ("preprocessor", preprocessor),
            (
                "classifier",
                LogisticRegression(random_state=42, max_iter=2000, solver="lbfgs"),
            ),
        ]
    )


def metrics(y_true: np.ndarray, proba: np.ndarray) -> dict:
    pred = (proba >= 0.5).astype(int)
    return {
        "n": int(len(y_true)),
        "accuracy": round(float(accuracy_score(y_true, pred)), 4),
        "precision": round(float(precision_score(y_true, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y_true, proba)), 4),
        "brier": round(float(brier_score_loss(y_true, proba)), 4),
        "positive_rate": round(float(pred.mean()), 4),
    }


def fit_candidate(train: pd.DataFrame, val: pd.DataFrame, test: pd.DataFrame, features: list[str]) -> dict:
    weights = np.where(train[SOURCE] == "mendeley", MENDELEY_WEIGHT, 1.0)
    pipe = build_pipeline(features)
    pipe.fit(train[features], train[TARGET], classifier__sample_weight=weights)
    return {
        "features": features,
        "metrics_val": metrics(
            val[TARGET].to_numpy(), pipe.predict_proba(val[features])[:, 1]
        ),
        "metrics_test": metrics(
            test[TARGET].to_numpy(), pipe.predict_proba(test[features])[:, 1]
        ),
        "coefficients": {
            name: round(float(coef), 6)
            for name, coef in zip(features, pipe.named_steps["classifier"].coef_[0])
        },
        "intercept": round(float(pipe.named_steps["classifier"].intercept_[0]), 8),
    }


def main() -> None:
    train = pd.read_csv(DATA_DIR / "train.csv")
    val = pd.read_csv(DATA_DIR / "validation.csv")
    test = pd.read_csv(DATA_DIR / "test.csv")

    results: dict[str, dict] = {
        "data": {
            "train": len(train),
            "validation": len(val),
            "test": len(test),
            "positive_rate_test": round(float(test[TARGET].mean()), 4),
            "sample_weight_mendeley": MENDELEY_WEIGHT,
        }
    }

    for name, features in FEATURE_SETS.items():
        results[name] = fit_candidate(train, val, test, features)
        print(
            f"{name:20s} test_f1={results[name]['metrics_test']['f1']:.4f} "
            f"auc={results[name]['metrics_test']['roc_auc']:.4f} "
            f"brier={results[name]['metrics_test']['brier']:.4f}"
        )

    if PRODUCTION_MODEL.exists():
        prod = joblib.load(PRODUCTION_MODEL)
        # 生产引擎加载时会补 _fill_dtype（旧 sklearn 工件在新版本下的兼容补丁）。
        for item in prod.named_steps["preprocessor"].transformers_:
            transformer = item[1]
            imputer = getattr(transformer, "named_steps", {}).get("imputer")
            if imputer is not None and not hasattr(imputer, "_fill_dtype") and hasattr(imputer, "_fit_dtype"):
                imputer._fill_dtype = imputer._fit_dtype
        prod_features = list(getattr(prod, "feature_names_in_", BASE_FEATURES))
        proba = prod.predict_proba(test[prod_features])[:, 1]
        results["production_v1_23"] = {
            "features": prod_features,
            "metrics_test": metrics(test[TARGET].to_numpy(), proba),
        }
        print(
            f"{'production_v1_23':20s} test_f1={results['production_v1_23']['metrics_test']['f1']:.4f} "
            f"auc={results['production_v1_23']['metrics_test']['roc_auc']:.4f} "
            f"brier={results['production_v1_23']['metrics_test']['brier']:.4f}"
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "structured_candidates_2026-11-01.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written: {out}")


if __name__ == "__main__":
    main()
