"""Tests for ExperimentTrainer."""

from __future__ import annotations

import importlib.machinery
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# CI 环境可能未安装 datasets 包（重量级依赖），注入 mock 以支持 @patch("datasets.Dataset")
if "datasets" not in sys.modules:
    _mock = MagicMock()
    _mock.__spec__ = importlib.machinery.ModuleSpec("datasets", None)
    sys.modules["datasets"] = _mock

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
        train_df = pd.DataFrame(
            {
                "sleep_hours": [7.0, 8.0, 6.0],
                "sleep_quality": [3, 4, 2],
                "exercise_minutes": [30, 45, 20],
                "heart_rate": [70, 75, 80],
                "systolic_bp": [120, 130, 110],
                "diastolic_bp": [80, 85, 75],
                "steps": [5000, 8000, 3000],
                "label": [0, 1, 0],
            }
        )
        val_df = pd.DataFrame(
            {
                "sleep_hours": [8.0, 7.0],
                "sleep_quality": [4, 3],
                "exercise_minutes": [45, 30],
                "heart_rate": [75, 70],
                "systolic_bp": [130, 120],
                "diastolic_bp": [85, 80],
                "steps": [8000, 5000],
                "label": [1, 0],
            }
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "app.services.experiment_trainer.TRAINED_ROOT", Path(tmpdir) / "trained"
            ):
                result = trainer.train_physiological_model(
                    train_df, val_df, "phys_test"
                )

        assert result["model_type"] == "sklearn_logistic_regression"
        assert result["message"] == "生理模型训练完成，模型已保存"
        assert "model" in result

    def test_train_physiological_model_empty_train(self):
        """TC-COV-EXP-034: train_physiological_model raises when train empty."""
        trainer = ExperimentTrainer()
        with pytest.raises(ValueError, match="为空"):
            trainer.train_physiological_model(
                pd.DataFrame(),
                pd.DataFrame(
                    {
                        "sleep_hours": [7.0],
                        "sleep_quality": [3],
                        "exercise_minutes": [30],
                        "heart_rate": [70],
                        "systolic_bp": [120],
                        "diastolic_bp": [80],
                        "steps": [5000],
                        "label": [0],
                    }
                ),
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
                "bert_test",
                1,
                8,
                0.001,
            )

    def test_predict_labels_fallback(self):
        """TC-COV-EXP-038: _predict_labels propagates exceptions (H-Svc-12 移除静默兜底)."""
        trainer = ExperimentTrainer()
        mock_trainer = MagicMock()
        mock_trainer.predict.side_effect = Exception("fail")
        # H-Svc-12 修复：异常不再被静默吞掉返回 []，而是向上传播让上层处理
        with pytest.raises(Exception, match="fail"):
            trainer._predict_labels(mock_trainer, None)

    def test_predict_scores_fallback(self):
        """TC-COV-EXP-039: _predict_scores propagates exceptions (H-Svc-12 移除静默兜底)."""
        trainer = ExperimentTrainer()
        mock_trainer = MagicMock()
        mock_trainer.predict.side_effect = Exception("fail")
        with pytest.raises(Exception, match="fail"):
            trainer._predict_scores(mock_trainer, None)


# ──────────────────────────────────────────────────────────────────────────
# 以下为 ExperimentTrainer 扩展覆盖率测试
# 目标：将 experiment_trainer.py 覆盖率从 55% 提升至 90%+
# ──────────────────────────────────────────────────────────────────────────

import json

import numpy as np


