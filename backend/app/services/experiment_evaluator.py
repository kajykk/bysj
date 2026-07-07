from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from app.core.config import settings
from app.services.experiment_metrics import ExperimentMetrics

logger = logging.getLogger(__name__)

TRAINED_ROOT = Path(settings.model_dir) / "trained"


class ExperimentEvaluator:
    def trained_model_dir(self, model_name: str) -> Path:
        model_dir = TRAINED_ROOT / model_name
        legacy_dir = model_dir / "checkpoint-best"
        if legacy_dir.exists():
            return legacy_dir
        if model_dir.exists():
            return model_dir
        raise FileNotFoundError(f"模型目录不存在: {model_dir}")

    def predict(
        self, df: pd.DataFrame, model_name: str
    ) -> tuple[list[int], list[int], list[float]]:
        if "label" not in df.columns:
            raise ValueError("评估数据缺少必要列: label")
        if df.empty:
            raise ValueError("评估数据为空")

        model_dir = self.trained_model_dir(model_name)
        if (model_dir / "physiological_model.pkl").exists():
            # ML-005 修复：使用安全加载器（路径校验 + 大小校验 + 审计日志）
            from app.core.safe_pickle import safe_joblib_load

            model = safe_joblib_load(
                model_dir / "physiological_model.pkl",
                trusted_root=TRAINED_ROOT,
                model_id=f"experiment/{model_name}",
            )
            feature_cols = [
                "sleep_hours",
                "sleep_quality",
                "exercise_minutes",
                "heart_rate",
                "systolic_bp",
                "diastolic_bp",
                "steps",
            ]
            missing = set(feature_cols) - set(df.columns)
            if missing:
                raise ValueError(f"评估数据缺少必要列: {', '.join(sorted(missing))}")
            X = df[feature_cols].astype(float)
            y_true = df["label"].astype(int).tolist()
            y_pred = model.predict(X).astype(int).tolist()
            # H-Svc-6 修复：并非所有 sklearn 分类器都有 predict_proba（如 SVC 默认 probability=False）
            # 缺失时改用 decision_function + sigmoid 归一化，再不行则用 0.5 兜底
            if hasattr(model, "predict_proba"):
                y_score = model.predict_proba(X)[:, 1].astype(float).tolist()
            elif hasattr(model, "decision_function"):
                scores = model.decision_function(X)
                y_score = (1 / (1 + np.exp(-scores))).astype(float).tolist()
            else:
                y_score = [0.5] * len(y_true)
            return y_true, y_pred, y_score

        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        if "text" not in df.columns:
            raise ValueError("评估数据缺少必要列: text")

        tokenizer = AutoTokenizer.from_pretrained(model_dir)
        model = AutoModelForSequenceClassification.from_pretrained(model_dir)
        model.eval()
        y_true = df["label"].astype(int).tolist()
        y_pred: list[int] = []
        y_score: list[float] = []
        for text in df["text"].astype(str).tolist():
            inputs = tokenizer(
                text, return_tensors="pt", truncation=True, padding=True, max_length=128
            )
            with torch.no_grad():
                outputs = model(**inputs)
                logits = outputs.logits
                probs = torch.softmax(logits, dim=-1)[0]
                y_pred.append(int(torch.argmax(probs).item()))
                y_score.append(
                    float(probs[1].item())
                    if probs.shape[-1] > 1
                    else float(probs[0].item())
                )
        return y_true, y_pred, y_score

    def evaluate(self, df: pd.DataFrame, model_name: str, split: str) -> dict[str, Any]:
        y_true, y_pred, y_score = self.predict(df, model_name)
        metrics = ExperimentMetrics.metrics(y_true, y_pred, y_score)
        cm = ExperimentMetrics.confusion_matrix(y_true, y_pred)
        return {
            "model_name": model_name,
            "split": split,
            "metrics": metrics,
            "confusion_matrix": cm,
            "prediction_samples": ExperimentMetrics.prediction_samples(
                y_true, y_pred, y_score
            ),
            "eval_history": ExperimentMetrics.eval_history(
                y_true, y_pred, y_score, split=split, metrics=metrics
            ),
        }

    def compare(self, df: pd.DataFrame, model_names: list[str]) -> dict[str, Any]:
        results = []
        for model_name in model_names:
            # M-Svc-16 修复：单个模型评估失败不影响整体比较，记录错误后继续评估其他模型
            try:
                y_true, y_pred, y_score = self.predict(df, model_name)
                metrics = ExperimentMetrics.metrics(y_true, y_pred, y_score)
                results.append({"model_name": model_name, **metrics})
            except Exception as exc:
                logger.exception("evaluate model %s failed: %s", model_name, exc)
                # 提供 f1/auc 默认值，保证后续 sort 不抛 KeyError
                results.append(
                    {
                        "model_name": model_name,
                        "error": str(exc),
                        "f1": 0.0,
                        "auc": 0.0,
                    }
                )
        results.sort(key=lambda x: (x["f1"], x["auc"]), reverse=True)
        return {"results": results}
