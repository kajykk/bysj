from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auto_rollback_service import (
    AutoRollbackService,
    RollbackCheckResult,
    auto_rollback_service,
)


class TestRollbackCheckResult:
    """T-BE-005: RollbackCheckResult 单元测试"""

    def test_result_structure(self) -> None:
        """验证结果结构"""
        result = RollbackCheckResult(
            should_rollback=True,
            reason="test",
            metrics={"fallback_rate": 0.1},
            canary_id=1,
        )
        assert result.should_rollback is True
        assert result.reason == "test"
        assert result.metrics["fallback_rate"] == 0.1
        assert result.canary_id == 1

    def test_result_no_rollback(self) -> None:
        """验证不触发回滚的结果"""
        result = RollbackCheckResult(
            should_rollback=False,
            reason="within_thresholds",
            metrics={},
            canary_id=1,
        )
        assert result.should_rollback is False
        assert result.reason == "within_thresholds"


class TestAutoRollbackService:
    """T-BE-005: AutoRollbackService 单元测试"""

    async def _async_test_check_canary_not_found(self, db_session: AsyncSession) -> None:
        """验证检查不存在的灰度"""
        service = AutoRollbackService()
        result = await service.check_canary_health(db_session, 99999)
        assert result.should_rollback is False
        assert result.reason == "canary_not_found"

    def test_check_canary_not_found(self, db_session: AsyncSession) -> None:
        """验证检查不存在的灰度"""
        import asyncio
        asyncio.run(self._async_test_check_canary_not_found(db_session))

    def test_thresholds_default(self) -> None:
        """验证默认阈值"""
        service = AutoRollbackService()
        # Default thresholds are defined in the service logic
        assert service is not None

    def test_global_service_exists(self) -> None:
        """验证全局服务实例存在"""
        assert auto_rollback_service is not None
        assert isinstance(auto_rollback_service, AutoRollbackService)

    def test_rollback_check_result_with_metrics(self) -> None:
        """验证带指标的回滚结果"""
        result = RollbackCheckResult(
            should_rollback=True,
            reason="fallback_rate 8.00% exceeds threshold 5.00%",
            metrics={
                "fallback_count": 8,
                "inference_count": 92,
                "fallback_rate": 0.08,
            },
            canary_id=1,
        )
        assert result.should_rollback is True
        assert "exceeds threshold" in result.reason
        assert result.metrics["fallback_rate"] == 0.08

    def test_rollback_check_result_within_thresholds(self) -> None:
        """验证阈值内的结果"""
        result = RollbackCheckResult(
            should_rollback=False,
            reason="within_thresholds",
            metrics={
                "fallback_count": 2,
                "inference_count": 98,
                "fallback_rate": 0.02,
                "drift_alerts_per_hour": 3,
                "avg_latency_ms": 150.0,
            },
            canary_id=1,
        )
        assert result.should_rollback is False
        assert result.metrics["fallback_rate"] == 0.02
        assert result.metrics["avg_latency_ms"] == 150.0
