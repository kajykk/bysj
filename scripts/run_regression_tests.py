"""
Regression Test Runner.

Runs all backend tests and generates a comprehensive report.

Usage:
    python scripts/run_regression_tests.py [--verbose]

Output:
    - regression_report.json: Test results summary
    - Console output with test status
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Run regression tests")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("regression_report.json"),
        help="Output report path",
    )
    return parser.parse_args()


def run_tests(verbose: bool = False) -> dict:
    """Run all backend tests.

    Args:
        verbose: Whether to show verbose output.

    Returns:
        Dictionary with test results.
    """
    test_dirs = [
        "backend/tests",
    ]

    results = {
        "total_tests": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "test_suites": {},
    }

    for test_dir in test_dirs:
        if not Path(test_dir).exists():
            logger.warning("Test directory not found: %s", test_dir)
            continue

        logger.info("Running tests in %s...", test_dir)

        cmd = [sys.executable, "-m", "pytest", test_dir, "-v" if verbose else "", "--tb=short"]
        cmd = [c for c in cmd if c]  # Remove empty strings

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )

            # Parse output
            output = result.stdout + result.stderr

            # Count tests
            if "passed" in output:
                # Extract counts from summary line
                lines = output.split("\n")
                for line in lines:
                    if "passed" in line and "failed" in line:
                        # Parse: "X passed, Y failed, Z skipped"
                        parts = line.split(",")
                        for part in parts:
                            if "passed" in part:
                                results["passed"] += int(part.split()[0])
                            elif "failed" in part:
                                results["failed"] += int(part.split()[0])
                            elif "skipped" in part:
                                results["skipped"] += int(part.split()[0])

            results["test_suites"][test_dir] = {
                "returncode": result.returncode,
                "output": output[-500:] if len(output) > 500 else output,  # Last 500 chars
            }

            if result.returncode == 0:
                logger.info("✅ Tests passed in %s", test_dir)
            else:
                logger.error("❌ Tests failed in %s", test_dir)

        except subprocess.TimeoutExpired:
            logger.error("⏱️ Tests timed out in %s", test_dir)
            results["test_suites"][test_dir] = {
                "returncode": -1,
                "output": "Timeout",
            }
        except Exception as exc:
            logger.error("❌ Error running tests in %s: %s", test_dir, exc)
            results["test_suites"][test_dir] = {
                "returncode": -1,
                "output": str(exc),
            }

    results["total_tests"] = results["passed"] + results["failed"] + results["skipped"]
    results["success_rate"] = (
        results["passed"] / results["total_tests"] if results["total_tests"] > 0 else 0.0
    )

    return results


def generate_report(results: dict, output_path: Path) -> None:
    """Generate regression report.

    Args:
        results: Test results.
        output_path: Output file path.
    """
    report = {
        "summary": {
            "total_tests": results["total_tests"],
            "passed": results["passed"],
            "failed": results["failed"],
            "skipped": results["skipped"],
            "success_rate": round(results["success_rate"] * 100, 2),
            "status": "PASS" if results["failed"] == 0 else "FAIL",
        },
        "test_suites": results["test_suites"],
        "timestamp": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info("Report saved to %s", output_path)


def main() -> None:
    """Main entry point."""
    args = parse_args()

    logger.info("=" * 50)
    logger.info("Regression Test Runner")
    logger.info("=" * 50)

    results = run_tests(verbose=args.verbose)

    logger.info("=" * 50)
    logger.info("Results Summary")
    logger.info("=" * 50)
    logger.info("Total tests: %d", results["total_tests"])
    logger.info("Passed: %d", results["passed"])
    logger.info("Failed: %d", results["failed"])
    logger.info("Skipped: %d", results["skipped"])
    logger.info("Success rate: %.2f%%", results["success_rate"] * 100)
    logger.info("Status: %s", "PASS" if results["failed"] == 0 else "FAIL")
    logger.info("=" * 50)

    generate_report(results, args.output)

    sys.exit(0 if results["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
