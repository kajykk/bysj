"""D3 域外验证集构建与评估.

目标: 验证文本模型的域外泛化能力, 量化过拟合程度
数据: data/external/mmpsy_scores.csv (1275 条中文校园语料, 已有 PHQ-9 标签)
对照: 域内 Reddit+Twitter 英文 TF-IDF 模型 (F1=0.7891, AUC=0.8806)

评估内容:
  1. 用英文 TF-IDF 模型预测中文文本 (跨语言域外)
  2. 词汇重叠分析 (解释失效原因)
  3. 输出域外指标对比报告

验收:
  - 域外测试集 ≥ 2000 条 (现有 1275 条, 不足但可用)
  - 标注一致性: PHQ-9 量表标签 (豁免 Cohen's κ)
  - 合规: 已脱敏 MIT 许可

Usage:
    python scripts/d3_ood_validation.py
"""

from __future__ import annotations

import json
import logging
import pickle
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [D3] %(message)s")
logger = logging.getLogger("D3")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS_DIR = PROJECT_ROOT / "models" / "experiments"
TRAINING_JOBS_PATH = PROJECT_ROOT / "models" / "training_jobs.json"
ARTIFACTS_DIR = PROJECT_ROOT / "models" / "artifacts" / "d3_ood_validation"

# 数据路径
MMPSY_DATA_PATH = PROJECT_ROOT / "data" / "external" / "mmpsy_scores.csv"

# 现有文本模型路径 (英文 Reddit+Twitter 训练)
TEXT_MODEL_PATH = PROJECT_ROOT / "models" / "artifacts" / "text_depression_classifier" / "text_model.pkl"
TEXT_TFIDF_PATH = PROJECT_ROOT / "models" / "artifacts" / "text_depression_classifier" / "text_tfidf.pkl"
TEXT_METRICS_PATH = PROJECT_ROOT / "models" / "artifacts" / "text_depression_classifier" / "metrics.json"

# D3 验收阈值
TARGET_OOD_SIZE = 2000  # 域外集理想规模
MIN_OOD_SIZE = 1000     # 最低可用规模

# 域内基线 (来自 metrics.json)
INDOMAIN_BASELINE = {
    "f1": 0.7891,
    "auc": 0.8806,
    "source": "Reddit+Twitter 英文测试集",
}


def normalize_text(text: str) -> str:
    """文本归一化 (与训练脚本一致, 保留中文字符)."""
    import re
    text = str(text).lower().strip()
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    text = re.sub(r"@[\w_]+", " ", text)
    text = re.sub(r"#[\w_]+", " ", text)
    text = text.replace("&amp;", " and ")
    # 保留中文字符 \u4e00-\u9fff (与训练脚本一致)
    text = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def load_mmpsy_data() -> pd.DataFrame:
    """加载 mmpsy 中文校园语料.

    返回:
        DataFrame[user_id, phq9_score, phq9_level, phq9_binary, text]
        text 为多段对话合并后的全文
    """
    logger.info("加载 mmpsy 中文校园语料: %s", MMPSY_DATA_PATH)
    df = pd.read_csv(MMPSY_DATA_PATH)

    # 检查必要列
    required = ["user_id", "phq9_binary", "audio_transcript"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"mmpsy 数据缺失列: {missing}")

    # 合并多段对话文本 (用 | 分隔)
    df["text"] = df["audio_transcript"].astype(str).str.split("|").apply(
        lambda parts: " ".join(p.strip() for p in parts)
    )

    # 文本归一化
    df["text_normalized"] = df["text"].map(normalize_text)

    # 过滤空文本和短文本
    df = df[df["text_normalized"].str.len() >= 5].reset_index(drop=True)

    logger.info(
        "加载完成: %d 样本, 阳性率=%.2f%%, 平均文本长度=%.0f 字符",
        len(df),
        df["phq9_binary"].mean() * 100,
        df["text"].str.len().mean(),
    )
    logger.info("PHQ-9 等级分布: %s", df["phq9_level"].value_counts().to_dict())

    return df


