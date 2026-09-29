"""
Unified Physiological Model Training Pipeline (R-F2).

Merges the former train_physiological_xgboost.py / train_physiological_lightgbm.py
(same ~76% shared pipeline) into a single entry point:

    python scripts/train_physiological.py --model xgb    # XGBoost (默认)
    python scripts/train_physiological.py --model lgbm   # LightGBM

Per-model training/evaluation/importance code paths are preserved verbatim from
the original scripts; shared data loading / preprocessing / CV / SMOTE /
artifact saving is unified.

Output (per model):
    - model.json (xgb) / model.txt (lgbm)
    - scaler.json, feature_names.json, metrics.json, training_info.json, config.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.ml.data_cleaner import clean_dataset
from app.ml.data_loader import merge_datasets
from app.ml.data_split import stratified_split
from app.ml.feature_engineering import ALL_FEATURES, engineer_features, get_feature_matrix
from app.ml.scaler import SimpleStandardScaler, save_feature_names
from app.ml.smote import apply_smote_if_needed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIRS = {
    "xgb": Path("models/artifacts/physiological/xgboost"),
    "lgbm": Path("models/artifacts/physiological/lightgbm"),
}
MODEL_ARTIFACT_NAMES = {
    "xgb": "model.json",
    "lgbm": "model.txt",
}


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments (args 可注入以便测试)."""
    parser = argparse.ArgumentParser(
        description="Train physiological depression model (--model xgb|lgbm)"
    )
    parser.add_argument(
        "--model",
        type=str,
        choices=["xgb", "lgbm"],
        default="xgb",
        help="Model family to train (xgb=XGBoost, lgbm=LightGBM)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for model artifacts (default per model family)",
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
        help="Learning rate",
    )
    parser.add_argument(
        "--num-leaves",
        type=int,
        default=31,
        help="Number of leaves in one tree (LightGBM only)",
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
    return parser.parse_args(args)


def load_and_preprocess_data() -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    """Load and preprocess physiological data.

    Returns:
        Tuple of (feature_df, full_df, y_array).
    """
    logger.info("Loading datasets...")
    df = merge_datasets()
    logger.info("Loaded %d samples", len(df))

    logger.info("Cleaning data...")
    df = clean_dataset(df)
    logger.info("After cleaning: %d samples", len(df))

    logger.info("Engineering features...")
    df = engineer_features(df)

    # Get feature matrix
    X_df = get_feature_matrix(df)
    feature_names = list(X_df.columns)
    logger.info("Features (%d): %s", len(feature_names), feature_names)

    y = df["depression_label"].values.astype(np.int32)

    return X_df, df, y


def compute_class_weight(y: np.ndarray) -> float:
    """Compute scale_pos_weight for imbalanced data.

    Args:
        y: Target vector.

    Returns:
        scale_pos_weight value.
    """
    n_neg = np.sum(y == 0)
    n_pos = np.sum(y == 1)
    if n_pos == 0:
        return 1.0
    return n_neg / n_pos


def train_xgboost_model(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    feature_names: list[str],
    config: dict,
) -> tuple[Any, dict]:
    """Train XGBoost model (preserved verbatim from train_physiological_xgboost.py)."""
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


def train_lightgbm_model(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    feature_names: list[str],
    config: dict,
) -> tuple[Any, dict]:
    """Train LightGBM model (preserved verbatim from train_physiological_lightgbm.py)."""
    try:
        import lightgbm as lgb
    except ImportError:
        logger.error("LightGBM not installed. Install with: pip install lightgbm")
        raise

    # Compute scale_pos_weight
    if config["scale_pos_weight"] == "auto":
        scale_pos_weight = compute_class_weight(y_train)
        logger.info("Auto scale_pos_weight: %.2f", scale_pos_weight)
    else:
        scale_pos_weight = float(config["scale_pos_weight"])

    # Create datasets
    train_data = lgb.Dataset(X_train, label=y_train, feature_name=feature_names)
    val_data = lgb.Dataset(X_val, label=y_val, feature_name=feature_names, reference=train_data)

    # LightGBM parameters
    params = {
        "objective": "binary",
        "metric": ["binary_logloss", "auc", "binary_error"],
        "boosting_type": "gbdt",
        "num_leaves": config["num_leaves"],
        "max_depth": config["max_depth"],
        "learning_rate": config["learning_rate"],
        "bagging_fraction": config["subsample"],
        "feature_fraction": config["colsample_bytree"],
        "scale_pos_weight": scale_pos_weight,
        "random_state": config["random_state"],
        "verbose": -1,
    }

    logger.info("Training LightGBM with params: %s", params)

    # Train with early stopping
    model = lgb.train(
        params,
        train_data,
        num_boost_round=config["n_estimators"],
        valid_sets=[train_data, val_data],
        valid_names=["train", "val"],
        callbacks=[lgb.early_stopping(stopping_rounds=10, verbose=False)],
    )

    # Get best iteration info
    best_iteration = model.best_iteration if hasattr(model, "best_iteration") else config["n_estimators"]

    training_info = {
        "best_iteration": int(best_iteration),
        "final_num_trees": model.num_trees(),
    }

    logger.info("Training complete: best_iteration=%d", best_iteration)

    return model, training_info


_TRAINERS = {
    "xgb": train_xgboost_model,
    "lgbm": train_lightgbm_model,
}


def evaluate_model(
    model: Any,
    X: np.ndarray,
    y: np.ndarray,
    feature_names: list[str],
    model_kind: str,
) -> dict:
    """Evaluate model on given data (R-F2: xgb/lgbm 归一).

    XGBoost 需要 DMatrix 包装；LightGBM 直接 predict numpy 数组。
    """
    if model_kind == "xgb":
        import xgboost as xgb

        dtest = xgb.DMatrix(X, label=y, feature_names=feature_names)
        y_pred_proba = model.predict(dtest)
    else:
        y_pred_proba = model.predict(X)
    y_pred = (y_pred_proba >= 0.5).astype(int)

    # Compute metrics
    from app.ml.trainer import compute_metrics

    metrics = compute_metrics(y.reshape(-1, 1), y_pred_proba.reshape(-1, 1))
    metrics["n_samples"] = len(y)

    return metrics


def extract_feature_importance_xgb(model: Any, feature_names: list[str]) -> list[dict]:
    """Extract feature importance from XGBoost model (gain, f0/f1 mapping)."""
    importance_dict = model.get_score(importance_type="gain")

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


def extract_feature_importance_lightgbm(
    model: Any, feature_names: list[str]
) -> list[dict]:
    """Extract feature importance from LightGBM model (gain)."""
    importance = model.feature_importance(importance_type="gain")

    importance_list = []
    for feat_name, feat_importance in zip(feature_names, importance):
        importance_list.append({
            "feature": feat_name,
            "importance": float(feat_importance),
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
    model_kind: str,
) -> None:
    """Save all model artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save model (xgb → model.json, lgbm → model.txt)
    model_path = output_dir / MODEL_ARTIFACT_NAMES[model_kind]
    model.save_model(str(model_path))
    logger.info("Saved model to %s", model_path)

    # Save scaler
    scaler.save(output_dir / "scaler.json")

    # Save feature names
    save_feature_names(feature_names, output_dir / "feature_names.json")

    # Save metrics
    with open(output_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    # Save training info
    with open(output_dir / "training_info.json", "w", encoding="utf-8") as f:
        json.dump(training_info, f, indent=2)

    # Save config
    with open(output_dir / "config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    logger.info("All artifacts saved to %s", output_dir)


def main() -> None:
    """Main training pipeline."""
    args = parse_args()
    model_kind = args.model
    output_dir = args.output_dir or DEFAULT_OUTPUT_DIRS[model_kind]

    # Load data
    X_df, full_df, y = load_and_preprocess_data()
    X = X_df.values.astype(np.float32)
    feature_names = list(X_df.columns)

    # Split data
    logger.info("Splitting data...")
    X_train, X_val, X_test, y_train, y_val, y_test = stratified_split(
        X, y, random_state=args.random_state
    )
    logger.info("Train: %d, Val: %d, Test: %d", len(X_train), len(X_val), len(X_test))

    # Scale features (fit on train only)
    logger.info("Scaling features...")
    scaler = SimpleStandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_val = scaler.transform(X_val)
    X_test = scaler.transform(X_test)

    # Apply SMOTE if needed (on train only, max ratio 0.8 per Ralph rules)
    logger.info("Applying SMOTE (ratio <= 0.8)...")
    X_train, y_train = apply_smote_if_needed(
        X_train, y_train, sampling_strategy=min(args.smote_ratio, 0.8)
    )
    logger.info("After SMOTE: %d samples", len(X_train))

    # Training config (字段与各模型原脚本 config.json 保持一致)
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
    if model_kind == "lgbm":
        config["num_leaves"] = args.num_leaves

    # Train model
    logger.info("Training %s model...", model_kind)
    train_fn = _TRAINERS[model_kind]
    model, training_info = train_fn(
        X_train, y_train, X_val, y_val, feature_names, config
    )

    # Evaluate on test set
    logger.info("Evaluating on test set...")
    test_metrics = evaluate_model(model, X_test, y_test, feature_names, model_kind)
    logger.info("Test metrics: %s", test_metrics)

    # Extract feature importance
    logger.info("Extracting feature importance...")
    if model_kind == "xgb":
        feature_importance = extract_feature_importance_xgb(model, feature_names)
    else:
        feature_importance = extract_feature_importance_lightgbm(model, feature_names)
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
        output_dir=output_dir,
        model_kind=model_kind,
    )

    logger.info("Training pipeline complete!")
    logger.info("Final Test F1: %.4f", test_metrics["f1"])


if __name__ == "__main__":
    main()
