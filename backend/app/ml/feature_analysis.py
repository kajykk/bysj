"""Feature analysis utilities for collinearity detection."""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)


def compute_correlation_matrix(X: np.ndarray, feature_names: list[str]) -> dict:
    """Compute feature correlation matrix.

    Args:
        X: Feature matrix (n_samples, n_features).
        feature_names: List of feature names.

    Returns:
        Dictionary with correlation matrix and highly correlated pairs.
    """
    n_features = X.shape[1]
    corr_matrix = np.corrcoef(X.T)

    # Find highly correlated pairs (|r| > 0.8)
    high_corr_pairs = []
    for i in range(n_features):
        for j in range(i + 1, n_features):
            corr = corr_matrix[i, j]
            if abs(corr) > 0.8:
                high_corr_pairs.append({
                    "feature1": feature_names[i],
                    "feature2": feature_names[j],
                    "correlation": float(corr),
                })

    result = {
        "correlation_matrix": corr_matrix.tolist(),
        "feature_names": feature_names,
        "high_correlation_pairs": high_corr_pairs,
        "n_high_correlation": len(high_corr_pairs),
    }

    logger.info("Correlation matrix computed: %d high correlation pairs found", len(high_corr_pairs))
    for pair in high_corr_pairs:
        logger.info(
            "  %s <-> %s: r=%.4f",
            pair["feature1"],
            pair["feature2"],
            pair["correlation"],
        )

    return result


def compute_vif(X: np.ndarray, feature_names: list[str]) -> dict:
    """Compute Variance Inflation Factor (VIF) for each feature.

    VIF = 1 / (1 - R^2) where R^2 is from regressing the feature on all others.
    VIF > 10 indicates high multicollinearity.

    Args:
        X: Feature matrix (n_samples, n_features).
        feature_names: List of feature names.

    Returns:
        Dictionary with VIF values and high VIF features.
    """
    n_features = X.shape[1]
    vif_values = []

    for i in range(n_features):
        # Regress feature i on all other features
        y = X[:, i]
        X_others = np.delete(X, i, axis=1)

        # Add constant term
        X_with_const = np.column_stack([np.ones(len(X_others)), X_others])

        # Compute R^2 using least squares
        try:
            # Normal equation: beta = (X^T X)^-1 X^T y
            # 使用 pinv 替代 inv，避免奇异矩阵抛出 LinAlgError
            XtX = X_with_const.T @ X_with_const
            XtX_inv = np.linalg.pinv(XtX)
            beta = XtX_inv @ X_with_const.T @ y

            # Predictions
            y_pred = X_with_const @ beta

            # R^2
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

            # 钳制 r_squared 到 [0, 1) 区间，避免负值导致 VIF < 1 不合理
            r_squared = max(0.0, min(0.9999, r_squared))

            # VIF
            vif = 1.0 / (1.0 - r_squared)

        except np.linalg.LinAlgError:
            vif = float("inf")

        vif_values.append(vif)

    # Identify high VIF features
    high_vif_features = []
    for i, vif in enumerate(vif_values):
        if vif > 10:
            high_vif_features.append({
                "feature": feature_names[i],
                "vif": float(vif),
            })

    result = {
        "vif_values": {feature_names[i]: float(vif_values[i]) for i in range(n_features)},
        "high_vif_features": high_vif_features,
        "n_high_vif": len(high_vif_features),
        "mean_vif": float(np.mean(vif_values)),
        "max_vif": float(np.max(vif_values)),
    }

    logger.info("VIF analysis complete: %d features with VIF > 10", len(high_vif_features))
    for feat in high_vif_features:
        logger.info("  %s: VIF=%.2f", feat["feature"], feat["vif"])

    return result


def analyze_features(
    X: np.ndarray,
    feature_names: list[str],
    vif_threshold: float = 10.0,
    corr_threshold: float = 0.8,
) -> dict:
    """Perform comprehensive feature analysis.

    Args:
        X: Feature matrix.
        feature_names: List of feature names.
        vif_threshold: VIF threshold for flagging.
        corr_threshold: Correlation threshold for flagging.

    Returns:
        Dictionary with all analysis results.
    """
    logger.info("Starting feature analysis for %d features...", len(feature_names))

    # Correlation analysis
    corr_result = compute_correlation_matrix(X, feature_names)

    # VIF analysis
    vif_result = compute_vif(X, feature_names)

    # Summary
    summary = {
        "n_features": len(feature_names),
        "n_high_correlation": corr_result["n_high_correlation"],
        "n_high_vif": vif_result["n_high_vif"],
        "mean_vif": vif_result["mean_vif"],
        "max_vif": vif_result["max_vif"],
        "recommendations": [],
    }

    # Generate recommendations
    if vif_result["n_high_vif"] > 0:
        summary["recommendations"].append(
            f"Consider removing or combining {vif_result['n_high_vif']} features with VIF > {vif_threshold}"
        )

    if corr_result["n_high_correlation"] > 0:
        summary["recommendations"].append(
            f"Consider removing one feature from each of {corr_result['n_high_correlation']} highly correlated pairs"
        )

    if vif_result["n_high_vif"] == 0 and corr_result["n_high_correlation"] == 0:
        summary["recommendations"].append("No multicollinearity issues detected")

    result = {
        "correlation_analysis": corr_result,
        "vif_analysis": vif_result,
        "summary": summary,
    }

    logger.info("Feature analysis complete")
    logger.info("  Mean VIF: %.2f", vif_result["mean_vif"])
    logger.info("  Max VIF: %.2f", vif_result["max_vif"])
    logger.info("  High correlation pairs: %d", corr_result["n_high_correlation"])

    return result
