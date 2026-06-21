"""Tests for ExperimentTrainer."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.services.experiment_trainer import ExperimentTrainer


class TestExperimentTrainer:
    """Test experiment trainer."""

    def test_latest_checkpoint_none(self):
        """TC-COV-EXP-028: latest_checkpoint returns None when no checkpoints."""
        trainer = ExperimentTrainer()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = trainer.latest_checkpoint(Path(tmpdir))
            assert result is None

    def test_latest_checkpoint_found(self):
        """TC-COV-EXP-029: latest_checkpoint returns latest checkpoint."""
        trainer = ExperimentTrainer()
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "checkpoint-100").mkdir()
            (Path(tmpdir) / "checkpoint-200").mkdir()
            result = trainer.latest_checkpoint(Path(tmpdir))
            assert result is not None
            assert result.name == "checkpoint-200"

    def test_trainer_log_history_empty(self):
        """TC-COV-EXP-030: trainer_log_history returns empty when no state."""
        trainer = ExperimentTrainer()
        mock_trainer = MagicMock()
        mock_trainer.state = None
        result = trainer.trainer_log_history(mock_trainer)
        assert result == []

    def test_trainer_log_history_with_logs(self):
        """TC-COV-EXP-031: trainer_log_history extracts log history."""
        trainer = ExperimentTrainer()
        mock_trainer = MagicMock()
        mock_state = MagicMock()
        mock_state.log_history = [{"loss": 0.5}, {"eval_loss": 0.4}]
        mock_trainer.state = mock_state
        result = trainer.trainer_log_history(mock_trainer)
        assert len(result) == 2
        assert result[0]["loss"] == 0.5

    def test_save_bundle_raises_on_missing_artifacts(self):
        """TC-COV-EXP-032: save_bundle raises when artifacts incomplete."""
        trainer = ExperimentTrainer()
        with pytest.raises(RuntimeError, match="不完整"):
            trainer.save_bundle("test_model", {"model_name": "test_model"})

    def test_train_physiological_model_success(self):
        """TC-COV-EXP-033: train_physiological_model returns artifacts."""
        trainer = ExperimentTrainer()
        train_df = pd.DataFrame({
            "sleep_hours": [7.0, 8.0, 6.0],
            "sleep_quality": [3, 4, 2],
            "exercise_minutes": [30, 45, 20],
            "heart_rate": [70, 75, 80],
            "systolic_bp": [120, 130, 110],
            "diastolic_bp": [80, 85, 75],
            "steps": [5000, 8000, 3000],
            "label": [0, 1, 0],
        })
        val_df = pd.DataFrame({
            "sleep_hours": [8.0, 7.0],
            "sleep_quality": [4, 3],
            "exercise_minutes": [45, 30],
            "heart_rate": [75, 70],
            "systolic_bp": [130, 120],
            "diastolic_bp": [85, 80],
            "steps": [8000, 5000],
            "label": [1, 0],
        })
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.services.experiment_trainer.TRAINED_ROOT", Path(tmpdir) / "trained"):
                result = trainer.train_physiological_model(train_df, val_df, "phys_test")

        assert result["model_type"] == "sklearn_logistic_regression"
        assert result["message"] == "生理模型训练完成，模型已保存"
        assert "model" in result

    def test_train_physiological_model_empty_train(self):
        """TC-COV-EXP-034: train_physiological_model raises when train empty."""
        trainer = ExperimentTrainer()
        with pytest.raises(ValueError, match="为空"):
            trainer.train_physiological_model(
                pd.DataFrame(),
                pd.DataFrame({"sleep_hours": [7.0], "sleep_quality": [3], "exercise_minutes": [30], "heart_rate": [70], "systolic_bp": [120], "diastolic_bp": [80], "steps": [5000], "label": [0]}),
                "phys_test",
            )

    def test_train_physiological_model_missing_columns(self):
        """TC-COV-EXP-035: train_physiological_model raises when columns missing."""
        trainer = ExperimentTrainer()
        train_df = pd.DataFrame({"sleep_hours": [7.0], "label": [0]})
        val_df = pd.DataFrame({"sleep_hours": [8.0], "label": [1]})
        with pytest.raises(ValueError, match="缺少必要列"):
            trainer.train_physiological_model(train_df, val_df, "phys_test")

    def test_train_empty_data(self):
        """TC-COV-EXP-036: train raises when data empty."""
        trainer = ExperimentTrainer()
        with pytest.raises(ValueError, match="为空"):
            trainer.train(pd.DataFrame(), pd.DataFrame(), "bert_test", 1, 8, 0.001)

    def test_train_missing_columns(self):
        """TC-COV-EXP-037: train raises when text/label missing."""
        trainer = ExperimentTrainer()
        with pytest.raises(ValueError, match="缺少必要列"):
            trainer.train(
                pd.DataFrame({"text": ["a"]}),
                pd.DataFrame({"text": ["b"]}),
                "bert_test", 1, 8, 0.001,
            )

    def test_predict_labels_fallback(self):
        """TC-COV-EXP-038: _predict_labels returns empty on exception."""
        trainer = ExperimentTrainer()
        mock_trainer = MagicMock()
        mock_trainer.predict.side_effect = Exception("fail")
        result = trainer._predict_labels(mock_trainer, None)
        assert result == []

    def test_predict_scores_fallback(self):
        """TC-COV-EXP-039: _predict_scores returns empty on exception."""
        trainer = ExperimentTrainer()
        mock_trainer = MagicMock()
        mock_trainer.predict.side_effect = Exception("fail")
        result = trainer._predict_scores(mock_trainer, None)
        assert result == []
