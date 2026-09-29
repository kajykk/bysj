"""
Model Selection Script for Physiological Depression Prediction.

Compares XGBoost / LightGBM / PyTorch MLP / NumPy MLP
and selects the best model based on:
- F1-Score (primary)
- ROC-AUC
- AUPRC
- Inference latency
- Model size
- Interpretability

Usage:
    python scripts/select_best_physiological_model.py \
        --xgboost-path models/artifacts/physiological/xgboost \
        --lightgbm-path models/artifacts/physiological/lightgbm \
        --pytorch-path models/artifacts/physiological/pytorch \
        --numpy-path models/artifacts/physiological \
        --output-dir models/selected

Output:
    - selection_report.json: Detailed comparison report
    - selected_model.txt: Name of selected model
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.ml.data_cleaner import clean_dataset
from app.ml.data_loader import merge_datasets
from app.ml.data_split import stratified_split
from app.ml.feature_engineering import engineer_features, get_feature_matrix
from app.ml.scaler import SimpleStandardScaler
from app.ml.smote import apply_smote_if_needed
from app.ml.trainer import compute_metrics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Select best physiological model")
    parser.add_argument(
        "--xgboost-path",
        type=Path,
        default=Path("models/artifacts/physiological/xgboost"),
        help="XGBoost model directory",
    )
    parser.add_argument(
        "--lightgbm-path",
        type=Path,
        default=Path("models/artifacts/physiological/lightgbm"),
        help="LightGBM model directory",
    )
    parser.add_argument(
        "--pytorch-path",
        type=Path,
        default=Path("models/artifacts/physiological/pytorch"),
        help="PyTorch model directory",
    )
    parser.add_argument(
        "--numpy-path",
        type=Path,
        default=Path("models/artifacts/physiological"),
        help="NumPy MLP model directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("models/selected"),
        help="Output directory for selection report",
    )
    return parser.parse_args()


def load_test_data() -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Load and preprocess test data.

    Returns:
        Tuple of (X_test, y_test, feature_names).
    """
    logger.info("Loading test data...")
    df = merge_datasets()
    df = clean_dataset(df)
    df = engineer_features(df)

    X_df = get_feature_matrix(df)
    feature_names = list(X_df.columns)
    X = X_df.values.astype(np.float32)
    y = df["depression_label"].values.astype(np.int32)

    # Split data
    X_train, X_val, X_test, y_train, y_val, y_test = stratified_split(X, y, random_state=42)

    # Scale features
    scaler = SimpleStandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_test = scaler.transform(X_test)

    return X_test, y_test, feature_names


def evaluate_xgboost(model_path: Path, X_test: np.ndarray, y_test: np.ndarray, feature_names: list[str]) -> dict | None:
    """Evaluate XGBoost model."""
    try:
        import xgboost as xgb

        model_file = model_path / "model.json"
        if not model_file.exists():
            logger.warning("XGBoost model not found: %s", model_file)
            return None

        model = xgb.Booster()
        model.load_model(str(model_file))

        dtest = xgb.DMatrix(X_test, label=y_test, feature_names=feature_names)

        # Measure latency
        start = time.perf_counter()
        y_pred_proba = model.predict(dtest)
        latency_ms = (time.perf_counter() - start) * 1000 / len(X_test)

        metrics = compute_metrics(y_test.reshape(-1, 1), y_pred_proba.reshape(-1, 1))
        metrics["latency_ms"] = latency_ms
        metrics["model_size_mb"] = model_file.stat().st_size / (1024 * 1024)

        return metrics
    except Exception as exc:
        logger.warning("XGBoost evaluation failed: %s", exc)
        return None


def evaluate_lightgbm(model_path: Path, X_test: np.ndarray, y_test: np.ndarray) -> dict | None:
    """Evaluate LightGBM model."""
    try:
        import lightgbm as lgb

        model_file = model_path / "model.txt"
        if not model_file.exists():
            logger.warning("LightGBM model not found: %s", model_file)
            return None

        model = lgb.Booster(model_file=str(model_file))

        # Measure latency
        start = time.perf_counter()
        y_pred_proba = model.predict(X_test)
        latency_ms = (time.perf_counter() - start) * 1000 / len(X_test)

        metrics = compute_metrics(y_test.reshape(-1, 1), y_pred_proba.reshape(-1, 1))
        metrics["latency_ms"] = latency_ms
        metrics["model_size_mb"] = model_file.stat().st_size / (1024 * 1024)

        return metrics
    except Exception as exc:
        logger.warning("LightGBM evaluation failed: %s", exc)
        return None


def evaluate_pytorch_mlp(model_path: Path, X_test: np.ndarray, y_test: np.ndarray) -> dict | None:
    """Evaluate PyTorch MLP model."""
    try:
        from app.ml.pytorch_mlp import PyTorchMLP, evaluate_pytorch_mlp

        model_file = model_path / "model.pth"
        if not model_file.exists():
            logger.warning("PyTorch model not found: %s", model_file)
            return None

        model = PyTorchMLP.load(model_file)

        # Measure latency
        start = time.perf_counter()
        metrics = evaluate_pytorch_mlp(model, X_test, y_test)
        latency_ms = (time.perf_counter() - start) * 1000 / len(X_test)

        metrics["latency_ms"] = latency_ms
        metrics["model_size_mb"] = model_file.stat().st_size / (1024 * 1024)

        return metrics
    except Exception as exc:
        logger.warning("PyTorch MLP evaluation failed: %s", exc)
        return None