def load_text_model() -> tuple[Any, Any, dict]:
    """加载现有 TF-IDF 文本模型."""
    logger.info("加载文本模型: %s", TEXT_MODEL_PATH)

    with open(TEXT_TFIDF_PATH, "rb") as f:
        tfidf = pickle.load(f)
    with open(TEXT_MODEL_PATH, "rb") as f:
        model = pickle.load(f)
    with open(TEXT_METRICS_PATH, "r", encoding="utf-8") as f:
        metrics = json.load(f)

    logger.info(
        "模型加载完成: TF-IDF 词汇表 %d 词, 域内 F1=%.4f, AUC=%.4f",
        len(tfidf.vocabulary_),
        metrics["test_metrics"]["f1"],
        metrics["test_metrics"]["roc_auc"],
    )
    return tfidf, model, metrics


def analyze_vocab_overlap(tfidf: Any, ood_texts: pd.Series) -> dict[str, Any]:
    """分析域内词汇表与域外文本的重叠率.

    英文 TF-IDF 词汇表 vs 中文文本, 预期重叠极低.
    """
    # TF-IDF 词汇表 (英文为主)
    vocab = set(tfidf.vocabulary_.keys())
    logger.info("TF-IDF 词汇表大小: %d", len(vocab))

    # 统计词汇表中的中文词
    chinese_vocab = [w for w in vocab if any("\u4e00" <= c <= "\u9fff" for c in w)]
    english_vocab = [w for w in vocab if not any("\u4e00" <= c <= "\u9fff" for c in w)]
    logger.info("词汇表构成: 英文 %d, 中文 %d", len(english_vocab), len(chinese_vocab))

    # 域外文本分词后与词汇表的交集
    ood_tokens = set()
    for text in ood_texts:
        ood_tokens.update(text.split())
    logger.info("域外文本独立 token 数: %d", len(ood_tokens))

    overlap = vocab & ood_tokens
    overlap_rate = len(overlap) / max(len(vocab), 1)
    ood_coverage = len(overlap) / max(len(ood_tokens), 1)

    logger.info("词汇重叠: %d 词 (%.2f%% 词汇表, %.2f%% 域外 token)",
                len(overlap), overlap_rate * 100, ood_coverage * 100)

    return {
        "vocab_size": len(vocab),
        "english_vocab": len(english_vocab),
        "chinese_vocab": len(chinese_vocab),
        "ood_token_count": len(ood_tokens),
        "overlap_count": len(overlap),
        "vocab_coverage_rate": float(overlap_rate),
        "ood_token_coverage_rate": float(ood_coverage),
        "overlap_examples": list(overlap)[:20],
    }


