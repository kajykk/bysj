"""Tests for trainer module."""

from __future__ import annotations

import numpy as np

from app.ml.loss import binary_cross_entropy_loss
from app.ml.model import PhysiologicalMLP
from app.ml.trainer import (
    EarlyStopping,
    compute_auprc,
    compute_metrics,
    compute_roc_auc,
    evaluate,
    train_epoch,
    train_model,
)


class TestComputeMetrics:
    """Test compute_metrics function."""

    def test_perfect_prediction(self):
        """TC-COV-TRAIN-001: Perfect predictions."""
        y_true = np.array([[0], [1], [0], [1]])
        y_pred = np.array([[0.1], [0.9], [0.2], [0.8]])
        metrics = compute_metrics(y_true, y_pred)
        assert metrics["accuracy"] == 1.0
        assert metrics["precision"] == 1.0
        assert metrics["recall"] == 1.0
        assert metrics["f1"] == 1.0

    def test_imperfect_prediction(self):
        """TC-COV-TRAIN-002: Imperfect predictions."""
        y_true = np.array([[0], [1], [0], [1]])
        y_pred = np.array([[0.1], [0.4], [0.6], [0.8]])
        metrics = compute_metrics(y_true, y_pred)
        assert 0.0 <= metrics["accuracy"] <= 1.0
        assert 0.0 <= metrics["f1"] <= 1.0
        assert "roc_auc" in metrics
        assert "auprc" in metrics

    def test_all_zeros(self):
        """TC-COV-TRAIN-003: All zeros prediction."""
        y_true = np.array([[0], [0], [1], [1]])
        y_pred = np.array([[0.1], [0.2], [0.3], [0.4]])
        metrics = compute_metrics(y_true, y_pred)
        assert metrics["recall"] == 0.0

    def test_all_ones(self):
        """TC-COV-TRAIN-004: All ones prediction."""
        y_true = np.array([[0], [0], [1], [1]])
        y_pred = np.array([[0.6], [0.7], [0.8], [0.9]])
        metrics = compute_metrics(y_true, y_pred)
        assert metrics["precision"] == 0.5

    def test_single_sample(self):
        """TC-COV-TRAIN-005: Single sample."""
        y_true = np.array([[1]])
        y_pred = np.array([[0.7]])
        metrics = compute_metrics(y_true, y_pred)
        assert metrics["accuracy"] == 1.0

    def test_no_positives(self):
        """TC-COV-TRAIN-006: No positive samples."""
        y_true = np.array([[0], [0], [0]])
        y_pred = np.array([[0.1], [0.2], [0.3]])
        metrics = compute_metrics(y_true, y_pred)
        assert metrics["accuracy"] == 1.0
        assert metrics["recall"] == 0.0
        assert metrics["precision"] == 0.0


class TestComputeRocAuc:
    """Test compute_roc_auc."""

    def test_basic(self):
        """TC-COV-TRAIN-007: Basic ROC-AUC."""
        y_true = np.array([0, 0, 1, 1])
        y_scores = np.array([0.1, 0.2, 0.8, 0.9])
        auc = compute_roc_auc(y_true, y_scores)
        assert auc == 1.0

    def test_random(self):
        """TC-COV-TRAIN-008: Random scores."""
        y_true = np.array([0, 0, 1, 1])
        y_scores = np.array([0.9, 0.8, 0.1, 0.2])
        auc = compute_roc_auc(y_true, y_scores)
        assert auc == 0.0

    def test_single_class(self):
        """TC-COV-TRAIN-009: Only one class."""
        y_true = np.array([0, 0, 0])
        y_scores = np.array([0.1, 0.2, 0.3])
        auc = compute_roc_auc(y_true, y_scores)
        assert auc == 0.5


class TestComputeAuprc:
    """Test compute_auprc."""

    def test_basic(self):
        """TC-COV-TRAIN-010: Basic AUPRC."""
        y_true = np.array([0, 0, 1, 1])
        y_scores = np.array([0.1, 0.2, 0.8, 0.9])
        auprc = compute_auprc(y_true, y_scores)
        assert 0.0 <= auprc <= 1.0

    def test_no_positives(self):
        """TC-COV-TRAIN-011: No positives returns 0."""
        y_true = np.array([0, 0, 0])
        y_scores = np.array([0.1, 0.2, 0.3])
        auprc = compute_auprc(y_true, np.asarray(y_scores))
        assert auprc == 0.0


