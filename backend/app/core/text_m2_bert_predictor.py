"""M2 BERT 文本推理器 (Feature Extraction 模式).

S3 P4 影子模式核心组件: 加载 M2 训练产物 (chinese-bert-wwm-ext + scaler + LogReg),
对文本提取 [CLS] embedding → 标准化 → LogReg 预测, 输出与生产 TF-IDF 对拍.

训练脚本: scripts/m2_text_bert.py (mode=feature_extraction)
训练数据: data/external/chinese_depression_corpus_v1.csv (8379 条, D3+ 扩充)
CV 验收: F1=0.8231±0.0222, AUC=0.9523±0.0339 (StratifiedGroupKFold, 15 折)

模型产物:
    models/artifacts/text_m2_bert/text_bert_cls_model.pkl  (LogReg)
    models/artifacts/text_m2_bert/text_bert_scaler.pkl     (StandardScaler)
    BERT 主体: hfl/chinese-bert-wwm-ext (transformers AutoModel, 在线/缓存加载)
"""

from __future__ import annotations

import asyncio
import logging
import pickle
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# M2 训练产物路径
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_M2_ARTIFACTS_DIR = _PROJECT_ROOT / "models" / "artifacts" / "text_m2_bert"
_M2_CLS_MODEL_PATH = _M2_ARTIFACTS_DIR / "text_bert_cls_model.pkl"
_M2_SCALER_PATH = _M2_ARTIFACTS_DIR / "text_bert_scaler.pkl"

# BERT 模型名 (与训练脚本一致)
_BERT_MODEL_NAME = "hfl/chinese-bert-wwm-ext"

# 训练时 max_len=256, 推理时保持一致
_M2_MAX_LEN = 256


class TextM2BertPredictor:
    """M2 BERT 文本推理器 (单例, 懒加载).

    Feature Extraction 模式: 冻结 BERT 主体, 只用 [CLS] embedding + LogReg 分类.
    与生产 text_bert_classifier (transformers 原生模型) 不兼容, 独立加载.
    """

    def __init__(self) -> None:
        self._initialized = False
        self._tokenizer: Any = None
        self._bert_model: Any = None
        self._scaler: Any = None
        self._classifier: Any = None
        self._device: str = "cpu"
        # 训练时 find_best_f1_threshold 找到的最优阈值 (metrics.json mean_threshold)
        self._threshold: float = 0.627

    async def _initialize(self) -> None:
        """懒加载 BERT + scaler + LogReg (首次调用时加载, 约 10s)."""
        if self._initialized:
            return

        try:
            import torch
            from transformers import AutoModel, AutoTokenizer

            # 1. 加载 BERT 主体 + tokenizer
            logger.info("[M2-BERT] 加载 BERT 模型: %s", _BERT_MODEL_NAME)
            self._tokenizer = AutoTokenizer.from_pretrained(_BERT_MODEL_NAME)
            self._bert_model = AutoModel.from_pretrained(_BERT_MODEL_NAME)

            # 设备检测
            if torch.cuda.is_available():
                self._device = "cuda"
                self._bert_model = self._bert_model.to(self._device)
            self._bert_model.eval()

            # 2. 加载 scaler + LogReg (M2 训练产物)
            if not _M2_CLS_MODEL_PATH.exists() or not _M2_SCALER_PATH.exists():
                raise FileNotFoundError(
                    f"M2 模型产物缺失: cls_model={_M2_CLS_MODEL_PATH.exists()}, "
                    f"scaler={_M2_SCALER_PATH.exists()}"
                )
            with open(_M2_SCALER_PATH, "rb") as f:
                self._scaler = pickle.load(f)
            with open(_M2_CLS_MODEL_PATH, "rb") as f:
                self._classifier = pickle.load(f)

            self._initialized = True
            logger.info(
                "[M2-BERT] 加载完成 (device=%s, threshold=%.3f, BERT params=%d)",
                self._device,
                self._threshold,
                sum(p.numel() for p in self._bert_model.parameters()),
            )
        except Exception as e:
            logger.error("[M2-BERT] 加载失败: %s", str(e)[:200])
            raise

    async def predict(self, text: str) -> dict[str, Any] | None:
        """M2 BERT 推理 (Feature Extraction 模式).

        Args:
            text: 输入文本

        Returns:
            {prediction, probability, sentiment_score, model_used} 或 None (失败)
        """
        if not self._initialized:
            await self._initialize()

        try:
            import torch

            # 1. Tokenize
            inputs = await asyncio.to_thread(
                self._tokenizer,
                text,
                return_tensors="pt",
                truncation=True,
                padding=True,
                max_length=_M2_MAX_LEN,
            )
            if self._device == "cuda":
                inputs = {k: v.to(self._device) for k, v in inputs.items()}

            # 2. BERT 前向 → [CLS] embedding (768-dim)
            with torch.no_grad():
                outputs = await asyncio.to_thread(self._bert_model, **inputs)
                cls_embedding = (
                    outputs.last_hidden_state[:, 0, :].cpu().numpy()
                )  # shape=(1, 768)

            # 3. scaler.transform → LogReg.predict_proba
            scaled = await asyncio.to_thread(self._scaler.transform, cls_embedding)
            proba = await asyncio.to_thread(self._classifier.predict_proba, scaled)
            probability = float(proba[0][1])

            # 4. 用训练时找的最优阈值做预测 (而非固定 0.5)
            prediction = int(probability >= self._threshold)

            return {
                "prediction": prediction,
                "probability": round(probability, 4),
                "sentiment_label": "negative" if prediction == 1 else "positive",
                "sentiment_score": round(probability, 4),
                "model_used": "text_m2_bert",
                "threshold": self._threshold,
            }
        except Exception as e:
            logger.warning("[M2-BERT] 推理失败: %s", str(e)[:200])
            return None


# 单例实例 (懒加载, 首次调用 get_m2_bert_predictor() 时初始化)
_m2_bert_predictor_instance: TextM2BertPredictor | None = None


def get_m2_bert_predictor() -> TextM2BertPredictor:
    """获取 M2 BERT 推理器单例."""
    global _m2_bert_predictor_instance
    if _m2_bert_predictor_instance is None:
        _m2_bert_predictor_instance = TextM2BertPredictor()
    return _m2_bert_predictor_instance
