"""P2 BERT ONNX INT8 动态量化技术验证 (G8).

目标: 通过 ONNX Runtime 量化路径达成真实磁盘压缩.
  - 体积压缩 ≥ 50% (FP32 ONNX vs INT8 ONNX 磁盘字节数)
  - AUC 损失 < 0.5pt (FP32 vs INT8 5-fold LogReg AUC 差×100)
  - BERT 单条 P95 ≤ 300ms

背景:
  - 现有 p2_bert_quantization.py 使用 torch.quantization.quantize_dynamic,
    state_dict 字节计算未反映真实压缩 (390MB→390MB, 压缩 0%).
  - 本脚本改用 ONNX 路径, 比较磁盘文件字节数 (真实压缩).

方法:
  1. 加载 HF chinese-bert-wwm-ext (FP32)
  2. 导出为 ONNX (opset 14, 动态 batch/序列维度)
  3. onnxruntime.quantization.quantize_dynamic 动态量化 (QInt8)
  4. 对比 FP32 ONNX vs INT8 ONNX 磁盘文件大小 (真实压缩)
  5. onnxruntime.InferenceSession 推理, 提取 [CLS] embedding
  6. mmpsy 子集 (300 条) 5-fold LogReg AUC 对比
  7. 单条延迟 P50/P95

回退方案 B (若 ONNX 路径失败):
  - torch.quantization.quantize_dynamic (全 Linear) + torch.save state_dict 比较磁盘大小
  - 结果中记录实际采用方案

Usage:
    python scripts/p2_bert_onnx_quantize.py
    python scripts/p2_bert_onnx_quantize.py --n-samples 300
"""

from __future__ import annotations

import argparse
import json
import logging
import os
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [P2-ONNX] %(message)s")
logger = logging.getLogger("P2-ONNX")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS_DIR = PROJECT_ROOT / "models" / "experiments"
TRAINING_JOBS_PATH = PROJECT_ROOT / "models" / "training_jobs.json"
ONNX_ARTIFACTS_DIR = PROJECT_ROOT / "models" / "artifacts" / "bert_onnx"
FALLBACK_ARTIFACTS_DIR = PROJECT_ROOT / "models" / "artifacts" / "bert_torch_quant"

MMPSY_DATA_PATH = PROJECT_ROOT / "data" / "external" / "mmpsy_scores.csv"
BERT_MODEL_NAME = "hfl/chinese-bert-wwm-ext"

N_FOLDS = 5
SEED = 42
MAX_LEN = 256
BATCH_SIZE = 16
OPSET = 14


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------
def load_mmpsy_subset(n_samples: int) -> tuple[list[str], np.ndarray]:
    """加载 mmpsy 子集 (分层抽样保持阳性率)."""
    df = pd.read_csv(MMPSY_DATA_PATH)
    if "text" not in df.columns:
        df["text"] = df["audio_transcript"].astype(str).str.split("|").apply(
            lambda parts: " ".join(p.strip() for p in parts)
        )
    df = df[df["text"].str.len() >= 5].reset_index(drop=True)
    df["phq9_binary"] = df["phq9_binary"].astype(int)

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
    logger.info("mmpsy 子集: %d 样本, 阳性率=%.2f%%", len(y), y.mean() * 100)
    return texts, y


# ---------------------------------------------------------------------------
# 评估工具
# ---------------------------------------------------------------------------
def cv_auc(X: np.ndarray, y: np.ndarray) -> dict[str, Any]:
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
    return {"auc_mean": float(arr.mean()), "auc_std": float(arr.std(ddof=1)), "folds": aucs}


def register_training_job(job_id: str, task: str, **extra: Any) -> None:
    """登记实验到 training_jobs.json."""
    if TRAINING_JOBS_PATH.exists():
        with open(TRAINING_JOBS_PATH, "r", encoding="utf-8") as f:
            jobs = json.load(f)
    else:
        jobs = {}
    entry = {
        "job_id": job_id,
        "status": "completed",
        "task": task,
        "created_at": time.time(),
        **extra,
    }
    jobs[job_id] = entry
    with open(TRAINING_JOBS_PATH, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)
    logger.info("已登记 training_jobs.json: %s", job_id)


