from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from app.services.validation_engine import (
    ValidationEngine,
    ValidationMetrics,
    validation_engine,
)


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

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
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


# ============================================================================
# 扩展测试：覆盖 validation_engine.py 未测试分支（目标覆盖率 90%+）
# ============================================================================

from unittest.mock import AsyncMock, patch  # noqa: E402

from app.services.validation_engine import ValidationResult  # noqa: E402


class TestValidationResultToDict:
    """ValidationResult.to_dict 单元测试，覆盖 lines 54-63"""

    def test_to_dict_without_baseline(self) -> None:
        """验证无 baseline 时 to_dict 仅包含基础字段"""
        result = ValidationResult(
            model_version="v1.0",
            metrics=ValidationMetrics(accuracy=0.95, sample_count=100),
            predictions=[{"index": 0}],
            errors=[],
        )
        d = result.to_dict()
        assert d["model_version"] == "v1.0"
        assert d["metrics"]["accuracy"] == 0.95
        assert d["predictions_count"] == 1
        assert "baseline_metrics" not in d
        assert "delta" not in d

    def test_to_dict_with_baseline(self) -> None:
        """验证带 baseline 时 to_dict 输出包含 baseline_metrics 和 delta"""
        result = ValidationResult(
            model_version="v1.0",
            metrics=ValidationMetrics(accuracy=0.95, sample_count=100),
            baseline_metrics=ValidationMetrics(accuracy=0.90, sample_count=100),
            delta={"accuracy": 0.05},
        )
        d = result.to_dict()
        assert d["baseline_metrics"]["accuracy"] == 0.9
        assert d["delta"]["accuracy"] == 0.05


class TestValidationEngineLoadDatasetExtended:
    """数据集加载扩展测试，覆盖 lines 116, 132-133"""

    def test_load_json_dataset_invalid_format(self, tmp_path: Path) -> None:
        """验证无效 JSON 格式（非 list、非 features/labels dict）抛出 ValueError"""
        engine = ValidationEngine()
        data = {"not_features": [], "not_labels": []}
        dataset_path = tmp_path / "invalid.json"
        dataset_path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid JSON dataset format"):
            engine.load_dataset(dataset_path)

    def test_load_csv_dataset_non_numeric_values(self, tmp_path: Path) -> None:
        """验证 CSV 中非数字值保留为字符串（不转换失败）"""
        engine = ValidationEngine()
        csv_content = "feature1,feature2,label\nabc,2.0,0\n3.0,xyz,1\n"
        dataset_path = tmp_path / "data.csv"
        dataset_path.write_text(csv_content, encoding="utf-8")
        features, labels = engine.load_dataset(dataset_path)
        assert features[0]["feature1"] == "abc"
        assert features[1]["feature2"] == "xyz"
        assert features[0]["feature2"] == 2.0
        assert features[1]["feature1"] == 3.0


