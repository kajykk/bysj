"""Tests for ExperimentService."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

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
    def test_train_model_physiological(
        self, mock_data_cls, mock_trainer_cls, mock_read_csv
    ):
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
    def test_evaluate_model_physiological(
        self, mock_data_cls, mock_eval_cls, mock_read_csv
    ):
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
        service.evaluate_model("ds1", "physiological_v1", "test")

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


# ──────────────────────────────────────────────────────────────────────────
# 以下为 ExperimentDataManager (app/services/experiment_data.py) 覆盖率补充测试
# 目标：将 experiment_data.py 覆盖率从 26% 提升至 90%+
# ──────────────────────────────────────────────────────────────────────────

import json
import tempfile
from pathlib import Path

from app.services.experiment_data import ExperimentDataManager


class TestExperimentDataManager:
    """ExperimentDataManager 各路径方法的覆盖率补充测试。"""

    def test_path_methods_return_correct_paths(self):
        """路径构造方法返回 DATA_ROOT / EXPERIMENT_ROOT 下的正确子路径。"""
        manager = ExperimentDataManager()
        assert manager.dataset_path("ds1").name == "ds1.csv"
        assert manager.meta_path("ds1").name == "ds1.meta.json"
        assert manager.train_path("ds1").name == "ds1_train.csv"
        assert manager.val_path("ds1").name == "ds1_validation.csv"
        assert manager.test_path("ds1").name == "ds1_test.csv"
        assert manager.physiological_dataset_path("ds1").name == "ds1_physiological.csv"

    def test_export_dataset_snapshot_writes_json(self):
        """export_dataset_snapshot 写入 snapshot.json 并返回快照字典。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.services.experiment_data.DATA_ROOT", Path(tmpdir)), patch(
                "app.services.experiment_data.EXPERIMENT_ROOT", Path(tmpdir) / "exp"
            ):
                manager = ExperimentDataManager()
                snapshot = manager.export_dataset_snapshot("ds_snap")
                assert snapshot["dataset_name"] == "ds_snap"
                assert "dataset_path" in snapshot
                assert "train_path" in snapshot
                snapshot_file = Path(tmpdir) / "ds_snap.snapshot.json"
                assert snapshot_file.exists()
                content = json.loads(snapshot_file.read_text(encoding="utf-8"))
                assert content["dataset_name"] == "ds_snap"

    def test_load_physiological_dataset_creates_demo_when_missing(self):
        """load_physiological_dataset 在文件不存在时自动创建演示数据集。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.services.experiment_data.DATA_ROOT", Path(tmpdir)), patch(
                "app.services.experiment_data.EXPERIMENT_ROOT", Path(tmpdir) / "exp"
            ):
                manager = ExperimentDataManager()
                df = manager.load_physiological_dataset("demo_phys")
                assert not df.empty
                required = {
                    "sleep_hours",
                    "sleep_quality",
                    "exercise_minutes",
                    "heart_rate",
                    "systolic_bp",
                    "diastolic_bp",
                    "steps",
                    "label",
                }
                assert required.issubset(set(df.columns))
                assert manager.physiological_dataset_path("demo_phys").exists()

    def test_load_physiological_dataset_reads_existing_csv(self):
        """load_physiological_dataset 读取已存在的 CSV 文件。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.services.experiment_data.DATA_ROOT", Path(tmpdir)), patch(
                "app.services.experiment_data.EXPERIMENT_ROOT", Path(tmpdir) / "exp"
            ):
                manager = ExperimentDataManager()
                csv_path = manager.physiological_dataset_path("existing_phys")
                pd.DataFrame(
                    {
                        "sleep_hours": [7.0, 6.5],
                        "sleep_quality": [3, 4],
                        "exercise_minutes": [30, 45],
                        "heart_rate": [70, 75],
                        "systolic_bp": [120, 130],
                        "diastolic_bp": [80, 85],
                        "steps": [5000, 8000],
                        "label": [0, 1],
                    }
                ).to_csv(csv_path, index=False)
                df = manager.load_physiological_dataset("existing_phys")
                assert len(df) == 2

    def test_load_physiological_dataset_raises_on_missing_columns(self):
        """load_physiological_dataset 缺少必要列时抛 ValueError。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.services.experiment_data.DATA_ROOT", Path(tmpdir)), patch(
                "app.services.experiment_data.EXPERIMENT_ROOT", Path(tmpdir) / "exp"
            ):
                manager = ExperimentDataManager()
                csv_path = manager.physiological_dataset_path("bad_phys")
                pd.DataFrame({"sleep_hours": [7.0], "label": [0]}).to_csv(
                    csv_path, index=False
                )
                with pytest.raises(ValueError, match="缺少必要列"):
                    manager.load_physiological_dataset("bad_phys")

    def test_import_dataset_creates_demo_and_splits(self):
        """import_dataset 在 CSV 不存在时自动创建演示数据集并完成划分。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.services.experiment_data.DATA_ROOT", Path(tmpdir)), patch(
                "app.services.experiment_data.EXPERIMENT_ROOT", Path(tmpdir) / "exp"
            ):
                manager = ExperimentDataManager()
                result = manager.import_dataset("demo_ds", "csv", 0.7, 0.15, 0.15)
                assert result["dataset_name"] == "demo_ds"
                assert result["total_samples"] == 240
                assert result["splits"]["train"] > 0
                assert result["splits"]["validation"] > 0
                assert result["splits"]["test"] > 0
                assert manager.train_path("demo_ds").exists()
                assert manager.val_path("demo_ds").exists()
                assert manager.test_path("demo_ds").exists()
                assert manager.meta_path("demo_ds").exists()

    def test_import_dataset_success_with_existing_csv(self):
        """import_dataset 使用已存在 CSV 文件成功划分。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.services.experiment_data.DATA_ROOT", Path(tmpdir)), patch(
                "app.services.experiment_data.EXPERIMENT_ROOT", Path(tmpdir) / "exp"
            ):
                manager = ExperimentDataManager()
                csv_path = manager.dataset_path("existing_ds")
                rows = [{"text": f"sample {i}", "label": i % 2} for i in range(20)]
                pd.DataFrame(rows).to_csv(csv_path, index=False)
                result = manager.import_dataset("existing_ds", "bert", 0.6, 0.2, 0.2)
                assert result["total_samples"] == 20
                assert (
                    result["splits"]["train"]
                    + result["splits"]["validation"]
                    + result["splits"]["test"]
                    == 20
                )

    def test_import_dataset_raises_on_missing_label_column(self):
        """import_dataset 缺少 label 列时抛 ValueError。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.services.experiment_data.DATA_ROOT", Path(tmpdir)), patch(
                "app.services.experiment_data.EXPERIMENT_ROOT", Path(tmpdir) / "exp"
            ):
                manager = ExperimentDataManager()
                csv_path = manager.dataset_path("no_label")
                pd.DataFrame({"text": ["a", "b", "c", "d"]}).to_csv(
                    csv_path, index=False
                )
                with pytest.raises(ValueError, match="label"):
                    manager.import_dataset("no_label", "csv", 0.7, 0.15, 0.15)

    def test_import_dataset_raises_on_text_source_missing_text_column(self):
        """import_dataset 文本类数据源缺少 text 列时抛 ValueError。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.services.experiment_data.DATA_ROOT", Path(tmpdir)), patch(
                "app.services.experiment_data.EXPERIMENT_ROOT", Path(tmpdir) / "exp"
            ):
                manager = ExperimentDataManager()
                csv_path = manager.dataset_path("no_text")
                pd.DataFrame({"age": [1, 2, 3, 4], "label": [0, 1, 0, 1]}).to_csv(
                    csv_path, index=False
                )
                with pytest.raises(ValueError, match="text"):
                    manager.import_dataset("no_text", "bert", 0.7, 0.15, 0.15)

    def test_import_dataset_raises_on_invalid_ratios_sum(self):
        """import_dataset 比例之和不为 1 时抛 ValueError。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.services.experiment_data.DATA_ROOT", Path(tmpdir)), patch(
                "app.services.experiment_data.EXPERIMENT_ROOT", Path(tmpdir) / "exp"
            ):
                manager = ExperimentDataManager()
                with pytest.raises(ValueError, match="等于 1"):
                    manager.import_dataset("bad_ratio", "csv", 0.5, 0.3, 0.3)

    def test_import_dataset_raises_on_negative_ratio(self):
        """import_dataset 出现负比例时抛 ValueError。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.services.experiment_data.DATA_ROOT", Path(tmpdir)), patch(
                "app.services.experiment_data.EXPERIMENT_ROOT", Path(tmpdir) / "exp"
            ):
                manager = ExperimentDataManager()
                # 比例之和为 1.0 但包含负值，触发 min(...) <= 0 检查
                with pytest.raises(ValueError, match="大于 0"):
                    manager.import_dataset("neg_ratio", "csv", 1.2, -0.1, -0.1)

    def test_import_dataset_raises_on_too_few_samples(self):
        """import_dataset 样本量少于 3 时抛 ValueError。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.services.experiment_data.DATA_ROOT", Path(tmpdir)), patch(
                "app.services.experiment_data.EXPERIMENT_ROOT", Path(tmpdir) / "exp"
            ):
                manager = ExperimentDataManager()
                csv_path = manager.dataset_path("tiny")
                pd.DataFrame({"text": ["a", "b"], "label": [0, 1]}).to_csv(
                    csv_path, index=False
                )
                with pytest.raises(ValueError, match="至少需要 3"):
                    manager.import_dataset("tiny", "csv", 0.7, 0.15, 0.15)

    def test_import_dataset_raises_on_min_class_less_than_two(self):
        """import_dataset 某类别样本数 < 2 时抛 ValueError (M-Svc-3 修复点)。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.services.experiment_data.DATA_ROOT", Path(tmpdir)), patch(
                "app.services.experiment_data.EXPERIMENT_ROOT", Path(tmpdir) / "exp"
            ):
                manager = ExperimentDataManager()
                csv_path = manager.dataset_path("one_class_min")
                rows = [
                    {"text": f"sample {i}", "label": 0 if i < 3 else 1}
                    for i in range(4)
                ]
                pd.DataFrame(rows).to_csv(csv_path, index=False)
                with pytest.raises(ValueError, match="至少 2 个样本"):
                    manager.import_dataset("one_class_min", "csv", 0.7, 0.15, 0.15)

    def test_import_dataset_raises_on_binary_split_min_class(self):
        """import_dataset 二分划分后某类别样本数 < 2 时抛 ValueError (M-Svc-3 修复点)。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.services.experiment_data.DATA_ROOT", Path(tmpdir)), patch(
                "app.services.experiment_data.EXPERIMENT_ROOT", Path(tmpdir) / "exp"
            ):
                manager = ExperimentDataManager()
                csv_path = manager.dataset_path("binary_split_min")
                rows = [
                    {"text": "a", "label": 0},
                    {"text": "b", "label": 0},
                    {"text": "c", "label": 1},
                    {"text": "d", "label": 1},
                ]
                pd.DataFrame(rows).to_csv(csv_path, index=False)
                with pytest.raises(ValueError, match="二分划分后"):
                    manager.import_dataset("binary_split_min", "csv", 0.5, 0.25, 0.25)