# ---------------------------------------------------------------------------
# ONNX 路径 (主方案)
# ---------------------------------------------------------------------------
def export_bert_to_onnx(model: Any, tokenizer: Any, onnx_path: Path) -> None:
    """导出 BERT (last_hidden_state) 为 ONNX, opset 14, 动态 batch/seq."""
    import torch

    class BertOnnxWrapper(torch.nn.Module):
        def __init__(self, m: Any) -> None:
            super().__init__()
            self.model = m

        def forward(self, input_ids, attention_mask, token_type_ids):
            out = self.model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                token_type_ids=token_type_ids,
            )
            return out.last_hidden_state

    wrapper = BertOnnxWrapper(model).eval()
    dummy_input_ids = torch.randint(0, tokenizer.vocab_size, (2, 8), dtype=torch.long)
    dummy_attention_mask = torch.ones((2, 8), dtype=torch.long)
    dummy_token_type_ids = torch.zeros((2, 8), dtype=torch.long)

    onnx_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("导出 ONNX: opset=%d, path=%s", OPSET, onnx_path)
    torch.onnx.export(
        wrapper,
        (dummy_input_ids, dummy_attention_mask, dummy_token_type_ids),
        str(onnx_path),
        input_names=["input_ids", "attention_mask", "token_type_ids"],
        output_names=["last_hidden_state"],
        dynamic_axes={
            "input_ids": {0: "batch", 1: "sequence"},
            "attention_mask": {0: "batch", 1: "sequence"},
            "token_type_ids": {0: "batch", 1: "sequence"},
            "last_hidden_state": {0: "batch", 1: "sequence"},
        },
        opset_version=OPSET,
        do_constant_folding=True,
    )
    logger.info("ONNX 导出完成: %.1f MB", onnx_path.stat().st_size / 1024**2)


def quantize_onnx_dynamic(fp32_path: Path, int8_path: Path, weight_type_name: str = "QInt8") -> None:
    """ONNX 动态量化 (weight-only INT8, 激活保持 FP32)."""
    from onnxruntime.quantization import quantize_dynamic, QuantType

    qtype = QuantType.QInt8 if weight_type_name == "QInt8" else QuantType.QUInt8
    logger.info("ONNX 动态量化: weight_type=%s, %s -> %s",
                weight_type_name, fp32_path.name, int8_path.name)
    quantize_dynamic(
        model_input=str(fp32_path),
        model_output=str(int8_path),
        weight_type=qtype,
    )
    logger.info("INT8 ONNX 量化完成: %.1f MB", int8_path.stat().st_size / 1024**2)


def make_onnx_session(onnx_path: Path):
    import onnxruntime as ort

    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(
        str(onnx_path), sess_options=so, providers=["CPUExecutionProvider"]
    )


def _build_feed(session, enc) -> dict[str, np.ndarray]:
    input_names = [i.name for i in session.get_inputs()]
    feed: dict[str, np.ndarray] = {}
    if "input_ids" in input_names:
        feed["input_ids"] = enc["input_ids"].astype(np.int64)
    if "attention_mask" in input_names:
        feed["attention_mask"] = enc["attention_mask"].astype(np.int64)
    if "token_type_ids" in input_names:
        feed["token_type_ids"] = enc["token_type_ids"].astype(np.int64)
    return feed


def extract_embeddings_onnx(
    texts: list[str], session: Any, tokenizer: Any,
    max_len: int = MAX_LEN, batch_size: int = BATCH_SIZE,
) -> np.ndarray:
    """ONNX 推理提取 [CLS] embedding."""
    from tqdm import tqdm

    all_emb = []
    for i in tqdm(range(0, len(texts), batch_size), desc="onnx-embedding"):
        batch = texts[i:i + batch_size]
        enc = tokenizer(
            batch, padding=True, truncation=True, max_length=max_len, return_tensors="np"
        )
        feed = _build_feed(session, enc)
        out = session.run(None, feed)[0]  # last_hidden_state
        cls = out[:, 0, :]
        all_emb.append(cls)
    return np.vstack(all_emb)


def single_latency_onnx_ms(
    session: Any, tokenizer: Any, text: str, n_runs: int = 20
) -> dict[str, float]:
    """单条 ONNX 推理延迟 (ms, warmup 后 n_runs 取 P50/P95)."""
    enc = tokenizer(text, truncation=True, padding=True, max_length=MAX_LEN, return_tensors="np")
    feed = _build_feed(session, enc)
    for _ in range(3):
        session.run(None, feed)
    lats = []
    for _ in range(n_runs):
        t0 = time.perf_counter()
        session.run(None, feed)
        lats.append((time.perf_counter() - t0) * 1000)
    arr = np.array(lats)
    return {
        "p50_ms": float(np.percentile(arr, 50)),
        "p95_ms": float(np.percentile(arr, 95)),
        "mean_ms": float(arr.mean()),
    }


