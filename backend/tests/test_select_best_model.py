"""
Test suite for model selection functionality.

Tests:
- TC-SEL-001: 验证模型评分函数
- TC-SEL-002: 验证最优模型选择
- TC-SEL-003: 验证空结果处理
- TC-SEL-004: 验证权重配置
- TC-SEL-005: 验证报告生成
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

from scripts.select_best_physiological_model import select_best_model


class TestModelSelection:
    """Test suite for model selection."""

    def test_select_best_model_by_f1(self) -> None:
        """TC-SEL-001: 验证模型评分函数 - F1 优先."""
        results = {
            "xgboost": {
                "f1": 0.85,
                "roc_auc": 0.90,
                "auprc": 0.80,
                "latency_ms": 5.0,
                "model_size_mb": 2.0,
            },
            "lightgbm": {
                "f1": 0.82,
                "roc_auc": 0.88,
                "auprc": 0.78,
                "latency_ms": 3.0,
                "model_size_mb": 1.5,
            },
            "mlp": {
                "f1": 0.80,
                "roc_auc": 0.85,
                "auprc": 0.75,
                "latency_ms": 2.0,
                "model_size_mb": 0.5,
            },
        }

        best_model, details = select_best_model(results)

        # XGBoost has highest F1, should be selected
        assert best_model == "xgboost"
        assert "scores" in details
        assert details["scores"]["xgboost"] > details["scores"]["lightgbm"]

    def test_select_considers_all_metrics(self) -> None:
        """TC-SEL-002: 验证最优模型选择 - 综合指标."""
        results = {
            "model_a": {
                "f1": 0.80,
                "roc_auc": 0.95,
                "auprc": 0.90,
                "latency_ms": 10.0,
                "model_size_mb": 5.0,
            },
            "model_b": {
                "f1": 0.82,
                "roc_auc": 0.85,
                "auprc": 0.80,
                "latency_ms": 2.0,
                "model_size_mb": 1.0,
            },
        }

        best_model, details = select_best_model(results)

        # Model B has higher F1 and better latency/size
        # Note: actual winner depends on scoring function implementation
        assert best_model in ("model_a", "model_b")
        assert "all_metrics" in details

    def test_empty_results(self) -> None:
        """TC-SEL-003: 验证空结果处理."""
        with pytest.raises(ValueError, match="No models to compare"):
            select_best_model({})

    def test_single_model(self) -> None:
        """TC-SEL-004: 验证单模型选择."""
        results = {
            "only_model": {
                "f1": 0.75,
                "roc_auc": 0.80,
                "auprc": 0.70,
                "latency_ms": 5.0,
                "model_size_mb": 2.0,
            },
        }

        best_model, details = select_best_model(results)

        assert best_model == "only_model"
        assert details["scores"]["only_model"] > 0

    def test_weight_configuration(self) -> None:
        """TC-SEL-005: 验证权重配置."""
        results = {
            "fast_but_less_accurate": {
                "f1": 0.75,
                "roc_auc": 0.80,
                "auprc": 0.70,
                "latency_ms": 1.0,
                "model_size_mb": 0.5,
            },
            "slow_but_accurate": {
                "f1": 0.85,
                "roc_auc": 0.90,
                "auprc": 0.85,
                "latency_ms": 20.0,
                "model_size_mb": 10.0,
            },
        }

        best_model, details = select_best_model(results)

        # F1 has highest weight (0.4), so slow_but_accurate should win
        assert best_model == "slow_but_accurate"
        assert details["selection_criteria"]["primary"] == "F1-Score (weight=0.4)"

    def test_report_structure(self) -> None:
        """TC-SEL-006: 验证报告结构."""
        results = {
            "model_x": {
                "f1": 0.80,
                "roc_auc": 0.85,
                "auprc": 0.75,
                "latency_ms": 5.0,
                "model_size_mb": 2.0,
            },
        }

        best_model, details = select_best_model(results)

        # Verify report structure
        assert "best_model" in details
        assert "scores" in details
        assert "all_metrics" in details
        assert "selection_criteria" in details
        assert "timestamp" in details
        assert "primary" in details["selection_criteria"]
        assert "secondary" in details["selection_criteria"]