class TestExperimentTrainerExtended:
    """ExperimentTrainer 扩展覆盖率补充测试。"""

    def test_latest_checkpoint_returns_none_when_dir_not_exists(self):
        """latest_checkpoint 在目录不存在时返回 None (覆盖 line 165)。"""
        trainer = ExperimentTrainer()
        result = trainer.latest_checkpoint(
            Path(tempfile.gettempdir()) / "nonexistent_checkpoint_dir_xyz_123"
        )
        assert result is None

    def test_save_bundle_success_writes_artifacts(self):
        """save_bundle 在产物完整时保存模型并写入 summary JSON (覆盖 lines 155-161)。"""
        trainer = ExperimentTrainer()
        mock_trainer = MagicMock()
        mock_tokenizer = MagicMock()
        mock_model = MagicMock()
        artifacts = {
            "trainer": mock_trainer,
            "tokenizer": mock_tokenizer,
            "model": mock_model,
            "train_loss": [0.5],
            "val_loss": [0.4],
            "val_accuracy": [0.9],
            "train_history": [],
            "trainer_log_history": [{"loss": 0.5}],
            "eval_history": [{"split": "validation"}],
            "message": "done",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "app.services.experiment_trainer.TRAINED_ROOT", Path(tmpdir) / "trained"
            ):
                save_dir = trainer.save_bundle("bundle_test", artifacts)
                assert save_dir.exists()
                assert (save_dir / "training_summary.json").exists()
                assert (save_dir / "trainer_log_history.json").exists()
                assert (save_dir / "eval_history.json").exists()
                mock_trainer.save_model.assert_called_once()
                mock_tokenizer.save_pretrained.assert_called_once()
                summary = json.loads(
                    (save_dir / "training_summary.json").read_text(encoding="utf-8")
                )
                assert summary["model_name"] == "bundle_test"

    @patch("sklearn.metrics.log_loss", side_effect=Exception("log_loss boom"))
    def test_train_physiological_model_log_loss_fallback(self, _mock_log_loss):
        """train_physiological_model 在 log_loss 失败时回退到 0.0 (覆盖 lines 214-216, L-Svc-4 修复点)。"""
        trainer = ExperimentTrainer()
        train_df = pd.DataFrame(
            {
                "sleep_hours": [7.0, 8.0, 6.0, 7.5],
                "sleep_quality": [3, 4, 2, 3],
                "exercise_minutes": [30, 45, 20, 35],
                "heart_rate": [70, 75, 80, 72],
                "systolic_bp": [120, 130, 110, 125],
                "diastolic_bp": [80, 85, 75, 82],
                "steps": [5000, 8000, 3000, 6000],
                "label": [0, 1, 0, 1],
            }
        )
        val_df = pd.DataFrame(
            {
                "sleep_hours": [8.0, 7.0],
                "sleep_quality": [4, 3],
                "exercise_minutes": [45, 30],
                "heart_rate": [75, 70],
                "systolic_bp": [130, 120],
                "diastolic_bp": [85, 80],
                "steps": [8000, 5000],
                "label": [1, 0],
            }
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "app.services.experiment_trainer.TRAINED_ROOT", Path(tmpdir) / "trained"
            ):
                result = trainer.train_physiological_model(
                    train_df, val_df, "phys_fallback"
                )
                assert result["train_loss"] == [0.0]
                assert result["val_loss"] == [0.0]
                assert result["val_accuracy"][0] >= 0.0

    def test_predict_labels_success_returns_argmax(self):
        """_predict_labels 成功路径：返回 argmax 预测标签 (覆盖 line 243)。"""
        trainer = ExperimentTrainer()
        mock_trainer = MagicMock()
        mock_result = MagicMock()
        mock_result.predictions = np.array([[0.1, 0.9], [0.8, 0.2], [0.3, 0.7]])
        mock_trainer.predict.return_value = mock_result
        labels = trainer._predict_labels(mock_trainer, MagicMock())
        assert labels == [1, 0, 1]

    def test_predict_scores_success_returns_softmax(self):
        """_predict_scores 成功路径：返回 softmax 正类概率 (覆盖 lines 249-250)。"""
        trainer = ExperimentTrainer()
        mock_trainer = MagicMock()
        mock_result = MagicMock()
        mock_result.predictions = np.array([[0.1, 0.9], [0.8, 0.2], [0.3, 0.7]])
        mock_trainer.predict.return_value = mock_result
        scores = trainer._predict_scores(mock_trainer, MagicMock())
        assert len(scores) == 3
        for s in scores:
            assert 0.0 <= float(s) <= 1.0

    @patch("datasets.Dataset")
    @patch("transformers.trainer.Trainer")
    @patch("transformers.training_args.TrainingArguments")
    @patch("transformers.models.auto.modeling_auto.AutoModelForSequenceClassification")
    @patch("transformers.models.auto.tokenization_auto.AutoTokenizer")
    def test_train_full_flow_with_mocks(
        self,
        mock_tokenizer_cls,
        mock_model_cls,
        mock_training_args_cls,
        mock_trainer_cls,
        mock_dataset_cls,
    ):
        """train 方法完整流程：mock 依赖后验证产物结构 (覆盖 lines 33-130)。"""
        trainer = ExperimentTrainer()

        # ── Mock tokenizer ──
        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": [[1, 2, 3]],
            "token_type_ids": [[0, 0, 0]],
            "attention_mask": [[1, 1, 1]],
        }
        mock_tokenizer_cls.from_pretrained.return_value = mock_tokenizer

        # ── Mock dataset chain: Dataset.from_pandas(...).map(tokenize, batched=True) ──
        # 包含 text 列以触发 remove_columns 分支 (覆盖 lines 42-47)
        mock_train_ds = MagicMock()
        mock_train_ds.column_names = [
            "text",
            "labels",
            "input_ids",
            "token_type_ids",
            "attention_mask",
        ]
        mock_train_ds.__len__ = MagicMock(return_value=10)
        mock_train_ds.remove_columns.return_value = mock_train_ds

        mock_val_ds = MagicMock()
        mock_val_ds.column_names = [
            "text",
            "labels",
            "input_ids",
            "token_type_ids",
            "attention_mask",
        ]
        mock_val_ds.__len__ = MagicMock(return_value=5)
        mock_val_ds.remove_columns.return_value = mock_val_ds

        mock_train_pandas = MagicMock()
        mock_train_pandas.map.return_value = mock_train_ds
        mock_val_pandas = MagicMock()
        mock_val_pandas.map.return_value = mock_val_ds
        mock_dataset_cls.from_pandas.side_effect = [mock_train_pandas, mock_val_pandas]

        # ── Mock model ──
        mock_model = MagicMock()
        mock_model_cls.from_pretrained.return_value = mock_model

        # ── Mock Trainer: 通过 side_effect 捕获 compute_metrics 和 callbacks ──
        mock_trainer_instance = MagicMock()
        captured: dict = {}

        def trainer_side_effect(**kwargs):
            captured["compute_metrics"] = kwargs.get("compute_metrics")
            captured["callbacks"] = kwargs.get("callbacks", [])
            return mock_trainer_instance

        mock_trainer_cls.side_effect = trainer_side_effect

        # train_output
        mock_train_output = MagicMock()
        mock_train_output.training_loss = 0.45
        mock_train_output.metrics = {"train_loss": 0.45}
        mock_trainer_instance.train.return_value = mock_train_output

        # evaluate result
        mock_trainer_instance.evaluate.return_value = {
            "eval_loss": 0.38,
            "eval_accuracy": 0.92,
            "eval_f1": 0.88,
        }

        # predict result (5 行匹配 val_df 长度)
        mock_predictions = MagicMock()
        mock_predictions.predictions = np.array(
            [
                [0.1, 0.9],
                [0.8, 0.2],
                [0.3, 0.7],
                [0.6, 0.4],
                [0.2, 0.8],
            ]
        )
        mock_trainer_instance.predict.return_value = mock_predictions

        # trainer.state.log_history
        mock_state = MagicMock()
        mock_state.log_history = [
            {"loss": 0.5, "epoch": 1},
            {"eval_loss": 0.4, "epoch": 1},
        ]
        mock_trainer_instance.state = mock_state

        # ── 测试数据 ──
        train_df = pd.DataFrame(
            {
                "text": [f"训练样本 {i}" for i in range(10)],
                "label": [i % 2 for i in range(10)],
            }
        )
        val_df = pd.DataFrame(
            {
                "text": [f"验证样本 {i}" for i in range(5)],
                "label": [i % 2 for i in range(5)],
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "app.services.experiment_trainer.TRAINED_ROOT", Path(tmpdir) / "trained"
            ):
                result = trainer.train(train_df, val_df, "mock_bert", 2, 8, 0.001)

        # ── 验证返回结构 ──
        assert result["model_type"] == "huggingface_bert"
        assert result["base_model"] == "bert-base-chinese"
        assert isinstance(result["train_loss"], list)
        assert isinstance(result["val_loss"], list)
        assert isinstance(result["val_accuracy"], list)
        assert isinstance(result["train_history"], list)
        assert isinstance(result["trainer_log_history"], list)
        assert isinstance(result["eval_history"], list)
        assert result["message"] == "HuggingFace BERT 训练完成，模型已保存"
        assert "trainer" in result and "tokenizer" in result and "model" in result

        # ── 调用 compute_metrics 覆盖其函数体 (lines 95-108) ──
        compute_metrics = captured.get("compute_metrics")
        assert compute_metrics is not None

        # 多输出 (softmax) 路径 (line 106)
        logits_2d = np.array([[0.1, 0.9], [0.8, 0.2]])
        labels_arr = np.array([1, 0])
        metrics_multi = compute_metrics((logits_2d, labels_arr))
        assert "accuracy" in metrics_multi
        assert "f1" in metrics_multi

        # 单输出 (sigmoid) 路径 (line 104), shape=(N, 1)
        logits_single = np.array([[0.5], [0.3]])
        metrics_single = compute_metrics((logits_single, labels_arr))
        assert "accuracy" in metrics_single

        # labels 为 list 而非 ndarray (覆盖 hasattr else 分支, line 107)
        metrics_list_labels = compute_metrics((logits_2d, [1, 0]))
        assert "accuracy" in metrics_list_labels

        # ── 调用 on_log 覆盖 EpochHistoryCallback (lines 63-74) ──
        callbacks = captured.get("callbacks", [])
        assert len(callbacks) > 0
        cb = callbacks[0]
        mock_state_log = MagicMock()
        mock_state_log.epoch = 1
        mock_control = MagicMock()

        # logs=None → 提前返回 (line 63-64)
        cb.on_log(None, mock_state_log, mock_control, logs=None)

        # logs 含 loss → 设置 current_train_loss (line 65-66)
        cb.on_log(None, mock_state_log, mock_control, logs={"loss": 0.5})

        # logs 含 eval_loss + eval_accuracy → 追加历史 (line 67-73)
        cb.on_log(
            None,
            mock_state_log,
            mock_control,
            logs={"eval_loss": 0.4, "eval_accuracy": 0.9},
        )
        assert len(cb.history) == 1
        assert cb.history[0]["val_accuracy"] == 0.9

        # logs 含 eval_loss + eval_acc (非 eval_accuracy) → 走 logs.get 回退 (line 72)
        cb.on_log(
            None,
            mock_state_log,
            mock_control,
            logs={"eval_loss": 0.35, "eval_acc": 0.85},
        )
        assert len(cb.history) == 2
        assert cb.history[1]["val_accuracy"] == 0.85

        # logs 含 loss 但无 eval_loss → current_train_loss 更新, 历史不追加
        prev_count = len(cb.history)
        cb.on_log(None, mock_state_log, mock_control, logs={"loss": 0.3})
        assert len(cb.history) == prev_count

        # state.epoch 为 None → 回退 len(history)+1 (line 69)
        mock_state_no_epoch = MagicMock()
        mock_state_no_epoch.epoch = None
        cb.on_log(
            None,
            mock_state_no_epoch,
            mock_control,
            logs={"eval_loss": 0.3, "eval_accuracy": 0.8},
        )
        last_entry = cb.history[-1]
        assert last_entry["epoch"] == len(cb.history)

    @patch("datasets.Dataset")
    @patch("transformers.Trainer")
    @patch("transformers.TrainingArguments")
    @patch("transformers.AutoModelForSequenceClassification")
    @patch("transformers.AutoTokenizer")
    def test_train_raises_when_dataset_empty_after_map(
        self,
        mock_tokenizer_cls,
        mock_model_cls,
        mock_training_args_cls,
        mock_trainer_cls,
        mock_dataset_cls,
    ):
        """train 在 Dataset.map 后返回空数据集时抛 ValueError (覆盖 lines 40-41)。"""
        trainer = ExperimentTrainer()

        mock_tokenizer = MagicMock()
        mock_tokenizer_cls.from_pretrained.return_value = mock_tokenizer

        # 空数据集
        mock_train_ds = MagicMock()
        mock_train_ds.__len__ = MagicMock(return_value=0)
        mock_val_ds = MagicMock()
        mock_val_ds.__len__ = MagicMock(return_value=5)

        mock_train_pandas = MagicMock()
        mock_train_pandas.map.return_value = mock_train_ds
        mock_val_pandas = MagicMock()
        mock_val_pandas.map.return_value = mock_val_ds
        mock_dataset_cls.from_pandas.side_effect = [mock_train_pandas, mock_val_pandas]

        mock_model = MagicMock()
        mock_model_cls.from_pretrained.return_value = mock_model

        train_df = pd.DataFrame({"text": ["a"] * 5, "label": [0, 1, 0, 1, 0]})
        val_df = pd.DataFrame({"text": ["b"] * 5, "label": [0, 1, 0, 1, 0]})

        with pytest.raises(ValueError, match="构建失败"):
            trainer.train(train_df, val_df, "empty_ds", 1, 8, 0.001)
