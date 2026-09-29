"""训练真正的中英双语文本抑郁分类模型 (TF-IDF + LogisticRegression).

背景:
  - 生产文本主模型 (text_depression_classifier) 词表纯英文, 中文输入全部 OOV,
    验证显示中文域 AUC≈0.50 (D3 域外问题).
  - "双语回退" (improved_bilingual) 此前是主模型的字节级副本, 并非真双语.
  - 本脚本训练真双语模型: 中文语料 + 英文 Reddit 语料混合, jieba 中文分词,
    产出覆盖中英两域的新回退模型, 替换 models/text/improved_bilingual_*.

训练数据:
  - 中文: data/external/chinese_depression_corpus_v1.csv (8379 条, 含 D3+ 增强)
  - 英文: datasets/text/depression_dataset_reddit_cleaned.csv (7731 条)

评估:
  - 中英混合 80/20 stratified split (保留 200 条中文 original 做中文域 holdout)
  - 输出中文域 / 英文域分别指标

用法:
    python scripts/ml_training/train_bilingual_text.py
"""

from __future__ import annotations

import json
import logging
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("bilingual")

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.text_tokenizer import zh_bilingual_tokenize  # noqa: E402

ZH_CORPUS = REPO_ROOT / "data" / "external" / "chinese_depression_corpus_v1.csv"
EN_CORPUS = REPO_ROOT / "datasets" / "text" / "depression_dataset_reddit_cleaned.csv"

OUT_MODEL = BACKEND_ROOT / "models" / "text" / "improved_bilingual_model.pkl"
OUT_TFIDF = BACKEND_ROOT / "models" / "text" / "improved_bilingual_tfidf.pkl"
OUT_METRICS = BACKEND_ROOT / "models" / "text" / "improved_bilingual_metrics.json"

RANDOM_STATE = 42
MAX_FEATURES = 120000


def load_zh() -> pd.DataFrame:
    """返回 (augmented 训练子集, original 验证子集).

    防泄漏: v1 corpus 含 1275 条 original, verify 脚本以同文本评估;
    训练必须排除全部 original, original 全量作为中文域外验证集。
    """
    df = pd.read_csv(ZH_CORPUS)
    df = df[df["text"].str.len() >= 5].copy()
    df["label"] = df["phq9_binary"].astype(int)
    is_orig = df.get("augmentation", pd.Series(["original"] * len(df))).fillna("original") == "original"
    return df[~is_orig][["text", "label"]], df[is_orig][["text", "label"]].reset_index(drop=True)


def load_en() -> pd.DataFrame:
    from data_utils import clean_text  # noqa: PLC0415  (scripts/ml_training)

    df = pd.read_csv(EN_CORPUS)
    df = df.dropna(subset=["clean_text", "is_depression"]).copy()
    df["text"] = df["clean_text"].astype(str).map(clean_text)
    df["label"] = pd.to_numeric(df["is_depression"], errors="coerce").fillna(0).astype(int)
    df = df[df["label"].isin([0, 1])].drop_duplicates(subset=["text"])
    return df[["text", "label"]]