def run_onnx_path(
    texts: list[str], y: np.ndarray, tokenizer: Any, model: Any, timestamp: str
) -> dict[str, Any]:
    """ONNX 主方案: 导出 → 量化 → 推理 → AUC/延迟."""
    start = time.time()
    fp32_onnx = ONNX_ARTIFACTS_DIR / "bert_fp32.onnx"
    int8_onnx = ONNX_ARTIFACTS_DIR / "bert_int8.onnx"

    # 1. 导出 FP32 ONNX
    export_bert_to_onnx(model, tokenizer, fp32_onnx)
    fp32_size = fp32_onnx.stat().st_size

    # 2. 动态量化 INT8 ONNX
    quantize_onnx_dynamic(fp32_onnx, int8_onnx, weight_type_name="QInt8")
    int8_size = int8_onnx.stat().st_size

    # 3. FP32 ONNX 推理
    logger.info("FP32 ONNX 推理...")
    sess_fp32 = make_onnx_session(fp32_onnx)
    t0 = time.perf_counter()
    emb_fp32 = extract_embeddings_onnx(texts, sess_fp32, tokenizer)
    fp32_extract_s = time.perf_counter() - t0
    auc_fp32 = cv_auc(emb_fp32, y)
    logger.info("FP32 ONNX AUC=%.4f±%.4f", auc_fp32["auc_mean"], auc_fp32["auc_std"])
    lat_fp32 = single_latency_onnx_ms(sess_fp32, tokenizer, texts[0])
    logger.info("FP32 ONNX 延迟: P50=%.1fms P95=%.1fms", lat_fp32["p50_ms"], lat_fp32["p95_ms"])

    # 4. INT8 ONNX 推理
    logger.info("INT8 ONNX 推理...")
    sess_int8 = make_onnx_session(int8_onnx)
    t0 = time.perf_counter()
    emb_int8 = extract_embeddings_onnx(texts, sess_int8, tokenizer)
    int8_extract_s = time.perf_counter() - t0
    auc_int8 = cv_auc(emb_int8, y)
    logger.info("INT8 ONNX AUC=%.4f±%.4f", auc_int8["auc_mean"], auc_int8["auc_std"])
    lat_int8 = single_latency_onnx_ms(sess_int8, tokenizer, texts[0])
    logger.info("INT8 ONNX 延迟: P50=%.1fms P95=%.1fms", lat_int8["p50_ms"], lat_int8["p95_ms"])

    size_compression = (1 - int8_size / fp32_size) * 100
    auc_loss = auc_fp32["auc_mean"] - auc_int8["auc_mean"]
    auc_loss_pt = auc_loss * 100

    result = {
        "approach": "ONNX Runtime dynamic quantization (QInt8, weight-only)",
        "opset": OPSET,
        "fp32": {
            "onnx_path": str(fp32_onnx),
            "file_size_bytes": fp32_size,
            "file_size_mb": round(fp32_size / 1024**2, 2),
            "auc_mean": auc_fp32["auc_mean"],
            "auc_std": auc_fp32["auc_std"],
            "auc_folds": auc_fp32["folds"],
            "extract_time_s": round(fp32_extract_s, 1),
            "latency_p50_ms": round(lat_fp32["p50_ms"], 2),
            "latency_p95_ms": round(lat_fp32["p95_ms"], 2),
        },
        "int8": {
            "onnx_path": str(int8_onnx),
            "file_size_bytes": int8_size,
            "file_size_mb": round(int8_size / 1024**2, 2),
            "quant_type": "QInt8",
            "auc_mean": auc_int8["auc_mean"],
            "auc_std": auc_int8["auc_std"],
            "auc_folds": auc_int8["folds"],
            "extract_time_s": round(int8_extract_s, 1),
            "latency_p50_ms": round(lat_int8["p50_ms"], 2),
            "latency_p95_ms": round(lat_int8["p95_ms"], 2),
        },
        "comparison": {
            "size_compression_pct": round(size_compression, 2),
            "auc_loss": round(auc_loss, 4),
            "auc_loss_pt": round(auc_loss_pt, 2),
            "latency_p95_speedup": (
                round(lat_fp32["p95_ms"] / lat_int8["p95_ms"], 2)
                if lat_int8["p95_ms"] > 0 else 0
            ),
            "embedding_diff_mean": float(np.abs(emb_fp32 - emb_int8).mean()),
        },
        "elapsed_s": round(time.time() - start, 1),
    }

    result["acceptance"] = {
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
    }
    return result


