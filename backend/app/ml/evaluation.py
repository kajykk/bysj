"""Advanced evaluation utilities for model assessment."""

from __future__ import annotations

import logging
from typing import Callable

import numpy as np

logger = logging.getLogger(__name__)


def compute_confusion_matrix(
    y_true: np.ndarray, y_pred: np.ndarray, threshold: float = 0.5
) -> dict:
    """Compute confusion matrix elements.

    Args:
        y_true: True labels.
        y_pred: Predicted probabilities.
        threshold: Classification threshold.

    Returns:
        Dictionary with TP, FP, TN, FN counts and rates.
    """
    y_pred_binary = (y_pred >= threshold).astype(int)
    y_true_flat = y_true.flatten().astype(int)
    y_pred_flat = y_pred_binary.flatten()

    tp = int(np.sum((y_true_flat == 1) & (y_pred_flat == 1)))
    fp = int(np.sum((y_true_flat == 0) & (y_pred_flat == 1)))
    tn = int(np.sum((y_true_flat == 0) & (y_pred_flat == 0)))
    fn = int(np.sum((y_true_flat == 1) & (y_pred_flat == 0)))

    total = tp + fp + tn + fn

    result = {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "total": total,
        "tp_rate": tp / total if total > 0 else 0.0,
        "fp_rate": fp / total if total > 0 else 0.0,
        "tn_rate": tn / total if total > 0 else 0.0,
        "fn_rate": fn / total if total > 0 else 0.0,
        "sensitivity": tp / (tp + fn) if (tp + fn) > 0 else 0.0,
        "specificity": tn / (tn + fp) if (tn + fp) > 0 else 0.0,
    }

    logger.info(
        "Confusion Matrix: TP=%d, FP=%d, TN=%d, FN=%d",
        tp,
        fp,
        tn,
        fn,
    )

    return result


def compute_roc_curve(
    y_true: np.ndarray, y_scores: np.ndarray, n_thresholds: int = 100
) -> dict:
    """Compute ROC curve points.

    Args:
        y_true: True binary labels.
        y_scores: Predicted scores/probabilities.
        n_thresholds: Number of threshold points.

    Returns:
        Dictionary with FPR, TPR arrays and AUC.
    """
    n_pos = np.sum(y_true)
    n_neg = len(y_true) - n_pos

    if n_pos == 0 or n_neg == 0:
        return {
            "fpr": [0.0, 1.0],
            "tpr": [0.0, 1.0],
            "thresholds": [0.0, 1.0],
            "auc": 0.5,
        }

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

    # Compute AUC using trapezoidal rule
    try:
        auc = np.trapezoid(tprs, fprs)
    except AttributeError:
        auc = np.trapz(tprs, fprs)

    return {
        "fpr": fprs.tolist(),
        "tpr": tprs.tolist(),
        "thresholds": y_scores[desc_order].tolist(),
        "auc": float(auc),
    }


def compute_calibration_curve(
    y_true: np.ndarray,
    y_scores: np.ndarray,
    n_bins: int = 10,
) -> dict:
    """Compute calibration curve (reliability diagram).

    Args:
        y_true: True binary labels.
        y_scores: Predicted probabilities.
        n_bins: Number of bins for calibration.

    Returns:
        Dictionary with mean predicted values and fraction of positives.
    """
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    bin_lowers = bin_boundaries[:-1]
    bin_uppers = bin_boundaries[1:]

    bin_centers = []
    bin_accuracies = []
    bin_counts = []

    for lower, upper in zip(bin_lowers, bin_uppers):
        in_bin = (y_scores >= lower) & (y_scores <= upper)
        prop_in_bin = np.mean(in_bin)

        if prop_in_bin > 0:
            accuracy_in_bin = np.mean(y_true[in_bin])
            avg_confidence_in_bin = np.mean(y_scores[in_bin])
            bin_centers.append(avg_confidence_in_bin)
            bin_accuracies.append(accuracy_in_bin)
            bin_counts.append(int(np.sum(in_bin)))
        else:
            bin_centers.append((lower + upper) / 2)
            bin_accuracies.append(0.0)
            bin_counts.append(0)

    # Expected calibration error
    ece = 0.0
    total_samples = len(y_true)
    for i in range(n_bins):
        # L-ML-1 修复：与上方 bin 划分保持一致，使用 >= 下界
        in_bin = (y_scores >= bin_lowers[i]) & (y_scores <= bin_uppers[i])
        bin_weight = np.sum(in_bin) / total_samples
        if bin_weight > 0:
            ece += bin_weight * abs(bin_accuracies[i] - bin_centers[i])

    return {
        "bin_centers": bin_centers,
        "bin_accuracies": bin_accuracies,
        "bin_counts": bin_counts,
        "expected_calibration_error": float(ece),
    }


