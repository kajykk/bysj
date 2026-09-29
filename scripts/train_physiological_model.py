"""Train and save physiological depression prediction model."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.ml.data_loader import merge_datasets
from app.ml.data_cleaner import clean_dataset
from app.ml.feature_engineering import engineer_features, get_feature_matrix
from app.ml.data_split import stratified_split
from app.ml.smote import simple_smote
from app.ml.model import PhysiologicalMLP
from app.ml.trainer import train_model, evaluate
from app.ml.loss import focal_loss
from app.ml.scaler import SimpleStandardScaler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ARTIFACTS_DIR = Path("models/artifacts/physiological")


def main():
    """Train and save the physiological model."""
    logger.info("Loading data...")
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
    logger.info("Features: %s", feature_names)

    # Prepare data
    X = X_df.values.astype(np.float32)
    y = df["depression_label"].values.astype(np.float32).reshape(-1, 1)

    logger.info("Splitting data...")
    X_train, X_val, X_test, y_train, y_val, y_test = stratified_split(X, y)
    logger.info("Train: %d, Val: %d, Test: %d", len(X_train), len(X_val), len(X_test))

    logger.info("Scaling features...")
    scaler = SimpleStandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_val = scaler.transform(X_val)
    X_test = scaler.transform(X_test)

    # Save scaler
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    scaler.save(ARTIFACTS_DIR / "scaler.json")

    # Save feature names
    with open(ARTIFACTS_DIR / "feature_names.json", "w", encoding="utf-8") as f:
        json.dump(feature_names, f, ensure_ascii=False, indent=2)

    logger.info("Applying SMOTE...")
    X_train, y_train = simple_smote(X_train, y_train)
    logger.info("After SMOTE: %d samples", len(X_train))

    logger.info("Training model...")
    model = PhysiologicalMLP(
        input_dim=X_train.shape[1],
        hidden_dims=[64, 32, 16],
        dropout_rate=0.3,
        use_batch_norm=False,
    )

    history = train_model(
        model,
        X_train,
        y_train,
        X_val,
        y_val,
        epochs=100,
        batch_size=32,
        learning_rate=0.001,
        weight_decay=0.01,
        patience=15,
        loss_fn=focal_loss,
    )

    # Evaluate on test set
    test_loss, test_metrics = evaluate(model, X_test, y_test, focal_loss)
    logger.info("Test metrics: %s", test_metrics)

    # Save model
    model.save(ARTIFACTS_DIR / "model.json")

    # Save metrics
    metrics = {
        "test_metrics": test_metrics,
        "history": {
            "train_loss": [float(x) for x in history["train_loss"]],
            "val_loss": [float(x) for x in history["val_loss"]],
            "train_f1": [float(x) for x in history["train_f1"]],
            "val_f1": [float(x) for x in history["val_f1"]],
            "best_epoch": history["best_epoch"],
            "best_val_f1": float(history["best_val_f1"]),
        },
    }
    with open(ARTIFACTS_DIR / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    logger.info("Training complete. Artifacts saved to %s", ARTIFACTS_DIR)


if __name__ == "__main__":
    main()
