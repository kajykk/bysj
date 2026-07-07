from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class ExperimentMetrics:
    @staticmethod
    def metrics(
        y_true: list[int], y_pred: list[int], y_score: list[float]
    ) -> dict[str, float | bool]:
        from sklearn.metrics import (
            accuracy_score,
            precision_recall_fscore_support,
            roc_auc_score,
        )

        acc = accuracy_score(y_true, y_pred)
        # L-10 修复：根据 y_true 类别数动态选择 average 参数。
        # C-Svc-7 修复：当 y_true 仅含单一类别（全 0 或全 1）时，
        # average="binary" 仍要求 pos_label=1 存在，会抛 ValueError。
        # 修复：当 num_classes < 2 时回退到 "micro"（按样本平均），
        # 避免 precision_recall_fscore_support 在单类场景下崩溃。
        num_classes = len(np.unique(y_true))
        if num_classes >= 2:
            average_param = "binary" if num_classes == 2 else "weighted"
        else:
            # 单类场景：micro 等价于 accuracy，避免依赖 pos_label
            average_param = "micro"
        precision, recall, f1, _ = precision_recall_fscore_support(
            y_true, y_pred, average=average_param, zero_division=0
        )
        # L-Svc-3 修复：AUC 失败静默降级 0.5 会误导调用方认为指标可信，
        # 增加 auc_reliable 标记，失败时显式标注 False 供下游判断/展示
        auc_reliable = True
        try:
            # 单类 y_true 时 roc_auc_score 会抛 ValueError，已捕获
            auc = roc_auc_score(y_true, y_score)
        except Exception as exc:
            # M-L 修复：记录 AUC 计算失败原因，避免静默降级为 0.5 掩盖数据问题
            # C-Svc-7：单类场景也会走此分支，记录更详细原因便于排查
            logger.warning(
                "ExperimentMetrics: roc_auc_score failed (num_classes=%d, y_true unique=%s), falling back to 0.5: %s",
                num_classes,
                np.unique(y_true).tolist(),
                exc,
            )
            auc = 0.5
            auc_reliable = False
        return {
            "accuracy": round(float(acc), 4),
            "precision": round(float(precision), 4),
            "recall": round(float(recall), 4),
            "f1": round(float(f1), 4),
            "auc": round(float(auc), 4),
            "auc_reliable": auc_reliable,
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
    def prediction_samples(
        y_true: list[int], y_pred: list[int], y_score: list[float], limit: int = 12
    ) -> list[dict[str, Any]]:
        samples: list[dict[str, Any]] = []
        for idx, (t, p, s) in enumerate(zip(y_true, y_pred, y_score)):
            samples.append(
                {
                    "index": idx,
                    "true_label": int(t),
                    "pred_label": int(p),
                    "score": round(float(s), 4),
                }
            )
            if len(samples) >= limit:
                break
        return samples

    @staticmethod
    def eval_history(
        y_true: list[int],
        y_pred: list[int],
        y_score: list[float],
        split: str,
        metrics: dict[str, float],
    ) -> list[dict[str, Any]]:
        return [
            {
                "split": split,
                "sample_count": len(y_true),
                "accuracy": metrics.get("accuracy", 0.0),
                "precision": metrics.get("precision", 0.0),
                "recall": metrics.get("recall", 0.0),
                "f1": metrics.get("f1", 0.0),
                "auc": metrics.get("auc", 0.5),
                "confusion_matrix": ExperimentMetrics.confusion_matrix(y_true, y_pred),
                "prediction_preview": ExperimentMetrics.prediction_samples(
                    y_true, y_pred, y_score, limit=5
                ),
            }
        ]

    @staticmethod
    def build_confusion_heatmap(cm: dict[str, int]) -> list[list[int]]:
        return [[cm.get("tn", 0), cm.get("fp", 0)], [cm.get("fn", 0), cm.get("tp", 0)]]
