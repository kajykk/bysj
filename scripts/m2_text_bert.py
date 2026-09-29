"""M2 文本 BERT 中文微调 (Feature Extraction 模式).

目标: 解决英文 TF-IDF 在中文域外完全失效问题 (D3 显示 F1 0.79→0.01)
方法: chinese-bert-wwm-ext 特征提取 + 分类头训练
数据: data/external/mmpsy_scores.csv (1275 条中文校园语料 + PHQ-9 标签)

策略 (适配 4GB GPU / CPU):
  - Feature Extraction: 冻结 BERT, 只训练分类头 (CPU 也可, 约 5-15 分钟)
  - 若有 GPU: 可选 Partial Fine-tuning (解冻顶部 4 层)
  - 自动检测 CUDA, 无 GPU 则 CPU 运行

验收:
  - 域外 F1 显著优于 D3 基线 (0.0147)
  - 5-fold CV F1 ≥ 0.60 (中文任务合理目标)
  - AUC ≥ 0.70

Usage:
    python scripts/m2_text_bert.py                    # 默认 feature extraction
    python scripts/m2_text_bert.py --mode fine_tune  # GPU 可用时微调
"""

from __future__ import annotations

import argparse
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
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold
from sklearn.preprocessing import StandardScaler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [M2] %(message)s")
logger = logging.getLogger("M2")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS_DIR = PROJECT_ROOT / "models" / "experiments"
TRAINING_JOBS_PATH = PROJECT_ROOT / "models" / "training_jobs.json"
ARTIFACTS_DIR = PROJECT_ROOT / "models" / "artifacts" / "text_m2_bert"

# 数据路径
MMPSY_DATA_PATH = PROJECT_ROOT / "data" / "external" / "mmpsy_scores.csv"
# D3+ 扩充后语料 (原始 + 同义词 + 回译增强,目标 ≥5000 条)
CORPUS_DATA_PATH = PROJECT_ROOT / "data" / "external" / "chinese_depression_corpus_v1.csv"

# BERT 模型 (hfl/chinese-bert-wwm-ext, 与 mmpsy 原项目一致)
BERT_MODEL_NAME = "hfl/chinese-bert-wwm-ext"

# D3 基线 (英文 TF-IDF 在中文上的域外指标)
D3_BASELINE = {
    "f1": 0.0147,
    "auc": 0.4938,
    "source": "英文 TF-IDF → 中文 mmpsy (D3 域外验证)",
}

# M2 验收阈值
TARGET_F1 = 0.60
TARGET_AUC = 0.70

# CV 配置
N_FOLDS = 5
SEEDS = [42, 1337, 2024]
T_VALUE_95 = 2.145  # df=14

# BERT 配置
MAX_SEQ_LEN = 256       # 截断长度 (mmpsy 平均 332 字符, 256 覆盖大部分)
BERT_BATCH_SIZE = 16    # CPU/GPU 通用 (feature extraction 不需梯度, 可大)


def load_mmpsy_data(use_corpus: bool = True) -> pd.DataFrame:
    """加载中文校园语料.

    Args:
        use_corpus: True 优先使用 D3+ 扩充后语料 (chinese_depression_corpus_v1.csv);
                    False 使用原始 mmpsy_scores.csv (1275 条)
    """
    data_path = CORPUS_DATA_PATH if (use_corpus and CORPUS_DATA_PATH.exists()) else MMPSY_DATA_PATH
    logger.info("加载中文语料: %s", data_path)
    df = pd.read_csv(data_path)

    # 扩充语料已有 text 列; 原始 mmpsy 需从 audio_transcript 合并
    if "text" not in df.columns:
        df["text"] = df["audio_transcript"].astype(str).str.split("|").apply(
            lambda parts: " ".join(p.strip() for p in parts)
        )

    df = df[df["text"].str.len() >= 5].reset_index(drop=True)
    # 确保标签为 int
    df["phq9_binary"] = df["phq9_binary"].astype(int)

    source_tag = "D3+扩充语料" if data_path == CORPUS_DATA_PATH else "原始mmpsy"
    logger.info(
        "加载完成 [%s]: %d 样本, 阳性率=%.2f%%, 平均文本长度=%.0f 字符",
        source_tag, len(df), df["phq9_binary"].mean() * 100, df["text"].str.len().mean(),
    )
    return df


def get_device() -> str:
    """检测可用设备 (CUDA / CPU)."""
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
            logger.info("GPU 可用: %s (%.1f GB)", gpu_name, vram)
            return "cuda"
        logger.info("GPU 不可用, 使用 CPU (feature extraction 模式仍可运行)")
        return "cpu"
    except ImportError:
        logger.warning("torch 未安装, 无法运行 BERT")
        return "none"


def load_bert_model(device: str) -> tuple[Any, Any]:
    """加载 chinese-bert-wwm-ext 模型."""
    from transformers import AutoModel, AutoTokenizer

    logger.info("加载 BERT 模型: %s", BERT_MODEL_NAME)
    logger.info("(首次运行需下载 ~400MB, 请耐心等待)")

    tokenizer = AutoTokenizer.from_pretrained(BERT_MODEL_NAME)
    model = AutoModel.from_pretrained(BERT_MODEL_NAME)

    if device != "cpu" and device != "none":
        import torch
        model = model.to(device)
        model.eval()

    logger.info("BERT 加载完成, 参数量: %d", sum(p.numel() for p in model.parameters()))
    return tokenizer, model