class TestValidationEngineMetricsExtended:
    """指标计算扩展测试，覆盖 lines 188-212, 218-219, 246-249, 265, 272, 275-278"""

    def test_calculate_metrics_small_binary_no_probabilities(self) -> None:
        """验证小数据集二分类无 probabilities 走轻量计算路径（含 fp 分支）"""
        engine = ValidationEngine()
        y_true = [0, 1, 0, 1]
        y_pred = [0, 1, 1, 1]  # (0,1) 触发 fp 分支
        metrics = engine.calculate_metrics(y_true, y_pred)
        assert metrics.sample_count == 4
        assert metrics.accuracy == 0.75
        # tp=2, fp=1, fn=0
        assert metrics.precision == 2 / 3
        assert metrics.recall == 1.0
        assert metrics.f1 is not None
        assert metrics.mae is not None
        assert metrics.rmse is not None

    def test_calculate_metrics_small_all_non_numeric_labels(self) -> None:
        """验证小数据集全部为非数字标签时返回空指标（total <= 0 分支）"""
        engine = ValidationEngine()
        y_true = ["cat", "dog"]
        y_pred = ["cat", "cat"]
        metrics = engine.calculate_metrics(y_true, y_pred)
        assert metrics.sample_count == 0
        assert metrics.accuracy is None

    def test_calculate_metrics_small_some_non_numeric_labels(self) -> None:
        """验证小数据集部分非数字标签被跳过（H-Svc-16 修复分支）"""
        engine = ValidationEngine()
        y_true = [0, 1, "cat", "dog"]
        y_pred = [0, 1, "cat", "cat"]
        metrics = engine.calculate_metrics(y_true, y_pred)
        assert metrics.sample_count == 2
        assert metrics.accuracy == 1.0

    def test_calculate_metrics_multiclass_with_probabilities(self) -> None:
        """验证多分类带 probabilities 走 np 多分类路径（weighted 平均）"""
        engine = ValidationEngine()
        y_true = [0, 1, 2, 0, 1, 2, 0, 1]
        y_pred = [0, 1, 2, 0, 0, 2, 1, 1]
        probs = [0.1, 0.9, 0.5, 0.2, 0.4, 0.6, 0.3, 0.7]
        metrics = engine.calculate_metrics(y_true, y_pred, probs)
        assert metrics.sample_count == 8
        assert metrics.accuracy is not None
        assert metrics.precision is not None
        assert metrics.recall is not None
        assert metrics.f1 is not None
        assert metrics.mae is not None
        assert metrics.rmse is not None

    def test_calculate_metrics_auc_value_error(self) -> None:
        """验证 AUC 计算抛出 ValueError 时被静默捕获（except 分支）"""
        engine = ValidationEngine()
        y_true = [0, 1, 0, 1, 0, 1, 0, 1]
        y_pred = [0, 1, 0, 1, 0, 1, 0, 1]
        probs = [0.1, 0.9, 0.2, 0.8, 0.3, 0.7, 0.4, 0.6]
        # 模拟 roc_auc_score 抛 ValueError（覆盖 except ValueError: pass 分支）
        with patch(
            "app.services.validation_engine.roc_auc_score",
            side_effect=ValueError("forced for test"),
        ):
            metrics = engine.calculate_metrics(y_true, y_pred, probs)
        # except 分支捕获 ValueError，auc 保持 None
        assert metrics.auc is None
        # 其他指标仍正常计算
        assert metrics.accuracy is not None

    def test_calculate_metrics_probabilities_length_mismatch(self) -> None:
        """验证 probabilities 长度不匹配时跳过 AUC 计算"""
        engine = ValidationEngine()
        y_true = [0, 1, 0, 1, 0, 1, 0, 1]
        y_pred = [0, 1, 0, 1, 0, 1, 0, 1]
        probs = [0.1, 0.9]  # 长度不匹配
        metrics = engine.calculate_metrics(y_true, y_pred, probs)
        assert metrics.auc is None
        assert metrics.accuracy is not None

    def test_calculate_metrics_exception_in_np_path(self) -> None:
        """验证 np 路径异常（非数字标签）被外层 except 捕获"""
        engine = ValidationEngine()
        y_true = ["a", "b", "c", "d"]
        y_pred = ["a", "b", "c", "d"]
        probs = [0.1, 0.2, 0.3, 0.4]
        metrics = engine.calculate_metrics(y_true, y_pred, probs)
        assert metrics.sample_count == 4
        assert metrics.accuracy is None
        assert metrics.precision is None


class TestRunModelInference:
    """_run_model_inference 单元测试，覆盖 lines 333-368"""

    async def test_run_model_inference_unknown_version(self) -> None:
        """验证未知 model_version 返回 None（未映射）"""
        engine = ValidationEngine()
        result = await engine._run_model_inference("v999", [{"a": 1}])
        assert result is None

    async def test_run_model_inference_success(self) -> None:
        """验证成功推理返回 predictions 和 probabilities"""
        engine = ValidationEngine()
        mock_predict = AsyncMock(return_value={"prediction": 1, "probability": 0.9})
        with patch("app.core.model_engine.model_engine") as mock_engine:
            mock_engine.predict_structured = mock_predict
            result = await engine._run_model_inference("v1.20", [{"a": 1}, {"b": 2}])
        assert result is not None
        predictions, probabilities = result
        assert predictions == [1, 1]
        assert probabilities == [0.9, 0.9]

    async def test_run_model_inference_exception(self) -> None:
        """验证推理异常返回 None（被 except 捕获）"""
        engine = ValidationEngine()
        mock_predict = AsyncMock(side_effect=RuntimeError("inference failed"))
        with patch("app.core.model_engine.model_engine") as mock_engine:
            mock_engine.predict_structured = mock_predict
            result = await engine._run_model_inference("v1.20", [{"a": 1}])
        assert result is None


