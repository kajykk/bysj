from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.core.config import settings
from app.services.experiment_metrics import ExperimentMetrics

logger = logging.getLogger(__name__)

TRAINED_ROOT = Path(settings.model_dir) / "trained"
DEFAULT_BERT_MODEL = "bert-base-chinese"


class ExperimentTrainer:
    def train(self, train_df: pd.DataFrame, val_df: pd.DataFrame, model_name: str, epochs: int, batch_size: int, learning_rate: float) -> dict[str, Any]:
        import torch
        from datasets import Dataset
        from transformers import AutoModelForSequenceClassification, AutoTokenizer, Trainer, TrainingArguments, TrainerCallback

        if train_df.empty or val_df.empty:
            raise ValueError("训练或验证数据为空")
        for frame_name, frame in (("train", train_df), ("validation", val_df)):
            missing = {"text", "label"} - set(frame.columns)
            if missing:
                raise ValueError(f"{frame_name} 数据缺少必要列: {', '.join(sorted(missing))}")

        tokenizer = AutoTokenizer.from_pretrained(DEFAULT_BERT_MODEL)

        def tokenize(batch: dict[str, list[Any]]) -> dict[str, Any]:
            return tokenizer(batch["text"], truncation=True, padding="max_length", max_length=128)

        train_ds = Dataset.from_pandas(train_df[["text", "label"]].rename(columns={"label": "labels"}), preserve_index=False).map(tokenize, batched=True)
        val_ds = Dataset.from_pandas(val_df[["text", "label"]].rename(columns={"label": "labels"}), preserve_index=False).map(tokenize, batched=True)
        if not len(train_ds) or not len(val_ds):
            raise ValueError("训练/验证数据集构建失败")
        cols_to_remove = [c for c in train_ds.column_names if c not in {"input_ids", "token_type_ids", "attention_mask", "labels"}]
        if cols_to_remove:
            train_ds = train_ds.remove_columns(cols_to_remove)
        cols_to_remove = [c for c in val_ds.column_names if c not in {"input_ids", "token_type_ids", "attention_mask", "labels"}]
        if cols_to_remove:
            val_ds = val_ds.remove_columns(cols_to_remove)
        train_ds.set_format(type="torch")
        val_ds.set_format(type="torch")

        model = AutoModelForSequenceClassification.from_pretrained(DEFAULT_BERT_MODEL, num_labels=2)
        model_dir = TRAINED_ROOT / model_name
        model_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_dir = model_dir / "checkpoints"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        class EpochHistoryCallback(TrainerCallback):
            def __init__(self) -> None:
                self.history: list[dict[str, Any]] = []
                self.current_train_loss: float | None = None

            def on_log(self, args: Any, state: Any, control: Any, logs: dict[str, float] | None = None, **kwargs: Any) -> Any:
                if not logs:
                    return control
                if "loss" in logs:
                    self.current_train_loss = float(logs["loss"])
                if "eval_loss" in logs:
                    self.history.append({
                        "epoch": int(getattr(state, "epoch", len(self.history) + 1) or len(self.history) + 1),
                        "train_loss": round(float(self.current_train_loss or logs.get("loss", 0.0)), 4),
                        "val_loss": round(float(logs.get("eval_loss", 0.0)), 4),
                        "val_accuracy": round(float(logs.get("eval_accuracy", logs.get("eval_acc", 0.0))), 4),
                    })
                return control

        history_callback = EpochHistoryCallback()
        training_args = TrainingArguments(
            output_dir=str(checkpoint_dir),
            learning_rate=learning_rate,
            per_device_train_batch_size=batch_size,
            per_device_eval_batch_size=batch_size,
            num_train_epochs=epochs,
            evaluation_strategy="epoch",
            save_strategy="epoch",
            save_total_limit=2,
            logging_strategy="epoch",
            load_best_model_at_end=True,
            metric_for_best_model="f1",
            greater_is_better=True,
            report_to=[],
            seed=42,
        )

        def compute_metrics(eval_pred: Any) -> dict[str, float]:
            logits, labels = eval_pred
            preds = np.argmax(logits, axis=-1)
            probs = torch.softmax(torch.tensor(logits), dim=-1)[:, 1].detach().cpu().numpy()
            labels_list = labels.tolist() if hasattr(labels, "tolist") else list(labels)
            return ExperimentMetrics.metrics(labels_list, preds.tolist(), probs.tolist())

        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=train_ds,
            eval_dataset=val_ds,
            tokenizer=tokenizer,
            compute_metrics=compute_metrics,
            callbacks=[history_callback],
        )
        latest_checkpoint = self.latest_checkpoint(checkpoint_dir)
        train_output = trainer.train(resume_from_checkpoint=str(latest_checkpoint) if latest_checkpoint else None)
        eval_result = trainer.evaluate(val_ds)
        train_history = history_callback.history or [{
            "epoch": 1,
            "train_loss": round(float(getattr(train_output, "training_loss", 0.0) or 0.0), 4),
            "val_loss": round(float(eval_result.get("eval_loss", 0.0)), 4),
            "val_accuracy": round(float(eval_result.get("eval_accuracy", eval_result.get("eval_acc", 0.0))), 4),
        }]

        return {
            "model_type": "huggingface_bert",
            "base_model": DEFAULT_BERT_MODEL,
            "train_loss": [row["train_loss"] for row in train_history],
            "val_loss": [row["val_loss"] for row in train_history],
            "val_accuracy": [row["val_accuracy"] for row in train_history],
            "train_history": train_history,
            "trainer_log_history": self.trainer_log_history(trainer),
            "eval_history": ExperimentMetrics.eval_history(val_df["label"].astype(int).tolist(), self._predict_labels(trainer, val_ds), self._predict_scores(trainer, val_ds), split="validation", metrics={k.replace("eval_", ""): v for k, v in eval_result.items() if k.startswith("eval_")}),
            "trainer_state": getattr(train_output, "metrics", {}) or {},
            "eval_result": eval_result,
            "message": "HuggingFace BERT 训练完成，模型已保存",
            "trainer": trainer,
            "tokenizer": tokenizer,
            "model": model,
        }

    def save_bundle(self, model_name: str, artifacts: dict[str, Any]) -> Path:
        save_dir = TRAINED_ROOT / model_name
        save_dir.mkdir(parents=True, exist_ok=True)
        trainer = artifacts.pop("trainer", None)
        tokenizer = artifacts.pop("tokenizer", None)
        model = artifacts.pop("model", None)
        if trainer is None or tokenizer is None or model is None:
            raise RuntimeError("训练产物不完整，无法保存模型")
        trainer.save_model(str(save_dir))
        tokenizer.save_pretrained(str(save_dir))
        summary = {**artifacts, "model_name": model_name, "saved_at": str(save_dir)}
        (save_dir / "training_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        (save_dir / "trainer_log_history.json").write_text(json.dumps(summary.get("trainer_log_history", []), ensure_ascii=False, indent=2), encoding="utf-8")
        (save_dir / "eval_history.json").write_text(json.dumps(summary.get("eval_history", []), ensure_ascii=False, indent=2), encoding="utf-8")
        return save_dir

    def latest_checkpoint(self, checkpoint_dir: Path) -> Path | None:
        if not checkpoint_dir.exists():
            return None
        checkpoints = sorted([p for p in checkpoint_dir.iterdir() if p.is_dir() and p.name.startswith("checkpoint-")])
        return checkpoints[-1] if checkpoints else None

    def trainer_log_history(self, trainer: Any) -> list[dict[str, Any]]:
        state = getattr(trainer, "state", None)
        history = getattr(state, "log_history", None) if state is not None else None
        return [dict(item) for item in history] if history else []

    def train_physiological_model(self, train_df: pd.DataFrame, val_df: pd.DataFrame, model_name: str = "physiological_fusion_proxy") -> dict[str, Any]:
        if train_df.empty or val_df.empty:
            raise ValueError("生理训练或验证数据为空")
        required = {"sleep_hours", "sleep_quality", "exercise_minutes", "heart_rate", "systolic_bp", "diastolic_bp", "steps", "label"}
        for frame_name, frame in (("train", train_df), ("validation", val_df)):
            missing = required - set(frame.columns)
            if missing:
                raise ValueError(f"{frame_name} 数据缺少必要列: {', '.join(sorted(missing))}")

        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        feature_cols = ["sleep_hours", "sleep_quality", "exercise_minutes", "heart_rate", "systolic_bp", "diastolic_bp", "steps"]
        X_train = train_df[feature_cols].astype(float)
        y_train = train_df["label"].astype(int)
        X_val = val_df[feature_cols].astype(float)
        y_val = val_df["label"].astype(int)

        model = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=500)),
        ])
        model.fit(X_train, y_train)
        val_pred = model.predict(X_val)
        val_proba = model.predict_proba(X_val)[:, 1]
        metrics = ExperimentMetrics.metrics(y_val.tolist(), val_pred.tolist(), val_proba.tolist())
        model_dir = TRAINED_ROOT / model_name
        model_dir.mkdir(parents=True, exist_ok=True)
        import joblib
        joblib.dump(model, model_dir / "physiological_model.pkl")
        return {
            "model_type": "sklearn_logistic_regression",
            "base_model": "physiological_features",
            "train_loss": [],
            "val_loss": [],
            "val_accuracy": [metrics.get("accuracy", 0.0)],
            "train_history": [],
            "trainer_log_history": [],
            "eval_history": [{"split": "validation", **metrics}],
            "trainer_state": {},
            "eval_result": metrics,
            "message": "生理模型训练完成，模型已保存",
            "model": model,
        }

    def _predict_labels(self, trainer: Any, dataset: Any) -> list[int]:
        try:
            preds = trainer.predict(dataset)
            return np.argmax(preds.predictions, axis=-1).astype(int).tolist()
        except Exception:
            return []

    def _predict_scores(self, trainer: Any, dataset: Any) -> list[float]:
        try:
            import torch
            preds = trainer.predict(dataset)
            probs = torch.softmax(torch.tensor(preds.predictions), dim=-1)[:, 1].detach().cpu().numpy()
            return probs.astype(float).tolist()
        except Exception:
            return []
