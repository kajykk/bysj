"""P2 BERT INT8 动态量化技术验证.

目标: 验证 INT8 动态量化对 BERT 的体积压缩与精度损失, 为 BERT 上线做准备.
验收 (计划 G7/G8):
  - 体积压缩 ≥ 50%
  - AUC 损失 < 0.5pt (量化前后 LogReg AUC 差)
  - BERT 单条 P95 ≤ 300ms

前提说明:
  - 生产 BERT 模型 (models/text/bert_text_classifier/) 尚不存在, 生产走 TF-IDF
  - M2 只保存分类头 pkl + embedding 缓存, 无完整 BERT 权重
  - 故本脚本对 HF 预训练 chinese-bert-wwm-ext 做量化技术验证
  - 动态量化仅 CPU 生效 (weight-only INT8), GPU 推理需静态量化/ONNX

方法:
  1. 加载 HF chinese-bert-wwm-ext (FP32)
  2. mmpsy 子集 (300 条) 提取 FP32 embedding → 5-fold LogReg AUC_baseline
  3. torch.quantization.quantize_dynamic 量化 BERT (INT8 Linear)
  4. 提取 INT8 embedding → 5-fold LogReg AUC_quantized
  5. 对比: 模型体积 (state_dict 字节数)、AUC 损失、单条延迟

Usage:
    python scripts/p2_bert_quantization.py
    python scripts/p2_bert_quantization.py --n-samples 500  # 调整样本数
"""

from __future__ import annotations

import argparse
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
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [P2] %(message)s")
logger = logging.getLogger("P2")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS_DIR = PROJECT_ROOT / "models" / "experiments"

MMPSY_DATA_PATH = PROJECT_ROOT / "data" / "external" / "mmpsy_scores.csv"
BERT_MODEL_NAME = "hfl/chinese-bert-wwm-ext"

N_FOLDS = 5
SEED = 42
MAX_LEN = 256
BATCH_SIZE = 16


def load_mmpsy_subset(n_samples: int) -> tuple[list[str], np.ndarray]:
    """加载 mmpsy 子集 (分层抽样保持阳性率)."""
    df = pd.read_csv(MMPSY_DATA_PATH)
    if "text" not in df.columns:
        df["text"] = df["audio_transcript"].astype(str).str.split("|").apply(
            lambda parts: " ".join(p.strip() for p in parts)
        )
    df = df[df["text"].str.len() >= 5].reset_index(drop=True)
    df["phq9_binary"] = df["phq9_binary"].astype(int)

    # 分层抽样: 按标签分层取 n_samples
    if n_samples < len(df):
        pos = df[df["phq9_binary"] == 1].sample(
            n=int(n_samples * df["phq9_binary"].mean()), random_state=SEED
        )
        neg = df[df["phq9_binary"] == 0].sample(
            n=n_samples - len(pos), random_state=SEED
        )
        df = pd.concat([pos, neg]).sample(frac=1, random_state=SEED).reset_index(drop=True)

    texts = df["text"].tolist()
    y = df["phq9_binary"].values
    logger.info(
        "mmpsy 子集: %d 样本, 阳性率=%.2f%%", len(y), y.mean() * 100
    )
    return texts, y


def extract_embeddings(
    texts: list[str], model: Any, tokenizer: Any, max_len: int = MAX_LEN,
    batch_size: int = BATCH_SIZE,
) -> np.ndarray:
    """提取 BERT [CLS] embedding (CPU, no grad)."""
    import torch
    from tqdm import tqdm

    all_emb = []
    model.eval()
    for i in tqdm(range(0, len(texts), batch_size), desc="embedding"):
        batch = texts[i:i + batch_size]
        enc = tokenizer(
            batch, padding=True, truncation=True, max_length=max_len,
            return_tensors="pt",
        )
        with torch.no_grad():
            out = model(**enc)
        cls = out.last_hidden_state[:, 0, :].cpu().numpy()
        all_emb.append(cls)
    return np.vstack(all_emb)


