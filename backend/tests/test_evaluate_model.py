"""
Test suite for unified model evaluation script.

Tests:
- TC-GOV-001: 验证评估脚本功能
- TC-CMP-001: 验证对照实验评估流程
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Add project root to path
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / "backend"))
sys.path.insert(0, str(project_root))

try:
    from scripts.evaluation.evaluate_model import (
        cross_validate,
        generate_report,
        load_data,
        save_report,
    )
except ImportError:
    pytest.skip(
        "scripts/evaluation/evaluate_model.py 不存在, 跳过模型评估测试",
        allow_module_level=True,
    )


class TestEvaluateModel:
    """Test suite for unified model evaluation."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

        # Create a simple test dataset
        np.random.seed(42)
        n_samples = 100
        n_features = 5

        self.X = np.random.randn(n_samples, n_features)
        self.y = (self.X[:, 0] + self.X[:, 1] > 0).astype(int)

        self.df = pd.DataFrame(
            self.X,
            columns=[f"feature_{i}" for i in range(n_features)],
        )
        self.df["target"] = self.y

        self.data_path = Path(self.temp_dir) / "test_data.csv"
        self.df.to_csv(self.data_path, index=False)

        # Create a simple mock model file (using sklearn)
        from sklearn.linear_model import LogisticRegression

        model = LogisticRegression(random_state=42)
        model.fit(self.X, self.y)

        self.model_path = Path(self.temp_dir) / "test_model.pkl"
        import joblib

        joblib.dump(model, self.model_path)

    def test_load_data(self) -> None:
        """验证数据加载功能."""
        X, y, feature_names = load_data(str(self.data_path), "target")

        assert len(X) == 100
        assert X.shape[1] == 5
        assert len(y) == 100
        assert len(feature_names) == 5
        assert "feature_0" in feature_names

    def test_load_data_with_feature_columns(self) -> None:
        """验证指定特征列加载."""
        feature_columns = ["feature_0", "feature_1"]
        X, y, feature_names = load_data(str(self.data_path), "target", feature_columns)

        assert X.shape[1] == 2
        assert feature_names == feature_columns

    def test_cross_validation(self) -> None:
        """验证交叉验证功能."""
        result = cross_validate(
            model_type="logistic_regression",
            model_path=str(self.model_path),
            X=self.X,
            y=self.y,
            n_folds=3,
            random_state=42,
        )

        assert result["n_folds"] == 3
        assert len(result["fold_results"]) == 3
        assert "aggregated" in result

        # Check aggregated metrics
        for metric in ["f1", "precision", "recall", "accuracy"]:
            assert metric in result["aggregated"]
            assert "mean" in result["aggregated"][metric]
            assert "std" in result["aggregated"][metric]
            assert "ci_lower" in result["aggregated"][metric]
            assert "ci_upper" in result["aggregated"][metric]

    def test_generate_report(self) -> None:
        """验证报告生成功能."""
        report = generate_report(
            model_type="logistic_regression",
            model_path=str(self.model_path),
            X=self.X,
            y=self.y,
            feature_names=[f"feature_{i}" for i in range(5)],
            baseline_predictions=None,
            n_folds=3,
            n_bootstrap=100,
            random_state=42,
        )

        assert report["model_type"] == "logistic_regression"
        assert "dataset_info" in report
        assert report["dataset_info"]["n_samples"] == 100
        assert "cross_validation" in report
        assert "confusion_matrix" in report
        assert "roc_curve" in report
        assert "calibration_curve" in report
        assert "bootstrap_ci_f1" in report

    def test_save_report(self) -> None:
        """验证报告保存功能."""
        report = {
            "model_type": "test",
            "dataset_info": {"n_samples": 100},
            "cross_validation": {"n_folds": 3},
        }

        output_dir = Path(self.temp_dir) / "reports"
        filepath = save_report(report, str(output_dir))

        assert filepath.exists()
        assert filepath.suffix == ".json"

        # Verify saved content
        with open(filepath, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["model_type"] == "test"

    def test_report_with_baseline(self) -> None:
        """验证包含基线对比的报告."""
        # Create baseline predictions
        baseline_pred = np.random.random(len(self.y))

        report = generate_report(
            model_type="logistic_regression",
            model_path=str(self.model_path),
            X=self.X,
            y=self.y,
            feature_names=[f"feature_{i}" for i in range(5)],
            baseline_predictions=baseline_pred,
            n_folds=3,
            n_bootstrap=100,
            random_state=42,
        )

        assert "mcnemar_test" in report
        assert "statistic" in report["mcnemar_test"]
        assert "p_value" in report["mcnemar_test"]
        assert "conclusion" in report["mcnemar_test"]


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
