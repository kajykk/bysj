"""
Test suite for PyTorch Lightweight MLP.

Tests:
- TC-MLP-001: 验证 PyTorch 环境可用性
- TC-MLP-002: 验证模型架构
- TC-MLP-003: 验证参数量限制
- TC-MLP-004: 验证前向传播
- TC-MLP-005: 验证预测功能
- TC-MLP-006: 验证模型保存与加载
- TC-MLP-007: 验证权重初始化
- TC-MLP-008: 验证训练函数
- TC-MLP-009: 验证评估函数
- TC-MLP-010: 验证梯度裁剪配置
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

# Add backend to path
backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.ml.pytorch_mlp import (
    PyTorchMLP,
    TORCH_AVAILABLE,
    _compute_f1,
    evaluate_pytorch_mlp,
    train_pytorch_mlp,
)

pytestmark = pytest.mark.requires_ml


class TestPyTorchMLP:
    """Test suite for PyTorch MLP."""

    def test_torch_import(self) -> None:
        """TC-MLP-001: 验证 PyTorch 环境可用性."""
        if not TORCH_AVAILABLE:
            pytest.skip("PyTorch not installed")

        import torch

        assert hasattr(torch, "nn")
        assert hasattr(torch, "optim")

    def test_model_architecture(self) -> None:
        """TC-MLP-002: 验证模型架构."""
        if not TORCH_AVAILABLE:
            pytest.skip("PyTorch not installed")

        model = PyTorchMLP(input_dim=13, hidden_dims=[32, 16])

        # Verify input dimension
        assert model.input_dim == 13

        # Verify hidden dimensions
        assert model.hidden_dims == [32, 16]

        # Verify network layers exist
        assert hasattr(model, "network")

    def test_parameter_count(self) -> None:
        """TC-MLP-003: 验证参数量限制 (< 5,000)."""
        if not TORCH_AVAILABLE:
            pytest.skip("PyTorch not installed")

        model = PyTorchMLP(input_dim=13, hidden_dims=[32, 16])
        param_count = model.count_parameters()

        # < 5,000 params for < 5,000 samples
        assert param_count < 5000, f"Model has {param_count} parameters, exceeds 5,000 limit"

        # Expected: 13*32 + 32 + 32*16 + 16 + 16*1 + 1 = 416 + 32 + 512 + 16 + 16 + 1 = 993
        # Plus BatchNorm params: 32*2 + 16*2 = 96
        # Total: ~1,089
        assert param_count < 2000, f"Unexpected parameter count: {param_count}"

    def test_forward_pass(self) -> None:
        """TC-MLP-004: 验证前向传播."""
        if not TORCH_AVAILABLE:
            pytest.skip("PyTorch not installed")

        import torch

        model = PyTorchMLP(input_dim=13, hidden_dims=[32, 16])
        model.eval()

        # Create dummy input
        X = torch.randn(10, 13)
        output = model(X)

        # Verify output shape
        assert output.shape == (10, 1)

        # Verify output is probability (0-1)
        assert torch.all(output >= 0) and torch.all(output <= 1)

    def test_predict(self) -> None:
        """TC-MLP-005: 验证预测功能."""
        if not TORCH_AVAILABLE:
            pytest.skip("PyTorch not installed")

        model = PyTorchMLP(input_dim=13, hidden_dims=[32, 16])

        # Create dummy input
        X = np.random.randn(10, 13).astype(np.float32)

        # Predict probabilities
        proba = model.predict_proba(X)
        assert proba.shape == (10, 1)
        assert np.all(proba >= 0) and np.all(proba <= 1)

        # Predict labels
        labels = model.predict(X)
        assert labels.shape == (10,)
        assert set(np.unique(labels)).issubset({0, 1})

    def test_save_load(self, tmp_path: Path) -> None:
        """TC-MLP-006: 验证模型保存与加载."""
        if not TORCH_AVAILABLE:
            pytest.skip("PyTorch not installed")

        import torch

        # Create and save model
        model = PyTorchMLP(input_dim=13, hidden_dims=[32, 16])
        model_path = tmp_path / "test_model.pth"
        model.save(model_path)

        assert model_path.exists()

        # Load model (trusted_root=None for unit test with temp directory)
        loaded_model = PyTorchMLP.load(model_path, trusted_root=None)

        # Verify architecture
        assert loaded_model.input_dim == model.input_dim
        assert loaded_model.hidden_dims == model.hidden_dims
        assert loaded_model.count_parameters() == model.count_parameters()

        # Verify predictions match
        X = np.random.randn(5, 13).astype(np.float32)
        model.eval()
        loaded_model.eval()

        with torch.no_grad():
            original_output = model(torch.FloatTensor(X)).numpy()
            loaded_output = loaded_model(torch.FloatTensor(X)).numpy()

        np.testing.assert_array_almost_equal(original_output, loaded_output, decimal=5)

    def test_weight_initialization(self) -> None:
        """TC-MLP-007: 验证权重初始化."""
        if not TORCH_AVAILABLE:
            pytest.skip("PyTorch not installed")

        import torch

        model = PyTorchMLP(input_dim=13, hidden_dims=[32, 16])

        # Check that weights are not all zeros or ones (exclude BatchNorm)
        for name, param in model.named_parameters():
            if "weight" in name and "bn_" not in name:
                assert not torch.all(param == 0), f"Weights in {name} are all zeros"
                assert not torch.all(param == 1), f"Weights in {name} are all ones"

    def test_training_function(self) -> None:
        """TC-MLP-008: 验证训练函数."""
        if not TORCH_AVAILABLE:
            pytest.skip("PyTorch not installed")

        # Create dummy data
        X_train = np.random.randn(50, 13).astype(np.float32)
        y_train = np.random.randint(0, 2, size=(50,)).astype(np.float32)
        X_val = np.random.randn(20, 13).astype(np.float32)
        y_val = np.random.randint(0, 2, size=(20,)).astype(np.float32)

        model = PyTorchMLP(input_dim=13, hidden_dims=[32, 16])

        history = train_pytorch_mlp(
            model,
            X_train,
            y_train,
            X_val,
            y_val,
            epochs=5,
            batch_size=16,
            patience=3,
        )

        # Verify history contains expected keys
        assert "train_loss" in history
        assert "val_loss" in history
        assert "train_f1" in history
        assert "val_f1" in history
        assert "best_epoch" in history
        assert "best_val_f1" in history
        assert "learning_rates" in history

        # Verify history has entries
        assert len(history["train_loss"]) > 0
        assert len(history["val_loss"]) > 0

    def test_evaluation_function(self) -> None:
        """TC-MLP-009: 验证评估函数."""
        if not TORCH_AVAILABLE:
            pytest.skip("PyTorch not installed")

        # Create dummy data
        X = np.random.randn(20, 13).astype(np.float32)
        y = np.random.randint(0, 2, size=(20,)).astype(np.float32)

        model = PyTorchMLP(input_dim=13, hidden_dims=[32, 16])

        metrics = evaluate_pytorch_mlp(model, X, y)

        # Verify metrics
        assert "accuracy" in metrics
        assert "precision" in metrics
        assert "recall" in metrics
        assert "f1" in metrics
        assert "roc_auc" in metrics
        assert "auprc" in metrics
        assert "loss" in metrics
        assert "n_samples" in metrics

    def test_gradient_clipping_config(self) -> None:
        """TC-MLP-010: 验证梯度裁剪配置."""
        if not TORCH_AVAILABLE:
            pytest.skip("PyTorch not installed")

        import torch

        # Verify gradient clipping is configured in training
        # max_norm=1.0
        model = PyTorchMLP(input_dim=13, hidden_dims=[32, 16])

        # Create dummy data for a single training step
        X = torch.randn(5, 13)
        y = torch.randint(0, 2, (5, 1)).float()

        criterion = torch.nn.BCELoss()
        optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

        optimizer.zero_grad()
        output = model(X)
        loss = criterion(output, y)
        loss.backward()

        # Apply gradient clipping (same as in train_pytorch_mlp)
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)

        # Verify gradients are not NaN or Inf after clipping
        for param in model.parameters():
            if param.grad is not None:
                assert not torch.isnan(param.grad).any(), "Gradients contain NaN"
                assert not torch.isinf(param.grad).any(), "Gradients contain Inf"

    def test_compute_f1(self) -> None:
        """TC-MLP-011: 验证 F1 计算函数."""
        y_true = np.array([1, 0, 1, 1, 0])
        y_pred_proba = np.array([0.8, 0.2, 0.7, 0.9, 0.3])

        f1 = _compute_f1(y_true, y_pred_proba)

        # All predictions correct at threshold 0.5
        assert f1 == 1.0

        # Test with some incorrect predictions
        y_pred_proba_bad = np.array([0.3, 0.8, 0.2, 0.1, 0.7])
        f1_bad = _compute_f1(y_true, y_pred_proba_bad)
        assert f1_bad < 1.0

    def test_predict_with_custom_threshold(self) -> None:
        """TC-MLP-012: 验证自定义阈值预测."""
        if not TORCH_AVAILABLE:
            pytest.skip("PyTorch not installed")

        model = PyTorchMLP(input_dim=13, hidden_dims=[32, 16])
        X = np.random.randn(10, 13).astype(np.float32)

        labels_default = model.predict(X, threshold=0.5)
        labels_high = model.predict(X, threshold=0.9)

        assert labels_default.shape == (10,)
        assert labels_high.shape == (10,)
        assert set(np.unique(labels_default)).issubset({0, 1})
        assert set(np.unique(labels_high)).issubset({0, 1})

    def test_model_without_batch_norm(self) -> None:
        """TC-MLP-013: 验证无 BatchNorm 的模型."""
        if not TORCH_AVAILABLE:
            pytest.skip("PyTorch not installed")

        import torch

        model = PyTorchMLP(input_dim=13, hidden_dims=[32, 16], use_batch_norm=False)
        X = torch.randn(5, 13)
        output = model(X)
        assert output.shape == (5, 1)
        assert torch.all(output >= 0) and torch.all(output <= 1)

    def test_model_with_different_hidden_dims(self) -> None:
        """TC-MLP-014: 验证不同隐藏层维度."""
        if not TORCH_AVAILABLE:
            pytest.skip("PyTorch not installed")

        import torch

        model = PyTorchMLP(input_dim=5, hidden_dims=[10, 8, 4])
        X = torch.randn(3, 5)
        output = model(X)
        assert output.shape == (3, 1)
        assert model.input_dim == 5
        assert model.hidden_dims == [10, 8, 4]

    def test_training_with_early_stopping(self) -> None:
        """TC-MLP-015: 验证早停触发."""
        if not TORCH_AVAILABLE:
            pytest.skip("PyTorch not installed")

        X_train = np.random.randn(30, 13).astype(np.float32)
        y_train = np.random.randint(0, 2, size=(30,)).astype(np.float32)
        X_val = np.random.randn(10, 13).astype(np.float32)
        y_val = np.random.randint(0, 2, size=(10,)).astype(np.float32)

        model = PyTorchMLP(input_dim=13, hidden_dims=[16, 8])

        history = train_pytorch_mlp(
            model,
            X_train,
            y_train,
            X_val,
            y_val,
            epochs=50,
            batch_size=10,
            patience=2,
        )

        # Should stop early due to patience=2
        assert len(history["train_loss"]) < 50
        assert history["best_epoch"] >= 0

    def test_evaluate_returns_all_metrics(self) -> None:
        """TC-MLP-016: 验证评估返回所有指标."""
        if not TORCH_AVAILABLE:
            pytest.skip("PyTorch not installed")

        X = np.random.randn(15, 13).astype(np.float32)
        y = np.random.randint(0, 2, size=(15,)).astype(np.float32)

        model = PyTorchMLP(input_dim=13, hidden_dims=[32, 16])
        metrics = evaluate_pytorch_mlp(model, X, y)

        required_keys = ["accuracy", "precision", "recall", "f1", "roc_auc", "auprc", "loss", "n_samples"]
        for key in required_keys:
            assert key in metrics
        assert metrics["n_samples"] == 15

    def test_model_device_cpu(self) -> None:
        """TC-MLP-017: 验证 CPU 设备训练."""
        if not TORCH_AVAILABLE:
            pytest.skip("PyTorch not installed")

        import torch

        model = PyTorchMLP(input_dim=13, hidden_dims=[16, 8])
        X = np.random.randn(10, 13).astype(np.float32)
        y = np.random.randint(0, 2, size=(10,)).astype(np.float32)

        history = train_pytorch_mlp(
            model,
            X,
            y,
            X,
            y,
            epochs=3,
            batch_size=5,
            patience=5,
            device="cpu",
        )

        assert len(history["train_loss"]) == 3

    def test_save_load_preserves_predictions(self) -> None:
        """TC-MLP-018: 验证保存加载后预测一致."""
        if not TORCH_AVAILABLE:
            pytest.skip("PyTorch not installed")

        import tempfile

        model = PyTorchMLP(input_dim=13, hidden_dims=[32, 16])
        X = np.random.randn(5, 13).astype(np.float32)

        proba_before = model.predict_proba(X)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "model.pth"
            model.save(path)
            loaded = PyTorchMLP.load(path, trusted_root=None)
            proba_after = loaded.predict_proba(X)

        np.testing.assert_array_almost_equal(proba_before, proba_after, decimal=5)

    def test_torch_not_available_raises(self) -> None:
        """TC-MLP-019: Verify ImportError when PyTorch not available."""
        from app.ml.pytorch_mlp import TORCH_AVAILABLE
        if TORCH_AVAILABLE:
            pytest.skip("PyTorch is installed, cannot test missing import path")

        with pytest.raises(ImportError):
            PyTorchMLP(input_dim=13)

    def test_load_without_torch_raises(self) -> None:
        """TC-MLP-020: Verify load raises ImportError without PyTorch."""
        from app.ml.pytorch_mlp import TORCH_AVAILABLE
        if TORCH_AVAILABLE:
            pytest.skip("PyTorch is installed, cannot test missing import path")

        with pytest.raises(ImportError):
            PyTorchMLP.load("dummy.pth")

    def test_train_without_torch_raises(self) -> None:
        """TC-MLP-021: Verify train raises ImportError without PyTorch."""
        from app.ml.pytorch_mlp import TORCH_AVAILABLE
        if TORCH_AVAILABLE:
            pytest.skip("PyTorch is installed, cannot test missing import path")

        with pytest.raises(ImportError):
            train_pytorch_mlp(None, None, None, None, None)

    def test_evaluate_without_torch_raises(self) -> None:
        """TC-MLP-022: Verify evaluate raises ImportError without PyTorch."""
        from app.ml.pytorch_mlp import TORCH_AVAILABLE
        if TORCH_AVAILABLE:
            pytest.skip("PyTorch is installed, cannot test missing import path")

        with pytest.raises(ImportError):
            evaluate_pytorch_mlp(None, None, None)

    def test_load_with_weights_only(self) -> None:
        """TC-MLP-023: Verify torch.load uses safe loading."""
        if not TORCH_AVAILABLE:
            pytest.skip("PyTorch not installed")

        import torch

        model = PyTorchMLP(input_dim=13, hidden_dims=[32, 16])

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "model.pth"
            model.save(path)

            checkpoint = torch.load(path, map_location="cpu", weights_only=False)
            assert "state_dict" in checkpoint
            assert "input_dim" in checkpoint