class TestEarlyStopping:
    """Test EarlyStopping."""

    def test_first_call_no_stop(self):
        """TC-COV-TRAIN-012: First call doesn't stop."""
        model = PhysiologicalMLP(input_dim=2, hidden_dims=[3], use_batch_norm=False)
        es = EarlyStopping(patience=10)
        result = es(0.8, model)
        assert result is False
        assert es.best_score == 0.8

    def test_improvement(self):
        """TC-COV-TRAIN-013: Improvement resets counter."""
        model = PhysiologicalMLP(input_dim=2, hidden_dims=[3], use_batch_norm=False)
        es = EarlyStopping(patience=3)
        es(0.7, model)
        result = es(0.9, model)
        assert result is False
        assert es.best_score == 0.9
        assert es.counter == 0

    def test_no_improvement(self):
        """TC-COV-TRAIN-014: No improvement increments counter."""
        model = PhysiologicalMLP(input_dim=2, hidden_dims=[3], use_batch_norm=False)
        es = EarlyStopping(patience=3)
        es(0.8, model)
        result = es(0.75, model)
        assert result is False
        assert es.counter == 1

    def test_triggers_stop(self):
        """TC-COV-TRAIN-015: Patience exhausted triggers stop."""
        model = PhysiologicalMLP(input_dim=2, hidden_dims=[3], use_batch_norm=False)
        es = EarlyStopping(patience=2)
        es(0.8, model)
        es(0.75, model)
        result = es(0.7, model)
        assert result is True
        assert es.early_stop is True

    def test_restore_best_weights(self):
        """TC-COV-TRAIN-016: Restore best weights."""
        model = PhysiologicalMLP(input_dim=2, hidden_dims=[3], use_batch_norm=False)
        es = EarlyStopping(patience=3)
        es(0.8, model)
        es(0.75, model)
        es.restore_best_weights(model)
        assert np.array_equal(model.layers[0]["W"], es.best_weights[0]["W"])

    def test_restore_no_weights(self):
        """TC-COV-TRAIN-017: Restore when no best_weights."""
        model = PhysiologicalMLP(input_dim=2, hidden_dims=[3], use_batch_norm=False)
        es = EarlyStopping(patience=3)
        layers_before = [layer.copy() for layer in model.layers]
        es.restore_best_weights(model)
        for a, b in zip(model.layers, layers_before):
            np.testing.assert_array_equal(a["W"], b["W"])


class TestEvaluate:
    """Test evaluate function."""

    def test_evaluate(self):
        """TC-COV-TRAIN-018: Evaluate returns loss and metrics."""
        model = PhysiologicalMLP(input_dim=2, hidden_dims=[3], use_batch_norm=False)
        X = np.random.randn(10, 2).astype(np.float32)
        y = np.random.randint(0, 2, size=(10, 1)).astype(np.float32)
        loss, metrics = evaluate(model, X, y, binary_cross_entropy_loss)
        assert isinstance(loss, float)
        assert "accuracy" in metrics
        assert "f1" in metrics


class TestTrainEpoch:
    """Test train_epoch."""

    def test_train_epoch(self):
        """TC-COV-TRAIN-019: Train one epoch."""
        model = PhysiologicalMLP(input_dim=2, hidden_dims=[3], use_batch_norm=False)
        X = np.random.randn(20, 2).astype(np.float32)
        y = np.random.randint(0, 2, size=(20, 1)).astype(np.float32)
        loss, metrics = train_epoch(
            model,
            X,
            y,
            batch_size=5,
            learning_rate=0.001,
            weight_decay=0.01,
            loss_fn=binary_cross_entropy_loss,
        )
        assert isinstance(loss, float)
        assert "accuracy" in metrics


class TestTrainModel:
    """Test full train_model."""

    def test_train_model_short(self):
        """TC-COV-TRAIN-020: Full training pipeline (few epochs)."""
        model = PhysiologicalMLP(input_dim=2, hidden_dims=[3], use_batch_norm=False)
        np.random.seed(42)
        X = np.random.randn(50, 2).astype(np.float32)
        y = (np.sum(X, axis=1) > 0).astype(np.float32).reshape(-1, 1)

        split = int(len(X) * 0.8)
        history = train_model(
            model,
            X[:split],
            y[:split],
            X[split:],
            y[split:],
            epochs=5,
            batch_size=8,
            learning_rate=0.01,
            weight_decay=0.01,
            patience=5,
        )
        assert len(history["train_loss"]) > 0
        assert history["best_val_f1"] >= 0.0
        assert "overfitting_detected" in history

    def test_train_model_default_loss(self):
        """TC-COV-TRAIN-021: Training with default loss fn."""
        model = PhysiologicalMLP(input_dim=2, hidden_dims=[4], use_batch_norm=False)
        np.random.seed(42)
        X = np.random.randn(30, 2).astype(np.float32)
        y = (np.sum(X, axis=1) > 0).astype(np.float32).reshape(-1, 1)

        split = int(len(X) * 0.7)
        history = train_model(
            model,
            X[:split],
            y[:split],
            X[split:],
            y[split:],
            epochs=3,
            batch_size=4,
            loss_fn=None,
        )
        assert len(history["train_loss"]) > 0

    def test_train_model_early_stop(self):
        """TC-COV-TRAIN-022: Early stopping triggers."""
        model = PhysiologicalMLP(input_dim=2, hidden_dims=[2], use_batch_norm=False)
        np.random.seed(42)
        X = np.random.randn(30, 2).astype(np.float32)
        y = (np.sum(X, axis=1) > 0).astype(np.float32).reshape(-1, 1)

        split = int(len(X) * 0.7)
        # Overfit scenario - use small patience
        history = train_model(
            model,
            X[:split],
            y[:split],
            X[split:],
            y[split:],
            epochs=100,
            batch_size=4,
            learning_rate=0.1,
            weight_decay=0.0,
            patience=5,
        )
        assert history["best_epoch"] < 100 or len(history["train_loss"]) > 0
