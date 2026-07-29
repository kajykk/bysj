"""Tests for app/ml/loss.py.

覆盖模块: app.ml.loss (当前 22% → 目标 >80%).
关键路径:
- binary_cross_entropy_loss (1D/2D y_true, 数值稳定性)
- focal_loss (alpha/gamma 参数, 梯度计算)
- compute_class_weights (不平衡数据集)
"""

from __future__ import annotations

import numpy as np
import pytest

from app.ml.loss import binary_cross_entropy_loss, compute_class_weights, focal_loss


class TestBinaryCrossEntropyLoss:
    """Test binary_cross_entropy_loss."""

    def test_perfect_prediction(self):
        """TC-LOSS-001: 完美预测 loss 接近 0."""
        y_pred = np.array([[0.99], [0.01]])
        y_true = np.array([[1.0], [0.0]])
        loss, grad = binary_cross_entropy_loss(y_pred, y_true)
        assert loss < 0.05  # 接近 0
        assert grad.shape == (2, 1)

    def test_1d_y_true_compat(self):
        """TC-LOSS-002: 1D y_true 自动 reshape 为 2D (BUG-003 修复)."""
        y_pred = np.array([[0.6], [0.4]])
        y_true = np.array([1, 0])  # 1D
        loss, grad = binary_cross_entropy_loss(y_pred, y_true)
        # 不应抛错, 且 grad shape 与 y_pred 一致
        assert grad.shape == y_pred.shape

    def test_loss_value(self):
        """TC-LOSS-003: 已知输入的 loss 值正确."""
        y_pred = np.array([[0.5]])
        y_true = np.array([[1.0]])
        loss, _ = binary_cross_entropy_loss(y_pred, y_true)
        # -log(0.5) ≈ 0.693
        assert abs(loss - 0.6931) < 0.01

    def test_clip_avoids_log_zero(self):
        """TC-LOSS-004: 边界值 (0, 1) 通过 clip 避免除零."""
        y_pred = np.array([[0.0], [1.0]])
        y_true = np.array([[0.0], [1.0]])
        loss, grad = binary_cross_entropy_loss(y_pred, y_true)
        # 不抛错, loss 有限
        assert np.isfinite(loss)
        assert np.all(np.isfinite(grad))

    def test_gradient_shape(self):
        """TC-LOSS-005: 梯度 shape 与 y_pred 一致."""
        y_pred = np.array([[0.3], [0.7], [0.5]])
        y_true = np.array([[0.0], [1.0], [1.0]])
        _, grad = binary_cross_entropy_loss(y_pred, y_true)
        assert grad.shape == y_pred.shape

    def test_custom_epsilon(self):
        """TC-LOSS-006: 自定义 epsilon 生效 (y_pred 接近 0/1 时影响明显)."""
        # y_pred=0.0001 接近 0, 不同 epsilon 会产生不同 clip 结果
        y_pred = np.array([[0.0001]])
        y_true = np.array([[0.0]])
        loss1, _ = binary_cross_entropy_loss(y_pred, y_true, epsilon=1e-7)
        loss2, _ = binary_cross_entropy_loss(y_pred, y_true, epsilon=1e-3)
        # epsilon=1e-3 会 clip 到 0.001, 与 epsilon=1e-7 (clip 到 0.0001) 不同
        assert loss1 != loss2