def evaluate(y_true, y_prob) -> dict:
    y_pred = (y_prob >= 0.5).astype(int)
    return {
        "n": int(len(y_true)),
        "positive_rate": float(np.mean(y_true)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "specificity": float(recall_score(1 - y_true, 1 - y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, y_prob)),
        "brier": float(np.mean((y_true - y_prob) ** 2)),
    }


def main() -> None:
    zh_train, zh_holdout = load_zh()
    en = load_en()
    logger.info("中文训练语料(增强): %d 条 (阳性率 %.1f%%)", len(zh_train), zh_train["label"].mean() * 100)
    logger.info("中文 original 域外验证: %d 条 (阳性率 %.1f%%)", len(zh_holdout), zh_holdout["label"].mean() * 100)
    logger.info("英文语料: %d 条 (阳性率 %.1f%%)", len(en), en["label"].mean() * 100)

    # 英文训练/评估独立切分 (评估集不参与训练)
    en_train, en_eval = train_test_split(
        en, test_size=0.2, random_state=RANDOM_STATE, stratify=en["label"],
    )

    df = pd.concat([zh_train, en_train], ignore_index=True)
    df = df.drop_duplicates(subset=["text"]).reset_index(drop=True)

    holdout = zh_holdout.copy()
    en_holdout = en_eval.reset_index(drop=True).copy()
    logger.info("训练: %d 条 (增强中文+英文train), 中文域外验证: %d 条 original, 英文域外验证: %d 条",
                len(df), len(holdout), len(en_holdout))

    X_train, X_val, y_train, y_val = train_test_split(
        df["text"], df["label"],
        test_size=0.2, random_state=RANDOM_STATE, stratify=df["label"],
    )

    tfidf = TfidfVectorizer(
        tokenizer=zh_bilingual_tokenize,
        lowercase=True,
        sublinear_tf=True,
        min_df=2,
        max_df=0.95,
        max_features=MAX_FEATURES,
        ngram_range=(1, 2),
    )
    X_train_vec = tfidf.fit_transform(X_train)
    logger.info("词表大小: %d", len(tfidf.vocabulary_))

    model = LogisticRegression(C=1.0, class_weight="balanced", max_iter=3000, random_state=RANDOM_STATE)
    model.fit(X_train_vec, y_train)

    # 域内验证
    X_val_vec = tfidf.transform(X_val)
    val_metrics = evaluate(np.asarray(y_val), model.predict_proba(X_val_vec)[:, 1])

    # 中文域外验证 (original 全量, 训练未见过)
    X_zh_vec = tfidf.transform(holdout["text"])
    zh_metrics = evaluate(holdout["label"].values, model.predict_proba(X_zh_vec)[:, 1])

    # 英文域外验证 (独立 20%, 训练未见过)
    X_en_vec = tfidf.transform(en_holdout["text"])
    en_metrics = evaluate(en_holdout["label"].values, model.predict_proba(X_en_vec)[:, 1])

    logger.info("混合域内 val: %s", val_metrics)
    logger.info("中文域外验证 (original 全量, 无泄漏): %s", zh_metrics)
    logger.info("英文域外验证 (独立 20%%, 无泄漏): %s", en_metrics)

    payload = {
        "version": "bilingual_v1",
        "trained_at": pd.Timestamp.now().isoformat(),
        "zh_corpus": str(ZH_CORPUS),
        "en_corpus": str(EN_CORPUS),
        "n_train": int(len(df)),
        "n_zh_holdout": int(len(holdout)),
        "n_en_holdout": int(len(en_holdout)),
        "vocab_size": len(tfidf.vocabulary_),
        "metrics_val_mixed": val_metrics,
        "metrics_zh_holdout": zh_metrics,
        "metrics_en_holdout": en_metrics,
        "eval_note": (
            "zh_holdout = 1275 条 original 全量 (训练仅用 v1 增强子集, 零泄漏); "
            "en_holdout = 独立 20% 切分"
        ),
        "notes": "真双语模型: jieba 中文分词 + 英文词元混合词表; 替换此前英文主模型的字节副本",
    }

    OUT_MODEL.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_MODEL, "wb") as f:
        pickle.dump(model, f)
    with open(OUT_TFIDF, "wb") as f:
        pickle.dump(tfidf, f)
    OUT_METRICS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # 重新生成 sha256 侧车 (加载时强制校验)
    try:
        from app.utils.checksum import write_sha256_sidecar
        write_sha256_sidecar(OUT_MODEL)
        write_sha256_sidecar(OUT_TFIDF)
    except Exception as exc:
        logger.warning("sha256 sidecar 生成失败: %s", exc)

    logger.info("产物已保存: %s / %s / %s", OUT_MODEL, OUT_TFIDF, OUT_METRICS)


if __name__ == "__main__":
    main()
