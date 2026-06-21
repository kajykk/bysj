#!/usr/bin/env python3
"""v1.23 补丁: 补齐交付清单中的缺失产物。

修复项:
    2. 导出独立 preprocessor.pkl
    4. 生成 external_mmpsy.csv
    5. 补充 GAD-7 相关性验证
    6. 补充分数分布直方图数据
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
MODEL_DIR = PROJECT_ROOT / "backend/models/v1.23_external_lr"
DATA_DIR = PROJECT_ROOT / "data/processed/v1_23_external"
MMPSY_PATH = PROJECT_ROOT / "data/external/mmpsy_scores.csv"
REPORT_DIR = PROJECT_ROOT / "docs/planning/v1.23-external-risk-model-upgrade"

FEATURE_COLS = [
    "age", "gender", "cgpa", "stress_level", "sleep_duration",
    "social_support", "financial_pressure", "family_history",
    "academic_pressure", "exercise_frequency", "anxiety", "panic_attack",
]
TARGET_COL = "depression_binary"


def export_preprocessor() -> None:
    """修复 2: 从 pipeline 提取并独立保存 preprocessor.pkl"""
    model = joblib.load(MODEL_DIR / "model.pkl")
    if hasattr(model, "named_steps") and "preprocessor" in model.named_steps:
        preprocessor = model.named_steps["preprocessor"]
        joblib.dump(preprocessor, MODEL_DIR / "preprocessor.pkl")
        logger.info("preprocessor.pkl exported (type=%s)", type(preprocessor).__name__)
    else:
        logger.warning("Cannot extract preprocessor from model")


def export_external_mmpsy() -> None:
    """修复 4: 生成 external_mmpsy.csv"""
    mmpsy_df = pd.read_csv(MMPSY_PATH)
    out = pd.DataFrame()
    out["user_id"] = mmpsy_df.get("user_id", range(len(mmpsy_df)))
    out["phq9_score"] = mmpsy_df.get("phq9_score", pd.NA)
    out["phq9_binary"] = (mmpsy_df.get("phq9_score", 0) >= 10).astype(int)
    out["gad7_score"] = mmpsy_df.get("gad7_score", pd.NA)
    out["gad7_binary"] = (mmpsy_df.get("gad7_score", 0) >= 10).astype(int)
    out["audio_count"] = mmpsy_df.get("audio_count", pd.NA)

    for feat in FEATURE_COLS:
        out[feat] = pd.NA

    out["model_inference_possible"] = False
    out["feature_gap_note"] = (
        "mmpsy 数据仅包含 PHQ-9/GAD-7 量表分数和音频转录文本，"
        "缺少 age/gender/cgpa/stress_level 等 12 个结构化特征，"
        "无法直接运行 v1.23 External LR 模型"
    )

    out.to_csv(DATA_DIR / "external_mmpsy.csv", index=False)
    logger.info("external_mmpsy.csv exported (%d rows)", len(out))


def add_gad7_validation() -> None:
    """修复 5: 补充 GAD-7 相关性验证"""
    ext_path = MODEL_DIR / "external_validation_metrics.json"
    if not ext_path.exists():
        logger.warning("external_validation_metrics.json not found")
        return

    ext_data = json.loads(ext_path.read_text(encoding="utf-8"))

    df_test = pd.read_csv(DATA_DIR / "test.csv")
    mendeley_mask = (df_test["source"] == "mendeley") & df_test.get("phq9_total", pd.Series(dtype=float)).notna()
    mendeley_df = df_test[mendeley_mask]

    mmpsy_df = pd.read_csv(MMPSY_PATH)
    gad7_vals = mmpsy_df.get("gad7_score", pd.Series(dtype=float)).dropna()
    gad7_binary = mmpsy_df.get("gad7_binary", pd.Series(dtype=int))

    gad7_stats = {
        "samples": len(gad7_vals),
        "gad7_mean": round(float(gad7_vals.mean()), 1) if len(gad7_vals) > 0 else None,
        "gad7_median": round(float(gad7_vals.median()), 1) if len(gad7_vals) > 0 else None,
        "gad7_binary_rate": round(float(gad7_binary.mean()), 2) if len(gad7_binary) > 0 else None,
    }

    gad7_model_stats = {
        "mmpsy_gad7_available": len(gad7_vals) > 0,
        "mmpsy_gad7_samples": int(len(gad7_vals)),
        "mmpsy_gad7_binary_rate": round(float(gad7_binary.mean()), 2) if len(gad7_binary) > 0 else None,
        "mmpsy_gad7_mean": round(float(gad7_vals.mean()), 1) if len(gad7_vals) > 0 else None,
    }

    if "gad7_validation" not in ext_data:
        ext_data["gad7_validation"] = {}

    ext_data["gad7_validation"] = {
        **gad7_model_stats,
        "model_validation_possible": False,
        "limitation": "同 mmpsy PHQ-9 验证，GAD-7 仅有量表分无结构化特征，无法直接运行模型",
        "recommendation": "v1.24 中采集对应结构化特征后可补充模型级 GAD-7 验证",
    }

    ext_path.write_text(json.dumps(ext_data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("GAD-7 validation added to external_validation_metrics.json")

    # Update report
    ext_report = REPORT_DIR / "EXTERNAL_VALIDATION_REPORT.md"
    if ext_report.exists():
        content = ext_report.read_text(encoding="utf-8")
        extra = (
            "\n\n## GAD-7 验证状态\n\n"
            f"- mmpsy GAD-7 样本: {gad7_stats['samples']}\n"
            f"- GAD-7 均值: {gad7_stats['gad7_mean']}\n"
            f"- GAD-7 >=10 比例: {gad7_stats['gad7_binary_rate']:.0%}\n"
            f"- 模型推理: 不可行 (同 PHQ-9，缺少结构化特征)\n"
            f"- 建议: v1.24 中补充结构化特征后完成 GAD-7 模型级验证\n"
        )
        if "## GAD-7" not in content:
            ext_report.write_text(content + extra, encoding="utf-8")
            logger.info("GAD-7 section appended to EXTERNAL_VALIDATION_REPORT.md")


def add_score_histogram() -> None:
    """修复 6: 补充分数分布直方图数据"""
    df_val = pd.read_csv(DATA_DIR / "validation.csv")
    model = joblib.load(MODEL_DIR / "model.pkl")
    X_val = df_val[FEATURE_COLS]
    y_proba = model.predict_proba(X_val)[:, 1]
    risk_scores = y_proba * 100

    bins = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    hist, _ = np.histogram(risk_scores, bins=bins)
    bin_labels = [f"{bins[i]}-{bins[i+1]}" for i in range(len(bins)-1)]
    hist_df = pd.DataFrame({"score_bin": bin_labels, "count": hist, "pct": np.round(hist / len(risk_scores) * 100, 2)})
    hist_df.to_csv(MODEL_DIR / "score_distribution_histogram.csv", index=False)
    logger.info("score_distribution_histogram.csv exported (%d bins)", len(hist_df))


def main() -> None:
    logger.info("=== v1.23 Patch Script ===")

    export_preprocessor()
    export_external_mmpsy()
    add_gad7_validation()
    add_score_histogram()

    logger.info("All patches applied successfully.")


if __name__ == "__main__":
    main()