def cv_auc(X: np.ndarray, y: np.ndarray) -> dict[str, float]:
    """5-fold LogReg AUC (与 M2 feature_extraction 一致)."""
    aucs = []
    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)
    for tr, te in skf.split(X, y):
        scaler = StandardScaler()
        X_tr = scaler.fit_transform(X[tr])
        X_te = scaler.transform(X[te])
        clf = LogisticRegression(
            C=1.0, class_weight="balanced", max_iter=2000,
            random_state=SEED, solver="lbfgs",
        )
        clf.fit(X_tr, y[tr])
        prob = clf.predict_proba(X_te)[:, 1]
        aucs.append(float(roc_auc_score(y[te], prob)) if len(np.unique(y[te])) > 1 else 0.5)
    arr = np.array(aucs)
    return {
        "auc_mean": float(arr.mean()),
        "auc_std": float(arr.std(ddof=1)),
        "folds": aucs,
    }


def model_size_bytes(model: Any) -> int:
    """估算模型参数字节数 (state_dict, 跳过非张量量化参数)."""
    import torch
    total = 0
    for p in model.state_dict().values():
        # INT8 动态量化 state_dict 含 _dtype 等 dtype 标量, 需跳过
        if isinstance(p, torch.Tensor):
            total += p.numel() * p.element_size()
    return int(total)


def quantize_bert_ffn_only(model: Any) -> Any:
    """只量化 BERT FFN Linear (intermediate.dense + output.dense + attention.output.dense).

    保留注意力 QKV (query/key/value) 为 FP32, 避免注意力分布失真导致的严重精度损失.
    全 Linear 量化实验显示 AUC 损失 18.58pt (不可接受), FFN-only 预期损失 <0.5pt.
    """
    import torch
    layers = model.encoder.layer
    for layer in layers:
        # FFN: intermediate.dense (768->3072) + output.dense (3072->768)
        layer.intermediate.dense = torch.quantization.quantize_dynamic(
            layer.intermediate.dense, dtype=torch.qint8
        )
        layer.output.dense = torch.quantization.quantize_dynamic(
            layer.output.dense, dtype=torch.qint8
        )
        # attention.output.dense (768->768, 注意力输出投影, 非 QKV)
        layer.attention.output.dense = torch.quantization.quantize_dynamic(
            layer.attention.output.dense, dtype=torch.qint8
        )
    return model


def single_latency_ms(model: Any, tokenizer: Any, text: str, n_runs: int = 20) -> dict[str, float]:
    """单条推理延迟 (ms, warmup 后 n_runs 取 P50/P95)."""
    import torch

    # warmup 3 次
    for _ in range(3):
        enc = tokenizer(text, truncation=True, padding=True, max_length=MAX_LEN, return_tensors="pt")
        with torch.no_grad():
            _ = model(**enc)

    lats = []
    for _ in range(n_runs):
        enc = tokenizer(text, truncation=True, padding=True, max_length=MAX_LEN, return_tensors="pt")
        t0 = time.perf_counter()
        with torch.no_grad():
            _ = model(**enc)
        lats.append((time.perf_counter() - t0) * 1000)
    arr = np.array(lats)
    return {
        "p50_ms": float(np.percentile(arr, 50)),
        "p95_ms": float(np.percentile(arr, 95)),
        "mean_ms": float(arr.mean()),
    }


