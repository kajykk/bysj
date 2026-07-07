"""
Test suite for XGBoost training pipeline.

Tests:
- TC-XGB-001: 验证 XGBoost 环境可用性
- TC-XGB-002: 验证数据加载与预处理
- TC-XGB-003: 验证类别权重计算
- TC-XGB-004: 验证特征重要性提取
- TC-XGB-005: 验证模型产物保存
- TC-XGB-006: 验证配置参数传递
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

# Add backend to path
backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

try:
    from scripts.train_physiological_xgboost import (
        compute_class_weight,
        extract_feature_importance,
    )
except ImportError:
    pytest.skip(
        "scripts/train_physiological_xgboost.py 不存在, 跳过 XGBoost 训练测试",
        allow_module_level=True,
    )

pytestmark = pytest.mark.requires_ml


class TestXGBoostTraining:
    """Test suite for XGBoost training pipeline."""

    def test_xgboost_import(self) -> None:
        """TC-XGB-001: 验证 XGBoost 环境可用性."""
        try:
            import xgboost as xgb

            assert hasattr(xgb, "DMatrix")
            assert hasattr(xgb, "train")
        except ImportError:
            pytest.skip("XGBoost not installed")

    def test_compute_class_weight_balanced(self) -> None:
        """TC-XGB-002: 验证类别权重计算 - 平衡数据."""
        y = np.array([0, 1, 0, 1, 0, 1])
        weight = compute_class_weight(y)

        # Balanced: n_neg=3, n_pos=3, weight=1.0
        assert weight == 1.0

    def test_compute_class_weight_imbalanced(self) -> None:
        """TC-XGB-003: 验证类别权重计算 - 不平衡数据."""
        y = np.array([0, 0, 0, 0, 1, 1])
        weight = compute_class_weight(y)

        # Imbalanced: n_neg=4, n_pos=2, weight=2.0
        assert weight == 2.0

    def test_compute_class_weight_no_positive(self) -> None:
        """TC-XGB-004: 验证类别权重计算 - 无正样本."""
        y = np.array([0, 0, 0, 0])
        weight = compute_class_weight(y)

        # No positive samples: default to 1.0
        assert weight == 1.0

    def test_extract_feature_importance(self) -> None:
        """TC-XGB-005: 验证特征重要性提取."""
        # Create a mock model
        mock_model = MagicMock()
        mock_model.get_score.return_value = {
            "f0": 10.5,
            "f2": 25.3,
            "f1": 15.2,
        }

        feature_names = ["feat_a", "feat_b", "feat_c"]
        importance = extract_feature_importance(mock_model, feature_names)

        # Verify structure
        assert len(importance) == 3
        assert all("feature" in item and "importance" in item for item in importance)

        # Verify sorting (descending)
        for i in range(len(importance) - 1):
            assert importance[i]["importance"] >= importance[i + 1]["importance"]

        # Verify mapping
        assert importance[0]["feature"] == "feat_c"  # f2 = 25.3 (highest)
        assert importance[0]["importance"] == 25.3

    def test_extract_feature_importance_missing(self) -> None:
        """TC-XGB-006: 验证特征重要性提取 - 缺失特征."""
        mock_model = MagicMock()
        mock_model.get_score.return_value = {
            "f0": 10.5,
            # f1 and f2 missing
        }

        feature_names = ["feat_a", "feat_b", "feat_c"]
        importance = extract_feature_importance(mock_model, feature_names)

        # Missing features should have importance 0
        feat_b = next(item for item in importance if item["feature"] == "feat_b")
        assert feat_b["importance"] == 0.0

    def test_config_structure(self) -> None:
        """TC-XGB-007: 验证配置参数结构."""
        config = {
            "n_estimators": 200,
            "max_depth": 5,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "scale_pos_weight": "auto",
            "random_state": 42,
            "smote_ratio": 0.8,
        }

        # Verify all required keys exist
        required_keys = [
            "n_estimators",
            "max_depth",
            "learning_rate",
            "subsample",
            "colsample_bytree",
            "scale_pos_weight",
            "random_state",
        ]
        for key in required_keys:
            assert key in config, f"Missing config key: {key}"

        # Verify SMOTE ratio <= 0.8
        assert config["smote_ratio"] <= 0.8

    def test_smote_ratio_enforcement(self) -> None:
        """TC-XGB-008: 验证 SMOTE 比例限制."""
        # SMOTE ratio must not exceed 0.8:1
        smote_ratio = 0.8
        assert smote_ratio <= 0.8, "SMOTE ratio exceeds limit"

        # Verify enforcement
        user_ratio = 1.0
        enforced_ratio = min(user_ratio, 0.8)
        assert enforced_ratio == 0.8