# ---------------------------------------------------------------------------
# 回退方案 B (torch.save state_dict 磁盘字节比较)
# ---------------------------------------------------------------------------
def extract_embeddings_torch(
    texts: list[str], model: Any, tokenizer: Any,
    max_len: int = MAX_LEN, batch_size: int = BATCH_SIZE,
) -> np.ndarray:
    """torch 推理提取 [CLS] embedding (CPU)."""
    import torch
    from tqdm import tqdm

    all_emb = []
    model.eval()
    for i in tqdm(range(0, len(texts), batch_size), desc="torch-embedding"):
        batch = texts[i:i + batch_size]
        enc = tokenizer(batch, padding=True, truncation=True, max_length=max_len, return_tensors="pt")
        with torch.no_grad():
            out = model(**enc)
        cls = out.last_hidden_state[:, 0, :].cpu().numpy()
        all_emb.append(cls)
    return np.vstack(all_emb)


def single_latency_torch_ms(
    model: Any, tokenizer: Any, text: str, n_runs: int = 20
) -> dict[str, float]:
    """单条 torch 推理延迟 (ms)."""
    import torch

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


def run_fallback_torch_path(
    texts: list[str], y: np.ndarray, tokenizer: Any, model_fp32: Any, timestamp: str
) -> dict[str, Any]:
    """回退方案 B: torch 动态量化 (全 Linear) + torch.save state_dict 磁盘字节比较."""
    import torch

    start = time.time()
    FALLBACK_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    fp32_pkl = FALLBACK_ARTIFACTS_DIR / "bert_fp32_state_dict.pt"
    int8_pkl = FALLBACK_ARTIFACTS_DIR / "bert_int8_state_dict.pt"

    logger.info("[回退] 保存 FP32 state_dict (torch.save)...")
    torch.save(model_fp32.state_dict(), str(fp32_pkl))
    fp32_size = fp32_pkl.stat().st_size

    logger.info("[回退] torch 动态量化 (全 Linear, qint8)...")
    t0 = time.perf_counter()
    model_int8 = torch.quantization.quantize_dynamic(
        model_fp32, {torch.nn.Linear}, dtype=torch.qint8
    )
    model_int8.eval()
    quant_s = time.perf_counter() - t0
    torch.save(model_int8.state_dict(), str(int8_pkl))
    int8_size = int8_pkl.stat().st_size
    logger.info("[回退] FP32=%.1fMB INT8=%.1fMB 量化耗时=%.1fs",
                fp32_size / 1024**2, int8_size / 1024**2, quant_s)

    # FP32 embedding
    t0 = time.perf_counter()
    emb_fp32 = extract_embeddings_torch(texts, model_fp32, tokenizer)
    fp32_extract_s = time.perf_counter() - t0
    auc_fp32 = cv_auc(emb_fp32, y)
    lat_fp32 = single_latency_torch_ms(model_fp32, tokenizer, texts[0])

    # INT8 embedding
    t0 = time.perf_counter()
    emb_int8 = extract_embeddings_torch(texts, model_int8, tokenizer)
    int8_extract_s = time.perf_counter() - t0
    auc_int8 = cv_auc(emb_int8, y)
    lat_int8 = single_latency_torch_ms(model_int8, tokenizer, texts[0])

    size_compression = (1 - int8_size / fp32_size) * 100
    auc_loss = auc_fp32["auc_mean"] - auc_int8["auc_mean"]
    auc_loss_pt = auc_loss * 100

    return {
        "approach": "FALLBACK: torch.quantization.quantize_dynamic (全 Linear qint8) + torch.save 磁盘字节",
        "fp32": {
            "state_dict_path": str(fp32_pkl),
            "file_size_bytes": fp32_size,
            "file_size_mb": round(fp32_size / 1024**2, 2),
            "auc_mean": auc_fp32["auc_mean"],
            "auc_std": auc_fp32["auc_std"],
            "auc_folds": auc_fp32["folds"],
            "extract_time_s": round(fp32_extract_s, 1),
            "latency_p50_ms": round(lat_fp32["p50_ms"], 2),
            "latency_p95_ms": round(lat_fp32["p95_ms"], 2),
        },
        "int8": {
            "state_dict_path": str(int8_pkl),
            "file_size_bytes": int8_size,
            "file_size_mb": round(int8_size / 1024**2, 2),
            "quant_type": "torch.qint8 (dynamic, 全 Linear)",
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
            "latency_p95_speedup": (
                round(lat_fp32["p95_ms"] / lat_int8["p95_ms"], 2)
                if lat_int8["p95_ms"] > 0 else 0
            ),
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
        "elapsed_s": round(time.time() - start, 1),
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def run(n_samples: int = 300) -> dict[str, Any]:
    from transformers import AutoModel, AutoTokenizer

    start = time.time()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.info("=" * 60)
    logger.info("P2 BERT ONNX INT8 动态量化验证 (G8) - 启动")
    logger.info("n_samples=%d, opset=%d", n_samples, OPSET)
    logger.info("=" * 60)

    texts, y = load_mmpsy_subset(n_samples)

    # 加载 FP32 BERT
    logger.info("加载 FP32 BERT: %s", BERT_MODEL_NAME)
    tokenizer = AutoTokenizer.from_pretrained(BERT_MODEL_NAME)
    model = AutoModel.from_pretrained(BERT_MODEL_NAME)
    model.eval()

    # 尝试 ONNX 主方案, 失败则回退方案 B
    onnx_error: str | None = None
    try:
        logger.info("尝试 ONNX 主方案...")
        quant_result = run_onnx_path(texts, y, tokenizer, model, timestamp)
        approach_used = "onnx"
    except Exception as e:
        onnx_error = f"{type(e).__name__}: {e}"
        logger.warning("ONNX 主方案失败 (%s), 回退到方案 B (torch state_dict 磁盘字节)...", onnx_error)
        import traceback
        traceback.print_exc()
        quant_result = run_fallback_torch_path(texts, y, tokenizer, model, timestamp)
        approach_used = "fallback_torch"

    fp32_block = quant_result["fp32"]
    int8_block = quant_result["int8"]
    comp = quant_result["comparison"]
    acc = quant_result["acceptance"]

    size_compression = comp["size_compression_pct"]
    auc_loss_pt = comp["auc_loss_pt"]
    int8_p95 = int8_block["latency_p95_ms"]

    result = {
        "experiment_id": f"p2_bert_onnx_{timestamp}",
        "task": "P2 BERT ONNX INT8 动态量化验证 (G8)",
        "approach_used": approach_used,
        "onnx_error": onnx_error,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - start, 1),
        "bert_model": BERT_MODEL_NAME,
        "n_samples": int(len(y)),
        "pos_rate": float(y.mean()),
        "fp32": fp32_block,
        "int8": int8_block,
        "comparison": comp,
        "acceptance": acc,
        "notes": (
            "G8 验证: ONNX Runtime 动态量化 (weight-only INT8, 激活 FP32). "
            "体积压缩基于磁盘文件字节数 (真实压缩). "
            "AUC 基于 feature_extraction LogReg (5-fold). "
            "推理在 CPUExecutionProvider 上 (ONNX) / CPU (torch)."
        ),
    }
    if "opset" in quant_result:
        result["opset"] = quant_result["opset"]

    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    exp_path = EXPERIMENTS_DIR / f"p2_bert_onnx_{timestamp}.json"
    with open(exp_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    logger.info("结果已保存: %s", exp_path)

    register_training_job(
        result["experiment_id"],
        "P2_bert_onnx_quantize",
        approach=approach_used,
        fp32_mb=fp32_block["file_size_mb"],
        int8_mb=int8_block["file_size_mb"],
        size_compression_pct=round(size_compression, 2),
        auc_loss_pt=round(auc_loss_pt, 2),
        int8_p95_ms=round(int8_p95, 2),
        meets_g8=acc["all_passed"],
        timestamp=timestamp,
    )

    print("\n" + "=" * 60)
    print("P2 BERT ONNX INT8 动态量化验证 (G8) - 结果汇总")
    print("=" * 60)
    print(f"模型: {BERT_MODEL_NAME} | 样本: {len(y)} | 方案: {approach_used}")
    if onnx_error:
        print(f"ONNX 错误: {onnx_error}")
    print(f"\n体积: FP32={fp32_block['file_size_mb']}MB → INT8={int8_block['file_size_mb']}MB")
    print(f"      压缩率={size_compression:.1f}% (目标≥50%) {'✓' if acc['meets_size'] else '✗'}")
    print(f"\nAUC:  FP32={fp32_block['auc_mean']:.4f} → INT8={int8_block['auc_mean']:.4f}")
    print(f"      损失={auc_loss_pt:.2f}pt (目标<0.5pt) {'✓' if acc['meets_auc_loss'] else '✗'}")
    print(f"\n延迟: FP32 P95={fp32_block['latency_p95_ms']:.1f}ms → INT8 P95={int8_p95:.1f}ms")
    print(f"      (目标≤300ms) {'✓' if acc['meets_latency'] else '✗'}")
    print(f"\n总体验收: {'✓ 全部通过' if acc['all_passed'] else '✗ 部分未达标'}")
    print("=" * 60)

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="P2 BERT ONNX INT8 量化验证 (G8)")
    parser.add_argument("--n-samples", type=int, default=300, help="mmpsy 子集样本数 (默认 300)")
    args = parser.parse_args()
    run(n_samples=args.n_samples)
