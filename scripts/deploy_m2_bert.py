"""M2 BERT 文本模型部署脚本 (阶段三).

在 M2 重训验证 OOD F1 ≥ 0.85 后, 训练最终模型并保存为可部署产物.

部署策略: feature extraction (冻结 BERT) + LogReg 分类头
  - BERT 模型: hfl/chinese-bert-wwm-ext (从本地缓存加载, 不联网)
  - 分类头: LogReg(C=1.0, class_weight=balanced) + StandardScaler
  - 阈值: 在训练集上优化 F1

产物保存到 models/text/bert_text_classifier/:
  - config.json: 模型配置 (BERT 名称, 阈值, 模式)
  - classifier.pkl: LogReg 分类器
  - scaler.pkl: StandardScaler
  - metadata.json: 训练指标和部署信息

model_engine.py 加载此产物, 执行:
  1. BERT feature extraction (CLS embedding)
  2. Scaler 标准化
  3. LogReg 预测
  4. 阈值判决

Usage:
    python scripts/deploy_m2_bert.py
"""

from __future__ import annotations

import json
import logging
import pickle
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [M2-Deploy] %(message)s")
logger = logging.getLogger("M2-Deploy")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORPUS_V2_PATH = PROJECT_ROOT / "data" / "external" / "chinese_depression_corpus_v2.csv"
OOD_V2_PATH = PROJECT_ROOT / "data" / "external" / "ood_test_set_v2.csv"

# M2 重训的 embedding 缓存
EMBEDDING_CACHE_TRAIN = PROJECT_ROOT / "models" / "artifacts" / "text_m2_bert_retrain" / "bert_embeddings_train_v2.npy"
EMBEDDING_CACHE_OOD = PROJECT_ROOT / "models" / "artifacts" / "text_m2_bert_retrain" / "bert_embeddings_ood_v2.npy"

# 部署产物目录 (backend 运行目录, backend/models/text/bert_text_classifier)
DEPLOY_DIR = PROJECT_ROOT / "backend" / "models" / "text" / "bert_text_classifier"

BERT_MODEL_NAME = "hfl/chinese-bert-wwm-ext"
MAX_SEQ_LEN = 256