def evaluate_numpy_mlp(model_path: Path, X_test: np.ndarray, y_test: np.ndarray) -> dict | None:
    """Evaluate NumPy MLP model."""
    try:
        from app.ml.model import PhysiologicalMLP

        model_file = model_path / "model.json"
        if not model_file.exists():
            logger.warning("NumPy model not found: %s", model_file)
            return None

        model = PhysiologicalMLP.load(model_file)

        # Measure latency
        start = time.perf_counter()
        y_pred_proba = model.predict_proba(X_test)
        latency_ms = (time.perf_counter() - start) * 1000 / len(X_test)

        metrics = compute_metrics(y_test.reshape(-1, 1), y_pred_proba)
        metrics["latency_ms"] = latency_ms
        metrics["model_size_mb"] = model_file.stat().st_size / (1024 * 1024)

        return metrics
    except Exception as exc:
        logger.warning("NumPy MLP evaluation failed: %s", exc)
        return None


def select_best_model(results: dict[str, dict]) -> tuple[str, dict]:
    """Select best model based on F1 score and other criteria.

    Args:
        results: Dictionary of model_name -> metrics.

    Returns:
        Tuple of (best_model_name, selection_details).
    """
    if not results:
        raise ValueError("No models to compare")

    # Scoring weights
    weights = {
        "f1": 0.4,
        "roc_auc": 0.2,
        "auprc": 0.2,
        "latency_ms": -0.1,  # Lower is better
        "model_size_mb": -0.1,  # Lower is better
    }

    scores = {}
    for name, metrics in results.items():
        score = 0.0
        for metric, weight in weights.items():
            if metric in metrics:
                # Normalize latency and size (lower is better)
                if metric in ["latency_ms", "model_size_mb"]:
                    # Use inverse normalization
                    all_values = [m[metric] for m in results.values() if metric in m]
                    if all_values:
                        max_val = max(all_values)
                        if max_val > 0:
                            normalized = 1.0 - (metrics[metric] / max_val)
                        else:
                            normalized = 1.0
                    else:
                        normalized = 0.5
                else:
                    # Higher is better
                    normalized = metrics[metric]
                score += normalized * weight
        scores[name] = score

    best_model = max(scores, key=scores.get)

    selection_details = {
        "best_model": best_model,
        "scores": scores,
        "all_metrics": results,
        "selection_criteria": {
            "primary": "F1-Score (weight=0.4)",
            "secondary": ["ROC-AUC (0.2)", "AUPRC (0.2)", "Latency (-0.1)", "Model Size (-0.1)"],
        },
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    return best_model, selection_details


def main() -> None:
    """Main model selection pipeline."""
    args = parse_args()

    # Load test data
    X_test, y_test, feature_names = load_test_data()
    logger.info("Test data: %d samples, %d features", len(X_test), X_test.shape[1])

    # Evaluate all models
    results = {}

    logger.info("Evaluating XGBoost...")
    xgb_metrics = evaluate_xgboost(args.xgboost_path, X_test, y_test, feature_names)
    if xgb_metrics:
        results["xgboost"] = xgb_metrics
        logger.info("XGBoost F1: %.4f", xgb_metrics["f1"])

    logger.info("Evaluating LightGBM...")
    lgb_metrics = evaluate_lightgbm(args.lightgbm_path, X_test, y_test)
    if lgb_metrics:
        results["lightgbm"] = lgb_metrics
        logger.info("LightGBM F1: %.4f", lgb_metrics["f1"])

    logger.info("Evaluating PyTorch MLP...")
    pytorch_metrics = evaluate_pytorch_mlp(args.pytorch_path, X_test, y_test)
    if pytorch_metrics:
        results["pytorch_mlp"] = pytorch_metrics
        logger.info("PyTorch MLP F1: %.4f", pytorch_metrics["f1"])

    logger.info("Evaluating NumPy MLP (baseline)...")
    numpy_metrics = evaluate_numpy_mlp(args.numpy_path, X_test, y_test)
    if numpy_metrics:
        results["numpy_mlp"] = numpy_metrics
        logger.info("NumPy MLP F1: %.4f", numpy_metrics["f1"])

    # Select best model
    best_model, selection_details = select_best_model(results)

    logger.info("=" * 50)
    logger.info("MODEL SELECTION RESULT")
    logger.info("=" * 50)
    logger.info("Best model: %s", best_model)
    logger.info("F1-Score: %.4f", results[best_model]["f1"])
    logger.info("ROC-AUC: %.4f", results[best_model]["roc_auc"])
    logger.info("AUPRC: %.4f", results[best_model]["auprc"])
    logger.info("Latency: %.2f ms/sample", results[best_model]["latency_ms"])
    logger.info("Model size: %.2f MB", results[best_model]["model_size_mb"])
    logger.info("=" * 50)

    # Save report
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with open(args.output_dir / "selection_report.json", "w", encoding="utf-8") as f:
        json.dump(selection_details, f, indent=2)

    with open(args.output_dir / "selected_model.txt", "w", encoding="utf-8") as f:
        f.write(best_model)

    logger.info("Selection report saved to %s", args.output_dir)


if __name__ == "__main__":
    main()
