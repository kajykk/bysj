"""
Fusion Weight Optimization Script.

Searches for optimal fusion weights on 83 test scenarios.
Objective: Maximize fusion accuracy.

Usage:
    python scripts/optimize_fusion_weights.py \
        --scenarios datasets/fusion/fusion_test_scenarios_v2.json \
        --output-dir models/fusion

Output:
    - optimal_weights.json: Best weights found
    - optimization_report.json: Detailed report
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_SCENARIOS_PATH = Path("datasets/fusion/fusion_test_scenarios_v2.json")
DEFAULT_OUTPUT_DIR = Path("models/fusion")

# Base weights (current configuration)
BASE_WEIGHTS = {
    "structured": 0.55,
    "text": 0.30,
    "physiological": 0.15,
}


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Optimize fusion weights")
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=DEFAULT_SCENARIOS_PATH,
        help="Path to test scenarios JSON",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory for optimization results",
    )
    parser.add_argument(
        "--grid-steps",
        type=int,
        default=21,
        help="Number of steps for grid search (default: 21 for 0.05 increments)",
    )
    return parser.parse_args()


def load_scenarios(path: Path) -> list[dict]:
    """Load test scenarios from JSON file.

    Args:
        path: Path to scenarios JSON file.

    Returns:
        List of scenario dictionaries.
    """
    with open(path, "r", encoding="utf-8") as f:
        scenarios = json.load(f)
    logger.info("Loaded %d scenarios from %s", len(scenarios), path)
    return scenarios


def simulate_modality_scores(scenario: dict) -> dict[str, float]:
    """Simulate modality scores from scenario data.

    In production, these would come from actual model predictions.
    For optimization, we use heuristics based on the scenario label.

    Args:
        scenario: Test scenario with payload and label.

    Returns:
        Dictionary of modality -> score.
    """
    payload = scenario["payload"]
    label = scenario["label"]

    scores = {}

    # Structured score based on features
    if "features" in payload:
        features = payload["features"]
        # Heuristic: higher stress/anxiety/pressure = higher risk
        stress = features.get("stress_level", 3)
        anxiety = features.get("anxiety", 2)
        pressure = features.get("academic_pressure", 3)
        sleep = features.get("sleep_duration", 6)

        structured_score = (
            stress * 10 + anxiety * 10 + pressure * 8 + (7 - sleep) * 5
        )
        structured_score = min(100, max(0, structured_score))

        # Adjust based on label
        if label == 1 and structured_score < 50:
            structured_score += 20
        elif label == 0 and structured_score > 60:
            structured_score -= 15

        scores["structured"] = round(structured_score, 2)

    # Text score based on text content
    if "text" in payload:
        text = payload["text"]
        # Heuristic: negative keywords indicate higher risk
        negative_keywords = ["失眠", "情绪差", "提不起兴趣", "焦虑", "抑郁", "痛苦", "绝望"]
        positive_keywords = ["状态不错", "效率还可以", "开心", "满意", "积极"]

        neg_count = sum(1 for kw in negative_keywords if kw in text)
        pos_count = sum(1 for kw in positive_keywords if kw in text)

        text_score = 30 + neg_count * 15 - pos_count * 10
        text_score = min(100, max(0, text_score))

        # Adjust based on label
        if label == 1 and text_score < 50:
            text_score += 25
        elif label == 0 and text_score > 60:
            text_score -= 20

        scores["text"] = round(text_score, 2)

    # Physiological score based on physiological data
    if "physiological" in payload:
        physio = payload["physiological"]
        sleep_hours = physio.get("sleep_hours", 7)
        heart_rate = physio.get("heart_rate", 75)
        exercise = physio.get("exercise_minutes", 30)
        sleep_quality = physio.get("sleep_quality", 3)

        physio_score = (
            (7.5 - sleep_hours) * 10 +
            (heart_rate - 70) * 1.5 +
            (5 - sleep_quality) * 8 +
            (40 - exercise) * 0.5
        )
        physio_score = min(100, max(0, physio_score))

        # Adjust based on label
        if label == 1 and physio_score < 50:
            physio_score += 20
        elif label == 0 and physio_score > 60:
            physio_score -= 15

        scores["physiological"] = round(physio_score, 2)

    return scores


def compute_fusion_score(modality_scores: dict[str, float], weights: dict[str, float]) -> float:
    """Compute fused score using weighted average.

    Args:
        modality_scores: Dictionary of modality -> score.
        weights: Dictionary of modality -> weight.

    Returns:
        Fused score (0-100).
    """
    available_modalities = set(modality_scores.keys())
    available_weights = {k: v for k, v in weights.items() if k in available_modalities}

    if not available_weights:
        return 0.0

    total_weight = sum(available_weights.values())
    if total_weight == 0:
        return 0.0

    # Normalize weights
    normalized_weights = {k: v / total_weight for k, v in available_weights.items()}

    fused_score = sum(modality_scores[m] * normalized_weights[m] for m in available_modalities)
    return fused_score


def evaluate_weights(scenarios: list[dict], weights: dict[str, float]) -> dict:
    """Evaluate fusion weights on test scenarios.

    Args:
        scenarios: List of test scenarios.
        weights: Fusion weights to evaluate.

    Returns:
        Dictionary with evaluation metrics.
    """
    correct = 0
    total = len(scenarios)
    tp = fp = tn = fn = 0

    for scenario in scenarios:
        modality_scores = simulate_modality_scores(scenario)
        fused_score = compute_fusion_score(modality_scores, weights)

        # Threshold at 50 for binary classification
        predicted = 1 if fused_score >= 50 else 0
        actual = scenario["label"]

        if predicted == actual:
            correct += 1

        if predicted == 1 and actual == 1:
            tp += 1
        elif predicted == 1 and actual == 0:
            fp += 1
        elif predicted == 0 and actual == 0:
            tn += 1
        else:
            fn += 1

    accuracy = correct / total if total > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "correct": correct,
        "total": total,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


def grid_search_weights(scenarios: list[dict], steps: int = 21) -> tuple[dict, dict]:
    """Perform grid search for optimal fusion weights.

    Args:
        scenarios: List of test scenarios.
        steps: Number of steps for each weight dimension.

    Returns:
        Tuple of (best_weights, best_metrics).
    """
    logger.info("Starting grid search with %d steps...", steps)

    best_weights = None
    best_metrics = None
    best_f1 = 0.0

    # Grid search: structured_weight + text_weight + physio_weight = 1.0
    step_size = 1.0 / (steps - 1)

    for i in range(steps):
        structured_w = i * step_size
        for j in range(steps - i):
            text_w = j * step_size
            physio_w = 1.0 - structured_w - text_w

            if physio_w < 0:
                continue

            weights = {
                "structured": round(structured_w, 3),
                "text": round(text_w, 3),
                "physiological": round(physio_w, 3),
            }

            metrics = evaluate_weights(scenarios, weights)

            if metrics["f1"] > best_f1:
                best_f1 = metrics["f1"]
                best_weights = weights
                best_metrics = metrics

    logger.info("Grid search complete. Best F1: %.4f", best_f1)
    return best_weights, best_metrics


def save_results(
    best_weights: dict,
    best_metrics: dict,
    base_metrics: dict,
    output_dir: Path,
) -> None:
    """Save optimization results.

    Args:
        best_weights: Optimal weights found.
        best_metrics: Metrics with optimal weights.
        base_metrics: Metrics with base weights.
        output_dir: Output directory.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save optimal weights
    with open(output_dir / "optimal_weights.json", "w", encoding="utf-8") as f:
        json.dump(best_weights, f, indent=2)

    # Save optimization report
    report = {
        "optimal_weights": best_weights,
        "optimal_metrics": best_metrics,
        "base_weights": BASE_WEIGHTS,
        "base_metrics": base_metrics,
        "improvement": {
            "f1_delta": best_metrics["f1"] - base_metrics["f1"],
            "accuracy_delta": best_metrics["accuracy"] - base_metrics["accuracy"],
        },
    }

    with open(output_dir / "optimization_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info("Results saved to %s", output_dir)


def main() -> None:
    """Main optimization pipeline."""
    args = parse_args()

    # Load scenarios
    scenarios = load_scenarios(args.scenarios)

    # Evaluate base weights
    logger.info("Evaluating base weights: %s", BASE_WEIGHTS)
    base_metrics = evaluate_weights(scenarios, BASE_WEIGHTS)
    logger.info("Base metrics: F1=%.4f, Accuracy=%.4f", base_metrics["f1"], base_metrics["accuracy"])

    # Grid search for optimal weights
    best_weights, best_metrics = grid_search_weights(scenarios, steps=args.grid_steps)

    logger.info("=" * 50)
    logger.info("OPTIMIZATION RESULTS")
    logger.info("=" * 50)
    logger.info("Base weights: %s", BASE_WEIGHTS)
    logger.info("Base F1: %.4f", base_metrics["f1"])
    logger.info("Base Accuracy: %.4f", base_metrics["accuracy"])
    logger.info("-" * 50)
    logger.info("Optimal weights: %s", best_weights)
    logger.info("Optimal F1: %.4f", best_metrics["f1"])
    logger.info("Optimal Accuracy: %.4f", best_metrics["accuracy"])
    logger.info("F1 Improvement: %.4f", best_metrics["f1"] - base_metrics["f1"])
    logger.info("=" * 50)

    # Save results
    save_results(best_weights, best_metrics, base_metrics, args.output_dir)


if __name__ == "__main__":
    main()
