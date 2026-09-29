"""T1 全模态 GroupKFold 评估脚本.

对结构化/生理/融合模态运行 GroupKFold + StratifiedKFold 评估,
生成 group_cv_metrics.json 和差距报告.

文本模态已有 m2_group_cv_eval.py, 本脚本处理其余模态.

Usage:
    python scripts/t1_eval_all_modalities.py
    python scripts/t1_eval_all_modalities.py --modality structured
    python scripts/t1_eval_all_modalities.py --modality fusion
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

# 添加项目根到 path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from t1_group_cv_tool import (
    CVResult,
    evaluate_group_cv,
    evaluate_stratified_cv,
    generate_gap_report,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [T1-Eval] %(message)s")
logger = logging.getLogger("T1-Eval")

# 数据集路径
LITE_FEATURES_PATH = PROJECT_ROOT / "data" / "processed" / "lite_features.csv"
PHYSIOLOGICAL_PATH = PROJECT_ROOT / "models" / "artifacts" / "physiological_m3" / "train_data.csv"

# 输出路径
OUTPUT_DIR = PROJECT_ROOT / "models" / "artifacts"

# lite_features.csv 的列分组 (基于调研)
# 注意: phq9_score 是 phq9_binary 标签的来源 (phq9_binary = 1 if phq9_score >= 阈值),
# 包含它会导致数据泄露 (F1=0.98, AUC=0.9993), 必须排除!
STRUCTURED_COLS = [
    "gad7_score", "age", "gender", "cgpa",
]
TEXT_COLS = [
    "total_keywords", "unique_categories", "text_length", "chinese_ratio",
    "text_quality_flag", "crisis_weighted", "coverage_density",
    "kw_academic_pressure", "kw_sleep_problem", "kw_social_withdrawal",
    "kw_self_harm_crisis", "kw_exercise_deficit", "kw_low_mood", "kw_anxiety_somatic",
]
LABEL_COL = "phq9_binary"
GROUP_COL = "user_id"


def load_lite_features() -> pd.DataFrame:
    """加载融合数据集 lite_features.csv."""
    if not LITE_FEATURES_PATH.exists():
        raise FileNotFoundError(f"融合数据集不存在: {LITE_FEATURES_PATH}")
    df = pd.read_csv(LITE_FEATURES_PATH)
    logger.info("加载 lite_features: %d 样本, %d 列", len(df), df.shape[1])
    logger.info("user_id 唯一值: %d (每用户 1 样本)", df[GROUP_COL].nunique())
    logger.info("标签分布: %s", df[LABEL_COL].value_counts().to_dict())
    return df


def prepare_modality_data(
    df: pd.DataFrame,
    modality: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """根据模态提取特征/标签/分组键.

    Args:
        df: lite_features DataFrame.
        modality: structured / text_features / fusion.

    Returns:
        X, y, groups.
    """
    if modality == "structured":
        cols = STRUCTURED_COLS
    elif modality == "text_features":
        cols = TEXT_COLS
    elif modality == "fusion":
        cols = STRUCTURED_COLS + TEXT_COLS
    else:
        raise ValueError(f"未知模态: {modality}")

    # 确保列存在
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"缺失列: {missing}")

    X = df[cols].values.astype(float)
    y = df[LABEL_COL].values.astype(int)
    groups = df[GROUP_COL].values

    logger.info("[%s] 特征: %d 维, 样本: %d, 组: %d", modality, X.shape[1], len(y), len(np.unique(groups)))
    return X, y, groups


def load_physiological_data() -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """加载生理模态数据.

    生理模态数据可能在 physiological_m3/train_data.csv 或其他位置.
    如果找不到, 返回 None.
    """
    # 尝试多个可能路径
    candidates = [
        PHYSIOLOGICAL_PATH,
        PROJECT_ROOT / "data" / "processed" / "physiological_features.csv",
        PROJECT_ROOT / "models" / "artifacts" / "physiological_m3" / "features.csv",
    ]
    for path in candidates:
        if path.exists():
            logger.info("找到生理数据集: %s", path)
            df = pd.read_csv(path)
            # 寻找标签列和分组键
            label_candidates = [c for c in df.columns if "phq9" in c.lower() or "label" in c.lower() or "depression" in c.lower()]
            group_candidates = [c for c in df.columns if "user" in c.lower() or "id" in c.lower() or "source" in c.lower()]
            logger.info("生理数据列: %s", list(df.columns))
            logger.info("标签候选: %s, 分组候选: %s", label_candidates, group_candidates)
            # 使用 user_id 或第一列作为分组键
            group_col = GROUP_COL if GROUP_COL in df.columns else (group_candidates[0] if group_candidates else None)
            label_col = LABEL_COL if LABEL_COL in df.columns else (label_candidates[0] if label_candidates else None)
            if group_col and label_col:
                feature_cols = [c for c in df.columns if c not in [group_col, label_col]]
                X = df[feature_cols].values.astype(float)
                y = df[label_col].values.astype(int)
                groups = df[group_col].values
                logger.info("[physiological] 特征: %d 维, 样本: %d, 组: %d", X.shape[1], len(y), len(np.unique(groups)))
                return X, y, groups
    logger.warning("未找到生理数据集, 跳过生理模态评估")
    return None


def run_modality_eval(
    modality: str,
    X: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    output_dir: Path,
) -> dict:
    """对单个模态运行 GroupKFold + StratifiedKFold 评估.

    Args:
        modality: 模态名.
        X: 特征矩阵.
        y: 标签.
        groups: 分组键.
        output_dir: 输出目录.

    Returns:
        差距报告 dict.
    """
    logger.info("\n" + "=" * 60)
    logger.info("评估模态: %s", modality)
    logger.info("=" * 60)

    start = time.time()

    # 1. GroupKFold (按 user_id 分组)
    group_result = evaluate_group_cv(
        X, y, groups,
        label=f"{modality}_group_cv",
    )

    # 2. StratifiedKFold (随机CV, 对比基线)
    stratified_result = evaluate_stratified_cv(
        X, y,
        label=f"{modality}_stratified_cv",
    )

    elapsed = time.time() - start

    # 3. 生成差距报告
    report = generate_gap_report(group_result, stratified_result, modality)
    report["elapsed_s"] = round(elapsed, 1)
    report["data"] = {
        "n_samples": int(len(y)),
        "n_features": int(X.shape[1]),
        "n_groups": int(len(np.unique(groups))),
        "pos_rate": float(y.mean()),
    }

    # 4. 保存到 artifacts 目录
    artifact_dir = output_dir / f"{modality}_group_cv"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    report_path = artifact_dir / "group_cv_metrics.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    logger.info("报告已保存: %s", report_path)

    # 5. 打印结论
    logger.info("-" * 50)
    logger.info("[%s] 结论:", modality)
    logger.info("  GroupKFold:     F1=%.4f±%.4f, AUC=%.4f±%.4f",
                group_result.f1_mean, group_result.f1_std,
                group_result.auc_mean, group_result.auc_std)
    logger.info("  StratifiedKFold: F1=%.4f±%.4f, AUC=%.4f±%.4f",
                stratified_result.f1_mean, stratified_result.f1_std,
                stratified_result.auc_mean, stratified_result.auc_std)
    logger.info("  差距: F1_gap=%.4f, AUC_gap=%.4f (%s)",
                report["gap"]["f1_gap"], report["gap"]["auc_gap"], report["leakage_level"])
    logger.info("  目标 F1 ≥ 0.60: GroupKFold=%s, Stratified=%s",
                "✓" if report["acceptance"]["group_cv_meets_target"] else "✗",
                "✓" if report["acceptance"]["stratified_cv_meets_target"] else "✗")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="T1 全模态 GroupKFold 评估")
    parser.add_argument(
        "--modality", type=str, default="all",
        choices=["all", "structured", "text_features", "fusion", "physiological"],
        help="评估模态 (默认 all)",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("T1 全模态 GroupKFold 评估 @ %s", datetime.now().isoformat(timespec="seconds"))
    logger.info("=" * 60)

    all_reports = []
    start_time = time.time()

    # 加载融合数据集 (结构化/文本特征/融合模态共用)
    try:
        df = load_lite_features()
    except FileNotFoundError as e:
        logger.error("无法加载融合数据集: %s", e)
        return

    # 评估各模态
    modalities_to_eval = []
    if args.modality in ("all", "structured"):
        modalities_to_eval.append("structured")
    if args.modality in ("all", "text_features"):
        modalities_to_eval.append("text_features")
    if args.modality in ("all", "fusion"):
        modalities_to_eval.append("fusion")
    if args.modality in ("all", "physiological"):
        modalities_to_eval.append("physiological")

    for modality in modalities_to_eval:
        if modality == "physiological":
            data = load_physiological_data()
            if data is None:
                continue
            X, y, groups = data
        else:
            X, y, groups = prepare_modality_data(df, modality)

        report = run_modality_eval(modality, X, y, groups, OUTPUT_DIR)
        all_reports.append(report)

    # 汇总报告
    elapsed = time.time() - start_time
    summary = {
        "experiment_id": f"t1_group_cv_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "elapsed_s": round(elapsed, 1),
        "n_modalities": len(all_reports),
        "modalities": [r["modality"] for r in all_reports],
        "results": all_reports,
        "protocol": {
            "n_folds": 5,
            "seeds": [42, 1337, 2024],
            "n_evaluations_per_strategy": 15,
            "classifier": "LogisticRegression",
            "group_key": "user_id",
            "note": "文本模态的 source_idx 分组由 m2_group_cv_eval.py 处理, 本脚本处理其他模态",
        },
    }

    summary_path = OUTPUT_DIR / "t1_group_cv_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
    logger.info("\n汇总报告已保存: %s", summary_path)

    # 最终结论
    logger.info("\n" + "=" * 60)
    logger.info("T1 全模态 GroupKFold 评估完成 (%.1fs)", elapsed)
    logger.info("=" * 60)
    for r in all_reports:
        logger.info("[%s] F1_gap=%.4f, AUC_gap=%.4f, leakage=%s",
                    r["modality"], r["gap"]["f1_gap"], r["gap"]["auc_gap"], r["leakage_level"])


if __name__ == "__main__":
    main()