class TestValidateModel:
    """validate_model 单元测试，覆盖 lines 388-431"""

    async def test_validate_model_dataset_load_failure(self, tmp_path: Path) -> None:
        """验证数据集加载失败时返回带错误的空结果"""
        engine = ValidationEngine()
        result = await engine.validate_model("v1.20", tmp_path / "nonexistent.json")
        assert len(result.errors) == 1
        assert "Failed to load dataset" in result.errors[0]

    async def test_validate_model_inference_unavailable(self, tmp_path: Path) -> None:
        """验证推理不可用（未知版本）时记录错误并返回空指标"""
        engine = ValidationEngine()
        data = [{"a": 1.0, "label": 0}]
        dataset_path = tmp_path / "dataset.json"
        dataset_path.write_text(json.dumps(data), encoding="utf-8")
        result = await engine.validate_model("v999", dataset_path)
        assert any("Model inference unavailable" in e for e in result.errors)
        assert result.metrics.sample_count == 0

    async def test_validate_model_success(self, tmp_path: Path) -> None:
        """验证成功验证流程生成完整指标和预测列表"""
        engine = ValidationEngine()
        data = [
            {"a": 1.0, "label": 0},
            {"a": 2.0, "label": 1},
        ]
        dataset_path = tmp_path / "dataset.json"
        dataset_path.write_text(json.dumps(data), encoding="utf-8")
        mock_predict = AsyncMock(return_value={"prediction": 1, "probability": 0.9})
        with patch("app.core.model_engine.model_engine") as mock_engine:
            mock_engine.predict_structured = mock_predict
            result = await engine.validate_model("v1.20", dataset_path)
        assert len(result.errors) == 0
        assert result.metrics.sample_count == 2
        assert len(result.predictions) == 2
        assert result.predictions[0]["index"] == 0
        assert result.predictions[0]["probability"] == 0.9

    async def test_validate_model_with_baseline(self, tmp_path: Path) -> None:
        """验证带 baseline 的对比流程生成 baseline_metrics 和 delta"""
        engine = ValidationEngine()
        data = [
            {"a": 1.0, "label": 0},
            {"a": 2.0, "label": 1},
        ]
        dataset_path = tmp_path / "dataset.json"
        dataset_path.write_text(json.dumps(data), encoding="utf-8")
        mock_predict = AsyncMock(return_value={"prediction": 1, "probability": 0.9})
        with patch("app.core.model_engine.model_engine") as mock_engine:
            mock_engine.predict_structured = mock_predict
            result = await engine.validate_model(
                "v1.20", dataset_path, baseline_version="v1.21"
            )
        assert result.baseline_metrics is not None
        assert "accuracy" in result.delta

    async def test_validate_model_baseline_unavailable(self, tmp_path: Path) -> None:
        """验证 baseline 推理不可用时记录错误且 baseline_metrics 为 None"""
        engine = ValidationEngine()
        data = [
            {"a": 1.0, "label": 0},
            {"a": 2.0, "label": 1},
        ]
        dataset_path = tmp_path / "dataset.json"
        dataset_path.write_text(json.dumps(data), encoding="utf-8")
        # 主模型 v1.20 成功，baseline 版本 v999 未知导致推理不可用
        mock_predict = AsyncMock(return_value={"prediction": 1, "probability": 0.9})
        with patch("app.core.model_engine.model_engine") as mock_engine:
            mock_engine.predict_structured = mock_predict
            result = await engine.validate_model(
                "v1.20", dataset_path, baseline_version="v999"
            )
        assert any("Baseline metrics unavailable" in e for e in result.errors)
        assert result.baseline_metrics is None


class TestComputeBaselineMetrics:
    """_compute_baseline_metrics 单元测试，覆盖 lines 443-462"""

    async def test_compute_baseline_metrics_dataset_load_failure(
        self, tmp_path: Path
    ) -> None:
        """验证 baseline 数据集加载失败返回 None"""
        engine = ValidationEngine()
        result = await engine._compute_baseline_metrics(
            "v1.21", tmp_path / "nonexistent.json"
        )
        assert result is None

    async def test_compute_baseline_metrics_inference_unavailable(
        self, tmp_path: Path
    ) -> None:
        """验证 baseline 推理不可用（未知版本）返回 None"""
        engine = ValidationEngine()
        data = [{"a": 1.0, "label": 0}]
        dataset_path = tmp_path / "dataset.json"
        dataset_path.write_text(json.dumps(data), encoding="utf-8")
        result = await engine._compute_baseline_metrics("v999", dataset_path)
        assert result is None

    async def test_compute_baseline_metrics_success(self, tmp_path: Path) -> None:
        """验证 baseline 指标计算成功"""
        engine = ValidationEngine()
        data = [
            {"a": 1.0, "label": 0},
            {"a": 2.0, "label": 1},
        ]
        dataset_path = tmp_path / "dataset.json"
        dataset_path.write_text(json.dumps(data), encoding="utf-8")
        mock_predict = AsyncMock(return_value={"prediction": 1, "probability": 0.9})
        with patch("app.core.model_engine.model_engine") as mock_engine:
            mock_engine.predict_structured = mock_predict
            result = await engine._compute_baseline_metrics("v1.21", dataset_path)
        assert result is not None
        assert result.sample_count == 2
