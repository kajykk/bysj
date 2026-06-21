#!/usr/bin/env python3
"""CI sklearn 和模型兼容性检查脚本。

在 CI 流水线中调用，用于验证：
1. sklearn 版本是否在支持范围内
2. 所有注册模型的环境兼容性
3. 模型文件是否存在且可用

退出码:
  0: 全部检查通过
  1: 存在不兼容或错误

用法:
  python scripts/check_compatibility.py [--json] [--models-dir PATH]
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[CI-COMPAT] %(message)s")
logger = logging.getLogger(__name__)


def check_sklearn_version_range() -> dict:
    import sklearn
    from packaging import version

    min_ver = version.parse("1.3.2")
    max_ver = version.parse("1.4.0")
    current = version.parse(sklearn.__version__)

    ok = min_ver <= current < max_ver
    return {
        "check": "sklearn_version",
        "current": sklearn.__version__,
        "required": ">=1.3.2,<1.4.0",
        "ok": ok,
        "detail": (
            f"sklearn {sklearn.__version__} within [{min_ver}, {max_ver})"
            if ok
            else f"sklearn {sklearn.__version__} OUTSIDE [{min_ver}, {max_ver})"
        ),
    }


def check_all_models(models_dir: Path | None = None) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    try:
        from app.core.model_compatibility import (
            MODEL_COMPATIBILITY_REGISTRY,
            check_all_model_compatibilities,
        )
    except ImportError as exc:
        return {
            "check": "model_compatibility",
            "ok": False,
            "detail": f"Failed to import model_compatibility: {exc}",
        }
    except Exception as exc:
        return {
            "check": "model_compatibility",
            "ok": False,
            "detail": f"Unexpected error loading model_compatibility: {exc}",
        }

    total = len(MODEL_COMPATIBILITY_REGISTRY)
    results = check_all_model_compatibilities()

    ok_count = sum(1 for ok, _ in results.values() if ok)
    failed = {mid: msg for mid, (ok, msg) in results.items() if not ok}

    return {
        "check": "model_compatibility",
        "total": total,
        "ok_count": ok_count,
        "failed_count": len(failed),
        "ok": len(failed) == 0,
        "detail": (
            f"{ok_count}/{total} models compatible"
            if len(failed) == 0
            else f"{ok_count}/{total} models compatible; failures: {failed}"
        ),
        "failures": failed,
    }


def check_model_files(models_dir: Path | None = None) -> dict:
    project_root = Path(__file__).resolve().parents[2]
    models_dir = models_dir or (project_root / "models")

    expected_files = [
        "structured/Logistic_Regression_quick.pkl",
        "text/improved_bilingual_model.pkl",
        "text/improved_bilingual_tfidf.pkl",
        "artifacts/physiological/model.json",
        "artifacts/physiological/scaler.json",
        "artifacts/physiological/feature_names.json",
    ]

    missing: list[str] = []
    found: list[str] = []

    for rel_path in expected_files:
        full_path = models_dir / rel_path
        if full_path.exists():
            found.append(rel_path)
        else:
            missing.append(rel_path)

    return {
        "check": "model_files",
        "total": len(expected_files),
        "found": len(found),
        "missing_count": len(missing),
        "ok": len(missing) == 0,
        "detail": (
            f"All {len(expected_files)} model files present"
            if len(missing) == 0
            else f"Missing {len(missing)}/{len(expected_files)}: {missing}"
        ),
        "missing": missing,
    }


def main() -> int:
    output_json = "--json" in sys.argv

    results: list[dict] = []

    # 1. sklearn version check
    try:
        results.append(check_sklearn_version_range())
    except ImportError as exc:
        results.append({"check": "sklearn_version", "ok": False, "detail": f"sklearn not installed: {exc}"})
    except Exception as exc:
        results.append({"check": "sklearn_version", "ok": False, "detail": str(exc)})

    # 2. model file existence check
    results.append(check_model_files())

    # 3. model compatibility registry check
    try:
        results.append(check_all_models())
    except Exception as exc:
        results.append({"check": "model_compatibility", "ok": False, "detail": str(exc)})

    all_ok = all(r["ok"] for r in results)

    if output_json:
        print(json.dumps({"ok": all_ok, "results": results}, indent=2, ensure_ascii=False))
    else:
        for r in results:
            status_icon = "✅" if r["ok"] else "❌"
            logger.info("%s %s: %s", status_icon, r["check"], r["detail"])
        logger.info("=" * 50)
        logger.info("Overall: %s", "ALL CHECKS PASSED" if all_ok else "SOME CHECKS FAILED")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
