"""Feature importance validation by comparing SHAP and VIF results."""

from __future__ import annotations

import logging
from typing import Callable

import numpy as np

from app.ml.evaluation import compute_shap_values_approximation
from app.ml.feature_analysis import compute_vif

logger = logging.getLogger(__name__)


def validate_feature_importance(
    X: np.ndarray,
    feature_names: list[str],
    model_predict_fn: Callable,
    vif_threshold: float = 10.0,
    shap_threshold: float = 0.05,
) -> dict:
    """Validate feature importance by comparing SHAP and VIF results.

    This helps identify:
    1. Features that are important (high SHAP) but not collinear (low VIF) -> Keep
    2. Features that are collinear (high VIF) but not important (low SHAP) -> Remove candidate
    3. Features that are both important and collinear -> Consider combining

    Args:
        X: Feature matrix.
        feature_names: List of feature names.
        model_predict_fn: Function that takes X and returns predictions.
        vif_threshold: VIF threshold for flagging.
        shap_threshold: SHAP importance threshold for flagging.

    Returns:
        Dictionary with validation results and recommendations.
    """
    logger.info("Starting feature importance validation...")

    # Compute SHAP values
    shap_result = compute_shap_values_approximation(X, feature_names, model_predict_fn)
    shap_importances = shap_result["feature_importances"]

    # Compute VIF
    vif_result = compute_vif(X, feature_names)
    vif_values = vif_result["vif_values"]

    # Compare and categorize features
    feature_analysis = []
    for feat in feature_names:
        shap_imp = shap_importances.get(feat, 0.0)
        vif_val = vif_values.get(feat, 0.0)

        # Determine category
        is_important = shap_imp >= shap_threshold
        is_collinear = vif_val >= vif_threshold

        if is_important and not is_collinear:
            category = "keep"
            recommendation = "Keep: Important and not collinear"
        elif is_important and is_collinear:
            category = "review"
            recommendation = "Review: Important but collinear, consider combining"
        elif not is_important and is_collinear:
            category = "remove_candidate"
            recommendation = "Remove candidate: Collinear but not important"
        else:
            category = "optional"
            recommendation = "Optional: Not important and not collinear"

        feature_analysis.append(
            {
                "feature": feat,
                "shap_importance": float(shap_imp),
                "vif": float(vif_val),
                "is_important": is_important,
                "is_collinear": is_collinear,
                "category": category,
                "recommendation": recommendation,
            }
        )

    # Sort by SHAP importance descending
    feature_analysis.sort(key=lambda x: x["shap_importance"], reverse=True)

    # Generate summary
    keep_features = [f["feature"] for f in feature_analysis if f["category"] == "keep"]
    review_features = [
        f["feature"] for f in feature_analysis if f["category"] == "review"
    ]
    remove_candidates = [
        f["feature"] for f in feature_analysis if f["category"] == "remove_candidate"
    ]
    optional_features = [
        f["feature"] for f in feature_analysis if f["category"] == "optional"
    ]

    summary = {
        "total_features": len(feature_names),
        "keep": len(keep_features),
        "review": len(review_features),
        # BUG-004 修复：原 "remove_candidates" 键同时被赋值为 int (count, L96) 和
        # list (feature names, L100)，后者覆盖前者，导致计数丢失。改用不冲突的键名。
        "remove_candidate_count": len(remove_candidates),
        "optional": len(optional_features),
        "keep_features": keep_features,
        "review_features": review_features,
        "remove_candidates": remove_candidates,
        "optional_features": optional_features,
    }

    result = {
        "feature_analysis": feature_analysis,
        "summary": summary,
        "shap_result": shap_result,
        "vif_result": vif_result,
    }

    logger.info("Feature importance validation complete")
    logger.info("  Keep: %d features", len(keep_features))
    logger.info("  Review: %d features", len(review_features))
    logger.info("  Remove candidates: %d features", len(remove_candidates))
    logger.info("  Optional: %d features", len(optional_features))

    if keep_features:
        logger.info("  Top keep features: %s", keep_features[:5])
    if remove_candidates:
        logger.info("  Remove candidates: %s", remove_candidates)

    return result


def select_final_features(
    validation_result: dict,
    keep_optional: bool = True,
) -> list[str]:
    """Select final feature subset based on validation results.

    Args:
        validation_result: Result from validate_feature_importance().
        keep_optional: Whether to keep optional features.

    Returns:
        List of selected feature names.
    """
    summary = validation_result["summary"]

    selected = []
    selected.extend(summary["keep_features"])
    selected.extend(summary["review_features"])

    if keep_optional:
        selected.extend(summary["optional_features"])

    logger.info(
        "Selected %d features out of %d",
        len(selected),
        summary["total_features"],
    )

    return selected