def run_p2(n_samples: int = 300, quant_mode: str = "ffn_only") -> dict[str, Any]:
    """P2 量化验证主流程.

    quant_mode: "all" 量化所有 Linear (含注意力 QKV, AUC 损失大);
                "ffn_only" 只量化 FFN (保留注意力, 推荐默认).
    """
    from transformers import AutoModel, AutoTokenizer
    import torch

    start = time.time()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.info("=" * 60)
    logger.info("P2 BERT INT8 动态量化验证 - 启动 (n_samples=%d, quant_mode=%s)", n_samples, quant_mode)
    logger.info("=" * 60)

    # 1. 加载 mmpsy 子集
    texts, y = load_mmpsy_subset(n_samples)

    # 2. 加载 FP32 BERT
    logger.info("加载 FP32 BERT: %s", BERT_MODEL_NAME)
    tokenizer = AutoTokenizer.from_pretrained(BERT_MODEL_NAME)
    model_fp32 = AutoModel.from_pretrained(BERT_MODEL_NAME)
    model_fp32.eval()
    fp32_size = model_size_bytes(model_fp32)
    logger.info("FP32 模型参数字节数: %d (%.1f MB)", fp32_size, fp32_size / 1024**2)

    # 3. FP32 embedding → AUC
    t0 = time.perf_counter()
    emb_fp32 = extract_embeddings(texts, model_fp32, tokenizer)
    fp32_extract_s = time.perf_counter() - t0
    logger.info("FP32 embedding 提取: %.1fs, shape=%s", fp32_extract_s, emb_fp32.shape)
    auc_fp32 = cv_auc(emb_fp32, y)
    logger.info("FP32 AUC=%.4f±%.4f", auc_fp32["auc_mean"], auc_fp32["auc_std"])

    # 4. FP32 延迟
    lat_fp32 = single_latency_ms(model_fp32, tokenizer, texts[0])
    logger.info("FP32 延迟: P50=%.1fms P95=%.1fms", lat_fp32["p50_ms"], lat_fp32["p95_ms"])

    # 5. 动态量化 INT8
    if quant_mode == "ffn_only":
        logger.info("FFN-only 量化 BERT → INT8 (保留注意力 QKV FP32)")
        t0 = time.perf_counter()
        model_int8 = quantize_bert_ffn_only(model_fp32)
    else:
        logger.info("全 Linear 量化 BERT → INT8 (含注意力 QKV)")
        t0 = time.perf_counter()
        model_int8 = torch.quantization.quantize_dynamic(
            model_fp32, {torch.nn.Linear}, dtype=torch.qint8
        )
    model_int8.eval()
    quant_s = time.perf_counter() - t0
    int8_size = model_size_bytes(model_int8)
    logger.info("INT8 模型参数字节数: %d (%.1f MB), 量化耗时=%.1fs", int8_size, int8_size / 1024**2, quant_s)

    # 6. INT8 embedding → AUC
    t0 = time.perf_counter()
    emb_int8 = extract_embeddings(texts, model_int8, tokenizer)
    int8_extract_s = time.perf_counter() - t0
    logger.info("INT8 embedding 提取: %.1fs", int8_extract_s)
    auc_int8 = cv_auc(emb_int8, y)
    logger.info("INT8 AUC=%.4f±%.4f", auc_int8["auc_mean"], auc_int8["auc_std"])

    # 7. INT8 延迟
    lat_int8 = single_latency_ms(model_int8, tokenizer, texts[0])
    logger.info("INT8 延迟: P50=%.1fms P95=%.1fms", lat_int8["p50_ms"], lat_int8["p95_ms"])

    # 8. 汇总
    size_compression = (1 - int8_size / fp32_size) * 100
    auc_loss = auc_fp32["auc_mean"] - auc_int8["auc_mean"]
    # AUC 损失用 pt (百分点): 1 pt = 0.01
    auc_loss_pt = auc_loss * 100

    result = {
        "experiment_id": f"p2_bert_quantization_{quant_mode}_{timestamp}",
        "task": "P2 BERT INT8 动态量化技术验证",
        "quant_mode": quant_mode,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - start, 1),
        "bert_model": BERT_MODEL_NAME,
        "n_samples": int(len(y)),
        "pos_rate": float(y.mean()),
        "fp32": {
            "model_size_bytes": fp32_size,
            "model_size_mb": round(fp32_size / 1024**2, 2),
            "auc_mean": auc_fp32["auc_mean"],
            "auc_std": auc_fp32["auc_std"],
            "auc_folds": auc_fp32["folds"],
            "extract_time_s": round(fp32_extract_s, 1),
            "latency_p50_ms": round(lat_fp32["p50_ms"], 2),
            "latency_p95_ms": round(lat_fp32["p95_ms"], 2),
        },
        "int8": {
            "model_size_bytes": int8_size,
            "model_size_mb": round(int8_size / 1024**2, 2),
            "auc_mean": auc_int8["auc_mean"],
            "auc_std": auc_int8["auc_std"],
            "auc_folds": auc_int8["folds"],
            "extract_time_s": round(int8_extract_s, 1),
            "latency_p50_ms": round(lat_int8["p50_ms"], 2),
            "latency_p95_ms": round(lat_int8["p95_ms"], 2),
            "quant_time_s": round(quant_s, 2),
        },
        "comparison": {
            "size_compression_pct": round(size_compression, 2),
            "auc_loss": round(auc_loss, 4),
            "auc_loss_pt": round(auc_loss_pt, 2),
            "latency_p95_speedup": round(lat_fp32["p95_ms"] / lat_int8["p95_ms"], 2) if lat_int8["p95_ms"] > 0 else 0,
            "embedding_diff_mean": float(np.abs(emb_fp32 - emb_int8).mean()),
        },
        "acceptance": {
            "size_compression_target_pct": 50.0,
            "auc_loss_target_pt": 0.5,
            "bert_p95_target_ms": 300.0,
            "meets_size": size_compression >= 50.0,
            "meets_auc_loss": auc_loss_pt < 0.5,
            "meets_latency": lat_int8["p95_ms"] <= 300.0,
            "all_passed": (
                size_compression >= 50.0
                and auc_loss_pt < 0.5
                and lat_int8["p95_ms"] <= 300.0
            ),
        },
        "notes": (
            "动态量化仅 CPU 生效 (weight-only INT8); GPU 推理需静态量化/ONNX. "
            "生产 BERT 模型尚不存在, 此为 HF 预训练模型量化技术验证. "
            "AUC 基于 feature_extraction LogReg (非 M2 fine_tune)."
        ),
    }

    # 保存
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    exp_path = EXPERIMENTS_DIR / f"p2_bert_quantization_{quant_mode}_{timestamp}.json"
    with open(exp_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    logger.info("结果已保存: %s", exp_path)

    # 打印汇总
    print("\n" + "=" * 60)
    print("P2 BERT INT8 动态量化验证 - 结果汇总")
    print("=" * 60)
    print(f"模型: {BERT_MODEL_NAME} | 样本: {len(y)}")
    print(f"\n体积: FP32={result['fp32']['model_size_mb']}MB → INT8={result['int8']['model_size_mb']}MB")
    print(f"      压缩率={size_compression:.1f}% (目标≥50%) {'✓' if result['acceptance']['meets_size'] else '✗'}")
    print(f"\nAUC:  FP32={auc_fp32['auc_mean']:.4f} → INT8={auc_int8['auc_mean']:.4f}")
    print(f"      损失={auc_loss_pt:.2f}pt (目标<0.5pt) {'✓' if result['acceptance']['meets_auc_loss'] else '✗'}")
    print(f"\n延迟: FP32 P95={lat_fp32['p95_ms']:.1f}ms → INT8 P95={lat_int8['p95_ms']:.1f}ms")
    print(f"      (目标≤300ms) {'✓' if result['acceptance']['meets_latency'] else '✗'}")
    print(f"\n总体验收: {'✓ 全部通过' if result['acceptance']['all_passed'] else '✗ 部分未达标'}")
    print("=" * 60)

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="P2 BERT INT8 量化验证")
    parser.add_argument("--n-samples", type=int, default=300, help="mmpsy 子集样本数 (默认 300)")
    parser.add_argument(
        "--quant-mode", choices=["ffn_only", "all"], default="ffn_only",
        help="量化模式: ffn_only (保留注意力, 默认) / all (全 Linear, AUC 损失大)",
    )
    args = parser.parse_args()
    run_p2(n_samples=args.n_samples, quant_mode=args.quant_mode)
