"""
Test suite for data splitting functionality.

Tests:
- TC-DATA-026: 验证分层划分比例
- TC-DATA-027: 验证划分无重叠
- TC-DATA-028: 验证类别分布保持
- TC-DATA-029: 验证划分完整性
- TC-DATA-030: 验证随机种子可复现性
- TC-DATA-031: 验证划分比例验证
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# Add backend to path
backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.ml.data_split import (
    stratified_split,
    verify_split_integrity,
)


class TestDataSplit:
    """Test suite for data splitting functionality."""

    @pytest.fixture
    def sample_data(self) -> tuple[np.ndarray, np.ndarray]:
        """Create sample feature matrix and target vector."""
        rng = np.random.RandomState(42)
        X = rng.randn(100, 5)
        # Create imbalanced binary target (30% positive)
        y = np.array([1] * 30 + [0] * 70)
        rng.shuffle(y)
        return X, y

    def test_split_ratios(self, sample_data: tuple[np.ndarray, np.ndarray]) -> None:
        """TC-DATA-026: 验证分层划分比例."""
        X, y = sample_data
        X_train, X_val, X_test, y_train, y_val, y_test = stratified_split(
            X, y, train_ratio=0.7, val_ratio=0.15, test_ratio=0.15
        )

        total = len(y)
        # Allow ±1 for rounding in stratified split
        assert abs(len(y_train) - int(total * 0.7)) <= 1
        assert abs(len(y_val) - int(total * 0.15)) <= 1
        # Remaining goes to test
        assert len(y_test) == total - len(y_train) - len(y_val)

    def test_no_overlap(self, sample_data: tuple[np.ndarray, np.ndarray]) -> None:
        """TC-DATA-027: 验证划分无重叠."""
        X, y = sample_data
        X_train, X_val, X_test, y_train, y_val, y_test = stratified_split(X, y)

        # Verify no overlaps using sets
        train_set = set(map(tuple, X_train))
        val_set = set(map(tuple, X_val))
        test_set = set(map(tuple, X_test))

        assert len(train_set & val_set) == 0, "Train and val overlap"
        assert len(train_set & test_set) == 0, "Train and test overlap"
        assert len(val_set & test_set) == 0, "Val and test overlap"

    def test_class_distribution(
        self, sample_data: tuple[np.ndarray, np.ndarray]
    ) -> None:
        """TC-DATA-028: 验证类别分布保持."""
        X, y = sample_data
        X_train, X_val, X_test, y_train, y_val, y_test = stratified_split(X, y)

        # Calculate original class distribution
        original_ratio = np.sum(y) / len(y)

        # Verify each split maintains similar distribution
        train_ratio = np.sum(y_train) / len(y_train)
        val_ratio = np.sum(y_val) / len(y_val)
        test_ratio = np.sum(y_test) / len(y_test)

        # Allow 10% tolerance for small datasets
        assert abs(train_ratio - original_ratio) < 0.1
        assert abs(val_ratio - original_ratio) < 0.1
        assert abs(test_ratio - original_ratio) < 0.1

    def test_split_integrity(self, sample_data: tuple[np.ndarray, np.ndarray]) -> None:
        """TC-DATA-029: 验证划分完整性."""
        X, y = sample_data
        splits = stratified_split(X, y)
        X_train, X_val, X_test, y_train, y_val, y_test = splits

        # Verify total samples match
        total = len(y_train) + len(y_val) + len(y_test)
        assert total == len(y), f"Total samples mismatch: {total} != {len(y)}"

        # Verify using integrity function
        assert verify_split_integrity(X, y, *splits)

    def test_reproducibility(self, sample_data: tuple[np.ndarray, np.ndarray]) -> None:
        """TC-DATA-030: 验证随机种子可复现性."""
        X, y = sample_data

        split1 = stratified_split(X, y, random_state=42)
        split2 = stratified_split(X, y, random_state=42)

        X_train1, X_val1, X_test1, y_train1, y_val1, y_test1 = split1
        X_train2, X_val2, X_test2, y_train2, y_val2, y_test2 = split2

        # Verify identical splits
        np.testing.assert_array_equal(X_train1, X_train2)
        np.testing.assert_array_equal(X_val1, X_val2)
        np.testing.assert_array_equal(X_test1, X_test2)
        np.testing.assert_array_equal(y_train1, y_train2)
        np.testing.assert_array_equal(y_val1, y_val2)
        np.testing.assert_array_equal(y_test1, y_test2)

    def test_invalid_ratios(self, sample_data: tuple[np.ndarray, np.ndarray]) -> None:
        """TC-DATA-031: 验证划分比例验证."""
        X, y = sample_data

        with pytest.raises(ValueError, match="Ratios must sum to 1.0"):
            stratified_split(X, y, train_ratio=0.5, val_ratio=0.3, test_ratio=0.3)

    def test_different_random_states(
        self, sample_data: tuple[np.ndarray, np.ndarray]
    ) -> None:
        """TC-DATA-032: 验证不同随机种子产生不同划分."""
        X, y = sample_data

        split1 = stratified_split(X, y, random_state=42)
        split2 = stratified_split(X, y, random_state=123)

        X_train1, _, _, _, _, _ = split1
        X_train2, _, _, _, _, _ = split2

        # Verify different splits
        assert not np.array_equal(X_train1, X_train2)