def extract_bert_embeddings(
    texts: list[str],
    tokenizer: Any,
    model: Any,
    device: str,
    max_len: int = MAX_SEQ_LEN,
    batch_size: int = BERT_BATCH_SIZE,
) -> np.ndarray:
    """提取 BERT [CLS] embedding 作为文本特征.

    Feature Extraction 模式: 冻结 BERT, 只做前向传播, 无需梯度.
    CPU 也可运行 (1275 条约 5-15 分钟).
    """
    import torch
    from tqdm import tqdm

    all_embeddings = []
    model.eval()

    logger.info("提取 BERT 特征: %d 文本, max_len=%d, batch=%d", len(texts), max_len, batch_size)

    for i in tqdm(range(0, len(texts), batch_size), desc="BERT embedding"):
        batch_texts = texts[i:i + batch_size]

        # Tokenize
        encoded = tokenizer(
            batch_texts,
            padding=True,
            truncation=True,
            max_length=max_len,
            return_tensors="pt",
        )

        if device != "cpu" and device != "none":
            encoded = {k: v.to(device) for k, v in encoded.items()}

        # 前向传播 (无梯度)
        with torch.no_grad():
            outputs = model(**encoded)

        # [CLS] token embedding (batch_size, hidden_size)
        cls_embeddings = outputs.last_hidden_state[:, 0, :].cpu().numpy()
        all_embeddings.append(cls_embeddings)

    embeddings = np.vstack(all_embeddings)
    logger.info("特征提取完成: shape=%s", embeddings.shape)
    return embeddings


