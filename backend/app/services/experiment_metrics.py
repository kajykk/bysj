from __future__ import annotations

from typing import Any

import numpy as np


class ExperimentMetrics:
    @staticmethod
    def metrics(y_true: list[int], y_pred: list[int], y_score: list[float]) -> dict[str, float]:
        from sklearn.metrics import accuracy_score, precision_recall_fscore_support, roc_auc_score

        acc = accuracy_score(y_true, y_pred)
        precision, recall, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)
        try:
            auc = roc_auc_score(y_true, y_score)
        except Exception:
            auc = 0.5
        return {
            "accuracy": round(float(acc), 4),
            "precision": round(float(precision), 4),
            "recall": round(float(recall), 4),
            "f1": round(float(f1), 4),
            "auc": round(float(auc), 4),
        }

    @staticmethod
    def confusion_matrix(y_true: list[int], y_pred: list[int]) -> dict[str, int]:
        tp = tn = fp = fn = 0
        for t, p in zip(y_true, y_pred):
            if t == 1 and p == 1:
                tp += 1
            elif t == 0 and p == 0:
                tn += 1
            elif t == 0 and p == 1:
                fp += 1
            elif t == 1 and p == 0:
                fn += 1
        return {"tn": tn, "fp": fp, "fn": fn, "tp": tp}

    @staticmethod
    def prediction_samples(y_true: list[int], y_pred: list[int], y_score: list[float], limit: int = 12) -> list[dict[str, Any]]:
        samples: list[dict[str, Any]] = []
        for idx, (t, p, s) in enumerate(zip(y_true, y_pred, y_score)):
            samples.append({"index": idx, "true_label": int(t), "pred_label": int(p), "score": round(float(s), 4)})
            if len(samples) >= limit:
                break
        return samples

    @staticmethod
    def eval_history(y_true: list[int], y_pred: list[int], y_score: list[float], split: str, metrics: dict[str, float]) -> list[dict[str, Any]]:
        return [{
            "split": split,
            "sample_count": len(y_true),
            "accuracy": metrics.get("accuracy", 0.0),
            "precision": metrics.get("precision", 0.0),
            "recall": metrics.get("recall", 0.0),
            "f1": metrics.get("f1", 0.0),
            "auc": metrics.get("auc", 0.5),
            "confusion_matrix": ExperimentMetrics.confusion_matrix(y_true, y_pred),
            "prediction_preview": ExperimentMetrics.prediction_samples(y_true, y_pred, y_score, limit=5),
        }]

    @staticmethod
    def build_confusion_heatmap(cm: dict[str, int]) -> list[list[int]]:
        return [[cm.get("tn", 0), cm.get("fp", 0)], [cm.get("fn", 0), cm.get("tp", 0)]]
