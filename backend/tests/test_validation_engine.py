from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from app.services.validation_engine import ValidationEngine, ValidationMetrics, validation_engine


class TestValidationMetrics:
    """T-BE-007: ValidationMetrics 单元测试"""

    def test_default_values(self) -> None:
        """验证默认值"""
        metrics = ValidationMetrics()
        assert metrics.accuracy is None
        assert metrics.sample_count == 0

    def test_to_dict(self) -> None:
        """验证 to_dict 输出"""
        metrics = ValidationMetrics(accuracy=0.95, f1=0.92, sample_count=100)
        d = metrics.to_dict()
        assert d["accuracy"] == 0.95
        assert d["f1"] == 0.92
        assert d["sample_count"] == 100
        assert d["precision"] is None


class TestValidationEngineLoadDataset:
    """T-BE-007: 数据集加载单元测试"""

    def test_load_json_dataset(self) -> None:
        """验证 JSON 数据集加载"""
        engine = ValidationEngine()
        data = [
            {"feature1": 1.0, "feature2": 2.0, "label": 0},
            {"feature1": 3.0, "feature2": 4.0, "label": 1},
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            temp_path = Path(f.name)

        try:
            features, labels = engine.load_dataset(temp_path)
            assert len(features) == 2
            assert len(labels) == 2
            assert features[0] == {"feature1": 1.0, "feature2": 2.0}
            assert labels == [0, 1]
        finally:
            temp_path.unlink()

    def test_load_json_dataset_dict_format(self) -> None:
        """验证 JSON dict 格式数据集加载"""
        engine = ValidationEngine()
        data = {
            "features": [{"a": 1}, {"a": 2}],
            "labels": [0, 1],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            temp_path = Path(f.name)

        try:
            features, labels = engine.load_dataset(temp_path)
            assert len(features) == 2
            assert labels == [0, 1]
        finally:
            temp_path.unlink()

    def test_load_csv_dataset(self) -> None:
        """验证 CSV 数据集加载"""
        engine = ValidationEngine()
        csv_content = "feature1,feature2,label\n1.0,2.0,0\n3.0,4.0,1\n"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(csv_content)
            temp_path = Path(f.name)

        try:
            features, labels = engine.load_dataset(temp_path)
            assert len(features) == 2
            assert len(labels) == 2
            assert features[0]["feature1"] == 1.0
            assert labels == ["0", "1"]
        finally:
            temp_path.unlink()

    def test_load_dataset_not_found(self) -> None:
        """验证数据集不存在时抛出异常"""
        engine = ValidationEngine()
        with pytest.raises(FileNotFoundError):
            engine.load_dataset(Path("/nonexistent/dataset.json"))

    def test_load_dataset_unsupported_format(self) -> None:
        """验证不支持的格式抛出异常"""
        engine = ValidationEngine()
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            temp_path = Path(f.name)
        try:
            with pytest.raises(ValueError):
                engine.load_dataset(temp_path)
        finally:
            temp_path.unlink()


class TestValidationEngineMetrics:
    """T-BE-007: 指标计算单元测试"""

    def test_calculate_metrics_binary(self) -> None:
        """验证二分类指标计算"""
        engine = ValidationEngine()
        y_true = [0, 1, 0, 1, 1, 0, 1, 0]
        y_pred = [0, 1, 0, 0, 1, 0, 1, 1]
        probs = [0.1, 0.9, 0.2, 0.4, 0.8, 0.3, 0.95, 0.6]

        metrics = engine.calculate_metrics(y_true, y_pred, probs)
        assert metrics.accuracy is not None
        assert metrics.precision is not None
        assert metrics.recall is not None
        assert metrics.f1 is not None
        assert metrics.auc is not None
        assert metrics.sample_count == 8

    def test_calculate_metrics_multiclass(self) -> None:
        """验证多分类指标计算"""
        engine = ValidationEngine()
        y_true = [0, 1, 2, 0, 1, 2]
        y_pred = [0, 1, 2, 0, 0, 2]

        metrics = engine.calculate_metrics(y_true, y_pred)
        assert metrics.accuracy is not None
        assert metrics.precision is not None
        assert metrics.recall is not None
        assert metrics.f1 is not None
        assert metrics.auc is None  # No probabilities provided

    def test_calculate_metrics_empty(self) -> None:
        """验证空输入指标计算"""
        engine = ValidationEngine()
        metrics = engine.calculate_metrics([], [])
        assert metrics.accuracy is None
        assert metrics.sample_count == 0

    def test_compute_delta(self) -> None:
        """验证 delta 计算"""
        engine = ValidationEngine()
        current = ValidationMetrics(accuracy=0.95, f1=0.92)
        baseline = ValidationMetrics(accuracy=0.90, f1=0.88)

        delta = engine.compute_delta(current, baseline)
        assert delta["accuracy"] == 0.05
        assert delta["f1"] == 0.04
        assert delta["precision"] is None

    def test_compute_delta_negative(self) -> None:
        """验证负 delta 计算"""
        engine = ValidationEngine()
        current = ValidationMetrics(accuracy=0.85, f1=0.80)
        baseline = ValidationMetrics(accuracy=0.90, f1=0.88)

        delta = engine.compute_delta(current, baseline)
        assert delta["accuracy"] == -0.05
        assert delta["f1"] == -0.08


class TestValidationEngineGlobal:
    """T-BE-007: 全局引擎单元测试"""

    def test_global_engine_exists(self) -> None:
        """验证全局引擎实例存在"""
        assert validation_engine is not None
        assert isinstance(validation_engine, ValidationEngine)
