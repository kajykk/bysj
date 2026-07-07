from __future__ import annotations

import copy
import logging
from typing import Callable

import numpy as np

from app.ml.loss import binary_cross_entropy_loss
from app.ml.model import PhysiologicalMLP

logger = logging.getLogger(__name__)


def sgd_optimizer(
    model: PhysiologicalMLP,
    caches: list[dict],
    grad_output: np.ndarray,
    learning_rate: float,
    weight_decay: float,
) -> None:
    """SGD optimizer with weight decay (L2 regularization).

    Args:
        model: MLP model.
        caches: Forward pass caches.
        grad_output: Gradient from loss function.
        learning_rate: Learning rate.
        weight_decay: L2 regularization strength.
    """
    # Backward pass
    grad = grad_output

    for i in range(len(model.layers) - 1, -1, -1):
        layer = model.layers[i]
        cache = caches[i]

        if i == len(model.layers) - 1:
            # Output layer
            grad_z = grad * cache["a"] * (1 - cache["a"])  # sigmoid derivative
        else:
            # Hidden layer
            grad_a = grad
            if "dropout_mask" in cache:
                mask = cache["dropout_mask"]
                if grad_a.shape == mask.shape:
                    grad_a = grad_a * mask / (1 - cache.get("dropout_rate", 0.1))
                else:
                    grad_a = (
                        grad_a
                        * mask[: grad_a.shape[0], : grad_a.shape[1]]
                        / (1 - cache.get("dropout_rate", 0.1))
                    )
            grad_z = grad_a * (cache["z"] > 0).astype(np.float32)  # ReLU derivative

        # BatchNorm backward
        if "bn" in cache:
            bn_cache = cache["bn"]
            x_norm = bn_cache["x_norm"]
            var = bn_cache["var"]
            eps = 1e-5
            std = np.sqrt(var + eps)
            N = grad_z.shape[0]

            grad_gamma = np.sum(grad_z * x_norm, axis=0)
            grad_beta = np.sum(grad_z, axis=0)
            grad_x_norm = grad_z * layer["bn_gamma"]

            # Compute gradient w.r.t. BatchNorm input via chain rule
            grad_x = (
                (1.0 / N)
                * (1.0 / std)
                * (
                    N * grad_x_norm
                    - np.sum(grad_x_norm, axis=0)
                    - x_norm * np.sum(grad_x_norm * x_norm, axis=0)
                )
            )
            grad_z = grad_x

            # Update BN params
            layer["bn_gamma"] -= learning_rate * grad_gamma
            layer["bn_beta"] -= learning_rate * grad_beta

        # Compute gradients
        grad_W = cache["x"].T @ grad_z
        grad_b = np.sum(grad_z, axis=0)

        # Weight decay
        grad_W += weight_decay * layer["W"]

        # Update parameters
        layer["W"] -= learning_rate * grad_W
        layer["b"] -= learning_rate * grad_b

        # Propagate gradient to previous layer
        if i > 0:
            grad = grad_z @ layer["W"].T


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Compute classification metrics.

    Args:
        y_true: True labels.
        y_pred: Predicted probabilities.

    Returns:
        Dictionary with metrics.
    """
    y_pred_binary = (y_pred >= 0.5).astype(int)
    y_true_flat = y_true.flatten().astype(int)
    y_pred_flat = y_pred_binary.flatten()

    # Accuracy
    accuracy = np.mean(y_true_flat == y_pred_flat)

    # Precision, Recall, F1
    tp = np.sum((y_true_flat == 1) & (y_pred_flat == 1))
    fp = np.sum((y_true_flat == 0) & (y_pred_flat == 1))
    fn = np.sum((y_true_flat == 1) & (y_pred_flat == 0))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    # ROC-AUC
    roc_auc = compute_roc_auc(y_true_flat, y_pred.flatten())

    # AUPRC
    auprc = compute_auprc(y_true_flat, y_pred.flatten())

    return {
        "accuracy": float(accuracy),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "roc_auc": float(roc_auc),
        "auprc": float(auprc),
    }


def compute_roc_auc(y_true: np.ndarray, y_scores: np.ndarray) -> float:
    """Compute ROC-AUC using the trapezoidal rule.

    Args:
        y_true: True binary labels.
        y_scores: Predicted scores/probabilities.

    Returns:
        ROC-AUC score.
    """
    # Flatten inputs
    y_true = np.asarray(y_true).flatten()
    y_scores = np.asarray(y_scores).flatten()

    n_pos = np.sum(y_true)
    n_neg = len(y_true) - n_pos

    if n_pos == 0 or n_neg == 0:
        return 0.5

    # Sort by scores descending
    desc_order = np.argsort(y_scores)[::-1]
    y_true_sorted = y_true[desc_order]

    # Calculate TPR and FPR at each threshold
    tps = np.cumsum(y_true_sorted)
    fps = np.cumsum(1 - y_true_sorted)

    tprs = tps / n_pos
    fprs = fps / n_neg

    # Add (0, 0) point
    tprs = np.concatenate([[0], tprs])
    fprs = np.concatenate([[0], fprs])

    # Compute AUC using trapezoidal rule (np.trapz removed in NumPy 2.0)
    try:
        auc = np.trapezoid(tprs, fprs)
    except AttributeError:
        auc = np.trapz(tprs, fprs)
    return auc


def compute_auprc(y_true: np.ndarray, y_scores: np.ndarray) -> float:
    """Compute Area Under Precision-Recall Curve.

    Args:
        y_true: True binary labels.
        y_scores: Predicted scores/probabilities.

    Returns:
        AUPRC score.
    """
    # Sort by scores descending
    desc_order = np.argsort(y_scores)[::-1]
    y_true_sorted = y_true[desc_order]

    n_pos = np.sum(y_true)
    if n_pos == 0:
        return 0.0

    precisions = []
    recalls = []

    tp = 0
    fp = 0

    for i in range(len(y_true_sorted)):
        if y_true_sorted[i] == 1:
            tp += 1
        else:
            fp += 1

        precision = tp / (tp + fp)
        recall = tp / n_pos

        precisions.append(precision)
        recalls.append(recall)

    # Compute AUPRC using trapezoidal rule (np.trapz removed in NumPy 2.0)
    precisions = np.array(precisions)
    recalls = np.array(recalls)

    try:
        auprc = np.trapezoid(precisions, recalls)
    except AttributeError:
        auprc = np.trapz(precisions, recalls)
    return auprc


class EarlyStopping:
    """Early stopping to prevent overfitting."""

    def __init__(self, patience: int = 10, min_delta: float = 0.001):
        """Initialize early stopping.

        Args:
            patience: Number of epochs to wait before stopping.
            min_delta: Minimum change to qualify as improvement.
        """
        self.patience = patience
        self.min_delta = min_delta
        self.counter = 0
        self.best_score = None
        self.best_epoch = -1  # P1-ML-026 修复：跟踪最佳 epoch，与 best_weights 保持一致
        self.early_stop = False
        self.best_weights = None

    def __call__(self, score: float, model: PhysiologicalMLP, epoch: int = -1) -> bool:
        """Check if training should stop.

        Args:
            score: Current validation score (higher is better).
            model: Current model.
            epoch: Current epoch number (for best_epoch tracking).

        Returns:
            True if training should stop.
        """
        if self.best_score is None:
            self.best_score = score
            self.best_epoch = epoch
            self.best_weights = copy.deepcopy(model.layers)
            return False

        if score > self.best_score + self.min_delta:
            self.best_score = score
            self.best_epoch = epoch
            self.best_weights = copy.deepcopy(model.layers)
            self.counter = 0
            return False
        else:
            self.counter += 1
            if self.counter >= self.patience:
                self.early_stop = True
                return True
            return False

    def restore_best_weights(self, model: PhysiologicalMLP) -> None:
        """Restore best model weights."""
        if self.best_weights is not None:
            model.layers = self.best_weights
            logger.info("Restored best model weights (score=%.4f)", self.best_score)


def train_epoch(
    model: PhysiologicalMLP,
    X_train: np.ndarray,
    y_train: np.ndarray,
    batch_size: int,
    learning_rate: float,
    weight_decay: float,
    loss_fn: Callable,
    rng: np.random.RandomState | None = None,
) -> tuple[float, dict]:
    """Train for one epoch.

    Args:
        model: MLP model.
        X_train: Training features.
        y_train: Training labels.
        batch_size: Batch size.
        learning_rate: Learning rate.
        weight_decay: L2 regularization.
        loss_fn: Loss function.
        rng: Optional NumPy RandomState for reproducible shuffling. If None,
            falls back to the global np.random (not reproducible).

    Returns:
        Tuple of (avg_loss, metrics).
    """
    # C-ML-1 修复：删除 model.training = True 实例状态修改。
    # 原实现直接修改 model.training，多线程下 evaluate() 设置 model.training = False
    # 会影响 train_epoch 中的 Dropout 行为。改为通过 forward(training=True) 参数传入。
    n_samples = len(X_train)
    sampler = rng if rng is not None else np.random
    indices = sampler.permutation(n_samples)
    total_loss = 0.0
    all_preds = []
    all_true = []

    for i in range(0, n_samples, batch_size):
        batch_idx = indices[i : i + batch_size]
        X_batch = X_train[batch_idx]
        y_batch = y_train[batch_idx]

        # Forward
        # C-ML-1 修复：显式传入 training=True，不依赖实例状态
        output, caches = model.forward(X_batch, training=True)

        # Loss
        loss, grad = loss_fn(output, y_batch)
        total_loss += loss * len(batch_idx)

        # Backward
        sgd_optimizer(model, caches, grad, learning_rate, weight_decay)

        all_preds.append(output)
        all_true.append(y_batch)

    avg_loss = total_loss / n_samples
    all_preds = np.vstack(all_preds)
    all_true = np.vstack(all_true)
    metrics = compute_metrics(all_true, all_preds)

    return avg_loss, metrics


def evaluate(
    model: PhysiologicalMLP,
    X: np.ndarray,
    y: np.ndarray,
    loss_fn: Callable,
) -> tuple[float, dict]:
    """Evaluate model on validation/test set.

    Args:
        model: MLP model.
        X: Features.
        y: Labels.
        loss_fn: Loss function.

    Returns:
        Tuple of (loss, metrics).
    """
    # C-ML-1 修复：删除 model.training = False 实例状态修改。
    # 通过 forward(training=False) 参数传入，避免多线程下与 train_epoch 竞态。
    output, _ = model.forward(X, training=False)
    loss, _ = loss_fn(output, y)
    metrics = compute_metrics(y, output)
    return loss, metrics


def train_model(
    model: PhysiologicalMLP,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    epochs: int = 100,
    batch_size: int = 32,
    learning_rate: float = 0.001,
    weight_decay: float = 0.01,
    patience: int = 10,
    loss_fn: Callable | None = None,
    random_state: int | None = 42,
) -> dict:
    """Train model with early stopping.

    Args:
        model: MLP model.
        X_train: Training features.
        y_train: Training labels.
        X_val: Validation features.
        y_val: Validation labels.
        epochs: Maximum number of epochs.
        batch_size: Batch size.
        learning_rate: Learning rate.
        weight_decay: L2 regularization.
        patience: Early stopping patience.
        loss_fn: Loss function. Defaults to BCE.
        random_state: Random seed for reproducible batch shuffling.

    Returns:
        Training history dictionary.
    """
    if loss_fn is None:
        loss_fn = binary_cross_entropy_loss

    # Reproducible RNG for batch shuffling (M25)
    rng = np.random.RandomState(random_state)

    early_stopping = EarlyStopping(patience=patience)
    history = {
        "train_loss": [],
        "val_loss": [],
        "train_f1": [],
        "val_f1": [],
        "best_epoch": 0,
        "best_val_f1": 0.0,
    }

    logger.info(
        "Starting training: epochs=%d, lr=%.4f, wd=%.4f",
        epochs,
        learning_rate,
        weight_decay,
    )

    # Training gap monitoring
    gap_threshold = 0.15
    overfitting_detected = False
    overfitting_epoch = None

    for epoch in range(epochs):
        # Train
        train_loss, train_metrics = train_epoch(
            model,
            X_train,
            y_train,
            batch_size,
            learning_rate,
            weight_decay,
            loss_fn,
            rng=rng,
        )

        # Validate
        val_loss, val_metrics = evaluate(model, X_val, y_val, loss_fn)

        # Record history
        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["train_f1"].append(train_metrics["f1"])
        history["val_f1"].append(val_metrics["f1"])

        # Monitor train/val gap for overfitting
        f1_gap = train_metrics["f1"] - val_metrics["f1"]
        if f1_gap > gap_threshold and not overfitting_detected:
            overfitting_detected = True
            overfitting_epoch = epoch
            logger.warning(
                "OVERFITTING ALERT at epoch %d: train_f1=%.4f, val_f1=%.4f, gap=%.4f (threshold=%.4f)",
                epoch,
                train_metrics["f1"],
                val_metrics["f1"],
                f1_gap,
                gap_threshold,
            )

        # Log progress
        if epoch % 10 == 0 or epoch < 5:
            logger.info(
                "Epoch %d: train_loss=%.4f, val_loss=%.4f, train_f1=%.4f, val_f1=%.4f, gap=%.4f",
                epoch,
                train_loss,
                val_loss,
                train_metrics["f1"],
                val_metrics["f1"],
                f1_gap,
            )

        # Early stopping
        if early_stopping(val_metrics["f1"], model, epoch=epoch):
            logger.info("Early stopping triggered at epoch %d", epoch)
            break

        # P1-ML-026 修复：移除冗余的 best_val_f1/best_epoch 跟踪
        # best_val_f1 和 best_epoch 现在由 EarlyStopping 统一管理，
        # 确保 history["best_val_f1"] 与 best_weights 对应的 epoch 严格一致。

    # Restore best weights
    early_stopping.restore_best_weights(model)

    # P1-ML-026 修复：从 EarlyStopping 同步 best_val_f1 和 best_epoch，确保一致性
    if early_stopping.best_score is not None:
        history["best_val_f1"] = float(early_stopping.best_score)
        history["best_epoch"] = early_stopping.best_epoch

    # Record overfitting info in history
    history["overfitting_detected"] = overfitting_detected
    history["overfitting_epoch"] = overfitting_epoch
    if overfitting_detected:
        history["final_gap"] = history["train_f1"][-1] - history["val_f1"][-1]
        logger.warning(
            "Training completed with overfitting detected at epoch %d (final gap=%.4f)",
            overfitting_epoch,
            history["final_gap"],
        )

    logger.info(
        "Training complete: best_epoch=%d, best_val_f1=%.4f",
        history["best_epoch"],
        history["best_val_f1"],
    )

    return history
