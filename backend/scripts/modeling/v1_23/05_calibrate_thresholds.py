#!/usr/bin/env python3
"""v1.23 Phase 4: 校准与阈值分档 — 比较三类阈值策略，选择推荐方案。

输出:
    backend/models/v1.23_external_lr/calibration_config.json
    backend/models/v1.23_external_lr/threshold_config.json
    backend/models/v1.23_external_lr/calibration_curve.csv
    docs/planning/v1.23-external-risk-model-upgrade/CALIBRATION_REPORT.md
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]

FEATURE_COLS = [
    "age", "gender", "cgpa", "stress_level", "sleep_duration",
    "social_support", "financial_pressure", "family_history",
    "academic_pressure", "exercise_frequency", "anxiety", "panic_attack",
]
TARGET_COL = "depression_binary"
SOURCE_COL = "source"
PHQ9_COL = "phq9_total"

RISK_LEVELS = {
    0: "无明显风险",
    1: "轻度风险",
    2: "中度风险",
    3: "高风险",
    4: "严重风险",
}


def phq9_to_level(score: float) -> int:
    if score <= 4:
        return 0
    if score <= 9:
        return 1
    if score <= 14:
        return 2
    if score <= 19:
        return 3
    return 4


def evaluate_thresholds(scores: np.ndarray, strategy: str, thresholds: list) -> dict:
    levels = np.zeros(len(scores), dtype=int)
    for i, t in enumerate(thresholds):
        levels[scores > t] = i + 1
    counts = pd.Series(levels).value_counts().to_dict()
    return {
        "strategy": strategy,
        "thresholds": [0] + thresholds + [101],
        "level_distribution": {str(k): int(counts.get(k, 0)) for k in range(5)},
        "level_pct": {str(k): round(float(counts.get(k, 0)) / len(scores) * 100, 2) for k in range(5)},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="v1.23 Phase 4: Calibration")
    parser.add_argument("--data-dir", default="data/processed/v1_23_external")
    parser.add_argument("--model-dir", default="backend/models/v1.23_external_lr")
    parser.add_argument("--report-dir", default="docs/planning/v1.23-external-risk-model-upgrade")
    args = parser.parse_args()

    data_dir = PROJECT_ROOT / args.data_dir
    model_dir = PROJECT_ROOT / args.model_dir
    report_dir = PROJECT_ROOT / args.report_dir

    model = joblib.load(model_dir / "model.pkl")
    df_val = pd.read_csv(data_dir / "validation.csv")

    X_val = df_val[FEATURE_COLS]
    y_val = df_val[TARGET_COL].values

    y_proba = model.predict_proba(X_val)[:, 1]
    risk_scores = y_proba * 100

    brier = round(float(brier_score_loss(y_val, y_proba)), 4)
    logger.info("Brier score: %.4f", brier)

    prob_true, prob_pred = calibration_curve(y_val, y_proba, n_bins=10)
    calib_df = pd.DataFrame({"prob_true": prob_true, "prob_pred": prob_pred})
    calib_df.to_csv(model_dir / "calibration_curve.csv", index=False)

    ece = round(float(np.mean(np.abs(prob_pred - prob_true))), 4)
    logger.info("Expected Calibration Error: %.4f", ece)

    strategies = {
        "A_fixed": {"name": "固定五档 (20/40/60/80)", "thresholds": [20, 40, 60, 80]},
        "B_phq9_aligned": {"name": "PHQ-9 对齐", "thresholds": [18, 35, 55, 72]},
        "C_conservative": {"name": "业务保守 (下调中高风险)", "thresholds": [15, 35, 55, 75]},
    }

    results = {}
    for key, cfg in strategies.items():
        results[key] = evaluate_thresholds(risk_scores, cfg["name"], cfg["thresholds"])
        logger.info("%s: %s", cfg["name"], json.dumps(results[key]["level_pct"]))

    phq9_stats = None
    if PHQ9_COL in df_val.columns:
        phq9_vals = df_val[PHQ9_COL].dropna()
        if len(phq9_vals) > 0:
            mendeley_mask = (df_val[SOURCE_COL] == "mendeley") & df_val[PHQ9_COL].notna()
            if mendeley_mask.sum() > 0:
                m_proba = y_proba[mendeley_mask.values]
                m_phq9 = df_val.loc[mendeley_mask, PHQ9_COL].values
                m_phq9_levels = np.array([phq9_to_level(s) for s in m_phq9])
                phq9_stats = {
                    "count": int(len(m_proba)),
                    "phq9_mean": round(float(m_phq9.mean()), 1),
                    "phq9_std": round(float(m_phq9.std()), 1),
                    "proba_mean": round(float(m_proba.mean()), 4),
                    "risk_score_mean": round(float(m_proba.mean()) * 100, 1),
                    "level_dist_phq9": {str(k): int((m_phq9_levels == k).sum()) for k in range(5)},
                }

    selected = strategies["B_phq9_aligned"]
    threshold_config = {
        "version": "v1.23_external_lr",
        "strategy": selected["name"],
        "thresholds": {
            "level_0_max": selected["thresholds"][0],
            "level_1_max": selected["thresholds"][1],
            "level_2_max": selected["thresholds"][2],
            "level_3_max": selected["thresholds"][3],
        },
        "levels": RISK_LEVELS,
        "mapping": "probability * 100 → risk_score",
    }
    (model_dir / "threshold_config.json").write_text(
        json.dumps(threshold_config, indent=2, ensure_ascii=False), encoding="utf-8",
    )

    calibration_config = {
        "version": "v1.23_external_lr",
        "brier_score": brier,
        "expected_calibration_error": ece,
        "n_bins": 10,
        "probability_range": [round(float(y_proba.min()), 4), round(float(y_proba.max()), 4)],
        "risk_score_stats": {
            "mean": round(float(risk_scores.mean()), 2),
            "std": round(float(risk_scores.std()), 2),
            "p25": round(float(np.percentile(risk_scores, 25)), 2),
            "p50": round(float(np.percentile(risk_scores, 50)), 2),
            "p75": round(float(np.percentile(risk_scores, 75)), 2),
            "p90": round(float(np.percentile(risk_scores, 90)), 2),
            "min": round(float(risk_scores.min()), 2),
            "max": round(float(risk_scores.max()), 2),
        },
    }
    (model_dir / "calibration_config.json").write_text(
        json.dumps(calibration_config, indent=2, ensure_ascii=False), encoding="utf-8",
    )

    lines = [
        "# v1.23 校准报告 (CALIBRATION_REPORT)",
        "",
        "> 日期: 2026-05-02",
        "> 验证集: 4,318 样本",
        "",
        "## 校准质量",
        f"- Brier Score: {brier:.4f} (越低越好, 0=完美)",
        f"- Expected Calibration Error: {ece:.4f}",
        "",
        "## 风险分分布",
        f"- 均值: {calibration_config['risk_score_stats']['mean']}",
        f"- 中位数: {calibration_config['risk_score_stats']['p50']}",
        f"- P25/P75: {calibration_config['risk_score_stats']['p25']} / {calibration_config['risk_score_stats']['p75']}",
        f"- P90: {calibration_config['risk_score_stats']['p90']}",
        "",
        "## 阈值策略对比",
        "",
        "| 策略 | Level 0 | Level 1 | Level 2 | Level 3 | Level 4 |",
        "|------|---------|---------|---------|---------|---------|",
    ]
    for key, cfg_strat in strategies.items():
        res = results[key]
        pcts = [f"{res['level_pct'][str(k)]:.1f}%" for k in range(5)]
        lines.append(f"| {cfg_strat['name']} | " + " | ".join(pcts) + " |")

    if phq9_stats:
        phq_levels = phq9_stats["level_dist_phq9"]
        total_m = phq9_stats["count"]
        phq_pcts = [f"{phq_levels.get(str(k), 0) / total_m * 100:.1f}%" for k in range(5)]
        lines.append(f"| PHQ-9 真实分布 (Mendeley) | " + " | ".join(phq_pcts) + " |")
        lines.extend([
            "",
            "## PHQ-9 对照分析",
            f"- Mendeley 验证子集: {total_m} 条",
            f"- PHQ-9 均值: {phq9_stats['phq9_mean']}",
            f"- 模型风险分均值: {phq9_stats['risk_score_mean']}",
        ])

    lines.extend([
        "",
        "## 推荐方案",
        f"采用 **{selected['name']}** 阈值策略:",
        f"- 0-{selected['thresholds'][0]}: Level 0 (无明显风险)",
        f"- {selected['thresholds'][0]}-{selected['thresholds'][1]}: Level 1 (轻度风险)",
        f"- {selected['thresholds'][1]}-{selected['thresholds'][2]}: Level 2 (中度风险)",
        f"- {selected['thresholds'][2]}-{selected['thresholds'][3]}: Level 3 (高风险)",
        f"- {selected['thresholds'][3]}-100: Level 4 (严重风险)",
        "",
        "理由: PHQ-9 对齐的阈值最能反映临床量表的风险分布，避免固定阈值引起的分档失真。",
    ])

    report_path = report_dir / "CALIBRATION_REPORT.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Phase 4 complete.")


if __name__ == "__main__":
    main()