def evaluate_ood(tfidf: Any, model: Any, df: pd.DataFrame) -> dict[str, Any]:
    """用英文模型预测中文域外数据, 输出域外指标."""
    logger.info("=" * 50)
    logger.info("域外验证: 英文 TF-IDF 模型 → 中文 mmpsy 数据")
    logger.info("=" * 50)

    X_text = df["text_normalized"].values
    y_true = df["phq9_binary"].astype(int).values

    # TF-IDF 向量化
    X_tfidf = tfidf.transform(X_text)

    # 检查特征稀疏度 (中文文本在英文词汇表上几乎全 0)
    nonzero_per_sample = (X_tfidf != 0).sum(axis=1).A1
    zero_feature_rate = (nonzero_per_sample == 0).mean()

    logger.info("特征稀疏度: %.2f%% 样本无任何特征命中 (全零向量)",
                zero_feature_rate * 100)
    logger.info("平均非零特征数: %.2f / %d",
                nonzero_per_sample.mean(), X_tfidf.shape[1])

    # 模型预测
    y_pred = model.predict(X_tfidf)
    y_prob = model.predict_proba(X_tfidf)[:, 1]

    # 计算指标
    metrics = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, y_prob)) if len(np.unique(y_true)) > 1 else 0.5,
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
        "classification_report": classification_report(
            y_true, y_pred, output_dict=True, zero_division=0
        ),
        "n_samples": int(len(y_true)),
        "pos_rate": float(y_true.mean()),
        "zero_feature_rate": float(zero_feature_rate),
        "avg_nonzero_features": float(nonzero_per_sample.mean()),
        "prob_stats": {
            "mean": float(y_prob.mean()),
            "std": float(y_prob.std()),
            "min": float(y_prob.min()),
            "max": float(y_prob.max()),
            "p50": float(np.percentile(y_prob, 50)),
        },
    }

    logger.info("--- 域外指标 ---")
    logger.info("F1=%.4f (域内 %.4f, 下降 %.4f)",
                metrics["f1"], INDOMAIN_BASELINE["f1"],
                INDOMAIN_BASELINE["f1"] - metrics["f1"])
    logger.info("AUC=%.4f (域内 %.4f, 下降 %.4f)",
                metrics["roc_auc"], INDOMAIN_BASELINE["auc"],
                INDOMAIN_BASELINE["auc"] - metrics["roc_auc"])
    logger.info("准确率=%.4f, 召回=%.4f, 精确=%.4f",
                metrics["accuracy"], metrics["recall"], metrics["precision"])
    logger.info("混淆矩阵: %s", metrics["confusion_matrix"])
    logger.info("预测概率: mean=%.4f, std=%.4f (低方差表示模型不确定)",
                y_prob.mean(), y_prob.std())

    return metrics


