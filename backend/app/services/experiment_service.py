from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.experiment_data import ExperimentDataManager
from app.services.experiment_evaluator import ExperimentEvaluator
from app.services.experiment_trainer import ExperimentTrainer


class ExperimentService:
    def __init__(self) -> None:
        self.data = ExperimentDataManager()
        self.trainer = ExperimentTrainer()
        self.evaluator = ExperimentEvaluator()

    def import_dataset(self, dataset_name: str, source_type: str, train_ratio: float, val_ratio: float, test_ratio: float) -> dict[str, Any]:
        result = self.data.import_dataset(dataset_name, source_type, train_ratio, val_ratio, test_ratio)
        self.data.export_dataset_snapshot(dataset_name)
        return result

    def train_model(self, dataset_name: str, model_name: str, epochs: int, batch_size: int, learning_rate: float) -> dict[str, Any]:
        train_df = pd.read_csv(self.data.train_path(dataset_name))
        val_df = pd.read_csv(self.data.val_path(dataset_name))
        if model_name.startswith("physiological"):
            artifacts = self.trainer.train_physiological_model(train_df, val_df, model_name)
            return {
                "dataset_name": dataset_name,
                "model_name": model_name,
                "status": "completed",
                "epochs": epochs,
                "batch_size": batch_size,
                "learning_rate": learning_rate,
                "train_loss": artifacts.get("train_loss", []),
                "val_loss": artifacts.get("val_loss", []),
                "val_accuracy": artifacts.get("val_accuracy", []),
                "train_history": artifacts.get("train_history", []),
                "trainer_log_history": artifacts.get("trainer_log_history", []),
                "eval_history": artifacts.get("eval_history", []),
                "message": artifacts.get("message", "训练完成"),
            }
        artifacts = self.trainer.train(train_df, val_df, model_name, epochs, batch_size, learning_rate)
        self.trainer.save_bundle(model_name, artifacts)
        return {
            "dataset_name": dataset_name,
            "model_name": model_name,
            "status": "completed",
            "epochs": epochs,
            "batch_size": batch_size,
            "learning_rate": learning_rate,
            "train_loss": artifacts.get("train_loss", []),
            "val_loss": artifacts.get("val_loss", []),
            "val_accuracy": artifacts.get("val_accuracy", []),
            "train_history": artifacts.get("train_history", []),
            "trainer_log_history": artifacts.get("trainer_log_history", []),
            "eval_history": artifacts.get("eval_history", []),
            "message": artifacts.get("message", "训练完成"),
        }

    def evaluate_model(self, dataset_name: str, model_name: str, split: str) -> dict[str, Any]:
        if model_name.startswith("physiological"):
            df = self.data.load_physiological_dataset(dataset_name)
        else:
            df = pd.read_csv(self.data.test_path(dataset_name) if split == "test" else self.data.val_path(dataset_name))
        return {"dataset_name": dataset_name, **self.evaluator.evaluate(df, model_name, split)}

    def compare_models(self, dataset_name: str, model_names: list[str]) -> dict[str, Any]:
        df = pd.read_csv(self.data.test_path(dataset_name))
        compare = self.evaluator.compare(df, model_names)
        return {"dataset_name": dataset_name, **compare, "message": "对比实验完成"}
