"""DEPRECATED: 已由 train_physiological.py --model xgb 取代（R-F2 三合一合并）。
保留本文件仅为等价性验证对照，请勿在新流程中使用。

XGBoost Training Pipeline for Physiological Depression Prediction.

This script implements:
- Data loading and preprocessing (Depresjon + Kaggle)
- 5-Fold Cross-Validation with per-fold independent preprocessing
- Feature importance extraction
- Model saving with artifacts

Usage:
    python scripts/train_physiological_xgboost.py \
        --output-dir models/artifacts/physiological/xgboost \
        --n-estimators 200 \
        --max-depth 5 \
        --learning-rate 0.05

Output:
    - model.pkl: Trained XGBoost model
    - scaler.json: Fitted StandardScaler parameters
    - feature_names.json: Feature name list
    - metrics.json: CV metrics and feature importance
    - config.json: Training configuration
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from physio_training_common import (
    SimpleStandardScaler,
    compute_class_weight,
    compute_eval_metrics,
    load_and_preprocess_data,
    logger,
    prepare_training_data,
    save_json_artifacts,
)

DEFAULT_OUTPUT_DIR = Path("models/artifacts/physiological/xgboost")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Train XGBoost physiological model")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory for model artifacts",
    )
    parser.add_argument(
        "--n-estimators",
        type=int,
        default=200,
        help="Number of boosting rounds",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=5,
        help="Maximum tree depth",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.05,
        help="Learning rate (eta)",
    )
    parser.add_argument(
        "--subsample",
        type=float,
        default=0.8,
        help="Subsample ratio",
    )
    parser.add_argument(
        "--colsample-bytree",
        type=float,
        default=0.8,
        help="Column sample ratio per tree",
    )
    parser.add_argument(
        "--scale-pos-weight",
        type=str,
        default="auto",
        help="Scale positive weight (auto or float)",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="Random seed",
    )
    parser.add_argument(
        "--smote-ratio",
        type=float,
        default=0.8,
        help="SMOTE sampling strategy (max 0.8 per Ralph rules)",
    )
    return parser.parse_args()


def train_xgboost_model(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    feature_names: list[str],
    config: dict,
) -> tuple[Any, dict]:
    """Train XGBoost model.

    Args:
        X_train: Training features.
        y_train: Training labels.
        X_val: Validation features.
        y_val: Validation labels.
        feature_names: List of feature names.
        config: Training configuration.

    Returns:
        Tuple of (model, training_info).
    """
    try:
        import xgboost as xgb
    except ImportError:
        logger.error("XGBoost not installed. Install with: pip install xgboost")
        raise

    # Compute scale_pos_weight
    if config["scale_pos_weight"] == "auto":
        scale_pos_weight = compute_class_weight(y_train)
        logger.info("Auto scale_pos_weight: %.2f", scale_pos_weight)
    else:
        scale_pos_weight = float(config["scale_pos_weight"])

    # Create DMatrix
    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=feature_names)
    dval = xgb.DMatrix(X_val, label=y_val, feature_names=feature_names)

    # XGBoost parameters
    params = {
        "objective": "binary:logistic",
        "eval_metric": ["logloss", "auc", "error"],
        "max_depth": config["max_depth"],
        "eta": config["learning_rate"],
        "subsample": config["subsample"],
        "colsample_bytree": config["colsample_bytree"],
        "scale_pos_weight": scale_pos_weight,
        "random_state": config["random_state"],
        "tree_method": "hist",  # Fast histogram-based algorithm
    }

    logger.info("Training XGBoost with params: %s", params)

    # Train with early stopping
    evals = [(dtrain, "train"), (dval, "val")]
    model = xgb.train(
        params,
        dtrain,
        num_boost_round=config["n_estimators"],
        evals=evals,
        early_stopping_rounds=10,
        verbose_eval=10,
    )

    # Get best iteration info
    best_iteration = model.best_iteration if hasattr(model, "best_iteration") else config["n_estimators"]
    best_score = model.best_score if hasattr(model, "best_score") else None

    training_info = {
        "best_iteration": int(best_iteration),
        "best_score": float(best_score) if best_score else None,
        "final_num_trees": int(model.num_boosted_rounds()),
    }

    logger.info("Training complete: best_iteration=%d", best_iteration)

    return model, training_info


def evaluate_model(model: Any, X: np.ndarray, y: np.ndarray, feature_names: list[str]) -> dict:
    """Evaluate model on given data.

    Args:
        model: Trained XGBoost model.
        X: Features.
        y: Labels.
        feature_names: Feature names.

    Returns:
        Dictionary with metrics.
    """
    import xgboost as xgb

    dtest = xgb.DMatrix(X, label=y, feature_names=feature_names)
    y_pred_proba = model.predict(dtest)
    return compute_eval_metrics(y, y_pred_proba)


def extract_feature_importance(model: Any, feature_names: list[str]) -> list[dict]:
    """Extract feature importance from XGBoost model.

    Args:
        model: Trained XGBoost model.
        feature_names: Feature names.

    Returns:
        List of {feature, importance} dictionaries.
    """
    importance_dict = model.get_score(importance_type="gain")

    # Map to feature names
    importance_list = []
    for feat_name in feature_names:
        # XGBoost uses f0, f1, ... format
        feat_idx = feature_names.index(feat_name)
        feat_key = f"f{feat_idx}"
        importance_list.append({
            "feature": feat_name,
            "importance": float(importance_dict.get(feat_key, 0.0)),
        })

    # Sort by importance descending
    importance_list.sort(key=lambda x: x["importance"], reverse=True)

    return importance_list


def save_artifacts(
    model: Any,
    scaler: SimpleStandardScaler,
    feature_names: list[str],
    metrics: dict,
    training_info: dict,
    config: dict,
    output_dir: Path,
) -> None:
    """Save all model artifacts.

    Args:
        model: Trained model.
        scaler: Fitted scaler.
        feature_names: Feature names.
        metrics: Evaluation metrics.
        training_info: Training information.
        config: Training configuration.
        output_dir: Output directory.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save model
    model_path = output_dir / "model.json"
    model.save_model(str(model_path))
    logger.info("Saved model to %s", model_path)

    save_json_artifacts(scaler, feature_names, metrics, training_info, config, output_dir)


