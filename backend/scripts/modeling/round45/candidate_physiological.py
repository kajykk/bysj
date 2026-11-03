#!/usr/bin/env python3
"""ROUND_45 离线候选：生理派生特征重构对照。

不写生产工件，只输出到 outputs/candidates/round45/。
复用 ROUND_29 的 train-only cleaner/scaler、固定切分与超参，比较：
  current_13     现生产 13 特征（对照，应复现 metrics.json）
  raw7_bp_8      7 原始特征 + bp_category
  corrected_13   activity_intensity = steps / max(exercise, 30)

同时输出运动/睡眠/心率扫描，检查非单调性是否消失。
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss

PROJECT_ROOT = Path(__file__).resolve().parents[4]
BACKEND = Path(__file__).resolve().parents[3]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.ml.data_loader import load_depresjon_data  # noqa: E402
from app.ml.feature_engineering import engineer_features  # noqa: E402
from app.ml.model_loader import load_feature_names  # noqa: E402

RETRAIN_04 = Path(__file__).resolve().parents[1] / "eval" / "v1_29" / "04_round29_retrain_physiological.py"
OUT_DIR = PROJECT_ROOT / "outputs" / "candidates" / "round45"

RAW_FIELDS = [
    "sleep_hours",
    "sleep_quality",
    "exercise_minutes",
    "heart_rate",
    "systolic_bp",
    "diastolic_bp",
    "steps",
]
DEFAULTS = {
    "sleep_hours": 7.0,
    "sleep_quality": 3.0,
    "exercise_minutes": 30.0,
    "heart_rate": 70.0,
    "systolic_bp": 120.0,
    "diastolic_bp": 80.0,
    "steps": 5000.0,
}


def load_retrain_module():
    spec = importlib.util.spec_from_file_location("round29_retrain", RETRAIN_04)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FeatureAdapter:
    """代理 eval01：只覆盖 build_features，其余指标函数原样复用。"""

    def __init__(self, base, mode: str):
        self._base = base
        self._mode = mode

    def __getattr__(self, name):
        return getattr(self._base, name)

    def build_features(self, df, idx, cleaner, feats):
        cleaned = cleaner.transform(df.iloc[idx])
        engineered = engineer_features(cleaned)
        if self._mode == "corrected":
            engineered = engineered.copy()
            exercise = cleaned["exercise_minutes"].clip(lower=30.0)
            engineered["activity_intensity"] = cleaned["steps"] / exercise
        return engineered[feats].values.astype(np.float32)


def score_payload(pipe, feats: list[str], mode: str, payload: dict) -> float:
    raw = {**DEFAULTS, **payload}
    cleaned = pipe["cleaner"].transform_single(raw)
    engineered = engineer_features(pd.DataFrame([cleaned]))
    if mode == "corrected":
        engineered = engineered.copy()
        engineered["activity_intensity"] = cleaned["steps"] / max(
            float(cleaned["exercise_minutes"]), 30.0
        )
    X = engineered[feats].values.astype(np.float32)
    scaled = pipe["scaler"].transform(X)
    return float(np.asarray(pipe["model"].predict_proba(scaled)).reshape(-1)[0])


def sweep(pipe, feats: list[str], mode: str) -> dict:
    base = dict(DEFAULTS)
    out: dict[str, dict[str, float]] = {}
    for field, values in {
        "exercise_minutes": [0, 1, 5, 15, 30, 60],
        "sleep_hours": [3, 4, 7, 9, 15],
        "heart_rate": [70, 85, 100, 140],
    }.items():
        out[field] = {
            str(v): round(score_payload(pipe, feats, mode, {**base, field: v}), 4)
            for v in values
        }
    return out


def main() -> None:
    mod = load_retrain_module()
    e01 = mod._load_eval01()
    df = load_depresjon_data()
    y = df["depression_label"].values.astype(np.int64)
    tri, vai, tei = e01.split_indices(y)
    assert (len(tri), len(vai), len(tei)) == (719, 153, 157)
    e01._assert_split_matches(y, tri, vai, tei)
    all_feats = load_feature_names()
    base_hp = mod._load_hyperparameters()

    candidates = {
        "current_13": (all_feats, "current"),
        "raw7_bp_8": (
            [f for f in all_feats if f in RAW_FIELDS or f == "bp_category"],
            "current",
        ),
        "corrected_13": (all_feats, "corrected"),
    }

    results: dict[str, dict] = {
        "data": {
            "n": int(len(y)),
            "train": int(len(tri)),
            "validation": int(len(vai)),
            "test": int(len(tei)),
            "positive": int((y == 1).sum()),
        }
    }

    for name, (feats, mode) in candidates.items():
        hp = copy.deepcopy(base_hp)
        hp["input_dim"] = len(feats)
        adapter = FeatureAdapter(e01, mode)
        pipe = mod._train_pipeline(adapter, df, y, tri, vai, tei, feats, hp)
        scores = np.asarray(pipe["model"].predict_proba(pipe["scaler"].transform(pipe["X_test"]))).reshape(-1)
        m = e01.threshold_metrics(y[tei], scores)
        result = {
            "features": feats,
            "mode": mode,
            "input_dim": len(feats),
            "best_epoch": int(pipe["history"]["best_epoch"]),
            "metrics_test": {
                "n": int(m["n"]),
                "accuracy": round(float(m["acc"]), 4),
                "precision": round(float(m["prec"]), 4),
                "recall": round(float(m["rec"]), 4),
                "f1": round(float(m["f1"]), 4),
                "roc_auc": round(float(e01.auc_score(y[tei], scores)), 4),
                "auprc": round(float(mod.auprc_score(y[tei], scores)), 4),
                "brier": round(float(brier_score_loss(y[tei], scores)), 4),
                "confusion": {k: int(m[k]) for k in ("TP", "FP", "FN", "TN")},
            },
            "sweep": sweep(pipe, feats, mode),
        }
        results[name] = result
        mt = result["metrics_test"]
        print(
            f"{name:14s} f1={mt['f1']:.4f} auc={mt['roc_auc']:.4f} "
            f"auprc={mt['auprc']:.4f} brier={mt['brier']:.4f} epoch={result['best_epoch']}"
        )
        print(f"  exercise: {result['sweep']['exercise_minutes']}")
        print(f"  sleep   : {result['sweep']['sleep_hours']}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "physio_candidates_2026-11-01.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written: {out}")


if __name__ == "__main__":
    main()
