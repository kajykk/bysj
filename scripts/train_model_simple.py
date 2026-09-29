"""Simple script to train and save physiological model."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.ml.model import PhysiologicalMLP
from app.ml.trainer import train_model, evaluate
from app.ml.loss import focal_loss
from app.ml.scaler import SimpleStandardScaler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ARTIFACTS_DIR = Path("models/artifacts/physiological")


def generate_synthetic_data(n_samples=2000, n_features=13, random_state=42):
    """Generate synthetic physiological data for demonstration."""
    rng = np.random.RandomState(random_state)
    
    # Generate features with realistic ranges
    X = np.zeros((n_samples, n_features), dtype=np.float32)
    
    # Original features (7)
    X[:, 0] = rng.uniform(4, 10, n_samples)  # sleep_hours
    X[:, 1] = rng.uniform(1, 10, n_samples)  # sleep_quality
    X[:, 2] = rng.uniform(0, 120, n_samples)  # exercise_minutes
    X[:, 3] = rng.uniform(50, 120, n_samples)  # heart_rate
    X[:, 4] = rng.uniform(100, 160, n_samples)  # systolic_bp
    X[:, 5] = rng.uniform(60, 100, n_samples)  # diastolic_bp
    X[:, 6] = rng.uniform(1000, 15000, n_samples)  # steps
    
    # Derived features (6)
    X[:, 7] = X[:, 1] / (X[:, 0] + 1e-6)  # sleep_efficiency
    X[:, 8] = X[:, 6] / (X[:, 2] + 1e-6)  # activity_intensity
    X[:, 9] = X[:, 4] / (X[:, 5] + 1e-6)  # cardiovascular_risk
    X[:, 10] = X[:, 3] * (10 - X[:, 0])  # hr_sleep_interaction
    X[:, 11] = X[:, 6] * X[:, 2]  # overall_activity
    X[:, 12] = rng.randint(0, 3, n_samples).astype(np.float32)  # bp_category
    
    # Generate target (depression_label) with some correlation to features
    # Higher depression risk with: low sleep, high heart rate, low activity
    risk_score = (
        (10 - X[:, 0]) * 0.3 +  # Less sleep = higher risk
        (X[:, 3] - 50) / 70 * 0.3 +  # Higher HR = higher risk
        (10000 - X[:, 6]) / 9000 * 0.2 +  # Less steps = higher risk
        rng.normal(0, 0.2, n_samples)  # Noise
    )
    
    # Convert to binary labels
    y = (risk_score > np.median(risk_score)).astype(np.float32).reshape(-1, 1)
    
    return X, y


def stratified_split(X, y, train_ratio=0.7, val_ratio=0.15, test_ratio=0.15, random_state=42):
    """Split data into train/val/test sets."""
    rng = np.random.RandomState(random_state)
    n_samples = len(y)
    
    # Get indices for each class
    classes = np.unique(y)
    train_indices = []
    val_indices = []
    test_indices = []
    
    for cls in classes:
        cls_indices = np.where(y.flatten() == cls)[0]
        n_cls = len(cls_indices)
        rng.shuffle(cls_indices)
        
        n_train = int(n_cls * train_ratio)
        n_val = int(n_cls * val_ratio)
        
        train_indices.extend(cls_indices[:n_train])
        val_indices.extend(cls_indices[n_train:n_train + n_val])
        test_indices.extend(cls_indices[n_train + n_val:])
    
    rng.shuffle(train_indices)
    rng.shuffle(val_indices)
    rng.shuffle(test_indices)
    
    return (
        X[train_indices], X[val_indices], X[test_indices],
        y[train_indices], y[val_indices], y[test_indices]
    )


def main():
    """Train and save the physiological model."""
    logger.info("Generating synthetic training data...")
    X, y = generate_synthetic_data(n_samples=2000, n_features=13)
    logger.info("Generated %d samples with %d features", len(X), X.shape[1])
    logger.info("Class distribution: positive=%d, negative=%d", int(y.sum()), int(len(y) - y.sum()))
    
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
    feature_names = [
        "sleep_hours", "sleep_quality", "exercise_minutes", "heart_rate",
        "systolic_bp", "diastolic_bp", "steps",
        "sleep_efficiency", "activity_intensity", "cardiovascular_risk",
        "hr_sleep_interaction", "overall_activity", "bp_category"
    ]
    with open(ARTIFACTS_DIR / "feature_names.json", "w", encoding="utf-8") as f:
        json.dump(feature_names, f, ensure_ascii=False, indent=2)
    
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
    logger.info("Model parameters: %d", model.count_parameters())


if __name__ == "__main__":
    main()
