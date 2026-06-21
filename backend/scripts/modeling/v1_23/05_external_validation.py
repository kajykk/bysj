#!/usr/bin/env python3
"""v1.23 Phase 5: 外部验证 — 使用 Mendeley PHQ-9 做临床标签验证。

mmpsy 数据仅有量表分数无结构化特征，无法直接运行模型。

输出:
    backend/models/v1.23_external_lr/external_validation_metrics.json
    docs/planning/v1.23-external-risk-model-upgrade/EXTERNAL_VALIDATION_REPORT.md
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr
from sklearn.metrics import roc_auc_score

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


def phq9_binary(score: float) -> int:
    return 1 if score >= 10 else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="v1.23 Phase 5: External Validation")
    parser.add_argument("--data-dir", default="data/processed/v1_23_external")
    parser.add_argument("--model-dir", default="backend/models/v1.23_external_lr")
    parser.add_argument("--report-dir", default="docs/planning/v1.23-external-risk-model-upgrade")
    parser.add_argument("--mmpsy-path", default="data/external/mmpsy_scores.csv")
    args = parser.parse_args()

    data_dir = PROJECT_ROOT / args.data_dir
    model_dir = PROJECT_ROOT / args.model_dir
    report_dir = PROJECT_ROOT / args.report_dir

    model = joblib.load(model_dir / "model.pkl")
    df_test = pd.read_csv(data_dir / "test.csv")

    mendeley_mask = (df_test[SOURCE_COL] == "mendeley") & df_test[PHQ9_COL].notna()
    mendeley_df = df_test[mendeley_mask]
    if len(mendeley_df) == 0:
        logger.warning("No Mendeley PHQ-9 samples in test set")
        mendeley_df = df_test[df_test[PHQ9_COL].notna()]

    m_X = mendeley_df[FEATURE_COLS]
    m_phq9 = mendeley_df[PHQ9_COL].values

    m_proba = model.predict_proba(m_X)[:, 1]
    m_pred = (m_proba >= 0.5).astype(int)
    m_phq9_bin = np.array([phq9_binary(s) for s in m_phq9])

    m_phq9_auc = round(float(roc_auc_score(m_phq9_bin, m_proba)), 4) if len(np.unique(m_phq9_bin)) > 1 else None
    pearson_r, pearson_p = pearsonr(m_proba, m_phq9)
    spearman_rho, spearman_p = spearmanr(m_proba, m_phq9)

    pearson_r = round(float(pearson_r), 4)
    spearman_rho = round(float(spearman_rho), 4)
    pearson_p = round(float(pearson_p), 6)
    spearman_p = round(float(spearman_p), 6)

    logger.info("PHQ-9 binary AUC: %s", m_phq9_auc)
    logger.info("Pearson r=%.4f (p=%.6f)", pearson_r, pearson_p)
    logger.info("Spearman rho=%.4f (p=%.6f)", spearman_rho, spearman_p)

    # Quantile analysis
    quantiles = [0, 0.25, 0.5, 0.75, 1.0]
    quant_chunks = {}
    for i in range(len(quantiles) - 1):
        lo = np.percentile(m_proba, quantiles[i] * 100)
        hi = np.percentile(m_proba, quantiles[i + 1] * 100)
        mask = (m_proba >= lo) & (m_proba <= hi)
        if mask.sum() == 0:
            quant_chunks[f"Q{i+1}"] = {"samples": 0}
            continue
        sub_scores = m_phq9[mask]
        quant_chunks[f"Q{i+1}"] = {
            "samples": int(mask.sum()),
            "phq9_mean": round(float(sub_scores.mean()), 1),
            "phq9_median": round(float(np.median(sub_scores)), 1),
            "proba_range": f"{lo:.3f} - {hi:.3f}",
            "phq9_binary_rate": round(float((sub_scores >= 10).mean()), 2),
        }

    # High-score recall
    high_mask = m_phq9 >= 10
    high_cutoffs = {0.4: 0, 0.5: 0, 0.6: 0}
    for t in high_cutoffs:
        pred_high = m_proba >= t
        high_cutoffs[t] = round(float((pred_high & high_mask).sum() / max(high_mask.sum(), 1)), 4)
    logger.info("High-score recall: %s", json.dumps(high_cutoffs))

    mmpsy_df = pd.read_csv(PROJECT_ROOT / args.mmpsy_path)
    mmpsy_stats = {
        "samples": len(mmpsy_df),
        "phq9_mean": round(float(mmpsy_df["phq9_score"].mean()), 1),
        "phq9_median": round(float(mmpsy_df["phq9_score"].median()), 1),
        "phq9_binary_rate": round(float(mmpsy_df["phq9_binary"].mean()), 2),
        "gad7_mean": round(float(mmpsy_df["gad7_score"].mean()), 1),
        "model_inference_possible": False,
        "limitation": "mmpsy 仅有量表分数和音频转录文本，缺少 age/gender/cgpa 等 12 个结构化特征，无法直接运行 v1.23 模型",
    }

    metrics = {
        "validation_set": "Mendeley PHQ-9 (test subset)",
        "samples": len(mendeley_df),
        "phq9_binary_auc": m_phq9_auc,
        "pearson_r": pearson_r,
        "pearson_p": pearson_p,
        "spearman_rho": spearman_rho,
        "spearman_p": spearman_p,
        "quantile_analysis": quant_chunks,
        "high_score_recall": high_cutoffs,
        "mmpsy_status": mmpsy_stats,
    }
    (model_dir / "external_validation_metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8",
    )

    lines = [
        "# v1.23 外部验证报告 (EXTERNAL_VALIDATION_REPORT)",
        "",
        "> 日期: 2026-05-02",
        f"> 验证集: Mendeley PHQ-9 (test 子集, n={len(mendeley_df)})",
        "",
        "## PHQ-9 二分类验证",
        f"- PHQ-9 >=10 标签 vs 模型概率 AUC: **{m_phq9_auc}**",
        "",
        "## PHQ-9 总分相关性",
        f"- Pearson r: **{pearson_r}** (p={pearson_p})",
        f"- Spearman ρ: **{spearman_rho}** (p={spearman_p})",
        "",
        "## 分位数分析",
    ]
    for q, info in quant_chunks.items():
        lines.append(f"- {q} (n={info['samples']}): PHQ-9均值={info['phq9_mean']}, 中高风险率={info['phq9_binary_rate']:.0%}")

    lines.extend([
        "",
        "## 高分样本召回率",
        "| 概率阈值 | 召回率 |",
        "|----------|--------|",
    ])
    for t, r in high_cutoffs.items():
        lines.append(f"| >= {t} | {r:.1%} |")

    lines.extend([
        "",
        "## mmpsy 数据状态",
        f"- 样本: {mmpsy_stats['samples']}",
        f"- PHQ-9 均值: {mmpsy_stats['phq9_mean']}, 中高风险率: {mmpsy_stats['phq9_binary_rate']:.0%}",
        f"- GAD-7 均值: {mmpsy_stats['gad7_mean']}",
        f"- 模型推理: **不可行** — {mmpsy_stats['limitation']}",
        "",
        "## 与 v1.22 决策阈值对照",
        "",
        "| 阈值 | 要求 | 实际 | 状态 |",
        "|------|------|------|------|",
        f"| mmpsy AUC | > 0.80 (升级) | N/A (无特征可推理) | ⚠ 无法评估 |",
        f"| PHQ-9 Pearson r | >= 0.5 | {pearson_r} | {'✅' if abs(pearson_r) >= 0.5 else '❌'} |",
        f"| PHQ-9 Spearman ρ | >= 0.5 | {spearman_rho} | {'✅' if abs(spearman_rho) >= 0.5 else '❌'} |",
        f"| PHQ-9 binary AUC | >= 0.80 | {m_phq9_auc} | {'✅' if m_phq9_auc and m_phq9_auc >= 0.80 else '❌' if m_phq9_auc else 'N/A'} |",
        "",
        "## 外部验证结论",
        f"基于 Mendeley PHQ-9 test 子集 (n={len(mendeley_df)})：",
        f"- 模型概率与 PHQ-9 总分的 Pearson r = {pearson_r}，Spearman ρ = {spearman_rho}",
        f"- PHQ-9 >=10 的二分类 AUC = {m_phq9_auc}",
    ])

    if pearson_r >= 0.5 and spearman_rho >= 0.5:
        lines.append("- 连续分相关性达标 ✅")
    else:
        lines.append("- ⚠ 连续分相关性未完全达标，建议持续观察")

    lines.extend([
        f"- mmpsy 外部一致性验证因缺少结构化特征而**无法执行**",
        "- 建议后续版本获取 mmpsy 对应的结构化特征或直接采集新的外部验证数据",
        "",
        "> **建议**: 以 Mendeley PHQ-9 作为当前版本的主要临床标签验证集；在 v1.24 中考虑补充外部结构化验证数据。",
    ])

    report_path = report_dir / "EXTERNAL_VALIDATION_REPORT.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Phase 5 complete.")


if __name__ == "__main__":
    main()
