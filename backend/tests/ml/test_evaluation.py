"""Tests for evaluation module."""

from __future__ import annotations

import numpy as np

from app.ml.evaluation import (
    compute_calibration_curve,
    compute_confusion_matrix,
    compute_roc_curve,
    compute_shap_values_approximation,
    generate_evaluation_report,
)


class TestComputeConfusionMatrix:
    """Test compute_confusion_matrix."""

    def test_perfect_prediction(self):
        """TC-COV-ML-033: Perfect prediction confusion matrix."""
        y_true = np.array([0, 0, 1, 1])
        y_pred = np.array([0.1, 0.2, 0.8, 0.9])
        result = compute_confusion_matrix(y_true, y_pred)
        assert result["tp"] == 2
        assert result["tn"] == 2
        assert result["fp"] == 0
        assert result["fn"] == 0
        assert result["total"] == 4

    def test_mixed_prediction(self):
        """TC-COV-ML-034: Mixed prediction confusion matrix."""
        y_true = np.array([0, 0, 1, 1])
        y_pred = np.array([0.6, 0.2, 0.8, 0.4])
        result = compute_confusion_matrix(y_true, y_pred)
        assert result["tp"] == 1
        assert result["tn"] == 1
        assert result["fp"] == 1
        assert result["fn"] == 1

    def test_empty(self):
        """TC-COV-ML-035: Empty input returns zero counts."""
        y_true = np.array([])
        y_pred = np.array([])
        result = compute_confusion_matrix(y_true, y_pred)
        assert result["total"] == 0


class TestComputeRocCurve:
    """Test compute_roc_curve."""

    def test_basic(self):
        """TC-COV-ML-036: ROC curve computation."""
        y_true = np.array([0, 0, 1, 1])
        y_scores = np.array([0.1, 0.4, 0.6, 0.9])
        result = compute_roc_curve(y_true, y_scores)
        assert "fpr" in result
        assert "tpr" in result
        assert "auc" in result
        assert 0 <= result["auc"] <= 1

    def test_single_class(self):
        """TC-COV-ML-037: Single class returns default ROC."""
        y_true = np.array([0, 0, 0, 0])
        y_scores = np.array([0.1, 0.4, 0.6, 0.9])
        result = compute_roc_curve(y_true, y_scores)
        assert result["auc"] == 0.5


class TestComputeCalibrationCurve:
    """Test compute_calibration_curve."""

    def test_basic(self):
        """TC-COV-ML-038: Calibration curve computation."""
        y_true = np.array([0, 0, 1, 1])
        y_scores = np.array([0.1, 0.4, 0.6, 0.9])
        result = compute_calibration_curve(y_true, y_scores, n_bins=5)
        assert "bin_centers" in result
        assert "bin_accuracies" in result
        assert "expected_calibration_error" in result


class TestComputeShapValues:
    """Test compute_shap_values_approximation."""

    def test_basic(self):
        """TC-COV-ML-039: SHAP approximation computation."""
        X = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
        feature_names = ["f1", "f2"]

        def mock_predict(X):
            return X[:, 0] + X[:, 1]

        result = compute_shap_values_approximation(
            X, feature_names, mock_predict, n_samples=3
        )
        assert "feature_importances" in result
        assert "sorted_features" in result
        assert len(result["sorted_features"]) == 2


class TestGenerateEvaluationReport:
    """Test generate_evaluation_report."""

    def test_full_report(self):
        """TC-COV-ML-040: Full evaluation report generation."""
        y_true = np.array([0, 0, 1, 1])
        y_pred = np.array([0.1, 0.4, 0.6, 0.9])
        result = generate_evaluation_report(y_true, y_pred)
        assert "confusion_matrix" in result
        assert "roc_curve" in result
        assert "calibration_curve" in result

    def test_with_shap(self):
        """TC-COV-ML-041: Report with SHAP values."""
        y_true = np.array([0, 0, 1, 1])
        y_pred = np.array([0.1, 0.4, 0.6, 0.9])
        feature_names = ["f1"]
        X = np.array([[0.1], [0.2], [0.3], [0.4]])

        def mock_predict(X):
            return X[:, 0]

        result = generate_evaluation_report(
            y_true,
            y_pred,
            feature_names=feature_names,
            model_predict_fn=mock_predict,
            X=X,
        )
        assert "shap_values" in result
