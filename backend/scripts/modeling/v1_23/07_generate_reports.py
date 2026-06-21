#!/usr/bin/env python3
"""v1.23 Phase 辅助: 报告聚合与交付完整性校验。

汇总所有 Phase 产出，输出最终完整性报告。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
MODEL_DIR = PROJECT_ROOT / "backend/models/v1.23_external_lr"
DATA_DIR = PROJECT_ROOT / "data/processed/v1_23_external"
SCRIPT_DIR = PROJECT_ROOT / "backend/scripts/modeling/v1_23"
REPORT_DIR = PROJECT_ROOT / "docs/planning/v1.23-external-risk-model-upgrade"

EXPECTED_SCRIPTS = [
    "01_prepare_external_dataset.py",
    "02_train_external_lr.py",
    "03_evaluate_external_lr.py",
    "04_compare_with_existing_models.py",
    "05_calibrate_thresholds.py",
    "05_external_validation.py",
    "06_export_model_artifacts.py",
    "07_generate_reports.py",
]

EXPECTED_MODELS = [
    "model.pkl",
    "preprocessor.pkl",
    "feature_schema.json",
    "threshold_config.json",
    "calibration_config.json",
    "metrics.json",
    "metrics_train.json",
    "metrics_eval.json",
    "comparison_metrics.json",
    "confusion_matrix.json",
    "external_validation_metrics.json",
    "feature_coefficients.csv",
    "roc_curve.csv",
    "pr_curve.csv",
    "calibration_curve.csv",
    "score_distribution_histogram.csv",
    "model_delta_samples.csv",
    "model_card.md",
]

EXPECTED_DATA = [
    "train.csv",
    "validation.csv",
    "test.csv",
    "external_mmpsy.csv",
    "split_metadata.json",
]

EXPECTED_REPORTS = [
    "V1.23_IMPLEMENTATION_PLAN.md",
    "DATA_ASSET_CHECKLIST.md",
    "DATA_PREPARATION_REPORT.md",
    "TRAINING_REPORT.md",
    "MODEL_EVALUATION_REPORT.md",
    "CALIBRATION_REPORT.md",
    "EXTERNAL_VALIDATION_REPORT.md",
    "MODEL_COMPARISON_REPORT.md",
    "DEPLOYMENT_DECISION_REPORT.md",
    "DELIVERY_REPORT.md",
]


def check_category(name: str, base: Path, expected: list[str]) -> dict:
    present = []
    missing = []
    for f in expected:
        if (base / f).exists():
            present.append(f)
        else:
            missing.append(f)
    logger.info(
        "%s: %d/%d present%s",
        name, len(present), len(expected),
        f" (missing: {missing})" if missing else "",
    )
    return {
        "category": name,
        "directory": str(base),
        "expected": len(expected),
        "present": len(present),
        "missing": missing,
        "present_files": present,
    }


def main() -> None:
    results = {
        "check_date": "2026-05-02",
        "version": "v1.23-external-risk-model-upgrade",
    }

    script_check = check_category("scripts", SCRIPT_DIR, EXPECTED_SCRIPTS)
    model_check = check_category("model_artifacts", MODEL_DIR, EXPECTED_MODELS)
    data_check = check_category("processed_data", DATA_DIR, EXPECTED_DATA)
    report_check = check_category("reports", REPORT_DIR, EXPECTED_REPORTS)

    results["categories"] = [script_check, model_check, data_check, report_check]

    all_missing = (
        [(SCRIPT_DIR / m, m) for m in script_check["missing"]]
        + [(MODEL_DIR / m, m) for m in model_check["missing"]]
        + [(DATA_DIR / m, m) for m in data_check["missing"]]
        + [(REPORT_DIR / m, m) for m in report_check["missing"]]
    )

    total_expected = sum(c["expected"] for c in results["categories"])
    total_present = sum(c["present"] for c in results["categories"])

    results["summary"] = {
        "total_expected": total_expected,
        "total_present": total_present,
        "total_missing": total_expected - total_present,
        "integrity_pct": round(total_present / total_expected * 100, 1),
        "all_complete": total_present == total_expected,
    }

    logger.info(
        "Integrity: %d/%d (%.1f%%) — %s",
        total_present, total_expected,
        total_present / total_expected * 100,
        "ALL COMPLETE ✅" if total_present == total_expected else "INCOMPLETE ❌",
    )

    if all_missing:
        logger.warning("Missing files:")
        for path, name in all_missing:
            logger.warning("  - %s", path)

    integrity_path = REPORT_DIR / "DELIVERY_INTEGRITY_CHECK.json"
    integrity_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    logger.info("Integrity report saved to %s", integrity_path)

    # Read key metrics for summary
    metrics = {}
    if (MODEL_DIR / "metrics.json").exists():
        mdata = json.loads((MODEL_DIR / "metrics.json").read_text(encoding="utf-8"))
        eval_m = mdata.get("eval_metrics", {})
        ext_m = mdata.get("external_validation", {})
        comp_m = mdata.get("comparison", {})
        metrics["test_auc"] = eval_m.get("roc_auc")
        metrics["test_f1"] = eval_m.get("f1")
        metrics["test_recall"] = eval_m.get("recall")
        metrics["test_specificity"] = eval_m.get("specificity")
        metrics["phq9_pearson_r"] = ext_m.get("pearson_r")
        metrics["phq9_binary_auc"] = ext_m.get("phq9_binary_auc")
        if isinstance(comp_m, dict) and "delta_v123_vs_v120" in comp_m:
            metrics["delta_v120_mean_abs"] = comp_m["delta_v123_vs_v120"]["mean_abs_delta"]

    summary_lines = [
        "# v1.23 报告聚合摘要 (Report Aggregation Summary)",
        "",
        f"> 校验日期: 2026-05-02",
        f"> 完整性: {total_present}/{total_expected} ({results['summary']['integrity_pct']:.1f}%)",
        "",
        "## 交付物统计",
        f"| 类别 | 预期 | 实际 | 完整性 |",
        f"|------|------|------|--------|",
    ]
    for cat in results["categories"]:
        pct = f"{cat['present']/cat['expected']*100:.0f}%"
        status = "✅" if not cat["missing"] else "⚠"
        summary_lines.append(f"| {cat['category']} {status} | {cat['expected']} | {cat['present']} | {pct} |")

    summary_lines.extend([
        "",
        "## 关键指标摘要",
        f"- 测试集 AUC: {metrics.get('test_auc', 'N/A')}",
        f"- 测试集 F1: {metrics.get('test_f1', 'N/A')}",
        f"- 测试集 Recall: {metrics.get('test_recall', 'N/A')}",
        f"- 测试集 Specificity: {metrics.get('test_specificity', 'N/A')}",
        f"- PHQ-9 Pearson r: {metrics.get('phq9_pearson_r', 'N/A')}",
        f"- PHQ-9 Binary AUC: {metrics.get('phq9_binary_auc', 'N/A')}",
        f"- vs v1.20 Mean Abs Delta: {metrics.get('delta_v120_mean_abs', 'N/A')}",
        "",
        "## 缺失文件",
    ])
    if all_missing:
        for path, name in all_missing:
            summary_lines.append(f"- `{name}` ({path})")
    else:
        summary_lines.append("- 无缺失 ✅")

    summary_lines.extend([
        "",
        "## 结论",
        f"{'✅ 全部交付物完整 — 方案完全执行。' if results['summary']['all_complete'] else '❌ 仍有缺失文件需补充。'}",
    ])

    report_path = REPORT_DIR / "REPORT_AGGREGATION_SUMMARY.md"
    report_path.write_text("\n".join(summary_lines), encoding="utf-8")
    logger.info("Summary report saved to %s", report_path)


if __name__ == "__main__":
    main()
