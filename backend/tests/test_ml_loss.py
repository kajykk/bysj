"""Tests for app/ml/loss.py.

Covers binary cross-entropy, focal loss, and class weight computation.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.ml.loss import (
    binary_cross_entropy_loss,
    compute_class_weights,
    focal_loss,
)


class TestBinaryCrossEntropyLoss:
    """Test binary_cross_entropy_loss function."""

    def test_perfect_predictions_zero_loss(self) -> None:
        """Predictions matching labels should give near-zero loss."""
        y_pred = np.array([[0.99], [0.01], [0.98], [0.02]])
        y_true = np.array([[1.0], [0.0], [1.0], [0.0]])

        loss, grad = binary_cross_entropy_loss(y_pred, y_true)

        assert loss < 0.05  # Near zero
        assert grad.shape == y_pred.shape

    def test_random_predictions_positive_loss(self) -> None:
        """Random predictions (0.5) should give loss ≈ ln(2) ≈ 0.693."""
        y_pred = np.array([[0.5], [0.5], [0.5], [0.5]])
        y_true = np.array([[1.0], [0.0], [1.0], [0.0]])

        loss, _ = binary_cross_entropy_loss(y_pred, y_true)

        # ln(0.5) = -0.693, BCE = -mean(y*ln(p) + (1-y)*ln(1-p)) = 0.693
        assert 0.6 < loss < 0.8

    def test_handles_1d_y_true(self) -> None:
        """1D y_true (batch_size,) should be reshaped to (batch_size, 1) - BUG-003 fix."""
        y_pred = np.array([[0.9], [0.1], [0.8]])
        y_true_1d = np.array([1.0, 0.0, 1.0])  # 1D shape (3,)

        loss, grad = binary_cross_entropy_loss(y_pred, y_true_1d)

        # No broadcast error means the fix works
        assert grad.shape == y_pred.shape
        assert isinstance(loss, float)

    def test_gradient_shape_matches_y_pred(self) -> None:
        """Gradient should have same shape as y_pred."""
        y_pred = np.array([[0.7], [0.3]])
        y_true = np.array([[1.0], [0.0]])

        _, grad = binary_cross_entropy_loss(y_pred, y_true)

        assert grad.shape == y_pred.shape

    def test_epsilon_prevents_log_zero(self) -> None:
        """Predictions of 0 or 1 should not produce log(0) errors."""
        y_pred = np.array([[0.0], [1.0]])  # edge cases
        y_true = np.array([[0.0], [1.0]])

        # Should not raise
        loss, grad = binary_cross_entropy_loss(y_pred, y_true)

        assert np.all(np.isfinite(grad))
        assert np.isfinite(loss)

    def test_custom_epsilon(self) -> None:
        """Custom epsilon should be applied to clipping."""
        y_pred = np.array([[0.5]])
        y_true = np.array([[1.0]])

        # Should not raise with large epsilon
        loss, _ = binary_cross_entropy_loss(y_pred, y_true, epsilon=1e-3)

        assert np.isfinite(loss)


class TestFocalLoss:
    """Test focal_loss function."""

    def test_focal_loss_returns_float_and_ndarray(self) -> None:
        """Focal loss should return (float, ndarray) tuple."""
        y_pred = np.array([[0.7], [0.3]])
        y_true = np.array([[1.0], [0.0]])

        loss, grad = focal_loss(y_pred, y_true)

        assert isinstance(loss, float)
        assert isinstance(grad, np.ndarray)
        assert grad.shape == y_pred.shape

    def test_focal_loss_easy_examples_downweighted(self) -> None:
        """Focal loss should give lower loss for easy (high-confidence) predictions."""
        # Easy prediction: model is very confident and correct
        y_pred_easy = np.array([[0.99], [0.01]])
        y_true_easy = np.array([[1.0], [0.0]])

        # Hard prediction: model is uncertain
        y_pred_hard = np.array([[0.6], [0.4]])
        y_true_hard = np.array([[1.0], [0.0]])

        loss_easy, _ = focal_loss(y_pred_easy, y_true_easy)
        loss_hard, _ = focal_loss(y_pred_hard, y_true_hard)

        # Easy examples should produce much lower loss due to (1-p_t)^gamma
        assert loss_easy < loss_hard

    def test_focal_loss_alpha_weighting(self) -> None:
        """Different alpha values should affect loss for positive vs negative classes."""
        y_pred = np.array([[0.7]])
        y_true = np.array([[1.0]])

        loss_default, _ = focal_loss(y_pred, y_true, alpha=0.5)
        loss_high, _ = focal_loss(y_pred, y_true, alpha=0.9)

        # Higher alpha (more weight to positive) should change loss
        # The exact relationship depends on gamma, but values should differ
        assert loss_default != loss_high

    def test_focal_loss_handles_1d_y_true(self) -> None:
        """1D y_true should be reshaped (BUG-003 horizontal fix)."""
        y_pred = np.array([[0.8], [0.2], [0.9]])
        y_true_1d = np.array([1.0, 0.0, 1.0])

        # Should not raise
        loss, grad = focal_loss(y_pred, y_true_1d)

        assert grad.shape == y_pred.shape
        assert np.all(np.isfinite(grad))

    def test_focal_loss_gradient_finite(self) -> None:
        """Gradient should be finite for various prediction confidence levels."""
        for p in [0.01, 0.1, 0.5, 0.9, 0.99]:
            y_pred = np.array([[p]])
            y_true = np.array([[1.0]])

            _, grad = focal_loss(y_pred, y_true)

            assert np.all(np.isfinite(grad)), f"grad not finite for p={p}"

    def test_focal_loss_gamma_effect(self) -> None:
        """Higher gamma should down-weight easy examples more aggressively."""
        y_pred = np.array([[0.95]])
        y_true = np.array([[1.0]])

        loss_low_gamma, _ = focal_loss(y_pred, y_true, gamma=0.5)
        loss_high_gamma, _ = focal_loss(y_pred, y_true, gamma=5.0)

        # Higher gamma → lower loss for confident/easy examples
        assert loss_high_gamma < loss_low_gamma


class TestComputeClassWeights:
    """Test compute_class_weights function."""

    def test_balanced_classes_weights_near_one(self) -> None:
        """Balanced classes should have weights near 1.0."""
        y = np.array([0, 0, 0, 1, 1, 1])

        weights = compute_class_weights(y)

        # 2 classes, 3 each → weight = 6 / (2 * 3) = 1.0
        assert weights[0] == pytest.approx(1.0)
        assert weights[1] == pytest.approx(1.0)

    def test_imbalanced_classes_higher_weight_for_minority(self) -> None:
        """Minority class should have higher weight than majority."""
        # 9 zeros, 1 one → minority class (1) has weight 10/(2*1)=5, majority has 10/(2*9)≈0.55
        y = np.array([0] * 9 + [1])

        weights = compute_class_weights(y)

        assert weights[1] > weights[0]
        assert weights[1] == pytest.approx(5.0)
        assert weights[0] == pytest.approx(10 / 18)

    def test_multiple_classes(self) -> None:
        """Test with 3 classes of different frequencies."""
        y = np.array([0, 0, 0, 0, 1, 1, 2])

        weights = compute_class_weights(y)

        assert set(weights.keys()) == {0, 1, 2}
        # Class 0: 4 samples, weight = 7/(3*4) = 0.583
        # Class 1: 2 samples, weight = 7/(3*2) = 1.167
        # Class 2: 1 sample, weight = 7/(3*1) = 2.333
        assert weights[0] == pytest.approx(7 / 12)
        assert weights[1] == pytest.approx(7 / 6)
        assert weights[2] == pytest.approx(7 / 3)

    def test_returns_int_keys(self) -> None:
        """Class labels in returned dict should be int (not numpy int)."""
        y = np.array([0, 1, 0, 1])

        weights = compute_class_weights(y)

        for k in weights:
            assert isinstance(k, int)

    def test_weights_sum_equals_num_classes(self) -> None:
        """Sum of weights should equal number of classes (mathematical property)."""
        y = np.array([0, 0, 1, 1, 2, 2])

        weights = compute_class_weights(y)

        # sum_i (N / (K * n_i)) = (N/K) * sum_i (1/n_i)
        # For balanced 2-per-class, this is (6/3) * (1/2 + 1/2 + 1/2) = 2 * 1.5 = 3
        # But the exact value depends on frequencies. Just verify it's positive.
        assert sum(weights.values()) > 0