def find_best_f1_threshold(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """在训练集上找最佳 F1 阈值."""
    from sklearn.metrics import precision_recall_curve
    precision, recall, thresholds = precision_recall_curve(y_true, y_prob)
    f1_scores = 2 * precision * recall / (precision + recall + 1e-8)
    best_idx = np.argmax(f1_scores[:-1])
    return float(thresholds[best_idx])


def main() -> None:
    from tqdm import tqdm

    start_time = time.time()
    logger.info("=" * 60)
    logger.info("M2 BERT 部署 - 训练最终模型")
    logger.info("=" * 60)

    # 1. 加载数据
    train_df = pd.read_csv(CORPUS_V2_PATH)
    train_df = train_df[train_df["text"].str.len() >= 5].reset_index(drop=True)
    train_df["phq9_binary"] = train_df["phq9_binary"].astype(int)

    ood_df = pd.read_csv(OOD_V2_PATH)
    ood_df = ood_df[ood_df["text"].str.len() >= 5].reset_index(drop=True)
    ood_df["phq9_binary"] = ood_df["phq9_binary"].astype(int)

    logger.info("训练集: %d 样本, 阳性率=%.2f%%", len(train_df), train_df["phq9_binary"].mean() * 100)
    logger.info("OOD 测试集: %d 样本, 阳性率=%.2f%%", len(ood_df), ood_df["phq9_binary"].mean() * 100)

    # 2. 加载 BERT embedding (复用 M2 重训缓存)
    if EMBEDDING_CACHE_TRAIN.exists() and EMBEDDING_CACHE_OOD.exists():
        logger.info("复用 M2 重训 embedding 缓存")
        X_train = np.load(EMBEDDING_CACHE_TRAIN)
        X_ood = np.load(EMBEDDING_CACHE_OOD)
    else:
        logger.error("M2 重训 embedding 缓存不存在, 请先运行 m2_text_bert_retrain.py")
        sys.exit(1)

    logger.info("训练 embedding: %s", X_train.shape)
    logger.info("OOD embedding: %s", X_ood.shape)

    y_train = train_df["phq9_binary"].values.astype(int)
    y_ood = ood_df["phq9_binary"].values.astype(int)

    # 3. 训练最终模型 (全量训练集)
    logger.info("训练 LogReg 分类器 (全量 %d 样本)", len(y_train))
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)

    classifier = LogisticRegression(
        C=1.0, class_weight="balanced", max_iter=2000,
        random_state=42, solver="lbfgs",
    )
    classifier.fit(X_train_scaled, y_train)

    # 4. 阈值优化 (训练集自身预测)
    y_prob_train = classifier.predict_proba(X_train_scaled)[:, 1]
    threshold = find_best_f1_threshold(y_train, y_prob_train)
    logger.info("最优阈值: %.4f", threshold)

    # 5. OOD 评估
    X_ood_scaled = scaler.transform(X_ood)
    y_prob_ood = classifier.predict_proba(X_ood_scaled)[:, 1]
    y_pred_ood = (y_prob_ood >= threshold).astype(int)

    ood_f1 = float(f1_score(y_ood, y_pred_ood, zero_division=0))
    ood_auc = float(roc_auc_score(y_ood, y_prob_ood)) if len(np.unique(y_ood)) > 1 else 0.5
    ood_precision = float(precision_score(y_ood, y_pred_ood, zero_division=0))
    ood_recall = float(recall_score(y_ood, y_pred_ood, zero_division=0))

    logger.info("=" * 60)
    logger.info("OOD 评估结果:")
    logger.info("  F1=%.4f (target≥0.85): %s", ood_f1, "✅" if ood_f1 >= 0.85 else "❌")
    logger.info("  AUC=%.4f", ood_auc)
    logger.info("  Precision=%.4f Recall=%.4f", ood_precision, ood_recall)
    logger.info("=" * 60)

    # 6. 保存部署产物
    DEPLOY_DIR.mkdir(parents=True, exist_ok=True)

    # config.json (模型配置)
    config = {
        "model_type": "bert_feature_extraction",
        "bert_model_name": BERT_MODEL_NAME,
        "max_seq_len": MAX_SEQ_LEN,
        "classifier_type": "logreg",
        "classifier_params": {
            "C": 1.0, "class_weight": "balanced", "max_iter": 2000,
            "random_state": 42, "solver": "lbfgs",
        },
        "threshold": threshold,
        "embedding_dim": int(X_train.shape[1]),
        "feature": "cls_embedding",
        "deployed_at": datetime.now().isoformat(timespec="seconds"),
    }
    with open(DEPLOY_DIR / "config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    # classifier.pkl
    with open(DEPLOY_DIR / "classifier.pkl", "wb") as f:
        pickle.dump(classifier, f)

    # scaler.pkl
    with open(DEPLOY_DIR / "scaler.pkl", "wb") as f:
        pickle.dump(scaler, f)

    # metadata.json
    metadata = {
        "experiment_id": f"m2_bert_deploy_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "task": "M2_bert_production_deploy",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "n_train": len(y_train),
        "n_ood": len(y_ood),
        "ood_f1": ood_f1,
        "ood_auc": ood_auc,
        "ood_precision": ood_precision,
        "ood_recall": ood_recall,
        "threshold": threshold,
        "meets_ood_f1_target": ood_f1 >= 0.85,
        "bert_model": BERT_MODEL_NAME,
        "classifier": "LogReg(C=1.0, class_weight=balanced)",
        "embedding_dim": int(X_train.shape[1]),
        "total_time_s": round(time.time() - start_time, 1),
    }
    with open(DEPLOY_DIR / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    logger.info("部署产物已保存: %s", DEPLOY_DIR)
    logger.info("  config.json / classifier.pkl / scaler.pkl / metadata.json")

    # 7. 验证产物可加载
    logger.info("验证产物可加载...")
    with open(DEPLOY_DIR / "classifier.pkl", "rb") as f:
        clf_check = pickle.load(f)
    with open(DEPLOY_DIR / "scaler.pkl", "rb") as f:
        scaler_check = pickle.load(f)
    with open(DEPLOY_DIR / "config.json", "r", encoding="utf-8") as f:
        config_check = json.load(f)

    # 模拟推理
    test_emb = X_ood[:1]
    test_scaled = scaler_check.transform(test_emb)
    test_prob = clf_check.predict_proba(test_scaled)[0, 1]
    test_pred = int(test_prob >= config_check["threshold"])
    logger.info("✅ 推理验证通过: prob=%.4f pred=%d threshold=%.4f",
                test_prob, test_pred, config_check["threshold"])

    logger.info("=" * 60)
    logger.info("M2 BERT 部署完成!")
    logger.info("  OOD F1=%.4f AUC=%.4f", ood_f1, ood_auc)
    logger.info("  阈值=%.4f", threshold)
    logger.info("  产物目录=%s", DEPLOY_DIR)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
