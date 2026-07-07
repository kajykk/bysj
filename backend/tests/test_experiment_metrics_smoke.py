"""Tests for experiment metrics module."""

from __future__ import annotations

from app.services.experiment_metrics import ExperimentMetrics


class TestExperimentMetrics:
    """Test ExperimentMetrics static methods."""

    def test_metrics(self):
        """TC-COV-EM-001: Compute metrics."""
        y_true = [0, 0, 1, 1, 0, 1]
        y_pred = [0, 0, 1, 1, 1, 1]
        y_score = [0.1, 0.2, 0.8, 0.9, 0.6, 0.7]
        result = ExperimentMetrics.metrics(y_true, y_pred, y_score)
        assert "accuracy" in result
        assert "precision" in result
        assert "recall" in result
        assert "f1" in result
        assert "auc" in result
        assert 0.0 <= result["accuracy"] <= 1.0

    def test_metrics_auc_fallback(self):
        """TC-COV-EM-002: AUC fallback when only one class."""
        y_true = [0, 0, 0]
        y_pred = [0, 0, 0]
        y_score = [0.1, 0.2, 0.3]
        result = ExperimentMetrics.metrics(y_true, y_pred, y_score)
        assert result["auc"] == 0.5 or result["auc"] != result["auc"]  # 0.5 or nan

    def test_confusion_matrix(self):
        """TC-COV-EM-003: Compute confusion matrix."""
        y_true = [0, 0, 1, 1, 0, 1]
        y_pred = [0, 1, 1, 1, 0, 0]
        cm = ExperimentMetrics.confusion_matrix(y_true, y_pred)
        assert cm["tp"] == 2
        assert cm["tn"] == 2
        assert cm["fp"] == 1
        assert cm["fn"] == 1

    def test_prediction_samples(self):
        """TC-COV-EM-004: Get prediction samples."""
        y_true = [0, 1, 0, 1]
        y_pred = [0, 1, 1, 1]
        y_score = [0.1, 0.9, 0.6, 0.8]
        samples = ExperimentMetrics.prediction_samples(y_true, y_pred, y_score, limit=2)
        assert len(samples) == 2
        assert "index" in samples[0]
        assert "true_label" in samples[0]
        assert "pred_label" in samples[0]
        assert "score" in samples[0]

    def test_prediction_samples_limit(self):
        """TC-COV-EM-005: Limit respected."""
        y_true = [0] * 20
        y_pred = [0] * 20
        y_score = [0.1] * 20
        samples = ExperimentMetrics.prediction_samples(y_true, y_pred, y_score, limit=5)
        assert len(samples) == 5

    def test_eval_history(self):
        """TC-COV-EM-006: Build eval history."""
        y_true = [0, 0, 1, 1]
        y_pred = [0, 0, 1, 1]
        y_score = [0.1, 0.2, 0.8, 0.9]
        metrics = {
            "accuracy": 1.0,
            "precision": 1.0,
            "recall": 1.0,
            "f1": 1.0,
            "auc": 1.0,
        }
        history = ExperimentMetrics.eval_history(
            y_true, y_pred, y_score, "test", metrics
        )
        assert len(history) == 1
        assert history[0]["split"] == "test"
        assert history[0]["sample_count"] == 4
        assert "confusion_matrix" in history[0]
        assert "prediction_preview" in history[0]

    def test_build_confusion_heatmap(self):
        """TC-COV-EM-007: Build confusion heatmap."""
        cm = {"tn": 5, "fp": 2, "fn": 1, "tp": 8}
        heatmap = ExperimentMetrics.build_confusion_heatmap(cm)
        assert heatmap == [[5, 2], [1, 8]]

    def test_build_confusion_heatmap_defaults(self):
        """TC-COV-EM-008: Build heatmap with missing keys."""
        cm = {"tn": 3, "tp": 4}
        heatmap = ExperimentMetrics.build_confusion_heatmap(cm)
        assert heatmap == [[3, 0], [0, 4]]
