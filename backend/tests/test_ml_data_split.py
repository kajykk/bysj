"""Tests for app/ml data_split module."""

from __future__ import annotations

import numpy as np
import pytest

from app.ml.data_split import stratified_split, verify_split_integrity


class TestStratifiedSplit:
    """Test stratified_split function."""

    def test_basic_split(self):
        """TC-COV-ML-047: Basic stratified split."""
        X = np.random.randn(100, 5)
        y = np.array([0] * 50 + [1] * 50)
        X_train, X_val, X_test, y_train, y_val, y_test = stratified_split(X, y)
        assert len(X_train) > 0
        assert len(X_val) > 0
        assert len(X_test) > 0
        assert len(X_train) + len(X_val) + len(X_test) == 100

    def test_ratio_validation(self):
        """TC-COV-ML-048: Invalid ratios raise error."""
        X = np.random.randn(100, 5)
        y = np.array([0] * 50 + [1] * 50)
        with pytest.raises(ValueError, match="Ratios must sum to 1.0"):
            stratified_split(X, y, train_ratio=0.5, val_ratio=0.5, test_ratio=0.5)

    def test_class_distribution(self):
        """TC-COV-ML-049: Class distribution maintained."""
        X = np.random.randn(100, 5)
        y = np.array([0] * 80 + [1] * 20)
        X_train, X_val, X_test, y_train, y_val, y_test = stratified_split(X, y)
        # Check that both classes are present in all splits
        assert len(np.unique(y_train)) == 2
        assert len(np.unique(y_val)) == 2
        assert len(np.unique(y_test)) == 2

    def test_reproducibility(self):
        """TC-COV-ML-050: Same random_state gives same split."""
        X = np.random.randn(100, 5)
        y = np.array([0] * 50 + [1] * 50)
        result1 = stratified_split(X, y, random_state=42)
        result2 = stratified_split(X, y, random_state=42)
        np.testing.assert_array_equal(result1[0], result2[0])  # X_train
        np.testing.assert_array_equal(result1[3], result2[3])  # y_train

    def test_custom_ratios(self):
        """TC-COV-ML-051: Custom split ratios."""
        X = np.random.randn(100, 5)
        y = np.array([0] * 50 + [1] * 50)
        X_train, X_val, X_test, y_train, y_val, y_test = stratified_split(
            X, y, train_ratio=0.8, val_ratio=0.1, test_ratio=0.1
        )
        assert len(X_train) == 80
        assert len(X_val) == 10
        assert len(X_test) == 10


class TestVerifySplitIntegrity:
    """Test verify_split_integrity function."""

    def test_valid_split(self):
        """TC-COV-ML-052: Valid split passes verification."""
        X = np.random.randn(100, 5)
        y = np.array([0] * 50 + [1] * 50)
        splits = stratified_split(X, y)
        result = verify_split_integrity(X, y, *splits)
        assert result is True

    def test_invalid_total(self):
        """TC-COV-ML-053: Invalid total samples fails."""
        X = np.random.randn(100, 5)
        y = np.array([0] * 50 + [1] * 50)
        with pytest.raises(AssertionError):
            verify_split_integrity(
                X, y,
                X[:30], X[:30], X[:30],
                y[:30], y[:30], y[:30],
            )
