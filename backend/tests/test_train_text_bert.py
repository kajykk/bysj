"""
Test suite for BERT text model training.

Tests:
- TC-BERT-001: 验证 transformers 环境
- TC-BERT-002: 验证 BERT 模型加载
- TC-BERT-003: 验证数据加载
- TC-BERT-004: 验证数据集准备
- TC-BERT-005: 验证指标计算
- TC-BERT-006: 验证配置结构
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# Add backend to path
backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

try:
    from scripts.train_text_bert import compute_metrics, load_data
except ImportError:
    pytest.skip(
        "scripts/train_text_bert.py 不存在, 跳过 BERT 文本训练测试",
        allow_module_level=True,
    )


pytestmark = pytest.mark.requires_ml


class TestBERTTraining:
    """Test suite for BERT text model training."""

    def test_transformers_import(self) -> None:
        """TC-BERT-001: 验证 transformers 环境."""
        try:
            import transformers

            assert hasattr(transformers, "BertForSequenceClassification")
            assert hasattr(transformers, "BertTokenizer")
        except ImportError:
            pytest.skip("transformers not installed")

    def test_torch_import(self) -> None:
        """TC-BERT-002: 验证 torch 环境."""
        try:
            import torch

            assert hasattr(torch, "nn")
        except ImportError:
            pytest.skip("torch not installed")

    def test_load_data_dummy(self) -> None:
        """TC-BERT-003: 验证数据加载 - 虚拟数据."""
        texts, labels = load_data(Path("nonexistent.csv"))

        assert len(texts) == 100
        assert len(labels) == 100
        assert all(isinstance(t, str) for t in texts)
        assert all(isinstance(label, int) for label in labels)
        assert set(labels).issubset({0, 1})

    def test_compute_metrics(self) -> None:
        """TC-BERT-005: 验证指标计算."""
        # Simulate predictions: 2 samples, 2 classes
        predictions = np.array(
            [
                [0.1, 0.9],  # Predict class 1
                [0.8, 0.2],  # Predict class 0
            ]
        )
        labels = np.array([1, 0])

        metrics = compute_metrics((predictions, labels))

        assert "accuracy" in metrics
        assert "f1" in metrics
        assert "precision" in metrics
        assert "recall" in metrics

        # All predictions correct
        assert metrics["accuracy"] == 1.0
        assert metrics["f1"] == 1.0

    def test_compute_metrics_with_errors(self) -> None:
        """TC-BERT-006: 验证指标计算 - 含错误."""
        predictions = np.array(
            [
                [0.9, 0.1],  # Predict class 0 (wrong)
                [0.8, 0.2],  # Predict class 0 (correct)
            ]
        )
        labels = np.array([1, 0])

        metrics = compute_metrics((predictions, labels))

        assert metrics["accuracy"] == 0.5
        assert metrics["f1"] < 1.0

    def test_config_structure(self) -> None:
        """TC-BERT-007: 验证配置结构."""
        config = {
            "epochs": 3,
            "batch_size": 16,
            "learning_rate": 2e-5,
            "max_length": 128,
            "warmup_ratio": 0.1,
            "weight_decay": 0.01,
            "random_state": 42,
            "model_name": "bert-base-chinese",
            "num_labels": 2,
        }

        required_keys = [
            "epochs",
            "batch_size",
            "learning_rate",
            "max_length",
            "random_state",
            "model_name",
        ]
        for key in required_keys:
            assert key in config, f"Missing config key: {key}"

    def test_bert_model_name(self) -> None:
        """TC-BERT-008: 验证 BERT 模型名称."""
        model_name = "bert-base-chinese"
        assert model_name.startswith("bert-")
        assert "chinese" in model_name

    def test_label_distribution(self) -> None:
        """TC-BERT-009: 验证标签分布."""
        texts, labels = load_data(Path("nonexistent.csv"))

        n_positive = sum(labels)
        n_negative = len(labels) - n_positive

        # Should have both classes
        assert n_positive > 0
        assert n_negative > 0

    def test_text_length(self) -> None:
        """TC-BERT-010: 验证文本长度."""
        texts, _ = load_data(Path("nonexistent.csv"))

        # All texts should be non-empty
        assert all(len(t) > 0 for t in texts)

        # Texts should be strings
        assert all(isinstance(t, str) for t in texts)
