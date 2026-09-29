"""为 1275 mmpsy 样本生成 BERT embedding 缓存 (M4 融合重训依赖).

数据: data/external/mmpsy_scores.csv (1275 条中文校园语料)
输出: models/artifacts/text_m2_bert/bert_embeddings_n1275.npy
模型: hfl/chinese-bert-wwm-ext (与 M2/M4 一致)

Usage:
    python scripts/generate_bert_cache_n1275.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [BERT-Cache] %(message)s")
logger = logging.getLogger("BERT-Cache")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MMPSY_PATH = PROJECT_ROOT / "data" / "external" / "mmpsy_scores.csv"
CACHE_PATH = PROJECT_ROOT / "models" / "artifacts" / "text_m2_bert" / "bert_embeddings_n1275.npy"

BERT_MODEL_NAME = "hfl/chinese-bert-wwm-ext"
MAX_SEQ_LEN = 256
BERT_BATCH_SIZE = 16


def get_device() -> str:
    import torch
    if torch.cuda.is_available():
        logger.info("GPU: %s", torch.cuda.get_device_name(0))
        return "cuda"
    logger.info("使用 CPU")
    return "cpu"


def extract_embeddings(texts: list[str], device: str) -> np.ndarray:
    import torch
    from tqdm import tqdm
    from transformers import AutoModel, AutoTokenizer

    logger.info("加载 BERT: %s", BERT_MODEL_NAME)
    tokenizer = AutoTokenizer.from_pretrained(BERT_MODEL_NAME)
    model = AutoModel.from_pretrained(BERT_MODEL_NAME)
    if device == "cuda":
        model = model.to(device)
    model.eval()

    all_emb = []
    for i in tqdm(range(0, len(texts), BERT_BATCH_SIZE), desc="BERT embedding"):
        batch = texts[i:i + BERT_BATCH_SIZE]
        encoded = tokenizer(batch, padding=True, truncation=True, max_length=MAX_SEQ_LEN, return_tensors="pt")
        if device == "cuda":
            encoded = {k: v.to(device) for k, v in encoded.items()}
        with torch.no_grad():
            outputs = model(**encoded)
        cls = outputs.last_hidden_state[:, 0, :].cpu().numpy()
        all_emb.append(cls)

    embeddings = np.vstack(all_emb)
    logger.info("embedding shape=%s", embeddings.shape)
    return embeddings


def main() -> None:
    if CACHE_PATH.exists():
        logger.info("缓存已存在, 跳过: %s", CACHE_PATH)
        return

    df = pd.read_csv(MMPSY_PATH)
    logger.info("加载: %d 样本", len(df))

    text_col = "audio_transcript" if "audio_transcript" in df.columns else "text"
    texts = df[text_col].fillna("").astype(str).tolist()
    texts = [t if len(t) >= 5 else "无文本" for t in texts]
    logger.info("文本列: %s, 平均长度=%.0f", text_col, np.mean([len(t) for t in texts]))

    device = get_device()
    embeddings = extract_embeddings(texts, device)

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.save(CACHE_PATH, embeddings)
    logger.info("缓存已保存: %s", CACHE_PATH)

    # 校验样本数
    assert embeddings.shape[0] == 1275, f"样本数不匹配: {embeddings.shape[0]} != 1275"
    logger.info("✅ 校验通过: 1275 样本, %d 维", embeddings.shape[1])


if __name__ == "__main__":
    main()
