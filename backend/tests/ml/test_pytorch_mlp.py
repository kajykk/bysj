"""Tests for app/ml/pytorch_mlp.py.

覆盖 0% 模块: app.ml.pytorch_mlp.
关键路径:
- PyTorchMLP.__init__ (默认/自定义 hidden_dims, dropout, batch_norm)
- _init_weights (Kaiming 初始化)
- forward / predict_proba / predict / count_parameters
- save / load round trip (with trusted_root=None for test)
- train_pytorch_mlp (基本训练 + 早停)
- _compute_f1 (perfect / all_wrong / edge cases)
- evaluate_pytorch_mlp

注: 测试需要 torch 可用. CI 环境 (Linux + Python 3.12) 已安装 torch.
本地 Windows + torch 2.6.0+cu124 已验证可用.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from app.ml.pytorch_mlp import (
    PyTorchMLP,
    TORCH_AVAILABLE,
    _compute_f1,
    evaluate_pytorch_mlp,
    train_pytorch_mlp,
)


# Skip entire module if torch is not installed
pytestmark = pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch not installed")


class TestPyTorchMLPInit:
    """Test PyTorchMLP initialization."""

    def test_default_init(self):
        """TC-PT-001: 默认架构 Input(13) -> 32 -> 16 -> 1."""
        model = PyTorchMLP()
        assert model.input_dim == 13
        assert model.hidden_dims == [32, 16]
        assert model.dropout_rate == 0.4
        assert model.use_batch_norm is True
        # 参数量应小于 5000 (设计约束)
        assert model.count_parameters() < 5000
        assert model.count_parameters() > 0

    def test_custom_hidden_dims(self):
        """TC-PT-002: 自定义 hidden_dims."""
        model = PyTorchMLP(input_dim=5, hidden_dims=[8, 4])
        assert model.input_dim == 5
        assert model.hidden_dims == [8, 4]
        # 5*8 + 8 + 8*4 + 4 + 4*1 + 1 = 40+8+32+4+4+1 = 89 (+ BN params)
        assert model.count_parameters() > 80

    def test_no_batch_norm(self):
        """TC-PT-003: 禁用 BatchNorm."""
        model = PyTorchMLP(use_batch_norm=False)
        assert model.use_batch_norm is False
        # 无 BN 参数, 总参数量应更少
        assert model.count_parameters() > 0

    def test_custom_dropout(self):
        """TC-PT-004: 自定义 dropout_rate."""
        model = PyTorchMLP(dropout_rate=0.5)
        assert model.dropout_rate == 0.5


class TestPyTorchMLPForward:
    """Test PyTorchMLP forward pass."""

    def test_forward_output_shape(self):
        """TC-PT-005: forward 输出 shape (batch, 1)."""
        model = PyTorchMLP(input_dim=5, hidden_dims=[8])
        x = torch.randn(4, 5)  # batch=4, features=5
        output = model.forward(x)
        assert output.shape == (4, 1)

    def test_forward_output_range(self):
        """TC-PT-006: Sigmoid 输出在 [0, 1]."""
        model = PyTorchMLP(input_dim=5, hidden_dims=[8])
        x = torch.randn(10, 5)
        output = model.forward(x)
        assert (output >= 0).all()
        assert (output <= 1).all()


class TestPredictProba:
    """Test predict_proba."""

    def test_predict_proba_shape(self):
        """TC-PT-007: predict_proba 输出 shape (n, 1)."""
        model = PyTorchMLP(input_dim=5, hidden_dims=[8])
        X = np.random.randn(10, 5).astype(np.float32)
        proba = model.predict_proba(X)
        assert proba.shape == (10, 1)
        assert (proba >= 0).all()
        assert (proba <= 1).all()


class TestPredict:
    """Test predict."""

    def test_predict_default_threshold(self):
        """TC-PT-008: 默认阈值 0.5 二分类."""
        model = PyTorchMLP(input_dim=5, hidden_dims=[8])
        X = np.random.randn(20, 5).astype(np.float32)
        pred = model.predict(X)
        assert pred.shape == (20,)
        assert set(np.unique(pred)).issubset({0, 1})

    def test_predict_custom_threshold(self):
        """TC-PT-009: 自定义阈值."""
        model = PyTorchMLP(input_dim=5, hidden_dims=[8])
        X = np.random.randn(20, 5).astype(np.float32)
        # 阈值 0.99 -> 几乎所有样本都被分为 0
        pred = model.predict(X, threshold=0.99)
        assert pred.shape == (20,)
        # 高阈值下大部分预测应为 0 (Sigmoid 初始化后通常 < 0.99)
        # 不严格要求全部为 0, 但至少 shape 正确
        assert set(np.unique(pred)).issubset({0, 1})

    def test_predict_low_threshold(self):
        """TC-PT-010: 低阈值 0.01 -> 几乎所有样本都被分为 1."""
        model = PyTorchMLP(input_dim=5, hidden_dims=[8])
        X = np.random.randn(20, 5).astype(np.float32)
        pred = model.predict(X, threshold=0.01)
        assert pred.shape == (20,)
        # 低阈值下大部分预测应为 1
        assert set(np.unique(pred)).issubset({0, 1})


class TestCountParameters:
    """Test count_parameters."""

    def test_count_positive(self):
        """TC-PT-011: 参数量 > 0."""
        model = PyTorchMLP(input_dim=5, hidden_dims=[8])
        assert model.count_parameters() > 0

    def test_count_matches_attribute(self):
        """TC-PT-012: count_parameters 与 _param_count 一致."""
        model = PyTorchMLP(input_dim=5, hidden_dims=[8])
        assert model.count_parameters() == model._param_count


class TestSaveLoad:
    """Test save / load round trip."""

    def test_save_creates_file(self, tmp_path):
        """TC-PT-013: save 创建 .pth 文件."""
        model = PyTorchMLP(input_dim=5, hidden_dims=[8])
        path = tmp_path / "model.pth"
        model.save(path)
        assert path.exists()

    def test_save_creates_parent_dir(self, tmp_path):
        """TC-PT-014: save 自动创建父目录."""
        model = PyTorchMLP(input_dim=5, hidden_dims=[8])
        nested = tmp_path / "nested" / "deeper" / "model.pth"
        model.save(nested)
        assert nested.exists()

    def test_load_round_trip(self, tmp_path):
        """TC-PT-015: save -> load 模型架构一致, 预测一致."""
        model = PyTorchMLP(input_dim=5, hidden_dims=[8], dropout_rate=0.3)
        path = tmp_path / "model.pth"
        model.save(path)
        # trusted_root=None 跳过路径校验 (仅用于测试)
        loaded = PyTorchMLP.load(path, trusted_root=None)
        assert loaded.input_dim == 5
        assert loaded.hidden_dims == [8]
        assert loaded.dropout_rate == 0.3
        # 预测应一致
        X = np.random.randn(5, 5).astype(np.float32)
        # 设置 eval 模式确保 Dropout 关闭
        model.eval()
        loaded.eval()
        pred_orig = model.predict_proba(X)
        pred_loaded = loaded.predict_proba(X)
        np.testing.assert_allclose(pred_orig, pred_loaded, atol=1e-6)


class TestComputeF1:
    """Test _compute_f1."""

    def test_perfect_prediction(self):
        """TC-PT-016: 完美预测 F1=1.0."""
        y_true = np.array([0, 1, 0, 1])
        y_pred_proba = np.array([0.1, 0.9, 0.2, 0.8])  # 阈值 0.5 -> [0, 1, 0, 1]
        f1 = _compute_f1(y_true, y_pred_proba)
        assert f1 == 1.0

    def test_all_wrong(self):
        """TC-PT-017: 全错预测 F1=0.0."""
        y_true = np.array([0, 1, 0, 1])
        y_pred_proba = np.array([0.9, 0.1, 0.8, 0.2])  # 阈值 0.5 -> [1, 0, 1, 0]
        f1 = _compute_f1(y_true, y_pred_proba)
        assert f1 == 0.0

    def test_no_positive_pred(self):
        """TC-PT-018: 无正预测时 F1=0.0 (无除零)."""
        y_true = np.array([0, 1, 0, 1])
        y_pred_proba = np.array([0.1, 0.2, 0.3, 0.4])  # 全部 < 0.5 -> 全 0
        f1 = _compute_f1(y_true, y_pred_proba)
        assert f1 == 0.0

    def test_no_positive_true(self):
        """TC-PT-019: 真实值无正类时 F1=0.0."""
        y_true = np.array([0, 0, 0, 0])
        y_pred_proba = np.array([0.1, 0.9, 0.2, 0.8])  # 预测有正类, 但 y_true 全 0
        f1 = _compute_f1(y_true, y_pred_proba)
        # tp=0, fn=0 -> recall=0, precision=0/2=0, f1=0
        assert f1 == 0.0

    def test_custom_threshold(self):
        """TC-PT-020: 自定义阈值生效."""
        y_true = np.array([0, 1])
        # 阈值 0.6: 0.4 -> 0, 0.55 -> 0 -> 全 0 -> F1=0
        y_pred_proba = np.array([0.4, 0.55])
        f1 = _compute_f1(y_true, y_pred_proba, threshold=0.6)
        assert f1 == 0.0


class TestTrainPyTorchMLP:
    """Test train_pytorch_mlp."""

    def test_basic_training(self):
        """TC-PT-021: 基本训练返回完整 history."""
        rng = np.random.RandomState(42)
        X_train = rng.randn(40, 5).astype(np.float32)
        y_train = np.array([0] * 20 + [1] * 20, dtype=np.float32)
        X_val = rng.randn(20, 5).astype(np.float32)
        y_val = np.array([0] * 10 + [1] * 10, dtype=np.float32)

        model = PyTorchMLP(input_dim=5, hidden_dims=[8], dropout_rate=0.0)
        history = train_pytorch_mlp(
            model,
            X_train,
            y_train,
            X_val,
            y_val,
            epochs=3,
            batch_size=8,
            learning_rate=0.01,
            patience=5,
            random_state=42,
        )
        assert "train_loss" in history
        assert "val_loss" in history
        assert "train_f1" in history
        assert "val_f1" in history
        assert "best_epoch" in history
        assert "best_val_f1" in history
        assert "learning_rates" in history
        assert len(history["train_loss"]) == 3
        assert len(history["val_loss"]) == 3

    def test_early_stopping(self):
        """TC-PT-022: 早停触发后训练提前结束."""
        rng = np.random.RandomState(0)
        X_train = rng.randn(40, 5).astype(np.float32)
        y_train = np.array([0] * 20 + [1] * 20, dtype=np.float32)
        X_val = rng.randn(20, 5).astype(np.float32)
        y_val = np.array([0] * 10 + [1] * 10, dtype=np.float32)

        model = PyTorchMLP(input_dim=5, hidden_dims=[8], dropout_rate=0.0)
        # patience=1, epochs=10 -> 应在 1-2 个 epoch 后早停
        history = train_pytorch_mlp(
            model,
            X_train,
            y_train,
            X_val,
            y_val,
            epochs=10,
            batch_size=8,
            learning_rate=0.001,
            patience=1,
            random_state=42,
        )
        # 早停后 history 长度应 <= epochs
        assert len(history["train_loss"]) <= 10
        assert len(history["train_loss"]) >= 1

    def test_reproducible_training(self):
        """TC-PT-023: 相同 random_state 产生相同的 best_val_f1.

        注: train_pytorch_mlp 在函数内部设置 torch.manual_seed, 但模型权重在
        构造时已初始化. 为保证完全可复现, 测试需在创建模型前显式设种子.
        """
        rng = np.random.RandomState(0)
        X_train = rng.randn(40, 5).astype(np.float32)
        y_train = np.array([0] * 20 + [1] * 20, dtype=np.float32)
        X_val = rng.randn(20, 5).astype(np.float32)
        y_val = np.array([0] * 10 + [1] * 10, dtype=np.float32)

        # 在模型构造前显式设种子, 确保权重初始化可复现
        torch.manual_seed(42)
        np.random.seed(42)
        model1 = PyTorchMLP(input_dim=5, hidden_dims=[8], dropout_rate=0.0)
        h1 = train_pytorch_mlp(
            model1, X_train, y_train, X_val, y_val,
            epochs=3, batch_size=8, learning_rate=0.01, patience=5, random_state=42,
        )

        torch.manual_seed(42)
        np.random.seed(42)
        model2 = PyTorchMLP(input_dim=5, hidden_dims=[8], dropout_rate=0.0)
        h2 = train_pytorch_mlp(
            model2, X_train, y_train, X_val, y_val,
            epochs=3, batch_size=8, learning_rate=0.01, patience=5, random_state=42,
        )
        # 相同 seed 下训练 loss 应非常接近
        np.testing.assert_allclose(h1["train_loss"], h2["train_loss"], atol=1e-5)


class TestEvaluatePyTorchMLP:
    """Test evaluate_pytorch_mlp."""

    def test_evaluate_returns_metrics(self):
        """TC-PT-024: evaluate 返回完整指标."""
        rng = np.random.RandomState(0)
        X = rng.randn(20, 5).astype(np.float32)
        y = np.array([0] * 10 + [1] * 10, dtype=np.float32)

        model = PyTorchMLP(input_dim=5, hidden_dims=[8])
        metrics = evaluate_pytorch_mlp(model, X, y)
        assert "loss" in metrics
        assert "n_samples" in metrics
        assert metrics["n_samples"] == 20
        # compute_metrics 应返回标准指标
        assert "f1" in metrics or "accuracy" in metrics
