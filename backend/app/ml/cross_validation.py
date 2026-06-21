"""Cross-validation utilities for physiological depression prediction."""

from __future__ import annotations

import logging
from typing import Callable

import numpy as np

from app.ml.model import PhysiologicalMLP
from app.ml.trainer import train_model, evaluate
from app.ml.scaler import SimpleStandardScaler
from app.ml.smote import simple_smote

logger = logging.getLogger(__name__)


def cross_validate_with_smote(
    X: np.ndarray,
    y: np.ndarray,
    n_folds: int = 5,
    model_params: dict | None = None,
    train_params: dict | None = None,
    loss_fn: Callable | None = None,
    random_state: int = 42,
    apply_smote: bool = True,
    sampling_strategy: float = 0.5,
) -> dict:
    """Perform k-fold cross-validation with SMOTE applied only to training folds.

    Each fold:
        1. Splits data into train/val
        2. Fits scaler on training data only
        3. Applies SMOTE to training data only (if enabled)
        4. Trains model
        5. Evaluates on validation fold

    Args:
        X: Feature matrix (n_samples, n_features).
        y: Target vector (n_samples,).
        n_folds: Number of cross-validation folds.
        model_params: Parameters for PhysiologicalMLP.
        train_params: Parameters for train_model.
        loss_fn: Loss function.
        random_state: Random seed.
        apply_smote: Whether to apply SMOTE to training folds.
        sampling_strategy: SMOTE sampling strategy.

    Returns:
        Dictionary with fold results and aggregated metrics.
    """
    rng = np.random.RandomState(random_state)
    n_samples = len(y)
    indices = np.arange(n_samples)
    rng.shuffle(indices)

    # Create folds
    fold_size = n_samples // n_folds
    folds = []
    for i in range(n_folds):
        start = i * fold_size
        end = start + fold_size if i < n_folds - 1 else n_samples
        folds.append(indices[start:end])

    if model_params is None:
        model_params = {
            "hidden_dims": [64, 32, 16],
            "dropout_rate": 0.3,
            "use_batch_norm": False,
        }

    if train_params is None:
        train_params = {
            "epochs": 50,
            "batch_size": 32,
            "learning_rate": 0.001,
            "weight_decay": 0.01,
            "patience": 10,
        }

    fold_results = []

    for fold_idx in range(n_folds):
        logger.info("=" * 50)
        logger.info("Fold %d/%d", fold_idx + 1, n_folds)
        logger.info("=" * 50)

        # Split into train and validation
        val_indices = folds[fold_idx]
        train_indices = np.concatenate([folds[i] for i in range(n_folds) if i != fold_idx])

        X_train_fold = X[train_indices]
        y_train_fold = y[train_indices]
        X_val_fold = X[val_indices]
        y_val_fold = y[val_indices]

        logger.info(
            "Train: %d samples, Val: %d samples",
            len(X_train_fold),
            len(X_val_fold),
        )

        # Fit scaler on training data only (prevent data leakage)
        scaler = SimpleStandardScaler()
        X_train_fold = scaler.fit_transform(X_train_fold)
        X_val_fold = scaler.transform(X_val_fold)

        # Apply SMOTE to training data only (prevent data leakage)
        # P1-ML-025 修复：每 fold 派生不同 SMOTE 种子，避免所有 fold 生成相同的合成样本
        if apply_smote:
            X_train_fold, y_train_fold = simple_smote(
                X_train_fold,
                y_train_fold,
                sampling_strategy=sampling_strategy,
                random_state=random_state + fold_idx,
            )
            logger.info("After SMOTE: %d training samples", len(X_train_fold))

        # Create and train model
        model = PhysiologicalMLP(
            input_dim=X.shape[1],
            random_state=random_state,
            **model_params,
        )

        history = train_model(
            model,
            X_train_fold,
            y_train_fold,
            X_val_fold,
            y_val_fold,
            loss_fn=loss_fn,
            random_state=random_state,
            **train_params,
        )

        # Evaluate on validation fold
        val_loss, val_metrics = evaluate(model, X_val_fold, y_val_fold, loss_fn)

        fold_result = {
            "fold": fold_idx + 1,
            "val_metrics": val_metrics,
            "best_val_f1": float(history["best_val_f1"]),
            "best_epoch": history["best_epoch"],
            "train_samples": len(X_train_fold),
            "val_samples": len(X_val_fold),
        }
        fold_results.append(fold_result)

        logger.info(
            "Fold %d results: F1=%.4f, Accuracy=%.4f, Precision=%.4f, Recall=%.4f",
            fold_idx + 1,
            val_metrics["f1"],
            val_metrics["accuracy"],
            val_metrics["precision"],
            val_metrics["recall"],
        )

    # Aggregate results
    metrics_keys = ["f1", "accuracy", "precision", "recall"]
    aggregated = {}
    for key in metrics_keys:
        values = [fold["val_metrics"][key] for fold in fold_results]
        aggregated[key] = {
            "mean": float(np.mean(values)),
            "std": float(np.std(values)),
            "min": float(np.min(values)),
            "max": float(np.max(values)),
        }

    results = {
        "n_folds": n_folds,
        "fold_results": fold_results,
        "aggregated": aggregated,
        "model_params": model_params,
        "train_params": train_params,
    }

    logger.info("=" * 50)
    logger.info("Cross-validation complete")
    logger.info("=" * 50)
    for key in metrics_keys:
        logger.info(
            "%s: %.4f +/- %.4f (range: %.4f - %.4f)",
            key.upper(),
            aggregated[key]["mean"],
            aggregated[key]["std"],
            aggregated[key]["min"],
            aggregated[key]["max"],
        )

    return results


def verify_no_data_leakage(
    X_train: np.ndarray,
    X_val: np.ndarray,
    tolerance: float = 1e-6,
) -> bool:
    """Verify that training and validation sets have no overlapping samples.

    Args:
        X_train: Training features.
        X_val: Validation features.
        tolerance: Numerical tolerance for comparison.

    Returns:
        True if no leakage detected.
    """
    # Convert to sets of tuples for comparison
    train_set = set(map(tuple, np.round(X_train, 6)))
    val_set = set(map(tuple, np.round(X_val, 6)))

    overlap = train_set & val_set

    if len(overlap) > 0:
        logger.error("DATA LEAKAGE DETECTED: %d samples overlap between train and val", len(overlap))
        return False

    logger.info("No data leakage detected between train and validation sets")
    return True
