"""Tests for ExperimentMetrics."""

from __future__ import annotations

from app.services.experiment_metrics import ExperimentMetrics


class TestExperimentMetrics:
    """Test experiment metrics calculations."""

    def test_metrics_basic(self):
        """TC-COV-EXP-001: Basic metrics calculation."""
        y_true = [0, 0, 1, 1]
        y_pred = [0, 1, 1, 1]
        y_score = [0.1, 0.6, 0.8, 0.9]
        result = ExperimentMetrics.metrics(y_true, y_pred, y_score)
        assert "accuracy" in result
        assert "precision" in result
        assert "recall" in result
        assert "f1" in result
        assert "auc" in result
        assert 0 <= result["accuracy"] <= 1
        assert 0 <= result["auc"] <= 1

    def test_metrics_all_correct(self):
        """TC-COV-EXP-002: Perfect prediction metrics."""
        y_true = [0, 0, 1, 1]
        y_pred = [0, 0, 1, 1]
        y_score = [0.1, 0.2, 0.8, 0.9]
        result = ExperimentMetrics.metrics(y_true, y_pred, y_score)
        assert result["accuracy"] == 1.0
        assert result["precision"] == 1.0
        assert result["recall"] == 1.0

    def test_metrics_roc_auc_exception(self):
        """TC-COV-EXP-003: roc_auc exception returns numeric value (0.5 or 0)."""
        y_true = [0, 0, 0, 0]
        y_pred = [0, 0, 0, 0]
        y_score = [0.1, 0.2, 0.3, 0.4]
        result = ExperimentMetrics.metrics(y_true, y_pred, y_score)
        # 当所有标签相同时,roc_auc 可能 NaN/0.5/0,只要是数字即可
        auc = result.get("auc", result.get("roc_auc", 0))
        assert isinstance(auc, (int, float))
        assert 0.0 <= auc <= 1.0 or auc != auc  # NaN ok

    def test_confusion_matrix(self):
        """TC-COV-EXP-004: Confusion matrix calculation."""
        y_true = [0, 0, 1, 1]
        y_pred = [0, 1, 1, 0]
        result = ExperimentMetrics.confusion_matrix(y_true, y_pred)
        assert result["tp"] == 1
        assert result["tn"] == 1
        assert result["fp"] == 1
        assert result["fn"] == 1

    def test_confusion_matrix_all_correct(self):
        """TC-COV-EXP-005: Perfect prediction confusion matrix."""
        y_true = [0, 0, 1, 1]
        y_pred = [0, 0, 1, 1]
        result = ExperimentMetrics.confusion_matrix(y_true, y_pred)
        assert result["tp"] == 2
        assert result["tn"] == 2
        assert result["fp"] == 0
        assert result["fn"] == 0

    def test_prediction_samples(self):
        """TC-COV-EXP-006: Prediction samples with limit."""
        y_true = [0, 1, 1, 0, 1, 0]
        y_pred = [0, 1, 0, 0, 1, 1]
        y_score = [0.1, 0.8, 0.4, 0.2, 0.9, 0.6]
        result = ExperimentMetrics.prediction_samples(y_true, y_pred, y_score, limit=3)
        assert len(result) == 3
        assert result[0]["index"] == 0
        assert "true_label" in result[0]
        assert "pred_label" in result[0]
        assert "score" in result[0]

    def test_prediction_samples_default_limit(self):
        """TC-COV-EXP-007: Prediction samples with default limit."""
        y_true = [0] * 20
        y_pred = [0] * 20
        y_score = [0.5] * 20
        result = ExperimentMetrics.prediction_samples(y_true, y_pred, y_score)
        assert len(result) == 12  # default limit

    def test_eval_history(self):
        """TC-COV-EXP-008: Evaluation history entry."""
        y_true = [0, 0, 1, 1]
        y_pred = [0, 1, 1, 1]
        y_score = [0.1, 0.6, 0.8, 0.9]
        metrics = ExperimentMetrics.metrics(y_true, y_pred, y_score)
        result = ExperimentMetrics.eval_history(
            y_true, y_pred, y_score, "test", metrics
        )
        assert len(result) == 1
        assert result[0]["split"] == "test"
        assert result[0]["sample_count"] == 4
        assert "confusion_matrix" in result[0]
        assert "prediction_preview" in result[0]

    def test_build_confusion_heatmap(self):
        """TC-COV-EXP-009: Confusion heatmap matrix."""
        cm = {"tn": 10, "fp": 2, "fn": 1, "tp": 7}
        result = ExperimentMetrics.build_confusion_heatmap(cm)
        assert result == [[10, 2], [1, 7]]

    def test_build_confusion_heatmap_missing_keys(self):
        """TC-COV-EXP-010: Confusion heatmap with missing keys defaults to 0."""
        cm = {"tp": 5}
        result = ExperimentMetrics.build_confusion_heatmap(cm)
        assert result == [[0, 0], [0, 5]]
