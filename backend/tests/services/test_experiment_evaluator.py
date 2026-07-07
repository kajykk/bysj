"""Tests for ExperimentEvaluator."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

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
            with patch(
                "app.services.experiment_evaluator.TRAINED_ROOT",
                Path(tmpdir) / "trained",
            ):
                result = evaluator.trained_model_dir("test_model")
                assert result == model_dir

    def test_trained_model_dir_legacy(self):
        """TC-COV-EXP-019: trained_model_dir falls back to checkpoint-best."""
        evaluator = ExperimentEvaluator()
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir) / "trained" / "test_model"
            checkpoint_dir = model_dir / "checkpoint-best"
            checkpoint_dir.mkdir(parents=True)
            with patch(
                "app.services.experiment_evaluator.TRAINED_ROOT",
                Path(tmpdir) / "trained",
            ):
                result = evaluator.trained_model_dir("test_model")
                assert result == checkpoint_dir

    def test_trained_model_dir_not_found(self):
        """TC-COV-EXP-020: trained_model_dir raises when missing."""
        evaluator = ExperimentEvaluator()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "app.services.experiment_evaluator.TRAINED_ROOT",
                Path(tmpdir) / "trained",
            ):
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
            with patch(
                "app.services.experiment_evaluator.TRAINED_ROOT",
                Path(tmpdir) / "trained",
            ):
                # ML-005 修复后：predict 使用 safe_joblib_load，mock 目标更新
                with patch(
                    "app.core.safe_pickle.safe_joblib_load", return_value=MagicMock()
                ):
                    with pytest.raises(ValueError, match="缺少必要列"):
                        evaluator.predict(df, "phys_model")

    def test_predict_physiological_success(self):
        """TC-COV-EXP-024: predict physiological returns predictions."""
        evaluator = ExperimentEvaluator()
        df = pd.DataFrame(
            {
                "label": [0, 1],
                "sleep_hours": [7.0, 8.0],
                "sleep_quality": [3, 4],
                "exercise_minutes": [30, 45],
                "heart_rate": [70, 75],
                "systolic_bp": [120, 130],
                "diastolic_bp": [80, 85],
                "steps": [5000, 8000],
            }
        )
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([0, 1])
        mock_model.predict_proba.return_value = np.array([[0.3, 0.7], [0.2, 0.8]])

        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir) / "trained" / "phys_model"
            model_dir.mkdir(parents=True)
            (model_dir / "physiological_model.pkl").write_bytes(b"x")
            with patch(
                "app.services.experiment_evaluator.TRAINED_ROOT",
                Path(tmpdir) / "trained",
            ):
                with patch(
                    "app.core.safe_pickle.safe_joblib_load", return_value=mock_model
                ):
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
            with patch(
                "app.services.experiment_evaluator.TRAINED_ROOT",
                Path(tmpdir) / "trained",
            ):
                with pytest.raises(ValueError, match="text"):
                    evaluator.predict(df, "text_model")

    def test_evaluate(self):
        """TC-COV-EXP-026: evaluate returns full result structure."""
        evaluator = ExperimentEvaluator()
        df = pd.DataFrame(
            {
                "label": [0, 1, 0, 1],
                "sleep_hours": [7.0, 8.0, 6.0, 9.0],
                "sleep_quality": [3, 4, 2, 5],
                "exercise_minutes": [30, 45, 20, 60],
                "heart_rate": [70, 75, 80, 65],
                "systolic_bp": [120, 130, 110, 125],
                "diastolic_bp": [80, 85, 75, 82],
                "steps": [5000, 8000, 3000, 10000],
            }
        )
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([0, 1, 0, 1])
        mock_model.predict_proba.return_value = np.array(
            [[0.6, 0.4], [0.3, 0.7], [0.7, 0.3], [0.2, 0.8]]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir) / "trained" / "phys_model"
            model_dir.mkdir(parents=True)
            (model_dir / "physiological_model.pkl").write_bytes(b"x")
            with patch(
                "app.services.experiment_evaluator.TRAINED_ROOT",
                Path(tmpdir) / "trained",
            ):
                with patch(
                    "app.core.safe_pickle.safe_joblib_load", return_value=mock_model
                ):
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
        df = pd.DataFrame(
            {
                "label": [0, 1, 0, 1],
                "sleep_hours": [7.0, 8.0, 6.0, 9.0],
                "sleep_quality": [3, 4, 2, 5],
                "exercise_minutes": [30, 45, 20, 60],
                "heart_rate": [70, 75, 80, 65],
                "systolic_bp": [120, 130, 110, 125],
                "diastolic_bp": [80, 85, 75, 82],
                "steps": [5000, 8000, 3000, 10000],
            }
        )
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([0, 1, 0, 1])
        mock_model.predict_proba.return_value = np.array(
            [[0.6, 0.4], [0.3, 0.7], [0.7, 0.3], [0.2, 0.8]]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir) / "trained" / "phys_model"
            model_dir.mkdir(parents=True)
            (model_dir / "physiological_model.pkl").write_bytes(b"x")
            with patch(
                "app.services.experiment_evaluator.TRAINED_ROOT",
                Path(tmpdir) / "trained",
            ):
                with patch(
                    "app.core.safe_pickle.safe_joblib_load", return_value=mock_model
                ):
                    result = evaluator.compare(df, ["phys_model"])

        assert "results" in result
        assert len(result["results"]) == 1
        assert result["results"][0]["model_name"] == "phys_model"

    def test_predict_physiological_decision_function(self):
        """TC-COV-EXP-028: predict 生理模型仅有 decision_function 时使用 sigmoid 归一化。"""
        evaluator = ExperimentEvaluator()
        df = pd.DataFrame(
            {
                "label": [0, 1],
                "sleep_hours": [7.0, 8.0],
                "sleep_quality": [3, 4],
                "exercise_minutes": [30, 45],
                "heart_rate": [70, 75],
                "systolic_bp": [120, 130],
                "diastolic_bp": [80, 85],
                "steps": [5000, 8000],
            }
        )
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([0, 1])
        # 删除 predict_proba，强制走 decision_function 分支
        del mock_model.predict_proba
        mock_model.decision_function.return_value = np.array([0.5, -0.3])

        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir) / "trained" / "phys_model"
            model_dir.mkdir(parents=True)
            (model_dir / "physiological_model.pkl").write_bytes(b"x")
            with patch(
                "app.services.experiment_evaluator.TRAINED_ROOT",
                Path(tmpdir) / "trained",
            ):
                with patch(
                    "app.core.safe_pickle.safe_joblib_load", return_value=mock_model
                ):
                    y_true, y_pred, y_score = evaluator.predict(df, "phys_model")
                    assert y_true == [0, 1]
                    assert y_pred == [0, 1]
                    assert len(y_score) == 2
                    # sigmoid(0.5) 和 sigmoid(-0.3) 都应在 (0, 1) 范围内
                    assert all(0.0 < s < 1.0 for s in y_score)

    def test_predict_physiological_no_proba_no_decision(self):
        """TC-COV-EXP-029: predict 生理模型既无 predict_proba 也无 decision_function 时使用 0.5 兜底。"""
        evaluator = ExperimentEvaluator()
        df = pd.DataFrame(
            {
                "label": [0, 1],
                "sleep_hours": [7.0, 8.0],
                "sleep_quality": [3, 4],
                "exercise_minutes": [30, 45],
                "heart_rate": [70, 75],
                "systolic_bp": [120, 130],
                "diastolic_bp": [80, 85],
                "steps": [5000, 8000],
            }
        )
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([0, 1])
        del mock_model.predict_proba
        del mock_model.decision_function

        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir) / "trained" / "phys_model"
            model_dir.mkdir(parents=True)
            (model_dir / "physiological_model.pkl").write_bytes(b"x")
            with patch(
                "app.services.experiment_evaluator.TRAINED_ROOT",
                Path(tmpdir) / "trained",
            ):
                with patch(
                    "app.core.safe_pickle.safe_joblib_load", return_value=mock_model
                ):
                    y_true, y_pred, y_score = evaluator.predict(df, "phys_model")
                    assert y_true == [0, 1]
                    assert y_pred == [0, 1]
                    assert y_score == [0.5, 0.5]

    def test_predict_text_model_success(self):
        """TC-COV-EXP-030: predict 文本模型预测完整路径。"""
        import torch as _torch

        evaluator = ExperimentEvaluator()
        df = pd.DataFrame({"label": [0, 1], "text": ["good day", "bad day"]})

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": _torch.tensor([[1, 2]]),
            "attention_mask": _torch.tensor([[1, 1]]),
        }

        mock_outputs = MagicMock()
        # 两行文本：第一行预测为类别 0，第二行预测为类别 1
        mock_outputs.logits = _torch.tensor([[0.1, 0.9], [0.8, 0.2]])
        mock_model = MagicMock()
        mock_model.return_value = mock_outputs

        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir) / "trained" / "text_model"
            model_dir.mkdir(parents=True)
            with patch(
                "app.services.experiment_evaluator.TRAINED_ROOT",
                Path(tmpdir) / "trained",
            ):
                with patch(
                    "transformers.AutoTokenizer.from_pretrained",
                    return_value=mock_tokenizer,
                ):
                    with patch(
                        "transformers.AutoModelForSequenceClassification.from_pretrained",
                        return_value=mock_model,
                    ):
                        y_true, y_pred, y_score = evaluator.predict(df, "text_model")
                        assert y_true == [0, 1]
                        assert len(y_pred) == 2
                        assert len(y_score) == 2

    def test_compare_with_failure(self):
        """TC-COV-EXP-031: compare 中单个模型评估失败不影响整体，记录错误并排序。"""
        evaluator = ExperimentEvaluator()
        df = pd.DataFrame({"label": [0, 1], "text": ["a", "b"]})

        with patch.object(
            evaluator, "predict", side_effect=Exception("model load error")
        ):
            result = evaluator.compare(df, ["failed_model"])
            assert len(result["results"]) == 1
            assert result["results"][0]["model_name"] == "failed_model"
            assert "error" in result["results"][0]
            assert result["results"][0]["f1"] == 0.0
            assert result["results"][0]["auc"] == 0.0

    def test_compare_mixed_success_and_failure(self):
        """TC-COV-EXP-032: compare 混合成功与失败模型时正确排序。"""
        evaluator = ExperimentEvaluator()
        df = pd.DataFrame(
            {
                "label": [0, 1],
                "sleep_hours": [7.0, 8.0],
                "sleep_quality": [3, 4],
                "exercise_minutes": [30, 45],
                "heart_rate": [70, 75],
                "systolic_bp": [120, 130],
                "diastolic_bp": [80, 85],
                "steps": [5000, 8000],
            }
        )
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array([0, 1])
        mock_model.predict_proba.return_value = np.array([[0.6, 0.4], [0.3, 0.7]])

        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir) / "trained" / "phys_model"
            model_dir.mkdir(parents=True)
            (model_dir / "physiological_model.pkl").write_bytes(b"x")
            with patch(
                "app.services.experiment_evaluator.TRAINED_ROOT",
                Path(tmpdir) / "trained",
            ):
                with patch(
                    "app.core.safe_pickle.safe_joblib_load", return_value=mock_model
                ):
                    # 第一个模型成功，第二个模型失败
                    original_predict = evaluator.predict

                    def predict_side_effect(inner_df, model_name):
                        if model_name == "bad_model":
                            raise FileNotFoundError("模型目录不存在")
                        return original_predict(inner_df, model_name)

                    with patch.object(
                        evaluator, "predict", side_effect=predict_side_effect
                    ):
                        result = evaluator.compare(df, ["phys_model", "bad_model"])

        assert len(result["results"]) == 2
        # 成功的模型应排在前面（f1 > 0）
        success_results = [
            r for r in result["results"] if r["model_name"] == "phys_model"
        ]
        assert len(success_results) == 1
        assert success_results[0]["f1"] > 0.0
        # 失败的模型 f1=0
        failed_results = [
            r for r in result["results"] if r["model_name"] == "bad_model"
        ]
        assert len(failed_results) == 1
        assert failed_results[0]["f1"] == 0.0
