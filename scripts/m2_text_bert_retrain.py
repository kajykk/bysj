"""M2 文本 BERT 重训 (阶段二).

目标: 在 v2 扩充语料 (15000) 上重训 M2 BERT, 域外 F1 ≥ 0.85
数据:
  - 训练: data/external/chinese_depression_corpus_v2.csv (15000, EDA 增强 + 原始)
  - 域外: data/external/ood_test_set_v2.csv (5000)
方法:
  - chinese-bert-wwm-ext feature extraction (冻结 BERT, 只训练分类头)
  - LogReg 分类头 (class_weight=balanced, 阈值优化)
  - 5-fold × 3 seeds StratifiedGroupKFold (按 source_idx 分组, 防同源泄漏)
  - 域外评估: 在 OOD 测试集上报告 F1/AUC + 95% CI
缓存: BERT embedding 提取后缓存, 避免重复计算

退出条件:
  - 域外 F1 ≥ 0.85
  - 所有实验含 95% CI
  - 登记入 training_jobs.json

Usage:
    python scripts/m2_text_bert_retrain.py
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import StandardScaler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [M2-Retrain] %(message)s")
logger = logging.getLogger("M2-Retrain")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORPUS_V2_PATH = PROJECT_ROOT / "data" / "external" / "chinese_depression_corpus_v2.csv"
OOD_V2_PATH = PROJECT_ROOT / "data" / "external" / "ood_test_set_v2.csv"
EXPERIMENTS_DIR = PROJECT_ROOT / "models" / "experiments"
TRAINING_JOBS_PATH = PROJECT_ROOT / "models" / "training_jobs.json"
ARTIFACTS_DIR = PROJECT_ROOT / "models" / "artifacts" / "text_m2_bert_retrain"
EMBEDDING_CACHE_TRAIN = ARTIFACTS_DIR / "bert_embeddings_train_v2.npy"
EMBEDDING_CACHE_OOD = ARTIFACTS_DIR / "bert_embeddings_ood_v2.npy"

BERT_MODEL_NAME = "hfl/chinese-bert-wwm-ext"
MAX_SEQ_LEN = 256
BERT_BATCH_SIZE = 16

# 阶段二目标
TARGET_OOD_F1 = 0.85

# CV 配置
N_FOLDS = 5
SEEDS = [42, 1337, 2024]
T_VALUE_95 = 2.145  # df=14


def load_v2_corpus() -> pd.DataFrame:
    """加载 v2 扩充语料."""
    logger.info("加载 v2 语料: %s", CORPUS_V2_PATH)
    df = pd.read_csv(CORPUS_V2_PATH)
    df = df[df["text"].str.len() >= 5].reset_index(drop=True)
    df["phq9_binary"] = df["phq9_binary"].astype(int)
    logger.info(
        "v2 语料: %d 样本, 阳性率=%.2f%%, 平均长度=%.0f 字符",
        len(df), df["phq9_binary"].mean() * 100, df["text"].str.len().mean(),
    )
    return df


def load_ood_test() -> pd.DataFrame:
    """加载 OOD 域外测试集."""
    logger.info("加载 OOD 测试集: %s", OOD_V2_PATH)
    df = pd.read_csv(OOD_V2_PATH)
    df = df[df["text"].str.len() >= 5].reset_index(drop=True)
    df["phq9_binary"] = df["phq9_binary"].astype(int)
    logger.info(
        "OOD 测试集: %d 样本, 阳性率=%.2f%%",
        len(df), df["phq9_binary"].mean() * 100,
    )
    return df


def get_device() -> str:
    """检测可用设备."""
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
            logger.info("GPU 可用: %s (%.1f GB)", gpu_name, vram)
            return "cuda"
        logger.info("GPU 不可用, 使用 CPU (feature extraction 模式)")
        return "cpu"
    except ImportError:
        logger.warning("torch 未安装")
        return "none"


def load_bert_model(device: str):
    """加载 BERT 模型."""
    from transformers import AutoModel, AutoTokenizer
    logger.info("加载 BERT 模型: %s", BERT_MODEL_NAME)
    tokenizer = AutoTokenizer.from_pretrained(BERT_MODEL_NAME)
    model = AutoModel.from_pretrained(BERT_MODEL_NAME)
    if device not in ("cpu", "none"):
        import torch
        model = model.to(device)
    model.eval()
    logger.info("BERT 参数量: %d", sum(p.numel() for p in model.parameters()))
    return tokenizer, model


def extract_bert_embeddings(
    texts: list[str],
    tokenizer,
    model,
    device: str,
    max_len: int = MAX_SEQ_LEN,
    batch_size: int = BERT_BATCH_SIZE,
) -> np.ndarray:
    """提取 BERT [CLS] embedding."""
    import torch
    from tqdm import tqdm

    all_embeddings = []
    model.eval()
    logger.info("提取 BERT 特征: %d 文本", len(texts))

    for i in tqdm(range(0, len(texts), batch_size), desc="BERT embedding"):
        batch_texts = texts[i:i + batch_size]
        encoded = tokenizer(
            batch_texts, padding=True, truncation=True,
            max_length=max_len, return_tensors="pt",
        )
        if device not in ("cpu", "none"):
            encoded = {k: v.to(device) for k, v in encoded.items()}
        with torch.no_grad():
            outputs = model(**encoded)
        cls_embeddings = outputs.last_hidden_state[:, 0, :].cpu().numpy()
        all_embeddings.append(cls_embeddings)

    embeddings = np.vstack(all_embeddings)
    logger.info("特征提取完成: shape=%s", embeddings.shape)
    return embeddings


def get_or_extract_embeddings(
    texts: list[str],
    cache_path: Path,
    tokenizer,
    model,
    device: str,
) -> np.ndarray:
    """获取或提取 BERT embedding (带缓存)."""
    if cache_path.exists():
        logger.info("加载缓存 embedding: %s", cache_path)
        return np.load(cache_path)
    embeddings = extract_bert_embeddings(texts, tokenizer, model, device)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(cache_path, embeddings)
    logger.info("embedding 已缓存: %s", cache_path)
    return embeddings


def find_best_f1_threshold(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """在训练集上找最佳 F1 阈值."""
    from sklearn.metrics import precision_recall_curve
    precision, recall, thresholds = precision_recall_curve(y_true, y_prob)
    f1_scores = 2 * precision * recall / (precision + recall + 1e-8)
    best_idx = np.argmax(f1_scores[:-1])
    return float(thresholds[best_idx])


def evaluate_cv_with_ood(
    X_train: np.ndarray,
    y_train: np.ndarray,
    groups: np.ndarray,
    X_ood: np.ndarray,
    y_ood: np.ndarray,
) -> dict[str, Any]:
    """5-fold × 3 seeds CV + OOD 域外评估.

    CV 用于估计训练集上的稳定性, OOD 用于报告域外泛化能力.
    每折: 在训练集上训练 LogReg + 阈值优化, 在 OOD 上评估.
    最终 OOD 指标: 15 折的平均 (与 M2 一致).
    """
    logger.info("=" * 60)
    logger.info("M2 重训 CV + OOD 评估 (train=%d, OOD=%d)", len(y_train), len(y_ood))
    logger.info("=" * 60)

    all_cv_f1 = []
    all_cv_auc = []
    all_ood_f1 = []
    all_ood_auc = []
    all_ood_precision = []
    all_ood_recall = []
    all_thresholds = []
    fold_details = []

    for seed in SEEDS:
        skf = StratifiedGroupKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
        for fold_idx, (tr_idx, te_idx) in enumerate(skf.split(X_train, y_train, groups)):
            X_tr, X_te = X_train[tr_idx], X_train[te_idx]
            y_tr, y_te = y_train[tr_idx], y_train[te_idx]

            scaler = StandardScaler()
            X_tr_s = scaler.fit_transform(X_tr)
            X_te_s = scaler.transform(X_te)
            X_ood_s = scaler.transform(X_ood)

            clf = LogisticRegression(
                C=1.0, class_weight="balanced", max_iter=2000,
                random_state=seed, solver="lbfgs",
            )
            clf.fit(X_tr_s, y_tr)

            # CV 指标 (验证集)
            y_prob_cv = clf.predict_proba(X_te_s)[:, 1]
            y_prob_tr = clf.predict_proba(X_tr_s)[:, 1]
            threshold = find_best_f1_threshold(y_tr, y_prob_tr)
            all_thresholds.append(threshold)
            y_pred_cv = (y_prob_cv >= threshold).astype(int)
            cv_f1 = float(f1_score(y_te, y_pred_cv, zero_division=0))
            cv_auc = float(roc_auc_score(y_te, y_prob_cv)) if len(np.unique(y_te)) > 1 else 0.5

            # OOD 域外评估
            y_prob_ood = clf.predict_proba(X_ood_s)[:, 1]
            y_pred_ood = (y_prob_ood >= threshold).astype(int)
            ood_f1 = float(f1_score(y_ood, y_pred_ood, zero_division=0))
            ood_auc = float(roc_auc_score(y_ood, y_prob_ood)) if len(np.unique(y_ood)) > 1 else 0.5
            ood_precision = float(precision_score(y_ood, y_pred_ood, zero_division=0))
            ood_recall = float(recall_score(y_ood, y_pred_ood, zero_division=0))

            all_cv_f1.append(cv_f1)
            all_cv_auc.append(cv_auc)
            all_ood_f1.append(ood_f1)
            all_ood_auc.append(ood_auc)
            all_ood_precision.append(ood_precision)
            all_ood_recall.append(ood_recall)

            fold_details.append({
                "seed": seed, "fold": fold_idx,
                "cv_f1": cv_f1, "cv_auc": cv_auc,
                "ood_f1": ood_f1, "ood_auc": ood_auc,
                "ood_precision": ood_precision, "ood_recall": ood_recall,
                "threshold": threshold,
            })

            logger.info(
                "[seed=%d fold=%d] CV F1=%.4f AUC=%.4f | OOD F1=%.4f AUC=%.4f P=%.4f R=%.4f thresh=%.3f",
                seed, fold_idx, cv_f1, cv_auc, ood_f1, ood_auc,
                ood_precision, ood_recall, threshold,
            )

    def ci(vals: list[float]) -> tuple[float, float, float]:
        arr = np.array(vals)
        n = len(arr)
        m = float(arr.mean())
        s = float(arr.std(ddof=1)) if n > 1 else 0.0
        c = T_VALUE_95 * s / np.sqrt(n) if n > 1 else 0.0
        return m, s, c

    cv_f1_mean, cv_f1_std, cv_f1_ci = ci(all_cv_f1)
    cv_auc_mean, cv_auc_std, cv_auc_ci = ci(all_cv_auc)
    ood_f1_mean, ood_f1_std, ood_f1_ci = ci(all_ood_f1)
    ood_auc_mean, ood_auc_std, ood_auc_ci = ci(all_ood_auc)
    ood_p_mean, _, _ = ci(all_ood_precision)
    ood_r_mean, _, _ = ci(all_ood_recall)
    mean_threshold = float(np.mean(all_thresholds))

    result = {
        "n_evaluations": len(all_ood_f1),
        "cv_f1_mean": cv_f1_mean, "cv_f1_std": cv_f1_std, "cv_f1_ci95": cv_f1_ci,
        "cv_auc_mean": cv_auc_mean, "cv_auc_std": cv_auc_std, "cv_auc_ci95": cv_auc_ci,
        "ood_f1_mean": ood_f1_mean, "ood_f1_std": ood_f1_std, "ood_f1_ci95": ood_f1_ci,
        "ood_f1_ci_lower": ood_f1_mean - ood_f1_ci,
        "ood_f1_ci_upper": ood_f1_mean + ood_f1_ci,
        "ood_auc_mean": ood_auc_mean, "ood_auc_std": ood_auc_std, "ood_auc_ci95": ood_auc_ci,
        "ood_precision_mean": ood_p_mean,
        "ood_recall_mean": ood_r_mean,
        "mean_threshold": mean_threshold,
        "meets_ood_f1_target": ood_f1_mean >= TARGET_OOD_F1,
        "fold_details": fold_details,
    }

    logger.info("=" * 60)
    logger.info("M2 重训最终结果:")
    logger.info("  CV F1=%.4f±%.4f (CI95: %.4f~%.4f)", cv_f1_mean, cv_f1_std, cv_f1_mean - cv_f1_ci, cv_f1_mean + cv_f1_ci)
    logger.info("  CV AUC=%.4f±%.4f", cv_auc_mean, cv_auc_std)
    logger.info("  OOD F1=%.4f±%.4f (CI95: %.4f~%.4f) target≥%.2f → %s",
                ood_f1_mean, ood_f1_std, ood_f1_mean - ood_f1_ci, ood_f1_mean + ood_f1_ci,
                TARGET_OOD_F1, "✅" if result["meets_ood_f1_target"] else "❌")
    logger.info("  OOD AUC=%.4f±%.4f", ood_auc_mean, ood_auc_std)
    logger.info("  OOD Precision=%.4f Recall=%.4f thresh=%.3f", ood_p_mean, ood_r_mean, mean_threshold)
    logger.info("=" * 60)

    return result


def register_training_job(result: dict[str, Any]) -> None:
    """登记到 training_jobs.json."""
    if TRAINING_JOBS_PATH.exists():
        with TRAINING_JOBS_PATH.open("r", encoding="utf-8") as f:
            jobs = json.load(f)
    else:
        jobs = {}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_id = f"m2_text_bert_retrain_{timestamp}"

    jobs[job_id] = {
        "job_id": job_id,
        "status": "completed",
        "task": "M2_text_bert_retrain_phase2",
        "created_at": time.time(),
        "data_source": str(CORPUS_V2_PATH),
        "ood_source": str(OOD_V2_PATH),
        "n_train": 15000,
        "n_ood": 5000,
        "bert_model": BERT_MODEL_NAME,
        "classifier": "LogReg(C=1.0, class_weight=balanced)",
        "cv_f1_mean": result["cv_f1_mean"],
        "cv_auc_mean": result["cv_auc_mean"],
        "ood_f1_mean": result["ood_f1_mean"],
        "ood_f1_ci95": result["ood_f1_ci95"],
        "ood_auc_mean": result["ood_auc_mean"],
        "ood_precision": result["ood_precision_mean"],
        "ood_recall": result["ood_recall_mean"],
        "mean_threshold": result["mean_threshold"],
        "meets_ood_f1_target": result["meets_ood_f1_target"],
        "timestamp": timestamp,
    }

    with TRAINING_JOBS_PATH.open("w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)
    logger.info("实验已登记: %s", job_id)


if __name__ == "__main__":
    # 1. 加载数据
    train_df = load_v2_corpus()
    ood_df = load_ood_test()

    # 2. 提取 BERT embedding (带缓存)
    device = get_device()
    if device == "none":
        logger.error("torch 未安装, 无法运行 BERT")
        sys.exit(1)

    tokenizer, model = load_bert_model(device)

    train_texts = train_df["text"].tolist()
    ood_texts = ood_df["text"].tolist()

    X_train = get_or_extract_embeddings(train_texts, EMBEDDING_CACHE_TRAIN, tokenizer, model, device)
    X_ood = get_or_extract_embeddings(ood_texts, EMBEDDING_CACHE_OOD, tokenizer, model, device)

    y_train = train_df["phq9_binary"].values.astype(int)
    y_ood = ood_df["phq9_binary"].values.astype(int)
    groups = train_df["source_idx"].values if "source_idx" in train_df.columns else None

    # 3. CV + OOD 评估
    result = evaluate_cv_with_ood(X_train, y_train, groups, X_ood, y_ood)

    # 4. 登记实验
    register_training_job(result)

    print("\n" + "=" * 60)
    print("阶段二-M2 文本 BERT 重训最终结果:")
    print(f"  CV F1={result['cv_f1_mean']:.4f} AUC={result['cv_auc_mean']:.4f}")
    print(f"  OOD F1={result['ood_f1_mean']:.4f} (CI95 ±{result['ood_f1_ci95']:.4f}) target≥{TARGET_OOD_F1}: {'✅' if result['meets_ood_f1_target'] else '❌'}")
    print(f"  OOD AUC={result['ood_auc_mean']:.4f}")
    print(f"  OOD P={result['ood_precision_mean']:.4f} R={result['ood_recall_mean']:.4f}")
    print("=" * 60)
