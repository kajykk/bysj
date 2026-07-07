from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)


def binary_cross_entropy_loss(
    y_pred: np.ndarray,
    y_true: np.ndarray,
    epsilon: float = 1e-7,
) -> tuple[float, np.ndarray]:
    """Binary cross-entropy loss.

    Args:
        y_pred: Predicted probabilities (batch_size, 1).
        y_true: True labels (batch_size, 1).
        epsilon: Small value to avoid log(0).

    Returns:
        Tuple of (loss, gradient).
    """
    # Clip predictions to avoid log(0)
    y_pred_clipped = np.clip(y_pred, epsilon, 1 - epsilon)

    # BUG-003 修复：规范化 y_true 形状为 (batch_size, 1)，避免 1D (batch_size,)
    # 与 2D (batch_size, 1) 的 y_pred 广播导致 (batch_size, batch_size) 错误梯度。
    # 原实现假设调用方传入 2D y_true，但 train_epoch 中 y_batch 可能是 1D 切片。
    y_true = np.asarray(y_true).reshape(-1, 1)

    # Compute loss
    loss = -np.mean(
        y_true * np.log(y_pred_clipped) + (1 - y_true) * np.log(1 - y_pred_clipped)
    )

    # Compute gradient
    # L-ML-5 修复：移除分母的额外 epsilon，y_pred 已 clip 到 [epsilon, 1-epsilon]，
    # y_pred * (1 - y_pred) 已被下界为 epsilon * (1 - epsilon)，无需再加 epsilon
    grad = (y_pred_clipped - y_true) / (y_pred_clipped * (1 - y_pred_clipped))
    grad = grad / len(y_true)

    return float(loss), grad


def focal_loss(
    y_pred: np.ndarray,
    y_true: np.ndarray,
    alpha: float = 0.75,
    gamma: float = 2.0,
    epsilon: float = 1e-7,
) -> tuple[float, np.ndarray]:
    """Focal Loss for handling class imbalance.

    Focal Loss down-weights easy examples and focuses on hard examples.
    alpha=0.75 increases weight for positive (depression) class.

    Args:
        y_pred: Predicted probabilities (batch_size, 1).
        y_true: True labels (batch_size, 1).
        alpha: Weighting factor for positive class (default 0.75).
        gamma: Focusing parameter (default 2.0).
        epsilon: Small value to avoid log(0).

    Returns:
        Tuple of (loss, gradient).
    """
    # Clip predictions
    y_pred_clipped = np.clip(y_pred, epsilon, 1 - epsilon)

    # BUG-003 横向排查：focal_loss 与 binary_cross_entropy_loss 同类问题
    # 规范化 y_true 形状为 (batch_size, 1)，避免 1D 广播错误
    y_true = np.asarray(y_true).reshape(-1, 1)

    # Compute focal weight
    p_t = y_pred_clipped * y_true + (1 - y_pred_clipped) * (1 - y_true)
    focal_weight = np.power(1 - p_t, gamma)

    # Compute alpha weight
    alpha_t = alpha * y_true + (1 - alpha) * (1 - y_true)

    # Compute loss
    bce = -(y_true * np.log(y_pred_clipped) + (1 - y_true) * np.log(1 - y_pred_clipped))
    loss = np.mean(alpha_t * focal_weight * bce)

    # Compute gradient
    # 完整 Focal Loss 梯度：dL/dp = alpha_t * [focal_weight * d(bce)/dp + bce * d(focal_weight)/dp]
    # d(bce)/dp = (p - y) / (p * (1-p))
    # d(focal_weight)/dp = -gamma * (1-p_t)^(gamma-1) * (2y-1)
    d_bce = (y_pred_clipped - y_true) / (
        y_pred_clipped * (1 - y_pred_clipped) + epsilon
    )
    two_y_minus_one = 2 * y_true - 1
    # 对 (1-p_t)^(gamma-1) 做数值保护，避免 0 的负幂
    one_minus_pt_safe = np.maximum(1 - p_t, epsilon)
    focal_weight_deriv = (
        -gamma * np.power(one_minus_pt_safe, gamma - 1) * two_y_minus_one
    )
    grad = alpha_t * (focal_weight * d_bce + bce * focal_weight_deriv)
    grad = grad / len(y_true)

    return float(loss), grad


def compute_class_weights(y: np.ndarray) -> dict[int, float]:
    """Compute class weights for imbalanced datasets.

    Args:
        y: Target vector.

    Returns:
        Dictionary mapping class labels to weights.
    """
    classes, counts = np.unique(y, return_counts=True)
    total = len(y)
    weights = {
        int(cls): total / (len(classes) * count) for cls, count in zip(classes, counts)
    }
    logger.info("Computed class weights: %s", weights)
    return weights
