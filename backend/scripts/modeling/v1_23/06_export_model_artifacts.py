#!/usr/bin/env python3
"""v1.23 Phase 7: 模型产物导出 — 校验产物完整性，生成 model_card.md 和 metrics.json。

输出:
    backend/models/v1.23_external_lr/feature_schema.json
    backend/models/v1.23_external_lr/metrics.json
    backend/models/v1.23_external_lr/model_card.md
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import joblib
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]

FEATURE_COLS = [
    "age", "gender", "cgpa", "stress_level", "sleep_duration",
    "social_support", "financial_pressure", "family_history",
    "academic_pressure", "exercise_frequency", "anxiety", "panic_attack",
]

REQUIRED_FILES = [
    "model.pkl", "metrics_train.json", "metrics_eval.json",
    "confusion_matrix.json", "threshold_config.json",
    "calibration_config.json", "comparison_metrics.json",
    "external_validation_metrics.json",
    "roc_curve.csv", "pr_curve.csv", "calibration_curve.csv",
    "feature_coefficients.csv", "model_delta_samples.csv",
]


def validate_model(model_path: Path) -> dict:
    model = joblib.load(model_path)
    if hasattr(model, "named_steps"):
        classifier = model.named_steps.get("classifier", model)
    else:
        classifier = model

    info = {"type": type(classifier).__name__, "framework": "sklearn"}
    if hasattr(classifier, "coef_"):
        info["n_features"] = classifier.coef_.shape[1]
        info["coef_range"] = [round(float(classifier.coef_.min()), 4), round(float(classifier.coef_.max()), 4)]
    if hasattr(classifier, "C"):
        info["C"] = classifier.C
    if hasattr(classifier, "class_weight"):
        info["class_weight"] = str(classifier.class_weight)
    return info


def main() -> None:
    parser = argparse.ArgumentParser(description="v1.23 Phase 7: Export Artifacts")
    parser.add_argument("--model-dir", default="backend/models/v1.23_external_lr")
    parser.add_argument("--report-dir", default="docs/planning/v1.23-external-risk-model-upgrade")
    args = parser.parse_args()

    model_dir = PROJECT_ROOT / args.model_dir
    report_dir = PROJECT_ROOT / args.report_dir

    # Validate files
    missing = []
    existing = []
    for f in REQUIRED_FILES:
        fp = model_dir / f
        if fp.exists():
            existing.append(f)
        else:
            missing.append(f)

    logger.info("Files present: %d/%d", len(existing), len(REQUIRED_FILES))
    if missing:
        logger.warning("Missing files: %s", missing)

    model_info = validate_model(model_dir / "model.pkl")
    logger.info("Model validated: %s", json.dumps(model_info))

    # feature_schema.json
    feature_schema = {
        "version": "v1.23_external_lr",
        "features": [
            {"name": "age", "type": "numeric", "required": True, "range": [12, 35], "default_strategy": "median"},
            {"name": "gender", "type": "numeric", "required": True, "mapping": {"female": 0, "male": 1}},
            {"name": "cgpa", "type": "numeric", "required": True, "range": [0, 4], "default_strategy": "median"},
            {"name": "stress_level", "type": "numeric", "required": True, "default_strategy": "median"},
            {"name": "sleep_duration", "type": "numeric", "required": True, "unit": "hours", "default_strategy": "median"},
            {"name": "social_support", "type": "numeric", "required": True, "warning": "多数数据集中为填充值 2.0"},
            {"name": "financial_pressure", "type": "numeric", "required": True, "default_strategy": "median"},
            {"name": "family_history", "type": "numeric", "required": True, "values": [0, 1]},
            {"name": "academic_pressure", "type": "numeric", "required": True, "default_strategy": "median"},
            {"name": "exercise_frequency", "type": "numeric", "required": True, "default_strategy": "median"},
            {"name": "anxiety", "type": "numeric", "required": True, "note": "可能为代理特征"},
            {"name": "panic_attack", "type": "numeric", "required": True, "values": [0, 1]},
        ],
        "target": "depression_binary",
        "score_output": "probability_0_1",
        "risk_score_mapping": "probability * 100",
        "input_features": len(FEATURE_COLS),
        "model_type": "LogisticRegression",
        "preprocessing": "SimpleImputer(median) + StandardScaler",
    }
    (model_dir / "feature_schema.json").write_text(
        json.dumps(feature_schema, indent=2, ensure_ascii=False), encoding="utf-8",
    )

    # metrics.json
    eval_path = model_dir / "metrics_eval.json"
    train_path = model_dir / "metrics_train.json"
    comp_path = model_dir / "comparison_metrics.json"
    ext_path = model_dir / "external_validation_metrics.json"
    calib_path = model_dir / "calibration_config.json"

    metrics = {
        "version": "v1.23_external_lr",
        "training_date": "2026-05-02",
        "random_state": 42,
        "training_setting": "weighted (Mendeley sample_weight=5.0)",
        "features": FEATURE_COLS,
        "target": "depression_binary",
    }
    for key, path in [
        ("train_metrics", train_path),
        ("eval_metrics", eval_path),
        ("comparison", comp_path),
        ("external_validation", ext_path),
    ]:
        if path.exists():
            metrics[key] = json.loads(path.read_text(encoding="utf-8"))
    if calib_path.exists():
        metrics["calibration"] = json.loads(calib_path.read_text(encoding="utf-8"))

    (model_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8",
    )

    # model_card.md
    eval_data = json.loads(eval_path.read_text(encoding="utf-8")) if eval_path.exists() else {}
    ext_data = json.loads(ext_path.read_text(encoding="utf-8")) if ext_path.exists() else {}
    comp_data = json.loads(comp_path.read_text(encoding="utf-8")) if comp_path.exists() else {}

    lines = [
        "# v1.23 External LR 模型卡 (Model Card)",
        "",
        "## 模型版本",
        "- 版本号: v1.23-external-risk-model-upgrade",
        "- 训练日期: 2026-05-02",
        "- 模型类型: Logistic Regression (sklearn)",
        "",
        "## 训练数据来源",
        "- Kaggle Student Depression (27,870 条, self_reported_binary 标签)",
        "- Mendeley PHQ-9 Dataset (682 条, phq9_total >= 10 标签)",
        "- 训练策略: 数据源加权 (Mendeley sample_weight=5.0x)",
        "",
        "## 特征列表",
    ]
    for f in feature_schema["features"]:
        note = f" (⚠ {f.get('warning', '')})" if f.get("warning") else ""
        note = note or (f" ({f.get('note', '')})" if f.get("note") else "")
        lines.append(f"- `{f['name']}` ({f['type']}){note}")
    lines.extend([
        "",
        "## 标签定义",
        "- `depression_binary = 1`: 存在中高风险抑郁倾向",
        "- `depression_binary = 0`: 未检测到明显中高风险抑郁倾向",
        "- 标签来源: Kaggle self_reported_binary (主要) + Mendeley phq9_total >= 10",
        "",
        "## 适用范围",
        "- 学生群体的心理健康风险筛查",
        "- 作为机构内部风险评估工具，辅助咨询师决策",
        "- 适用于结构化问卷数据场景",
        "",
        "## 不适用范围",
        "- 不构成临床诊断",
        "- 不直接输出为医学诊断结论",
        "- 不适用于非学生群体",
        "- 不适用于仅有文本或生理数据的场景",
        "",
        "## 性能指标",
        f"- 测试集 AUC: {eval_data.get('roc_auc', 'N/A')}",
        f"- 测试集 F1: {eval_data.get('f1', 'N/A')}",
        f"- 测试集 Recall: {eval_data.get('recall', 'N/A')}",
        f"- 测试集 Specificity: {eval_data.get('specificity', 'N/A')}",
        f"- PHQ-9 Pearson r: {ext_data.get('pearson_r', 'N/A')}",
        f"- PHQ-9 Binary AUC: {ext_data.get('phq9_binary_auc', 'N/A')}",
        "",
        "## 已知偏差",
        "- Kaggle 训练数据占比 97.6%，标签语义并非严格 PHQ-9 对齐",
        "- `social_support` 字段在大部分数据中为填充值 2.0，区分度低",
        "- 模型未在外部独立结构化数据集上完成验证 (mmpsy 缺乏对应特征)",
        "- 中风险样本与高风险样本的模型分界存在一定模糊地带",
        "",
        "## 风险提示",
        "- 本模型输出为「风险辅助评估」，不应作为心理健康的唯一判断依据",
        "- 高风险预测应触发人工复核流程",
        "- 低风险预测不排除实际风险存在",
        "",
        "## 回滚策略",
        "- v1.20 Synthetic LR 是当前默认模型，始终保持加载能力",
        "- v1.23 作为实验模型接入时，default=False，不影响主路径",
        "- 若 v1.23 异常（加载失败/预测异常/NaN），自动 fallback 至 v1.20",
        "",
        "## 结论",
        "- v1.23 External LR 暂不直接替换 v1.20 Synthetic LR",
        "- 以「候选实验模型」角色接入系统 (role=experimental, default=false)",
        "- 持续监控与默认模型的差异",
    ])

    (model_dir / "model_card.md").write_text("\n".join(lines), encoding="utf-8")
    logger.info("Phase 7 complete. Model artifacts validated (%d/%d files present).", len(existing), len(REQUIRED_FILES))


if __name__ == "__main__":
    main()