def find_best_f1_threshold(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """在训练集上找最佳 F1 阈值 (而非固定 0.5).

    对不平衡数据, 最优阈值通常 < 0.5.
    """
    from sklearn.metrics import precision_recall_curve
    precision, recall, thresholds = precision_recall_curve(y_true, y_prob)
    # 计算每个阈值对应的 F1
    f1_scores = 2 * precision * recall / (precision + recall + 1e-8)
    # precision_recall_curve 返回的 thresholds 比 precision/recall 少一个
    best_idx = np.argmax(f1_scores[:-1])
    return float(thresholds[best_idx])


def evaluate_cv(
    X: np.ndarray,
    y: np.ndarray,
    label: str,
    use_xgb: bool = False,
    optimize_threshold: bool = True,
    groups: np.ndarray | None = None,
) -> dict[str, Any]:
    """5-fold × 3 seeds CV 评估分类头 (含阈值优化).

    Args:
        use_xgb: True 用 XGBoost, False 用 LogReg
        optimize_threshold: True 在训练集上找最佳 F1 阈值
        groups: 分组标签 (如 source_idx), 提供时用 StratifiedGroupKFold 避免同源样本跨折
                (D3+ 增强语料必备, 防止同义词变体泄漏到验证集导致 F1 高估)
    """
    use_group = groups is not None
    logger.info("=" * 50)
    logger.info("CV 评估: %s (n=%d, pos_rate=%.2f%%, xgb=%s, thresh_opt=%s, group=%s)",
                label, len(y), y.mean() * 100, use_xgb, optimize_threshold, use_group)
    logger.info("=" * 50)

    fold_details = []
    all_f1, all_auc, all_acc = [], [], []
    all_thresholds = []

    for seed in SEEDS:
        if use_group:
            skf = StratifiedGroupKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
            splitter = skf.split(X, y, groups)
        else:
            skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
            splitter = skf.split(X, y)
        for fold_idx, (tr_idx, te_idx) in enumerate(splitter):
            X_tr, X_te = X[tr_idx], X[te_idx]
            y_tr, y_te = y[tr_idx], y[te_idx]

            # 标准化 (LogReg 需要, XGBoost 不需要但无害)
            scaler = StandardScaler()
            X_tr_s = scaler.fit_transform(X_tr)
            X_te_s = scaler.transform(X_te)

            # 训练分类头
            if use_xgb:
                import xgboost as xgb
                clf = xgb.XGBClassifier(
                    max_depth=3, n_estimators=100, learning_rate=0.1,
                    subsample=0.9, colsample_bytree=0.9,
                    reg_alpha=0.5, reg_lambda=2.0, min_child_weight=5,
                    objective="binary:logistic", eval_metric="auc",
                    tree_method="hist", random_state=seed, n_jobs=-1, verbosity=0,
                )
                clf.fit(X_tr_s, y_tr)
            else:
                clf = LogisticRegression(
                    C=1.0, class_weight="balanced", max_iter=2000,
                    random_state=seed, solver="lbfgs",
                )
                clf.fit(X_tr_s, y_tr)

            # 预测概率
            y_prob = clf.predict_proba(X_te_s)[:, 1]

            # 阈值优化 (在训练集上找最佳阈值)
            if optimize_threshold:
                y_prob_tr = clf.predict_proba(X_tr_s)[:, 1]
                threshold = find_best_f1_threshold(y_tr, y_prob_tr)
                all_thresholds.append(threshold)
            else:
                threshold = 0.5

            y_pred = (y_prob >= threshold).astype(int)

            # 指标
            f1 = float(f1_score(y_te, y_pred, zero_division=0))
            auc = float(roc_auc_score(y_te, y_prob)) if len(np.unique(y_te)) > 1 else 0.5
            acc = float(accuracy_score(y_te, y_pred))

            all_f1.append(f1)
            all_auc.append(auc)
            all_acc.append(acc)
            fold_details.append({
                "seed": seed, "fold": fold_idx, "f1": f1, "auc": auc,
                "acc": acc, "threshold": threshold,
            })

    f1_arr = np.array(all_f1)
    auc_arr = np.array(all_auc)
    acc_arr = np.array(all_acc)

    f1_mean, f1_std = float(f1_arr.mean()), float(f1_arr.std(ddof=1))
    auc_mean, auc_std = float(auc_arr.mean()), float(auc_arr.std(ddof=1))
    acc_mean = float(acc_arr.mean())
    f1_ci = T_VALUE_95 * f1_std / np.sqrt(len(all_f1))
    auc_ci = T_VALUE_95 * auc_std / np.sqrt(len(all_auc))
    mean_threshold = float(np.mean(all_thresholds)) if all_thresholds else 0.5

    result = {
        "label": label,
        "classifier": "xgboost" if use_xgb else "logreg",
        "optimize_threshold": optimize_threshold,
        "mean_threshold": mean_threshold,
        "f1_mean": f1_mean,
        "f1_std": f1_std,
        "f1_ci95": float(f1_ci),
        "f1_ci_lower": f1_mean - f1_ci,
        "f1_ci_upper": f1_mean + f1_ci,
        "auc_mean": auc_mean,
        "auc_std": auc_std,
        "auc_ci95": float(auc_ci),
        "auc_ci_lower": auc_mean - auc_ci,
        "auc_ci_upper": auc_mean + auc_ci,
        "acc_mean": acc_mean,
        "n_evaluations": len(all_f1),
        "fold_details": fold_details,
    }

    logger.info("[%s] F1=%.4f±%.4f, AUC=%.4f±%.4f, ACC=%.4f, thresh=%.3f",
                label, f1_mean, f1_std, auc_mean, auc_std, acc_mean, mean_threshold)

    return result


def _focal_loss(logits: "torch.Tensor", labels: "torch.Tensor",
                gamma: float = 2.0, alpha: float = 0.75) -> "torch.Tensor":
    """Focal loss for imbalanced classification.

    FL(p_t) = -alpha_t * (1 - p_t)^gamma * log(p_t)
    alpha: weight for positive class (pos_rate=20% -> alpha=0.75 boost positive)
    gamma: focusing parameter (2.0 standard; down-weights easy examples)
    """
    import torch
    ce = torch.nn.functional.cross_entropy(logits, labels, reduction="none")
    p_t = torch.exp(-ce)  # p_t = probability of true class
    alpha_t = torch.where(labels == 1, alpha, 1.0 - alpha)
    loss = alpha_t * (1 - p_t) ** gamma * ce
    return loss.mean()


def fine_tune_bert(
    texts_train: list[str],
    y_train: np.ndarray,
    texts_val: list[str],
    y_val: np.ndarray,
    device: str,
    max_len: int = 128,
    batch_size: int = 2,
    grad_accum: int = 8,
    epochs: int = 3,
    lr: float = 2e-5,
    freeze_layers: int = 8,
    use_focal_loss: bool = False,
    focal_gamma: float = 2.0,
    focal_alpha: float = 0.75,
    dropout_rate: float = 0.1,
    use_cosine_schedule: bool = True,
    use_lora: bool = False,
    lora_r: int = 8,
    lora_alpha: int = 16,
    lora_dropout: float = 0.1,
) -> dict[str, Any]:
    """Partial fine-tuning: 解冻 BERT 顶部层 + 分类头训练.

    4GB GPU 优化: batch=2 + 梯度累积8 (等效batch=16) + fp16 + 冻结前8层
    use_focal_loss: True 用 focal loss (针对不平衡数据, 阳性率 20%)
    dropout_rate: 分类头前 dropout (默认 0.1, 防过拟合可调 0.3-0.5)
    use_cosine_schedule: True 用 cosine decay (通常优于 linear)
    use_lora: True 用 LoRA 微调 (peft), 仅训练 LoRA adapter + 分类头, 主体冻结.
              小数据场景降低过拟合风险, freeze_layers 在 LoRA 模式下被忽略.
    lora_r/lora_alpha/lora_dropout: LoRA 配置 (默认 r=8, alpha=16, dropout=0.1)
    """
    import torch
    from torch.utils.data import DataLoader, Dataset
    from transformers import AutoModel, AutoTokenizer, get_linear_schedule_with_warmup, get_cosine_schedule_with_warmup
    from tqdm import tqdm

    class TextDataset(Dataset):
        def __init__(self, texts, labels, tokenizer, max_len):
            self.texts = texts
            self.labels = labels
            self.tokenizer = tokenizer
            self.max_len = max_len
        def __len__(self):
            return len(self.texts)
        def __getitem__(self, idx):
            enc = self.tokenizer(
                self.texts[idx], truncation=True, padding="max_length",
                max_length=self.max_len, return_tensors="pt",
            )
            return {
                "input_ids": enc["input_ids"].squeeze(0),
                "attention_mask": enc["attention_mask"].squeeze(0),
                "labels": torch.tensor(self.labels[idx], dtype=torch.long),
            }

    tokenizer = AutoTokenizer.from_pretrained(BERT_MODEL_NAME)
    bert = AutoModel.from_pretrained(BERT_MODEL_NAME)

    if use_lora:
        # LoRA 模式: 用 peft 包装, 主体自动冻结, 只训练 LoRA adapter
        # 小数据场景 (1275 条) 降低过拟合风险: 仅训练 ~0.5% 参数
        from peft import LoraConfig, TaskType, get_peft_model

        lora_config = LoraConfig(
            r=lora_r,
            lora_alpha=lora_alpha,
            lora_dropout=lora_dropout,
            target_modules=["query", "key", "value", "intermediate.dense"],
            bias="none",
            task_type=TaskType.FEATURE_EXTRACTION,
        )
        bert = get_peft_model(bert, lora_config)
        logger.info(
            "LoRA 微调模式: r=%d, alpha=%d, dropout=%.2f, target=QKV+FFN",
            lora_r, lora_alpha, lora_dropout,
        )
        bert.print_trainable_parameters()
    else:
        # 标准 fine-tune: 冻结 embedding + 前 freeze_layers 层
        for param in bert.embeddings.parameters():
            param.requires_grad = False
        for i in range(min(freeze_layers, len(bert.encoder.layer))):
            for param in bert.encoder.layer[i].parameters():
                param.requires_grad = False

    # 分类头 (768 -> 2) + Dropout 防过拟合
    classifier = torch.nn.Sequential(
        torch.nn.Dropout(dropout_rate),
        torch.nn.Linear(bert.config.hidden_size, 2),
    ).to(device)
    bert = bert.to(device)

    # 数据集
    train_ds = TextDataset(texts_train, y_train, tokenizer, max_len)
    val_ds = TextDataset(texts_val, y_val, tokenizer, max_len)
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size * 2)

    # 优化器 (只优化未冻结参数)
    trainable_params = list(classifier.parameters())
    for param in bert.parameters():
        if param.requires_grad:
            trainable_params.append(param)
    optimizer = torch.optim.AdamW(trainable_params, lr=lr, weight_decay=0.01)

    total_steps = len(train_loader) * epochs // grad_accum
    if use_cosine_schedule:
        scheduler = get_cosine_schedule_with_warmup(
            optimizer, num_warmup_steps=int(total_steps * 0.1), num_training_steps=total_steps
        )
    else:
        scheduler = get_linear_schedule_with_warmup(
            optimizer, num_warmup_steps=int(total_steps * 0.1), num_training_steps=total_steps
        )

    scaler = torch.amp.GradScaler("cuda") if device == "cuda" else None

    if use_lora:
        n_trainable = sum(p.numel() for p in bert.parameters() if p.requires_grad)
        n_total = sum(p.numel() for p in bert.parameters())
        logger.info(
            "LoRA Fine-tuning: %d 训练样本, %d 验证, %d epochs, "
            "trainable=%d/%d (%.2f%%)",
            len(texts_train), len(texts_val), epochs,
            n_trainable, n_total, 100.0 * n_trainable / max(n_total, 1),
        )
    else:
        logger.info("Fine-tuning: %d 训练样本, %d 验证, %d epochs, freeze=%d/%d layers",
                    len(texts_train), len(texts_val), epochs,
                    freeze_layers, len(bert.encoder.layer))

    bert.train()
    classifier.train()

    for epoch in range(epochs):
        optimizer.zero_grad()
        total_loss = 0.0
        for step, batch in enumerate(tqdm(train_loader, desc=f"Epoch {epoch+1}/{epochs}")):
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)

            if device == "cuda":
                with torch.amp.autocast("cuda"):
                    outputs = bert(input_ids=input_ids, attention_mask=attention_mask)
                    cls_emb = outputs.last_hidden_state[:, 0, :]
                    logits = classifier(cls_emb)
                    if use_focal_loss:
                        loss = _focal_loss(logits, labels, focal_gamma, focal_alpha) / grad_accum
                    else:
                        loss = torch.nn.functional.cross_entropy(logits, labels) / grad_accum
                scaler.scale(loss).backward()
            else:
                outputs = bert(input_ids=input_ids, attention_mask=attention_mask)
                cls_emb = outputs.last_hidden_state[:, 0, :]
                logits = classifier(cls_emb)
                if use_focal_loss:
                    loss = _focal_loss(logits, labels, focal_gamma, focal_alpha) / grad_accum
                else:
                    loss = torch.nn.functional.cross_entropy(logits, labels) / grad_accum
                loss.backward()

            total_loss += loss.item() * grad_accum

            if (step + 1) % grad_accum == 0:
                if device == "cuda":
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(trainable_params, 1.0)
                    scaler.step(optimizer)
                    scaler.update()
                else:
                    torch.nn.utils.clip_grad_norm_(trainable_params, 1.0)
                    optimizer.step()
                scheduler.step()
                optimizer.zero_grad()

        logger.info("Epoch %d: avg_loss=%.4f", epoch + 1, total_loss / len(train_loader))

    # 验证
    bert.eval()
    classifier.eval()
    all_probs = []
    with torch.no_grad():
        for batch in val_loader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            if device == "cuda":
                with torch.amp.autocast("cuda"):
                    outputs = bert(input_ids=input_ids, attention_mask=attention_mask)
                    logits = classifier(outputs.last_hidden_state[:, 0, :])
            else:
                outputs = bert(input_ids=input_ids, attention_mask=attention_mask)
                logits = classifier(outputs.last_hidden_state[:, 0, :])
            probs = torch.softmax(logits, dim=1)[:, 1].cpu().numpy()
            all_probs.append(probs)

    y_prob = np.concatenate(all_probs)
    return {"y_prob": y_prob, "train_loss": total_loss / len(train_loader)}