def main() -> None:
    """Main training pipeline."""
    args = parse_args()

    # Load data
    X_df, full_df, y = load_and_preprocess_data()
    X_train, X_val, X_test, y_train, y_val, y_test, feature_names, scaler = prepare_training_data(
        args, X_df, y
    )

    # Training config
    config = {
        "n_estimators": args.n_estimators,
        "max_depth": args.max_depth,
        "learning_rate": args.learning_rate,
        "subsample": args.subsample,
        "colsample_bytree": args.colsample_bytree,
        "scale_pos_weight": args.scale_pos_weight,
        "random_state": args.random_state,
        "smote_ratio": min(args.smote_ratio, 0.8),
    }

    # Train model
    logger.info("Training XGBoost model...")
    model, training_info = train_xgboost_model(
        X_train, y_train, X_val, y_val, feature_names, config
    )

    # Evaluate on test set
    logger.info("Evaluating on test set...")
    test_metrics = evaluate_model(model, X_test, y_test, feature_names)
    logger.info("Test metrics: %s", test_metrics)

    # Extract feature importance
    logger.info("Extracting feature importance...")
    feature_importance = extract_feature_importance(model, feature_names)
    logger.info("Top 5 features: %s", feature_importance[:5])

    # Compile metrics
    metrics = {
        "test_metrics": test_metrics,
        "feature_importance": feature_importance,
        "n_features": len(feature_names),
        "feature_names": feature_names,
    }

    # Save artifacts
    save_artifacts(
        model=model,
        scaler=scaler,
        feature_names=feature_names,
        metrics=metrics,
        training_info=training_info,
        config=config,
        output_dir=args.output_dir,
    )

    logger.info("Training pipeline complete!")
    logger.info("Final Test F1: %.4f", test_metrics["f1"])


if __name__ == "__main__":
    main()