def compute_shap_values_approximation(
    X: np.ndarray,
    feature_names: list[str],
    model_predict_fn: callable,
    n_samples: int = 100,
    random_state: int = 42,
) -> dict:
    """Compute approximate SHAP values using permutation importance.

    This is a simplified version for numpy-based models.
    For production, consider using the shap library.

    Args:
        X: Feature matrix.
        feature_names: List of feature names.
        model_predict_fn: Function that takes X and returns predictions.
        n_samples: Number of background samples.
        random_state: Random seed for reproducible permutation.

    Returns:
        Dictionary with feature importances.
    """
    rng = np.random.RandomState(random_state)
    n_features = X.shape[1]
    baseline_pred = np.mean(model_predict_fn(X))

    importances = []

    for i in range(n_features):
        # Permute feature i
        X_permuted = X.copy()
        rng.shuffle(X_permuted[:, i])

        # Compute prediction difference
        permuted_pred = np.mean(model_predict_fn(X_permuted))
        importance = abs(baseline_pred - permuted_pred)

        importances.append(importance)

    # Normalize
    total_importance = sum(importances)
    if total_importance > 0:
        importances = [imp / total_importance for imp in importances]

    # Sort by importance
    sorted_indices = np.argsort(importances)[::-1]

    result = {
        "feature_importances": {
            feature_names[i]: float(importances[i]) for i in range(n_features)
        },
        "sorted_features": [feature_names[i] for i in sorted_indices],
        "sorted_importances": [float(importances[i]) for i in sorted_indices],
    }

    logger.info("SHAP approximation complete")
    for i in range(min(5, n_features)):
        idx = sorted_indices[i]
        logger.info(
            "  %s: %.4f",
            feature_names[idx],
            importances[idx],
        )

    return result


def generate_evaluation_report(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    feature_names: list[str] | None = None,
    model_predict_fn: Callable | None = None,
    X: np.ndarray | None = None,
    random_state: int = 42,
) -> dict:
    """Generate comprehensive evaluation report.

    Args:
        y_true: True labels.
        y_pred: Predicted probabilities.
        feature_names: List of feature names.
        model_predict_fn: Function for SHAP computation.
        X: Feature matrix for SHAP computation. Required for SHAP values.
        random_state: Random seed for SHAP permutation.

    Returns:
        Dictionary with all evaluation metrics.
    """
    report = {}

    # Confusion matrix
    report["confusion_matrix"] = compute_confusion_matrix(y_true, y_pred)

    # ROC curve
    report["roc_curve"] = compute_roc_curve(y_true, y_pred.flatten())

    # Calibration curve
    report["calibration_curve"] = compute_calibration_curve(y_true, y_pred.flatten())

    # SHAP values (if model function and feature matrix provided)
    if model_predict_fn is not None and feature_names is not None and X is not None:
        report["shap_values"] = compute_shap_values_approximation(
            X,
            feature_names,
            model_predict_fn,
            random_state=random_state,
        )

    logger.info("Evaluation report generated")

    return report