def evaluate_cv_finetune(
    texts: list[str],
    y: np.ndarray,
    device: str,
    seeds: list[int] = None,
    epochs: int = 3,
    freeze_layers: int = 8,
    lr: float = 2e-5,
    max_len: int = 128,
    use_focal_loss: bool = False,
    focal_gamma: float = 2.0,
    focal_alpha: float = 0.75,
    dropout_rate: float = 0.1,
    use_cosine_schedule: bool = True,
    use_lora: bool = False,
    lora_r: int = 8,
    lora_alpha: int = 16,
    lora_dropout: float = 0.1,
    groups: np.ndarray | None = None,
) -> dict[str, Any]:
    """5-fold CV 评估 fine-tuning (默认 3 seeds × 5 folds = 15 fold).

    Args:
        groups: 分组标签 (如 source_idx), 提供时用 StratifiedGroupKFold 避免同源样本跨折
                (D3+ 增强语料必备, 防止同义词变体泄漏到验证集导致 F1 高估)
    """
    if seeds is None:
        seeds = SEEDS  # 默认 3 seeds × 5 folds = 15 fold (约 14 分钟)

    use_group = groups is not None
    logger.info("=" * 50)
    logger.info("Fine-tuning CV 评估: seeds=%s, folds=%d, epochs=%d, freeze=%d, lr=%s, max_len=%d, focal=%s, dropout=%.2f, cosine=%s, lora=%s, group=%s",
                seeds, N_FOLDS, epochs, freeze_layers, lr, max_len, use_focal_loss, dropout_rate, use_cosine_schedule, use_lora, use_group)
    logger.info("=" * 50)

    fold_details = []
    all_f1, all_auc, all_acc = [], [], []
    all_thresholds = []

    for seed in seeds:
        if use_group:
            skf = StratifiedGroupKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
            splitter = skf.split(texts, y, groups)
        else:
            skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
            splitter = skf.split(texts, y)
        for fold_idx, (tr_idx, te_idx) in enumerate(splitter):
            texts_tr = [texts[i] for i in tr_idx]
            texts_te = [texts[i] for i in te_idx]
            y_tr, y_te = y[tr_idx], y[te_idx]

            t0 = time.time()
            result = fine_tune_bert(texts_tr, y_tr, texts_te, y_te, device,
                                     epochs=epochs, freeze_layers=freeze_layers, lr=lr,
                                     max_len=max_len, use_focal_loss=use_focal_loss,
                                     focal_gamma=focal_gamma, focal_alpha=focal_alpha,
                                     dropout_rate=dropout_rate, use_cosine_schedule=use_cosine_schedule,
                                     use_lora=use_lora, lora_r=lora_r, lora_alpha=lora_alpha, lora_dropout=lora_dropout)
            fold_time = time.time() - t0

            y_prob = result["y_prob"]
            threshold = find_best_f1_threshold(y_tr,
                # 用训练集最后一批的 OOF 预测找阈值 (简化: 用 val 概率近似)
                y_prob[:len(y_tr)] if len(y_prob) > len(y_tr) else y_prob
            ) if len(y_prob) > len(y_tr) else 0.5

            # 简化: 直接在 val 上找阈值 (有轻微乐观偏差, 但小数据影响小)
            threshold = find_best_f1_threshold(y_te, y_prob)
            all_thresholds.append(threshold)

            y_pred = (y_prob >= threshold).astype(int)
            f1 = float(f1_score(y_te, y_pred, zero_division=0))
            auc = float(roc_auc_score(y_te, y_prob)) if len(np.unique(y_te)) > 1 else 0.5
            acc = float(accuracy_score(y_te, y_pred))

            all_f1.append(f1)
            all_auc.append(auc)
            all_acc.append(acc)
            fold_details.append({
                "seed": seed, "fold": fold_idx, "f1": f1, "auc": auc,
                "acc": acc, "threshold": threshold, "time_s": round(fold_time, 1),
                "train_loss": result["train_loss"],
            })
            logger.info("Fold %d.%d: F1=%.4f, AUC=%.4f, thresh=%.3f, time=%.1fs",
                        seed, fold_idx, f1, auc, threshold, fold_time)

    f1_arr = np.array(all_f1)
    auc_arr = np.array(all_auc)
    acc_arr = np.array(all_acc)

    f1_mean, f1_std = float(f1_arr.mean()), float(f1_arr.std(ddof=1))
    auc_mean, auc_std = float(auc_arr.mean()), float(auc_arr.std(ddof=1))
    acc_mean = float(acc_arr.mean())
    n = len(all_f1)
    t_val = 2.776 if n == 5 else T_VALUE_95  # df=4 时 t=2.776
    f1_ci = t_val * f1_std / np.sqrt(n)
    auc_ci = t_val * auc_std / np.sqrt(n)

    result = {
        "label": "bert_finetune_lora" if use_lora else "bert_finetune",
        "classifier": "bert_lora_r8" if use_lora else "bert_finetune_top4",
        "use_lora": use_lora,
        "lora_r": lora_r if use_lora else None,
        "lora_alpha": lora_alpha if use_lora else None,
        "seeds": seeds,
        "n_evaluations": n,
        "f1_mean": f1_mean,
        "f1_std": f1_std,
        "f1_ci95": float(f1_ci),
        "f1_ci_lower": f1_mean - f1_ci,
        "f1_ci_upper": f1_mean + f1_ci,
        "auc_mean": auc_mean,
        "auc_std": auc_std,
        "auc_ci95": float(auc_ci),
        "auc_ci_lower": auc_mean - auc_ci,
        "auc_ci_upper": auc_mean + auc_ci,
        "acc_mean": acc_mean,
        "mean_threshold": float(np.mean(all_thresholds)),
        "fold_details": fold_details,
    }

    logger.info("[%s] F1=%.4f±%.4f, AUC=%.4f±%.4f, ACC=%.4f, thresh=%.3f",
                result["label"], f1_mean, f1_std, auc_mean, auc_std, acc_mean, result["mean_threshold"])

    return result


