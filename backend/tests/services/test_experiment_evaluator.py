"""Tests for ExperimentEvaluator."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import joblib
import numpy as np
import pandas as pd
import pytest

from app.services.experiment_evaluator import ExperimentEvaluator


class TestExperimentEvaluator:
    """Test experiment evaluator."""

    def test_trained_model_dir_exists(self):
        """TC-COV-EXP-018: trained_model_dir returns existing dir."""
        evaluator = ExperimentEvaluator()
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir) / "trained" / "test_model"
            model_dir.mkdir(parents=True)
            with patch("app.services.experiment_evaluator.TRAINED_ROOT", Path(tmpdir) / "trained"):
                result = evaluator.trained_model_dir("test_model")
                assert result == model_dir

    def test_trained_model_dir_legacy(self):
        """TC-COV-EXP-019: trained_model_dir falls back to checkpoint-best."""
        evaluator = ExperimentEvaluator()
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir) / "trained" / "test_model"
            checkpoint_dir = model_dir / "checkpoint-best"
            checkpoint_dir.mkdir(parents=True)
            with patch("app.services.experiment_evaluator.TRAINED_ROOT", Path(tmpdir) / "trained"):
                result = evaluator.trained_model_dir("test_model")
                assert result == checkpoint_dir

    def test_trained_model_dir_not_found(self):
        """TC-COV-EXP-020: trained_model_dir raises when missing."""
        evaluator = ExperimentEvaluator()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.services.experiment_evaluator.TRAINED_ROOT", Path(tmpdir) / "trained"):
                with pytest.raises(FileNotFoundError, match="模型目录不存在"):
                    evaluator.trained_model_dir("nonexistent")

    def test_predict_missing_label(self):
        """TC-COV-EXP-021: predict raises when label missing."""
        evaluator = ExperimentEvaluator()
        df = pd.DataFrame({"text": ["a", "b"]})
        with pytest.raises(ValueError, match="label"):
            evaluator.predict(df, "any_model")

    def test_predict_empty_df(self):
        """TC-COV-EXP-022: predict raises when df empty."""
        evaluator = ExperimentEvaluator()
        df = pd.DataFrame({"label": pd.Series([], dtype=int)})
        with pytest.raises(ValueError, match="为空"):
            evaluator.predict(df, "any_model")

    def test_predict_physiological_missing_features(self):
        """TC-COV-EXP-023: predict physiological raises when features missing."""
        evaluator = ExperimentEvaluator()
        df = pd.DataFrame({"label": [0, 1], "sleep_hours": [7, 8]})
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir) / "trained" / "phys_model"
            model_dir.mkdir(parents=True)
            (model_dir / "physiological_model.pkl").write_bytes(b"x")
            with patch("app.services.experiment_evaluator.TRAINED_ROOT", Path(tmpdir) / "trained"):
                # ML-005 修复后：predict 使用 safe_joblib_load，mock 目标更新
                with patch("app.core.safe_pickle.safe_joblib_load", return_value=MagicMock()):
                    with pytest.raises(ValueError, match="缺少必要列"):
                        evaluator.predict(df, "phys_model")

    def test_predict_physiological_success(self):
        """TC-COV-EXP-024: predict physiological returns predictions."""
        evaluator = ExperimentEvaluator()
        df = pd.DataFrame({
            "label": [0, 1],
            "sleep_hours": [7.0, 8.0],
            "sleep_quality": [3, 4],
            "exercise_minutes": [30, 45],
            "heart_rate": [70, 75],
            "systolic_bp": [120, 130],
            "diastolic_bp": [80, 85],
            "steps": [5000, 8000],
        })
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([0, 1])
        mock_model.predict_proba.return_value = np.array([[0.3, 0.7], [0.2, 0.8]])

        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir) / "trained" / "phys_model"
            model_dir.mkdir(parents=True)
            (model_dir / "physiological_model.pkl").write_bytes(b"x")
            with patch("app.services.experiment_evaluator.TRAINED_ROOT", Path(tmpdir) / "trained"):
                with patch("app.core.safe_pickle.safe_joblib_load", return_value=mock_model):
                    y_true, y_pred, y_score = evaluator.predict(df, "phys_model")
                    assert y_true == [0, 1]
                    assert y_pred == [0, 1]
                    assert len(y_score) == 2

    def test_predict_text_missing_text(self):
        """TC-COV-EXP-025: predict text model raises when text missing."""
        evaluator = ExperimentEvaluator()
        df = pd.DataFrame({"label": [0, 1]})
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir) / "trained" / "text_model"
            model_dir.mkdir(parents=True)
            with patch("app.services.experiment_evaluator.TRAINED_ROOT", Path(tmpdir) / "trained"):
                with pytest.raises(ValueError, match="text"):
                    evaluator.predict(df, "text_model")

    def test_evaluate(self):
        """TC-COV-EXP-026: evaluate returns full result structure."""
        evaluator = ExperimentEvaluator()
        df = pd.DataFrame({
            "label": [0, 1, 0, 1],
            "sleep_hours": [7.0, 8.0, 6.0, 9.0],
            "sleep_quality": [3, 4, 2, 5],
            "exercise_minutes": [30, 45, 20, 60],
            "heart_rate": [70, 75, 80, 65],
            "systolic_bp": [120, 130, 110, 125],
            "diastolic_bp": [80, 85, 75, 82],
            "steps": [5000, 8000, 3000, 10000],
        })
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([0, 1, 0, 1])
        mock_model.predict_proba.return_value = np.array([[0.6, 0.4], [0.3, 0.7], [0.7, 0.3], [0.2, 0.8]])

        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir) / "trained" / "phys_model"
            model_dir.mkdir(parents=True)
            (model_dir / "physiological_model.pkl").write_bytes(b"x")
            with patch("app.services.experiment_evaluator.TRAINED_ROOT", Path(tmpdir) / "trained"):
                with patch("app.core.safe_pickle.safe_joblib_load", return_value=mock_model):
                    result = evaluator.evaluate(df, "phys_model", "test")

        assert result["model_name"] == "phys_model"
        assert result["split"] == "test"
        assert "metrics" in result
        assert "confusion_matrix" in result
        assert "prediction_samples" in result
        assert "eval_history" in result

    def test_compare(self):
        """TC-COV-EXP-027: compare returns sorted results."""
        evaluator = ExperimentEvaluator()
        df = pd.DataFrame({
            "label": [0, 1, 0, 1],
            "sleep_hours": [7.0, 8.0, 6.0, 9.0],
            "sleep_quality": [3, 4, 2, 5],
            "exercise_minutes": [30, 45, 20, 60],
            "heart_rate": [70, 75, 80, 65],
            "systolic_bp": [120, 130, 110, 125],
            "diastolic_bp": [80, 85, 75, 82],
            "steps": [5000, 8000, 3000, 10000],
        })
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([0, 1, 0, 1])
        mock_model.predict_proba.return_value = np.array([[0.6, 0.4], [0.3, 0.7], [0.7, 0.3], [0.2, 0.8]])

        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir) / "trained" / "phys_model"
            model_dir.mkdir(parents=True)
            (model_dir / "physiological_model.pkl").write_bytes(b"x")
            with patch("app.services.experiment_evaluator.TRAINED_ROOT", Path(tmpdir) / "trained"):
                with patch("app.core.safe_pickle.safe_joblib_load", return_value=mock_model):
                    result = evaluator.compare(df, ["phys_model"])

        assert "results" in result
        assert len(result["results"]) == 1
        assert result["results"][0]["model_name"] == "phys_model"
