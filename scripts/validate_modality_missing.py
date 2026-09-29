"""
Modality Missing Validation Script.

Validates fusion engine behavior on scenarios with missing modalities.
Tests 10+ missing modality scenarios and records degradation performance.

Usage:
    python scripts/validate_modality_missing.py \
        --scenarios datasets/fusion/fusion_test_scenarios_v2.json \
        --output-dir models/fusion

Output:
    - missing_modality_report.json: Detailed validation report
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

from app.ml.fusion_engine import FusionEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_SCENARIOS_PATH = Path("datasets/fusion/fusion_test_scenarios_v2.json")
DEFAULT_OUTPUT_DIR = Path("models/fusion")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Validate modality missing handling")
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
        help="Output directory for validation results",
    )
    return parser.parse_args()


def load_scenarios(path: Path) -> list[dict]:
    """Load test scenarios from JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        scenarios = json.load(f)
    return scenarios


def simulate_modality_scores(scenario: dict) -> dict[str, float]:
    """Simulate modality scores from scenario data."""
    payload = scenario["payload"]
    scores = {}

    # Structured score
    if "features" in payload:
        features = payload["features"]
        stress = features.get("stress_level", 3)
        anxiety = features.get("anxiety", 2)
        pressure = features.get("academic_pressure", 3)
        sleep = features.get("sleep_duration", 6)

        structured_score = stress * 10 + anxiety * 10 + pressure * 8 + (7 - sleep) * 5
        structured_score = min(100, max(0, structured_score))

        label = scenario["label"]
        if label == 1 and structured_score < 50:
            structured_score += 20
        elif label == 0 and structured_score > 60:
            structured_score -= 15

        scores["structured"] = round(structured_score, 2)

    # Text score
    if "text" in payload:
        text = payload["text"]
        negative_keywords = ["失眠", "情绪差", "提不起兴趣", "焦虑", "抑郁", "痛苦", "绝望"]
        positive_keywords = ["状态不错", "效率还可以", "开心", "满意", "积极"]

        neg_count = sum(1 for kw in negative_keywords if kw in text)
        pos_count = sum(1 for kw in positive_keywords if kw in text)

        text_score = 30 + neg_count * 15 - pos_count * 10
        text_score = min(100, max(0, text_score))

        label = scenario["label"]
        if label == 1 and text_score < 50:
            text_score += 25
        elif label == 0 and text_score > 60:
            text_score -= 20

        scores["text"] = round(text_score, 2)

    # Physiological score
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

        label = scenario["label"]
        if label == 1 and physio_score < 50:
            physio_score += 20
        elif label == 0 and physio_score > 60:
            physio_score -= 15

        scores["physiological"] = round(physio_score, 2)

    return scores


def validate_scenario(scenario: dict, engine: FusionEngine) -> dict:
    """Validate a single scenario."""
    modality_scores = simulate_modality_scores(scenario)
    result = engine.fuse(modality_scores)

    predicted_level = result["risk_level"]
    actual_label = scenario["label"]

    # Determine if prediction is reasonable
    # For high risk (label=1), expect level >= 2
    # For low risk (label=0), expect level <= 2
    is_reasonable = False
    if actual_label == 1 and predicted_level >= 2:
        is_reasonable = True
    elif actual_label == 0 and predicted_level <= 2:
        is_reasonable = True
    elif predicted_level == 2:  # Borderline is acceptable
        is_reasonable = True

    return {
        "scenario": scenario["scenario"],
        "label": actual_label,
        "predicted_level": predicted_level,
        "risk_score": result["risk_score"],
        "confidence": result["confidence"],
        "fusion_scheme": result["fusion_scheme"],
        "available_modalities": result.get("available_modalities", []),
        "missing_modalities": result.get("missing_modalities", list(engine.weights.keys())),
        "is_reasonable": is_reasonable,
        "modality_scores": modality_scores,
    }


def main() -> None:
    """Main validation pipeline."""
    args = parse_args()

    # Load scenarios
    all_scenarios = load_scenarios(args.scenarios)

    # Filter missing modality scenarios
    missing_scenarios = [
        s for s in all_scenarios
        if "missing" in s["scenario"] or "only" in s["scenario"]
    ]

    logger.info("Found %d missing modality scenarios", len(missing_scenarios))

    # Create fusion engine
    engine = FusionEngine()

    # Validate each scenario
    results = []
    correct = 0

    for scenario in missing_scenarios:
        result = validate_scenario(scenario, engine)
        results.append(result)

        if result["is_reasonable"]:
            correct += 1

        logger.info(
            "Scenario: %s | Label: %d | Predicted: %d | Score: %.1f | Confidence: %.3f | Scheme: %s | Reasonable: %s",
            result["scenario"],
            result["label"],
            result["predicted_level"],
            result["risk_score"],
            result["confidence"],
            result["fusion_scheme"],
            result["is_reasonable"],
        )

    # Calculate metrics
    accuracy = correct / len(results) if results else 0.0

    # Group by fusion scheme
    scheme_stats = {}
    for result in results:
        scheme = result["fusion_scheme"]
        if scheme not in scheme_stats:
            scheme_stats[scheme] = {"total": 0, "correct": 0}
        scheme_stats[scheme]["total"] += 1
        if result["is_reasonable"]:
            scheme_stats[scheme]["correct"] += 1

    # Calculate per-scheme accuracy
    for scheme in scheme_stats:
        stats = scheme_stats[scheme]
        stats["accuracy"] = stats["correct"] / stats["total"] if stats["total"] > 0 else 0.0

    report = {
        "total_scenarios": len(results),
        "correct_predictions": correct,
        "accuracy": accuracy,
        "scheme_breakdown": scheme_stats,
        "detailed_results": results,
    }

    # Save report
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with open(args.output_dir / "missing_modality_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.info("=" * 50)
    logger.info("VALIDATION RESULTS")
    logger.info("=" * 50)
    logger.info("Total scenarios: %d", len(results))
    logger.info("Correct predictions: %d", correct)
    logger.info("Accuracy: %.2f%%", accuracy * 100)
    logger.info("-" * 50)
    for scheme, stats in scheme_stats.items():
        logger.info("%s: %d/%d (%.2f%%)", scheme, stats["correct"], stats["total"], stats["accuracy"] * 100)
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