def generate_report(
    df: pd.DataFrame,
    vocab_analysis: dict,
    ood_metrics: dict,
    elapsed_s: float,
) -> dict[str, Any]:
    """生成 D3 域外验证报告."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 域内 vs 域外对比
    f1_drop = INDOMAIN_BASELINE["f1"] - ood_metrics["f1"]
    auc_drop = INDOMAIN_BASELINE["auc"] - ood_metrics["roc_auc"]

    # 验收判断
    meets_size = len(df) >= TARGET_OOD_SIZE
    meets_min_size = len(df) >= MIN_OOD_SIZE
    # 域外 F1 下降幅度判断过拟合程度
    severe_overfit = f1_drop > 0.3  # F1 下降超 30pt 视为严重域外失效

    report = {
        "experiment_id": f"d3_ood_validation_{timestamp}",
        "task": "D3 域外验证集构建与评估",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "elapsed_s": round(elapsed_s, 1),
        "data_source": {
            "name": "mmpsy (Multi-Modal Psychology Data)",
            "source": "广东省中学生心理访谈 (已脱敏, MIT 许可)",
            "n_samples": int(len(df)),
            "pos_rate": float(df["phq9_binary"].mean()),
            "phq9_level_distribution": df["phq9_level"].value_counts().to_dict(),
            "avg_text_length": float(df["text"].str.len().mean()),
            "label_source": "PHQ-9 量表 (教育局组织标准化评测)",
        },
        "indomain_baseline": INDOMAIN_BASELINE,
        "vocab_analysis": vocab_analysis,
        "ood_metrics": ood_metrics,
        "comparison": {
            "f1_indomain": INDOMAIN_BASELINE["f1"],
            "f1_ood": ood_metrics["f1"],
            "f1_drop": float(f1_drop),
            "auc_indomain": INDOMAIN_BASELINE["auc"],
            "auc_ood": ood_metrics["roc_auc"],
            "auc_drop": float(auc_drop),
        },
        "acceptance": {
            "meets_size_target": bool(meets_size),
            "meets_min_size": bool(meets_min_size),
            "size_actual": int(len(df)),
            "size_target": TARGET_OOD_SIZE,
            "label_authoritative": True,  # PHQ-9 量表标签
            "compliance_done": True,      # 已脱敏 MIT 许可
            "severe_overfit_detected": bool(severe_overfit),
            "notes": (
                "域外集规模 1275 < 2000 目标, 但已有 PHQ-9 权威标签, "
                "可用于域外泛化基准评估. 若 F1 严重下降, 需启动 M2 BERT 中文微调."
            ),
        },
        "conclusion": {
            "overfit_confirmed": bool(f1_drop > 0.1),
            "cross_language_failure": bool(vocab_analysis["vocab_coverage_rate"] < 0.05),
            "recommendation": (
                "英文 TF-IDF 模型在中文域外数据上严重失效, "
                "需启动 M2 BERT 中文微调以提升跨语言泛化能力."
                if severe_overfit
                else "域外泛化可接受, 可考虑扩充域外集进一步验证."
            ),
        },
    }

    return report


def save_report(report: dict) -> None:
    """保存 D3 报告与实验记录."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = report["experiment_id"].split("_")[-1]

    # 保存完整报告
    report_path = ARTIFACTS_DIR / "d3_ood_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info("报告已保存: %s", report_path)

    # 保存实验记录
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    exp_path = EXPERIMENTS_DIR / f"{report['experiment_id']}.json"
    with open(exp_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info("实验记录已保存: %s", exp_path)

    # 更新 training_jobs.json
    try:
        with open(TRAINING_JOBS_PATH, "r", encoding="utf-8") as f:
            jobs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        jobs = {}

    jobs[report["experiment_id"]] = {
        "job_id": report["experiment_id"],
        "status": "completed",
        "task": "D3_ood_validation",
        "created_at": time.time(),
        "n_ood_samples": report["data_source"]["n_samples"],
        "f1_indomain": report["comparison"]["f1_indomain"],
        "f1_ood": report["comparison"]["f1_ood"],
        "f1_drop": report["comparison"]["f1_drop"],
        "severe_overfit": report["acceptance"]["severe_overfit_detected"],
        "timestamp": timestamp,
    }
    with open(TRAINING_JOBS_PATH, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)
    logger.info("training_jobs.json 已更新")


def main() -> None:
    """D3 域外验证主流程."""
    start_time = time.time()
    logger.info("=" * 60)
    logger.info("D3 域外验证集构建与评估 - 启动")
    logger.info("=" * 60)

    # 1. 加载 mmpsy 中文域外数据
    df = load_mmpsy_data()

    # 2. 加载现有英文 TF-IDF 文本模型
    tfidf, model, _ = load_text_model()

    # 3. 词汇重叠分析 (解释跨语言失效原因)
    logger.info("=" * 50)
    logger.info("词汇重叠分析")
    logger.info("=" * 50)
    vocab_analysis = analyze_vocab_overlap(tfidf, df["text_normalized"])

    # 4. 域外预测评估
    ood_metrics = evaluate_ood(tfidf, model, df)

    # 5. 生成报告
    elapsed = time.time() - start_time
    report = generate_report(df, vocab_analysis, ood_metrics, elapsed)

    # 6. 保存报告
    save_report(report)

    # 7. 打印结论
    logger.info("=" * 60)
    logger.info("D3 域外验证完成 (%.1fs)", elapsed)
    logger.info("=" * 60)
    logger.info("结论:")
    logger.info("  域内 F1=%.4f → 域外 F1=%.4f (下降 %.4f)",
                report["comparison"]["f1_indomain"],
                report["comparison"]["f1_ood"],
                report["comparison"]["f1_drop"])
    logger.info("  域内 AUC=%.4f → 域外 AUC=%.4f (下降 %.4f)",
                report["comparison"]["auc_indomain"],
                report["comparison"]["auc_ood"],
                report["comparison"]["auc_drop"])
    logger.info("  词汇覆盖率: %.2f%% (英文词汇表 vs 中文文本)",
                vocab_analysis["vocab_coverage_rate"] * 100)
    logger.info("  零特征样本率: %.2f%%",
                ood_metrics["zero_feature_rate"] * 100)
    logger.info("  建议: %s", report["conclusion"]["recommendation"])


if __name__ == "__main__":
    main()