class TestFocalLoss:
    """Test focal_loss."""

    def test_basic_shape(self):
        """TC-LOSS-007: 基本调用返回 (loss, grad) 元组."""
        y_pred = np.array([[0.6], [0.4]])
        y_true = np.array([[1.0], [0.0]])
        loss, grad = focal_loss(y_pred, y_true)
        assert isinstance(loss, float)
        assert grad.shape == (2, 1)

    def test_1d_y_true_compat(self):
        """TC-LOSS-008: 1D y_true 自动 reshape (BUG-003 修复)."""
        y_pred = np.array([[0.6], [0.4]])
        y_true = np.array([1, 0])  # 1D
        loss, grad = focal_loss(y_pred, y_true)
        assert grad.shape == y_pred.shape

    def test_perfect_prediction_low_loss(self):
        """TC-LOSS-009: 完美预测 loss 接近 0."""
        y_pred = np.array([[0.99], [0.01]])
        y_true = np.array([[1.0], [0.0]])
        loss, _ = focal_loss(y_pred, y_true)
        assert loss < 0.5  # focal loss 不为 0 但应较小

    def test_alpha_weighting(self):
        """TC-LOSS-010: alpha 参数影响正负类权重."""
        y_pred = np.array([[0.3], [0.3]])
        y_true = np.array([[1.0], [0.0]])
        # alpha=0.99 (重正类) vs alpha=0.5 (平衡)
        loss_high_alpha, _ = focal_loss(y_pred, y_true, alpha=0.99)
        loss_balanced, _ = focal_loss(y_pred, y_true, alpha=0.5)
        # 不同 alpha 应产生不同 loss
        assert loss_high_alpha != loss_balanced

    def test_gamma_focusing(self):
        """TC-LOSS-011: gamma 参数控制难易样本权重."""
        # 简单样本 (预测正确, 高置信度)
        y_pred_easy = np.array([[0.95]])
        y_true = np.array([[1.0]])
        # 难样本 (预测错误, 低置信度)
        y_pred_hard = np.array([[0.05]])
        y_true_hard = np.array([[1.0]])

        # gamma=0: focal loss 退化为 BCE
        loss_easy_g0, _ = focal_loss(y_pred_easy, y_true, gamma=0.0)
        loss_hard_g0, _ = focal_loss(y_pred_hard, y_true_hard, gamma=0.0)

        # gamma=2: focal loss 加权难样本
        loss_easy_g2, _ = focal_loss(y_pred_easy, y_true, gamma=2.0)
        loss_hard_g2, _ = focal_loss(y_pred_hard, y_true_hard, gamma=2.0)

        # gamma=2 时 easy 样本被 down-weight, loss 应小于 gamma=0
        assert loss_easy_g2 < loss_easy_g0
        # gamma=2 时 hard 样本相对权重更高
        # 不严格断言 hard_g2 > hard_g0, 因为 focal 整体可能减小
        # 但 ratio hard/easy 应增大
        ratio_g0 = loss_hard_g0 / max(loss_easy_g0, 1e-10)
        ratio_g2 = loss_hard_g2 / max(loss_easy_g2, 1e-10)
        assert ratio_g2 > ratio_g0

    def test_clip_avoids_log_zero(self):
        """TC-LOSS-012: 边界值 (0, 1) 通过 clip 避免除零."""
        y_pred = np.array([[0.0], [1.0]])
        y_true = np.array([[0.0], [1.0]])
        loss, grad = focal_loss(y_pred, y_true)
        assert np.isfinite(loss)
        assert np.all(np.isfinite(grad))


class TestComputeClassWeights:
    """Test compute_class_weights."""

    def test_balanced_dataset(self):
        """TC-LOSS-013: 平衡数据集 (50/50) 权重相等."""
        y = np.array([0, 0, 1, 1])
        weights = compute_class_weights(y)
        assert weights[0] == 1.0
        assert weights[1] == 1.0

    def test_imbalanced_dataset(self):
        """TC-LOSS-014: 不平衡数据集, 少数类权重更高."""
        y = np.array([0] * 90 + [1] * 10)  # 9:1
        weights = compute_class_weights(y)
        # 少数类 (1) 权重应大于多数类 (0)
        assert weights[1] > weights[0]
        # 理论值: total / (n_classes * count)
        # class 0: 100 / (2 * 90) ≈ 0.556
        # class 1: 100 / (2 * 10) = 5.0
        assert abs(weights[0] - 100 / 180) < 0.01
        assert abs(weights[1] - 5.0) < 0.01

    def test_three_classes(self):
        """TC-LOSS-015: 3 类数据集."""
        y = np.array([0, 0, 1, 1, 2, 2])
        weights = compute_class_weights(y)
        assert len(weights) == 3
        # 平衡时所有类权重 = 1.0
        for cls in [0, 1, 2]:
            assert abs(weights[cls] - 1.0) < 0.01

    def test_returns_int_keys(self):
        """TC-LOSS-016: 返回的键为 int 类型."""
        y = np.array([0, 1])
        weights = compute_class_weights(y)
        for k in weights.keys():
            assert isinstance(k, int)
