"""
Baseline Freeze Script - v1.4 Deep Learning Transformation

This script records the current production model versions and metrics,
creating an immutable baseline for rollback and comparison purposes.

Usage:
    python scripts/baseline_freeze.py

Output:
    models/baselines/baseline_v1.3_YYYYMMDD_HHMMSS.json
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Baseline configuration
BASELINE_VERSION = "v1.3"
ITERATION_NAME = "v1.4-deep-learning-transformation"

# Current production model metrics (from existing artifacts)
CURRENT_BASELINE = {
    "baseline_version": BASELINE_VERSION,
    "iteration": ITERATION_NAME,
    "frozen_at": datetime.now(timezone.utc).isoformat(),
    "models": {
        "structured_catboost": {
            "model_id": "structured_logistic_regression_quick",
            "name": "Structured Data Model (CatBoost)",
            "version": "v1.0",
            "status": "production",
            "type": "catboost",
            "metrics": {
                "f1_score": 0.8725,
                "precision": 0.0,  # To be filled from actual metrics.json
                "recall": 0.0,
                "accuracy": 0.0,
                "roc_auc": 0.0,
            },
            "artifact_path": "models/artifacts/depression_tabular/best_model.pkl",
            "metrics_path": "models/artifacts/depression_tabular/metrics.json",
            "fallback_id": None,
            "enabled": True,
        },
        "text_tfidf_lr": {
            "model_id": "text_depression_model",
            "name": "Text Model (TF-IDF + LR)",
            "version": "v1.0",
            "status": "production",
            "type": "logistic_regression",
            "metrics": {
                "f1_score": 0.9681,
                "precision": 0.0,
                "recall": 0.0,
                "accuracy": 0.0,
                "roc_auc": 0.0,
            },
            "artifact_path": "models/artifacts/text_depression_classifier/text_model.pkl",
            "tfidf_path": "models/artifacts/text_depression_classifier/text_tfidf.pkl",
            "metrics_path": "models/artifacts/text_depression_classifier/metrics.json",
            "fallback_id": None,
            "enabled": True,
        },
        "physiological_numpy_mlp": {
            "model_id": "physiological_risk_model",
            "name": "Physiological Model (NumPy MLP)",
            "version": "v1.1-physio-optimization",
            "status": "production",
            "type": "mlp",
            "metrics": {
                "f1_score": 0.7243,
                "precision": 0.0,
                "recall": 0.0,
                "accuracy": 0.0,
                "roc_auc": 0.0,
            },
            "artifact_path": "models/artifacts/physiological/model.json",
            "scaler_path": "models/artifacts/physiological/scaler.json",
            "feature_names_path": "models/artifacts/physiological/feature_names.json",
            "metrics_path": "models/artifacts/physiological/metrics.json",
            "fallback_id": "heuristic_rule",
            "enabled": True,
        },
    },
    "fusion_config": {
        "weights": {
            "structured": 0.55,
            "text": 0.30,
            "physiological": 0.15,
        },
        "scheme": "lightweight_probability_fusion",
        "version": "v1.1-physio-optimization",
    },
    "validation": {
        "all_models_exist": False,
        "all_metrics_exist": False,
        "validation_timestamp": None,
    },
}


def load_actual_metrics(metrics_path: Path) -> dict:
    """Load actual metrics from metrics.json file."""
    try:
        with open(metrics_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.warning("Could not load metrics from %s: %s", metrics_path, exc)
        return {}


def validate_model_files(baseline: dict) -> dict:
    """Validate that all model files exist and are readable."""
    validation = {
        "all_models_exist": True,
        "all_metrics_exist": True,
        "missing_files": [],
        "validation_timestamp": datetime.now(timezone.utc).isoformat(),
    }

    project_root = Path(__file__).resolve().parents[1]

    for model_name, model_config in baseline["models"].items():
        artifact_path = project_root / model_config["artifact_path"]
        if not artifact_path.exists():
            validation["missing_files"].append(str(artifact_path))
            validation["all_models_exist"] = False
            logger.error("Missing model file: %s", artifact_path)
        else:
            logger.info("Verified model file: %s (%d bytes)", artifact_path, artifact_path.stat().st_size)

        metrics_path = project_root / model_config["metrics_path"]
        if not metrics_path.exists():
            validation["missing_files"].append(str(metrics_path))
            validation["all_metrics_exist"] = False
            logger.error("Missing metrics file: %s", metrics_path)
        else:
            logger.info("Verified metrics file: %s", metrics_path)
            # Load actual metrics
            actual_metrics = load_actual_metrics(metrics_path)
            if actual_metrics:
                for key in ["f1_score", "precision", "recall", "accuracy", "roc_auc"]:
                    if key in actual_metrics:
                        model_config["metrics"][key] = actual_metrics[key]

    return validation


def save_baseline(baseline: dict) -> Path:
    """Save baseline to JSON file."""
    baselines_dir = Path("models/baselines")
    baselines_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"baseline_{BASELINE_VERSION}_{timestamp}.json"
    filepath = baselines_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(baseline, f, indent=2, ensure_ascii=False)

    logger.info("Baseline saved to: %s", filepath)
    return filepath


def main() -> int:
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("Baseline Freeze - %s", ITERATION_NAME)
    logger.info("=" * 60)

    # Create baseline copy
    baseline = json.loads(json.dumps(CURRENT_BASELINE))

    # Validate model files
    logger.info("Validating model files...")
    validation = validate_model_files(baseline)
    baseline["validation"] = validation

    if not validation["all_models_exist"]:
        logger.error("Some model files are missing. Baseline may be incomplete.")

    # Save baseline
    filepath = save_baseline(baseline)

    # Print summary
    logger.info("-" * 60)
    logger.info("Baseline Summary:")
    logger.info("  Version: %s", baseline["baseline_version"])
    logger.info("  Iteration: %s", baseline["iteration"])
    logger.info("  Frozen at: %s", baseline["frozen_at"])
    logger.info("  Models:")
    for model_name, model_config in baseline["models"].items():
        logger.info(
            "    %s: F1=%.4f, status=%s",
            model_name,
            model_config["metrics"]["f1_score"],
            model_config["status"],
        )
    logger.info("  Fusion weights: %s", baseline["fusion_config"]["weights"])
    logger.info("  Validation: models_exist=%s, metrics_exist=%s",
                validation["all_models_exist"],
                validation["all_metrics_exist"])
    logger.info("-" * 60)
    logger.info("Baseline file: %s", filepath)

    return 0 if validation["all_models_exist"] else 1


if __name__ == "__main__":
    sys.exit(main())
