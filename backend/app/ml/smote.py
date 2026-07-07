from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def simple_smote(
    X: np.ndarray,
    y: np.ndarray,
    sampling_strategy: float = 0.5,
    k_neighbors: int = 5,
    random_state: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Simple SMOTE implementation using numpy only.

    Generates synthetic samples for the minority class by interpolating
    between existing minority class samples and their k-nearest neighbors.

    Args:
        X: Feature matrix (n_samples, n_features).
        y: Target vector (n_samples,).
        sampling_strategy: Ratio of minority to majority class after resampling.
            0.5 means minority:majority = 1:2.
        k_neighbors: Number of nearest neighbors to use.
        random_state: Random seed for reproducibility.

    Returns:
        Tuple of (X_resampled, y_resampled).
    """
    rng = np.random.RandomState(random_state)

    # Identify minority and majority classes
    classes, counts = np.unique(y, return_counts=True)
    minority_class = classes[np.argmin(counts)]
    majority_class = classes[np.argmax(counts)]

    n_minority = np.sum(y == minority_class)
    n_majority = np.sum(y == majority_class)

    logger.info(
        "Before SMOTE: minority=%d, majority=%d, ratio=%.3f",
        n_minority,
        n_majority,
        n_minority / n_majority,
    )

    # M-ML-2 修复：少数类样本数 < 2 时无法计算最近邻（至少需要 2 个样本），
    # 显式告警并返回原数据，避免静默失败
    if n_minority < 2:
        logger.warning("SMOTE skipped: minority class has only %d samples", n_minority)
        return X.copy(), y.copy()

    # H-09 修复：少数类样本数不足时自动调整 k_neighbors，防止越界
    if n_minority <= k_neighbors:
        k_neighbors = max(1, n_minority - 1)
        logger.warning(
            "minority samples (%d) <= k_neighbors, adjusted k_neighbors to %d",
            n_minority,
            k_neighbors,
        )

    # Calculate target number of minority samples
    target_minority = int(n_majority * sampling_strategy)
    n_synthetic = target_minority - n_minority

    if n_synthetic <= 0:
        logger.info("No SMOTE needed: minority class already at target ratio")
        return X.copy(), y.copy()

    # Extract minority samples
    minority_indices = np.where(y == minority_class)[0]
    X_minority = X[minority_indices]

    # Generate synthetic samples
    X_synthetic = []
    for _ in range(n_synthetic):
        # Random minority sample
        idx = rng.randint(0, len(X_minority))
        sample = X_minority[idx]

        # Find k nearest neighbors (using Euclidean distance)
        distances = np.linalg.norm(X_minority - sample, axis=1)
        # Exclude self (distance = 0)
        neighbor_indices = np.argsort(distances)[1 : k_neighbors + 1]

        if len(neighbor_indices) == 0:
            continue

        # Random neighbor
        neighbor_idx = rng.choice(neighbor_indices)
        neighbor = X_minority[neighbor_idx]

        # Interpolate
        alpha = rng.uniform(0, 1)
        synthetic = sample + alpha * (neighbor - sample)
        X_synthetic.append(synthetic)

    if len(X_synthetic) == 0:
        logger.warning("No synthetic samples generated")
        return X.copy(), y.copy()

    X_synthetic = np.array(X_synthetic)
    y_synthetic = np.full(len(X_synthetic), minority_class)

    # Combine original and synthetic
    X_resampled = np.vstack([X, X_synthetic])
    y_resampled = np.hstack([y, y_synthetic])

    logger.info(
        "After SMOTE: minority=%d, majority=%d, ratio=%.3f",
        np.sum(y_resampled == minority_class),
        np.sum(y_resampled == majority_class),
        np.sum(y_resampled == minority_class) / np.sum(y_resampled == majority_class),
    )

    return X_resampled, y_resampled


def apply_smote_if_needed(
    X_train: np.ndarray,
    y_train: np.ndarray,
    sampling_strategy: float = 0.5,
    min_imbalance_ratio: float = 0.8,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply SMOTE only if dataset is imbalanced.

    Args:
        X_train: Training features.
        y_train: Training labels.
        sampling_strategy: Target minority/majority ratio.
        min_imbalance_ratio: Minimum ratio to trigger SMOTE.

    Returns:
        Tuple of (X_train, y_train), possibly with synthetic samples.
    """
    classes, counts = np.unique(y_train, return_counts=True)
    if len(classes) < 2:
        logger.warning("Only one class found, skipping SMOTE")
        return X_train.copy(), y_train.copy()

    ratio = min(counts) / max(counts)

    if ratio >= min_imbalance_ratio:
        logger.info(
            "Dataset is balanced (ratio=%.3f >= %.3f), skipping SMOTE",
            ratio,
            min_imbalance_ratio,
        )
        return X_train.copy(), y_train.copy()

    logger.info(
        "Dataset is imbalanced (ratio=%.3f < %.3f), applying SMOTE",
        ratio,
        min_imbalance_ratio,
    )
    return simple_smote(X_train, y_train, sampling_strategy=sampling_strategy)
