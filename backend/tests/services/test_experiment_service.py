"""Tests for ExperimentService."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

import pandas as pd

from app.services.experiment_service import ExperimentService


class TestExperimentService:
    """Test experiment service."""

    def test_init(self):
        """TC-COV-EXP-011: Service initialization."""
        service = ExperimentService()
        assert service.data is not None
        assert service.trainer is not None
        assert service.evaluator is not None

    @patch("app.services.experiment_service.ExperimentDataManager")
    def test_import_dataset(self, mock_data_cls):
        """TC-COV-EXP-012: Import dataset delegates to data manager."""
        mock_data = MagicMock()
        mock_data.import_dataset.return_value = {"status": "ok", "rows": 100}
        mock_data.train_path.return_value = "/tmp/train.csv"
        mock_data_cls.return_value = mock_data

        service = ExperimentService()
        result = service.import_dataset("ds1", "csv", 0.7, 0.15, 0.15)

        mock_data.import_dataset.assert_called_once_with("ds1", "csv", 0.7, 0.15, 0.15)
        mock_data.export_dataset_snapshot.assert_called_once_with("ds1")
        assert result["status"] == "ok"

    @patch("app.services.experiment_service.pd.read_csv")
    @patch("app.services.experiment_service.ExperimentTrainer")
    @patch("app.services.experiment_service.ExperimentDataManager")
    def test_train_model_physiological(self, mock_data_cls, mock_trainer_cls, mock_read_csv):
        """TC-COV-EXP-013: Train physiological model path."""
        mock_data = MagicMock()
        mock_data.train_path.return_value = "/tmp/train.csv"
        mock_data.val_path.return_value = "/tmp/val.csv"
        mock_data_cls.return_value = mock_data

        mock_trainer = MagicMock()
        mock_trainer.train_physiological_model.return_value = {
            "train_loss": [0.5],
            "val_loss": [0.4],
            "val_accuracy": [0.9],
            "train_history": [],
            "trainer_log_history": [],
            "eval_history": [],
            "message": "训练完成",
        }
        mock_trainer_cls.return_value = mock_trainer

        mock_read_csv.return_value = pd.DataFrame({"a": [1, 2]})

        service = ExperimentService()
        result = service.train_model("ds1", "physiological_v1", 2, 8, 0.001)

        assert result["model_name"] == "physiological_v1"
        assert result["status"] == "completed"
        assert result["epochs"] == 2
        mock_trainer.train_physiological_model.assert_called_once()

    @patch("app.services.experiment_service.pd.read_csv")
    @patch("app.services.experiment_service.ExperimentTrainer")
    @patch("app.services.experiment_service.ExperimentDataManager")
    def test_train_model_standard(self, mock_data_cls, mock_trainer_cls, mock_read_csv):
        """TC-COV-EXP-014: Train standard model path."""
        mock_data = MagicMock()
        mock_data.train_path.return_value = "/tmp/train.csv"
        mock_data.val_path.return_value = "/tmp/val.csv"
        mock_data_cls.return_value = mock_data

        mock_trainer = MagicMock()
        mock_trainer.train.return_value = {
            "train_loss": [0.5],
            "val_loss": [0.4],
            "val_accuracy": [0.9],
            "train_history": [],
            "trainer_log_history": [],
            "eval_history": [],
            "message": "训练完成",
        }
        mock_trainer_cls.return_value = mock_trainer

        mock_read_csv.return_value = pd.DataFrame({"a": [1, 2]})

        service = ExperimentService()
        result = service.train_model("ds1", "bert_v1", 2, 8, 0.001)

        assert result["model_name"] == "bert_v1"
        assert result["status"] == "completed"
        mock_trainer.train.assert_called_once()
        mock_trainer.save_bundle.assert_called_once()

    @patch("app.services.experiment_service.pd.read_csv")
    @patch("app.services.experiment_service.ExperimentEvaluator")
    @patch("app.services.experiment_service.ExperimentDataManager")
    def test_evaluate_model_standard(self, mock_data_cls, mock_eval_cls, mock_read_csv):
        """TC-COV-EXP-015: Evaluate standard model path."""
        mock_data = MagicMock()
        mock_data.test_path.return_value = "/tmp/test.csv"
        mock_data_cls.return_value = mock_data

        mock_eval = MagicMock()
        mock_eval.evaluate.return_value = {
            "metrics": {"accuracy": 0.9},
            "confusion_matrix": {"tp": 10},
        }
        mock_eval_cls.return_value = mock_eval

        mock_read_csv.return_value = pd.DataFrame({"a": [1, 2]})

        service = ExperimentService()
        result = service.evaluate_model("ds1", "bert_v1", "test")

        assert result["dataset_name"] == "ds1"
        assert "metrics" in result
        mock_eval.evaluate.assert_called_once()

    @patch("app.services.experiment_service.pd.read_csv")
    @patch("app.services.experiment_service.ExperimentEvaluator")
    @patch("app.services.experiment_service.ExperimentDataManager")
    def test_evaluate_model_physiological(self, mock_data_cls, mock_eval_cls, mock_read_csv):
        """TC-COV-EXP-016: Evaluate physiological model path."""
        mock_data = MagicMock()
        mock_data.load_physiological_dataset.return_value = pd.DataFrame({"a": [1, 2]})
        mock_data_cls.return_value = mock_data

        mock_eval = MagicMock()
        mock_eval.evaluate.return_value = {
            "metrics": {"accuracy": 0.85},
        }
        mock_eval_cls.return_value = mock_eval

        service = ExperimentService()
        result = service.evaluate_model("ds1", "physiological_v1", "test")

        mock_data.load_physiological_dataset.assert_called_once_with("ds1")
        mock_eval.evaluate.assert_called_once()

    @patch("app.services.experiment_service.pd.read_csv")
    @patch("app.services.experiment_service.ExperimentEvaluator")
    @patch("app.services.experiment_service.ExperimentDataManager")
    def test_compare_models(self, mock_data_cls, mock_eval_cls, mock_read_csv):
        """TC-COV-EXP-017: Compare models delegates to evaluator."""
        mock_data = MagicMock()
        mock_data.test_path.return_value = "/tmp/test.csv"
        mock_data_cls.return_value = mock_data

        mock_eval = MagicMock()
        mock_eval.compare.return_value = {
            "results": [
                {"model_name": "m1", "f1": 0.9, "auc": 0.95},
                {"model_name": "m2", "f1": 0.85, "auc": 0.92},
            ],
        }
        mock_eval_cls.return_value = mock_eval

        mock_read_csv.return_value = pd.DataFrame({"a": [1, 2]})

        service = ExperimentService()
        result = service.compare_models("ds1", ["m1", "m2"])

        assert result["dataset_name"] == "ds1"
        assert len(result["results"]) == 2
        assert result["message"] == "对比实验完成"
        mock_eval.compare.assert_called_once()
