from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from pandas import DataFrame

logger = logging.getLogger(__name__)


def stratified_split(
    X: np.ndarray,
    y: np.ndarray,
    train_ratio: float = 0.7,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    random_state: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Stratified split of data into train/val/test sets.

    Maintains class distribution across all splits.

    Args:
        X: Feature matrix (n_samples, n_features).
        y: Target vector (n_samples,).
        train_ratio: Proportion for training set.
        val_ratio: Proportion for validation set.
        test_ratio: Proportion for test set.
        random_state: Random seed for reproducibility.

    Returns:
        Tuple of (X_train, X_val, X_test, y_train, y_val, y_test).

    Raises:
        ValueError: If ratios don't sum to 1.0.
    """
    if not np.isclose(train_ratio + val_ratio + test_ratio, 1.0):
        raise ValueError(f"Ratios must sum to 1.0, got {train_ratio + val_ratio + test_ratio}")

    rng = np.random.RandomState(random_state)
    n_samples = len(y)

    # Get indices for each class
    classes = np.unique(y)
    train_indices = []
    val_indices = []
    test_indices = []

    for cls in classes:
        cls_indices = np.where(y == cls)[0]
        n_cls = len(cls_indices)
        rng.shuffle(cls_indices)

        n_train = int(n_cls * train_ratio)
        n_val = int(n_cls * val_ratio)
        # Remaining goes to test

        train_indices.extend(cls_indices[:n_train])
        val_indices.extend(cls_indices[n_train : n_train + n_val])
        test_indices.extend(cls_indices[n_train + n_val :])

    # Shuffle indices
    rng.shuffle(train_indices)
    rng.shuffle(val_indices)
    rng.shuffle(test_indices)

    # Split data
    X_train = X[train_indices]
    X_val = X[val_indices]
    X_test = X[test_indices]
    y_train = y[train_indices]
    y_val = y[val_indices]
    y_test = y[test_indices]

    # M28: guard against empty splits (would cause ZeroDivisionError in logging
    # and downstream training failures)
    for name, y_split in [("train", y_train), ("val", y_val), ("test", y_test)]:
        if len(y_split) == 0:
            raise ValueError(
                f"Stratified split produced an empty {name} set. "
                f"Insufficient samples for the requested ratios "
                f"(train={train_ratio}, val={val_ratio}, test={test_ratio}). "
                f"Total samples: {n_samples}."
            )

    logger.info(
        "Stratified split: train=%d (%.1f%%), val=%d (%.1f%%), test=%d (%.1f%%)",
        len(y_train),
        len(y_train) / n_samples * 100,
        len(y_val),
        len(y_val) / n_samples * 100,
        len(y_test),
        len(y_test) / n_samples * 100,
    )

    # Log class distribution
    for name, y_split in [("train", y_train), ("val", y_val), ("test", y_test)]:
        pos = np.sum(y_split)
        neg = len(y_split) - pos
        total = len(y_split)
        pos_pct = pos / total * 100 if total > 0 else 0.0
        neg_pct = neg / total * 100 if total > 0 else 0.0
        logger.info(
            "  %s: positive=%d (%.1f%%), negative=%d (%.1f%%)",
            name,
            pos,
            pos_pct,
            neg,
            neg_pct,
        )

    return X_train, X_val, X_test, y_train, y_val, y_test


def verify_split_integrity(
    X: np.ndarray,
    y: np.ndarray,
    X_train: np.ndarray,
    X_val: np.ndarray,
    X_test: np.ndarray,
    y_train: np.ndarray,
    y_val: np.ndarray,
    y_test: np.ndarray,
) -> bool:
    """Verify that splits are correct and non-overlapping.

    Args:
        X: Original feature matrix.
        y: Original target vector.
        X_train, X_val, X_test: Split features.
        y_train, y_val, y_test: Split targets.

    Returns:
        True if splits are valid.
    """
    total = len(y_train) + len(y_val) + len(y_test)
    assert total == len(y), f"Total samples mismatch: {total} != {len(y)}"

    # Check no overlap
    train_set = set(map(tuple, X_train))
    val_set = set(map(tuple, X_val))
    test_set = set(map(tuple, X_test))

    assert len(train_set & val_set) == 0, "Train and val overlap"
    assert len(train_set & test_set) == 0, "Train and test overlap"
    assert len(val_set & test_set) == 0, "Val and test overlap"

    logger.info("Split integrity verified: no overlaps, total samples match")
    return True
