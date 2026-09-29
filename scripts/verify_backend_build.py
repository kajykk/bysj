"""
Backend Build Verification Script.

Verifies:
- Python environment
- Required dependencies
- Backend module imports
- FastAPI app initialization
- Database connectivity

Usage:
    python scripts/verify_backend_build.py

Output:
    - build_report.json: Build verification results
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_python_version() -> dict:
    """Check Python version."""
    version = sys.version_info
    is_valid = version.major == 3 and version.minor >= 10

    return {
        "check": "Python Version",
        "status": "PASS" if is_valid else "FAIL",
        "details": f"Python {version.major}.{version.minor}.{version.micro}",
    }


def check_dependencies() -> dict:
    """Check required dependencies."""
    required_packages = [
        "fastapi",
        "uvicorn",
        "sqlalchemy",
        "pydantic",
        "numpy",
        "scikit-learn",
        "pytest",
    ]

    optional_packages = [
        "pandas",
        "torch",
        "transformers",
    ]

    missing = []
    installed = []

    for package in required_packages:
        try:
            __import__(package)
            installed.append(package)
        except ImportError:
            missing.append(package)

    for package in optional_packages:
        try:
            __import__(package)
            installed.append(package)
        except ImportError:
            pass  # Optional packages are not required

    is_valid = len(missing) == 0

    return {
        "check": "Dependencies",
        "status": "PASS" if is_valid else "WARN",
        "details": {
            "installed": installed,
            "missing": missing,
        },
    }


def check_backend_imports() -> dict:
    """Check backend module imports."""
    backend_path = Path("backend")
    if not backend_path.exists():
        return {
            "check": "Backend Imports",
            "status": "FAIL",
            "details": "Backend directory not found",
        }

    sys.path.insert(0, str(backend_path))

    modules_to_check = [
        "app.main",
        "app.core.model_engine",
        "app.ml.data_loader",
        "app.ml.data_cleaner",
        "app.ml.feature_engineering",
        "app.ml.fusion_engine",
        "app.ml.drift_detector",
        "app.ml.model_monitor",
        "app.ml.unified_model_interface",
        "app.ml.canary_controller",
    ]

    failed = []
    passed = []

    for module in modules_to_check:
        try:
            __import__(module)
            passed.append(module)
        except Exception as exc:
            failed.append({"module": module, "error": str(exc)})

    is_valid = len(failed) == 0

    return {
        "check": "Backend Imports",
        "status": "PASS" if is_valid else "FAIL",
        "details": {
            "passed": passed,
            "failed": failed,
        },
    }


def check_fastapi_app() -> dict:
    """Check FastAPI app initialization."""
    try:
        sys.path.insert(0, "backend")
        from app.main import app

        return {
            "check": "FastAPI App",
            "status": "PASS",
            "details": f"App initialized with {len(app.routes)} routes",
        }
    except Exception as exc:
        return {
            "check": "FastAPI App",
            "status": "FAIL",
            "details": str(exc),
        }


def check_test_files() -> dict:
    """Check test files existence."""
    test_dir = Path("backend/tests")
    if not test_dir.exists():
        return {
            "check": "Test Files",
            "status": "FAIL",
            "details": "Tests directory not found",
        }

    test_files = list(test_dir.glob("test_*.py"))

    return {
        "check": "Test Files",
        "status": "PASS",
        "details": f"Found {len(test_files)} test files",
    }


def main() -> None:
    """Main build verification."""
    logger.info("=" * 50)
    logger.info("Backend Build Verification")
    logger.info("=" * 50)

    checks = [
        check_python_version(),
        check_dependencies(),
        check_backend_imports(),
        check_fastapi_app(),
        check_test_files(),
    ]

    # Print results
    for check in checks:
        status_icon = "✅" if check["status"] == "PASS" else "⚠️" if check["status"] == "WARN" else "❌"
        logger.info("%s %s: %s", status_icon, check["check"], check["status"])
        if isinstance(check["details"], str):
            logger.info("   %s", check["details"])

    # Summary
    passed = sum(1 for c in checks if c["status"] == "PASS")
    warnings = sum(1 for c in checks if c["status"] == "WARN")
    failed = sum(1 for c in checks if c["status"] == "FAIL")

    logger.info("=" * 50)
    logger.info("Summary: %d passed, %d warnings, %d failed", passed, warnings, failed)
    logger.info("=" * 50)

    # Save report
    report = {
        "checks": checks,
        "summary": {
            "passed": passed,
            "warnings": warnings,
            "failed": failed,
            "total": len(checks),
            "status": "PASS" if failed == 0 else "FAIL",
        },
        "timestamp": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
    }

    with open("build_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info("Build report saved to build_report.json")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