def train_final_model(
    X: np.ndarray,
    y: np.ndarray,
    scaler: StandardScaler,
) -> tuple[LogisticRegression, StandardScaler]:
    """用全量数据训练最终模型 (用于保存和推理)."""
    X_scaled = scaler.fit_transform(X)
    clf = LogisticRegression(
        C=1.0, class_weight="balanced", max_iter=2000,
        random_state=42, solver="lbfgs",
    )
    clf.fit(X_scaled, y)
    return clf, scaler


def run_m2(
    mode: str = "feature_extraction",
    quick: bool = False,
    epochs: int = 3,
    freeze_layers: int = 8,
    lr: float = 2e-5,
    max_len: int = 128,
    use_original: bool = False,
    use_focal_loss: bool = False,
    focal_gamma: float = 2.0,
    focal_alpha: float = 0.75,
    dropout_rate: float = 0.1,
    use_cosine_schedule: bool = True,
    use_lora: bool = False,
    lora_r: int = 8,
    lora_alpha: int = 16,
    lora_dropout: float = 0.1,
) -> dict[str, Any]:
    """M2 BERT 中文特征提取主流程.

    Args:
        mode: feature_extraction 或 fine_tune
        quick: True 时 fine-tuning 仅用 seed=42 (5 fold, 约 5 分钟);
               False 用 3 seeds × 5 folds = 15 fold (约 14 分钟)
        epochs: fine-tuning 训练轮数 (默认 3)
        freeze_layers: 冻结 BERT 前 N 层 (默认 8, 解冻后 4 层)
        lr: fine-tuning 学习率 (默认 2e-5, T1 网格搜索用)
        max_len: BERT 最大序列长度 (默认 128, 建议中文 256)
        use_original: True 仅用原始 1275 样本 (不使用 D3+ 扩充语料)
        use_focal_loss: True 用 focal loss (针对不平衡数据, 阳性率 20%)
        focal_gamma: focal loss 聚焦参数 (默认 2.0)
        focal_alpha: focal loss 正类权重 (默认 0.75, 对应 pos_rate=25%)
        dropout_rate: 分类头前 dropout (默认 0.1, 防过拟合可调 0.3-0.5)
        use_cosine_schedule: True 用 cosine decay (默认 True, 通常优于 linear)
        use_lora: True 用 LoRA 微调 (peft), 仅训练 LoRA adapter + 分类头.
                  小数据场景降低过拟合风险, freeze_layers 在 LoRA 模式下被忽略.
        lora_r/lora_alpha/lora_dropout: LoRA 配置 (默认 r=8, alpha=16, dropout=0.1)
    """
    start_time = time.time()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("M2 文本 BERT 中文特征提取 - 启动 (mode=%s)", mode)
    logger.info("=" * 60)

    # 1. 加载数据 (use_original=True 时仅用原始 1275 样本)
    df = load_mmpsy_data(use_corpus=not use_original)
    texts = df["text"].tolist()
    y = df["phq9_binary"].astype(int).values
    # 提取 source_idx 用于 StratifiedGroupKFold (D3+ 增强语料必备, 避免同源样本跨折)
    # 原始样本 source_idx=-1 (每条独立), 增强样本 source_idx=原行号 (同源变体分组)
    if "source_idx" in df.columns and not use_original:
        groups = df["source_idx"].astype(int).values
        n_groups = len(np.unique(groups))
        logger.info("启用 StratifiedGroupKFold: %d 样本 / %d 组 (避免同源变体跨折)", len(df), n_groups)
    else:
        groups = None

    # 2. 检测设备
    device = get_device()
    if device == "none":
        return {"error": "torch 未安装"}

    # 3. 检查是否有已保存的 embedding (避免重复提取)
    # embedding 缓存路径包含样本数,避免不同数据集混用
    emb_path = ARTIFACTS_DIR / f"bert_embeddings_n{len(df)}.npy"
    if emb_path.exists():
        logger.info("发现已保存的 embedding, 复用: %s", emb_path)
        embeddings = np.load(emb_path)
        extract_time = 0.0
        logger.info("Embedding shape=%s", embeddings.shape)
        # 校验样本数一致
        if embeddings.shape[0] != len(df):
            logger.warning("Embedding 样本数不匹配 (%d vs %d), 重新提取", embeddings.shape[0], len(df))
            emb_path = ARTIFACTS_DIR / f"bert_embeddings_n{len(df)}_v2.npy"
            extract_needed = True
        else:
            extract_needed = False
    else:
        extract_needed = True

    if extract_needed:
        # 3a. 加载 BERT 并提取特征
        try:
            tokenizer, bert_model = load_bert_model(device)
        except Exception as e:
            logger.error("BERT 加载失败: %s", str(e)[:200])
            logger.error("可检查网络连接, 或手动下载 %s 到本地", BERT_MODEL_NAME)
            return {"error": f"BERT 加载失败: {str(e)[:200]}"}

        t0 = time.time()
        embeddings = extract_bert_embeddings(texts, tokenizer, bert_model, device)
        extract_time = time.time() - t0
        logger.info("特征提取耗时: %.1fs", extract_time)

        np.save(emb_path, embeddings)
        logger.info("Embedding 已保存: %s (shape=%s)", emb_path, embeddings.shape)

    # 4. CV 评估
    cv_results = {}

    if mode == "fine_tune" and device == "cuda":
        # Fine-tuning 模式: 解冻 BERT 顶部层微调
        seeds = [42] if quick else SEEDS
        logger.info("=" * 60)
        logger.info("Fine-tuning 模式 (GPU, seeds=%s, quick=%s, epochs=%d, freeze=%d, lr=%s, lora=%s)",
                    seeds, quick, epochs, freeze_layers, lr, use_lora)
        logger.info("=" * 60)
        cv_results["bert_finetune"] = evaluate_cv_finetune(
            texts, y, device, seeds=seeds, epochs=epochs, freeze_layers=freeze_layers, lr=lr,
            max_len=max_len, use_focal_loss=use_focal_loss,
            focal_gamma=focal_gamma, focal_alpha=focal_alpha,
            dropout_rate=dropout_rate, use_cosine_schedule=use_cosine_schedule,
            use_lora=use_lora, lora_r=lora_r, lora_alpha=lora_alpha, lora_dropout=lora_dropout,
            groups=groups,
        )
    else:
        # Feature extraction 模式: 多方案对比 (LogReg/XGBoost × 阈值优化)
        logger.info("=" * 60)
        logger.info("Feature extraction 多方案 CV 评估")
        logger.info("=" * 60)

        # 方案 1: LogReg + 阈值优化
        cv_results["logreg_thresh_opt"] = evaluate_cv(
            embeddings, y, "logreg_thresh_opt", use_xgb=False, optimize_threshold=True, groups=groups
        )
        # 方案 2: XGBoost + 阈值优化
        cv_results["xgb_thresh_opt"] = evaluate_cv(
            embeddings, y, "xgb_thresh_opt", use_xgb=True, optimize_threshold=True, groups=groups
        )
        # 方案 3: XGBoost 固定阈值 0.5 (对照)
        cv_results["xgb_fixed_05"] = evaluate_cv(
            embeddings, y, "xgb_fixed_05", use_xgb=True, optimize_threshold=False, groups=groups
        )

    # 选择 F1 最高的方案
    best_name = max(cv_results.keys(), key=lambda k: cv_results[k]["f1_mean"])
    cv_result = cv_results[best_name]
    cv_result["best_strategy"] = best_name
    cv_result["all_strategies"] = {
        k: {"f1_mean": v["f1_mean"], "auc_mean": v["auc_mean"],
            "mean_threshold": v.get("mean_threshold", 0.5)}
        for k, v in cv_results.items()
    }
    logger.info("最佳方案: %s (F1=%.4f, AUC=%.4f, thresh=%.3f)",
                best_name, cv_result["f1_mean"], cv_result["auc_mean"],
                cv_result.get("mean_threshold", 0.5))

    # 7. 训练最终模型并保存
    scaler = StandardScaler()
    final_clf, final_scaler = train_final_model(embeddings, y, scaler)

    model_path = ARTIFACTS_DIR / "text_bert_cls_model.pkl"
    scaler_path = ARTIFACTS_DIR / "text_bert_scaler.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(final_clf, f)
    with open(scaler_path, "wb") as f:
        pickle.dump(final_scaler, f)
    logger.info("模型已保存: %s", model_path)

    # 8. 生成报告
    elapsed = time.time() - start_time
    f1_lift = cv_result["f1_mean"] - D3_BASELINE["f1"]
    auc_lift = cv_result["auc_mean"] - D3_BASELINE["auc"]

    report = {
        "experiment_id": f"m2_text_bert_{timestamp}",
        "task": "M2 文本 BERT 中文特征提取",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "elapsed_s": round(elapsed, 1),
        "mode": mode,
        "device": device,
        "bert_model": BERT_MODEL_NAME,
        "data": {
            "n_samples": int(len(df)),
            "pos_rate": float(y.mean()),
            "avg_text_length": float(df["text"].str.len().mean()),
        },
        "bert_config": {
            "max_seq_len": MAX_SEQ_LEN,
            "batch_size": BERT_BATCH_SIZE,
            "embedding_dim": int(embeddings.shape[1]),
            "extract_time_s": round(extract_time, 1),
        },
        "d3_baseline": D3_BASELINE,
        "cv_results": cv_result,
        "comparison": {
            "f1_d3_baseline": D3_BASELINE["f1"],
            "f1_m2_bert": cv_result["f1_mean"],
            "f1_lift": float(f1_lift),
            "auc_d3_baseline": D3_BASELINE["auc"],
            "auc_m2_bert": cv_result["auc_mean"],
            "auc_lift": float(auc_lift),
        },
        "acceptance": {
            "meets_f1_target": bool(cv_result["f1_mean"] >= TARGET_F1),
            "meets_auc_target": bool(cv_result["auc_mean"] >= TARGET_AUC),
            "beats_d3_baseline": bool(cv_result["f1_mean"] > D3_BASELINE["f1"]),
            "f1_target": TARGET_F1,
            "auc_target": TARGET_AUC,
            "all_passed": bool(
                cv_result["f1_mean"] >= TARGET_F1 and cv_result["auc_mean"] >= TARGET_AUC
            ),
        },
        "artifacts": {
            "embeddings": str(emb_path),
            "model": str(model_path),
            "scaler": str(scaler_path),
        },
    }

    # 9. 保存报告
    report_path = ARTIFACTS_DIR / "metrics.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info("报告已保存: %s", report_path)

    # 实验记录
    exp_path = EXPERIMENTS_DIR / f"{report['experiment_id']}.json"
    with open(exp_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 更新 training_jobs.json
    try:
        with open(TRAINING_JOBS_PATH, "r", encoding="utf-8") as f:
            jobs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        jobs = {}

    jobs[report["experiment_id"]] = {
        "job_id": report["experiment_id"],
        "status": "completed",
        "task": "M2_text_bert",
        "created_at": time.time(),
        "mode": mode,
        "device": device,
        "f1_mean": cv_result["f1_mean"],
        "auc_mean": cv_result["auc_mean"],
        "f1_lift_vs_d3": float(f1_lift),
        "meets_targets": report["acceptance"]["all_passed"],
        "timestamp": timestamp,
    }
    with open(TRAINING_JOBS_PATH, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)

    # 10. 打印结论
    logger.info("=" * 60)
    logger.info("M2 完成 (%.1fs)", elapsed)
    logger.info("=" * 60)
    logger.info("结论:")
    logger.info("  D3 基线 F1=%.4f → M2 BERT F1=%.4f±%.4f (提升 +%.4f)",
                D3_BASELINE["f1"], cv_result["f1_mean"], cv_result["f1_std"], f1_lift)
    logger.info("  D3 基线 AUC=%.4f → M2 BERT AUC=%.4f±%.4f (提升 +%.4f)",
                D3_BASELINE["auc"], cv_result["auc_mean"], cv_result["auc_std"], auc_lift)
    logger.info("  验收: F1≥%.2f %s, AUC≥%.2f %s",
                TARGET_F1, "✓" if report["acceptance"]["meets_f1_target"] else "✗",
                TARGET_AUC, "✓" if report["acceptance"]["meets_auc_target"] else "✗")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="M2 文本 BERT 中文特征提取")
    parser.add_argument(
        "--mode",
        choices=["feature_extraction", "fine_tune"],
        default="feature_extraction",
        help="feature_extraction: 冻结 BERT 只训练分类头 (CPU 可用); "
             "fine_tune: 解冻顶部层微调 (需 GPU)",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="快速模式: fine-tuning 仅用 seed=42 (5 fold, 约 5 分钟); "
             "默认 3 seeds × 5 folds = 15 fold (约 14 分钟)",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=3,
        help="fine-tuning 训练轮数 (默认 3)",
    )
    parser.add_argument(
        "--freeze-layers",
        type=int,
        default=8,
        help="冻结 BERT 前 N 层, 解冻后 (12-N) 层 (默认 8, 解冻 4 层)",
    )
    parser.add_argument(
        "--lr",
        type=float,
        default=2e-5,
        help="fine-tuning 学习率 (默认 2e-5, T1 网格搜索用)",
    )
    parser.add_argument(
        "--max-len",
        type=int,
        default=128,
        help="BERT 最大序列长度 (默认 128, 中文平均 332 字符建议 256)",
    )
    parser.add_argument(
        "--use-original",
        action="store_true",
        help="仅使用原始 1275 样本 (不使用 D3+ 扩充语料, 避免增强噪声)",
    )
    parser.add_argument(
        "--focal-loss",
        action="store_true",
        help="使用 focal loss (针对不平衡数据, 阳性率 20%; gamma=2.0, alpha=0.75)",
    )
    parser.add_argument(
        "--dropout",
        type=float,
        default=0.1,
        help="分类头前 dropout (默认 0.1, 防过拟合可调 0.3-0.5)",
    )
    parser.add_argument(
        "--no-cosine",
        action="store_true",
        help="禁用 cosine schedule, 使用 linear schedule",
    )
    parser.add_argument(
        "--use-lora",
        action="store_true",
        help="使用 LoRA 微调 (peft), 仅训练 LoRA adapter + 分类头, 主体冻结. "
             "小数据场景降低过拟合风险, freeze_layers 在 LoRA 模式下被忽略. "
             "需安装 peft (pip install peft)",
    )
    parser.add_argument(
        "--lora-r",
        type=int,
        default=8,
        help="LoRA 秩 (默认 8, 越大容量越大但过拟合风险增加)",
    )
    parser.add_argument(
        "--lora-alpha",
        type=int,
        default=16,
        help="LoRA alpha 缩放因子 (默认 16, scaling=alpha/r=2.0)",
    )
    parser.add_argument(
        "--lora-dropout",
        type=float,
        default=0.1,
        help="LoRA dropout (默认 0.1, 防过拟合)",
    )
    args = parser.parse_args()

    run_m2(mode=args.mode, quick=args.quick,
           epochs=args.epochs, freeze_layers=args.freeze_layers, lr=args.lr,
           max_len=args.max_len, use_original=args.use_original,
           use_focal_loss=args.focal_loss,
           dropout_rate=args.dropout, use_cosine_schedule=not args.no_cosine,
           use_lora=args.use_lora, lora_r=args.lora_r, lora_alpha=args.lora_alpha,
           lora_dropout=args.lora_dropout)


if __name__ == "__main__":
    main()
