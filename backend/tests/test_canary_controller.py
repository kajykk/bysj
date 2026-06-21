"""
Test suite for canary release controller.

Tests:
- TC-CAN-001: 验证用户 ID 哈希一致性
- TC-CAN-002: 验证流量分配
- TC-CAN-003: 验证新模型路由
- TC-CAN-004: 验证旧模型路由
- TC-CAN-005: 验证并行执行
- TC-CAN-006: 验证对比日志
- TC-CAN-007: 验证流量调整
- TC-CAN-008: 验证升级和回滚
- TC-CAN-009: 验证状态保存与加载
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

from app.ml.canary_controller import CanaryConfig, CanaryController


class TestCanaryController:
    """Test suite for canary controller."""

    @pytest.fixture
    def old_model(self) -> MagicMock:
        """Create old model mock."""
        model = MagicMock()
        model.predict.return_value = np.array([0, 1, 0])
        return model

    @pytest.fixture
    def new_model(self) -> MagicMock:
        """Create new model mock."""
        model = MagicMock()
        model.predict.return_value = np.array([1, 0, 1])
        return model

    def test_user_id_hash_consistency(self) -> None:
        """TC-CAN-001: 验证用户 ID 哈希一致性."""
        config = CanaryConfig()
        controller = CanaryController(config=config)

        # Same user ID should always get same result
        user_id = "user_123"
        result1 = controller.should_use_new_model(user_id)
        result2 = controller.should_use_new_model(user_id)

        assert result1 == result2

    def test_traffic_allocation(self) -> None:
        """TC-CAN-002: 验证流量分配."""
        config = CanaryConfig(new_model_traffic_percentage=50.0)
        controller = CanaryController(config=config)

        # Test with many users
        new_model_count = 0
        total = 1000

        for i in range(total):
            if controller.should_use_new_model(f"user_{i}"):
                new_model_count += 1

        # Should be approximately 50%
        ratio = new_model_count / total
        assert 0.45 <= ratio <= 0.55, f"Ratio {ratio} not within expected range"

    def test_new_model_routing(self, old_model: MagicMock, new_model: MagicMock) -> None:
        """TC-CAN-003: 验证新模型路由."""
        config = CanaryConfig(new_model_traffic_percentage=100.0, enable_parallel_execution=False)
        controller = CanaryController(config=config, old_model=old_model, new_model=new_model)

        X = np.random.randn(3, 10)
        result = controller.predict(X, user_id="test_user")

        assert result["model_used"] == "new"
        new_model.predict.assert_called_once()

    def test_old_model_routing(self, old_model: MagicMock, new_model: MagicMock) -> None:
        """TC-CAN-004: 验证旧模型路由."""
        config = CanaryConfig(new_model_traffic_percentage=0.0, enable_parallel_execution=False)
        controller = CanaryController(config=config, old_model=old_model, new_model=new_model)

        X = np.random.randn(3, 10)
        result = controller.predict(X, user_id="test_user")

        assert result["model_used"] == "old"
        old_model.predict.assert_called_once()

    def test_parallel_execution(self, old_model: MagicMock, new_model: MagicMock) -> None:
        """TC-CAN-005: 验证并行执行."""
        config = CanaryConfig(
            new_model_traffic_percentage=50.0,
            enable_parallel_execution=True,
        )
        controller = CanaryController(config=config, old_model=old_model, new_model=new_model)

        X = np.random.randn(3, 10)
        controller.predict(X, user_id="test_user")

        # Both models should be called for comparison
        assert old_model.predict.called
        assert new_model.predict.called

    def test_comparison_logging(self, old_model: MagicMock, new_model: MagicMock) -> None:
        """TC-CAN-006: 验证对比日志."""
        config = CanaryConfig(
            new_model_traffic_percentage=50.0,
            enable_parallel_execution=True,
        )
        controller = CanaryController(config=config, old_model=old_model, new_model=new_model)

        X = np.random.randn(3, 10)
        controller.predict(X, user_id="test_user")

        assert len(controller.comparison_history) > 0

        summary = controller.get_comparison_summary()
        assert "total_comparisons" in summary
        assert summary["total_comparisons"] > 0

    def test_traffic_adjustment(self, old_model: MagicMock, new_model: MagicMock) -> None:
        """TC-CAN-007: 验证流量调整."""
        config = CanaryConfig(new_model_traffic_percentage=10.0)
        controller = CanaryController(config=config, old_model=old_model, new_model=new_model)

        assert controller.config.new_model_traffic_percentage == 10.0

        controller.adjust_traffic(50.0)
        assert controller.config.new_model_traffic_percentage == 50.0

    def test_promote_and_rollback(self, old_model: MagicMock, new_model: MagicMock) -> None:
        """TC-CAN-008: 验证升级和回滚."""
        controller = CanaryController(
            config=CanaryConfig(new_model_traffic_percentage=10.0),
            old_model=old_model,
            new_model=new_model,
        )

        # Promote
        controller.promote_new_model()
        assert controller.config.new_model_traffic_percentage == 100.0

        # Rollback
        controller.rollback()
        assert controller.config.new_model_traffic_percentage == 0.0

    def test_state_save_load(self, old_model: MagicMock, new_model: MagicMock, tmp_path: Path) -> None:
        """TC-CAN-009: 验证状态保存与加载."""
        controller = CanaryController(
            config=CanaryConfig(new_model_traffic_percentage=25.0),
            old_model=old_model,
            new_model=new_model,
        )

        # Make some predictions
        X = np.random.randn(3, 10)
        for i in range(10):
            controller.predict(X, user_id=f"user_{i}")

        state_path = tmp_path / "canary_state.json"
        controller.save_state(state_path)

        assert state_path.exists()

        loaded_controller = CanaryController.load_state(state_path)

        assert loaded_controller.config.new_model_traffic_percentage == 25.0
        assert loaded_controller.new_model_requests == controller.new_model_requests
        assert loaded_controller.old_model_requests == controller.old_model_requests

    def test_comparison_summary(self, old_model: MagicMock, new_model: MagicMock) -> None:
        """TC-CAN-010: 验证对比摘要."""
        controller = CanaryController(
            config=CanaryConfig(new_model_traffic_percentage=50.0),
            old_model=old_model,
            new_model=new_model,
        )

        # Make predictions with different results
        old_model.predict.return_value = np.array([0, 1, 0])
        new_model.predict.return_value = np.array([1, 0, 1])

        X = np.random.randn(3, 10)
        for i in range(10):
            controller.predict(X, user_id=f"user_{i}")

        summary = controller.get_comparison_summary()

        assert "mismatch_rate" in summary
        assert summary["mismatch_rate"] > 0  # Different predictions should mismatch

    def test_empty_comparison_history(self) -> None:
        """TC-CAN-011: 验证空对比历史."""
        controller = CanaryController()

        summary = controller.get_comparison_summary()

        assert "message" in summary
        assert summary["message"] == "No comparison data available"
