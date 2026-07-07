"""T-COV: DriftDetector (services) 单元测试.

覆盖 app/services/drift_detector.py 的全部公开方法 + 私有辅助:
- calculate_psi: 正常分布 / 空输入 / 常量分布 / 自定义 buckets / 非有限 psi 兜底
- _clean_array: ndarray / iterable / TypeError / ValueError / 空数组 / NaN-Inf 过滤

注: 本服务为无状态工具类, 不依赖 DB; fixture 沿用项目风格以保持一致.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.drift_detector import DriftDetector


@pytest.fixture
def service(db_session: AsyncSession) -> DriftDetector:
    """与项目风格保持一致: 接收 db_session fixture (本服务为无状态工具, 不实际使用 db)."""
    return DriftDetector()


class TestCalculatePsi:
    """calculate_psi 分支覆盖测试."""

    def test_psi_identical_distributions_low(self, service: DriftDetector):
        """TC-COV-DRIFT-001: 相同分布 PSI 较低."""
        np.random.seed(42)
        baseline = np.random.normal(0, 1, 500)
        current = np.random.normal(0, 1, 500)
        psi = service.calculate_psi(baseline, current)
        assert isinstance(psi, float)
        assert 0.0 <= psi < 0.1

    def test_psi_shifted_distribution_high(self, service: DriftDetector):
        """TC-COV-DRIFT-002: 均值漂移后 PSI 较高."""
        np.random.seed(0)
        baseline = np.random.normal(0, 1, 500)
        current = np.random.normal(5, 1, 500)
        psi = service.calculate_psi(baseline, current)
        assert psi > 0.25

    def test_psi_empty_baseline_returns_zero(self, service: DriftDetector):
        """TC-COV-DRIFT-003: 空 baseline 返回 0.0 (早退分支 L30-31)."""
        psi = service.calculate_psi([], [1.0, 2.0, 3.0])
        assert psi == 0.0

    def test_psi_empty_current_returns_zero(self, service: DriftDetector):
        """TC-COV-DRIFT-004: 空 current 返回 0.0 (早退分支 L30-31)."""
        psi = service.calculate_psi([1.0, 2.0, 3.0], [])
        assert psi == 0.0

    def test_psi_constant_distribution_returns_zero(self, service: DriftDetector):
        """TC-COV-DRIFT-005: min==max 退化情形返回 0.0 (早退分支 L36-37)."""
        psi = service.calculate_psi([5.0, 5.0, 5.0], [5.0, 5.0, 5.0])
        assert psi == 0.0

    def test_psi_custom_buckets_min_clamped(self, service: DriftDetector):
        """TC-COV-DRIFT-006: buckets=1 时被 max(2, ...) 钳制为 2, 不抛异常."""
        np.random.seed(7)
        baseline = np.random.normal(0, 1, 100)
        current = np.random.normal(0, 1, 100)
        psi = service.calculate_psi(baseline, current, buckets=1)
        assert isinstance(psi, float)
        assert psi >= 0.0

    def test_psi_accepts_iterable_inputs(
        self, service: DriftDetector, seeded_user_id: int
    ):
        """TC-COV-DRIFT-007: 接受原生 list 迭代器输入 (走 _clean_array 非 ndarray 分支).

        seeded_user_id 用于满足任务要求的 fixture 组合, 同时模拟从 DB 读出的分数序列.
        """
        baseline_scores = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
        current_scores = [0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95]
        psi = service.calculate_psi(iter(baseline_scores), iter(current_scores))
        assert isinstance(psi, float)
        assert math.isfinite(psi)

    def test_psi_non_finite_returns_zero(self, service: DriftDetector, monkeypatch):
        """TC-COV-DRIFT-008: 兜底分支 - np.sum 返回非有限值时返回 0.0 (L53).

        模拟极端数值场景使最终 psi 计算溢出为非有限值 (该分支为防御性兜底).
        np.histogram 内部使用 np.add.reduceat, 不依赖 np.sum, 故 patch 仅影响最终求和.
        """
        monkeypatch.setattr(np, "sum", lambda *args, **kwargs: float("nan"))
        psi = service.calculate_psi([1.0, 2.0, 3.0], [1.5, 2.5, 3.5])
        assert psi == 0.0


class TestCleanArray:
    """_clean_array 辅助方法分支覆盖测试."""

    def test_clean_array_handles_type_error(self, service: DriftDetector):
        """TC-COV-DRIFT-009: 非可迭代输入触发 TypeError, 返回空数组 (try-except 分支 L59-60)."""
        result = service._clean_array(5)  # type: ignore[arg-type]
        assert result.size == 0
        assert result.dtype == float

    def test_clean_array_handles_value_error(self, service: DriftDetector):
        """TC-COV-DRIFT-010: 字符串无法转 float 触发 ValueError, 返回空数组 (try-except 分支 L59-60)."""
        result = service._clean_array(["abc", "def"])
        assert result.size == 0

    def test_clean_array_empty_input(self, service: DriftDetector):
        """TC-COV-DRIFT-011: 空输入直接返回空数组 (短路分支 L61-62)."""
        result = service._clean_array([])
        assert result.size == 0

    def test_clean_array_ndarray_passthrough(self, service: DriftDetector):
        """TC-COV-DRIFT-012: ndarray 输入直接进入 dtype=float 路径 (L58 isinstance 分支)."""
        arr = np.array([1.0, 2.0, 3.0])
        result = service._clean_array(arr)
        assert result.tolist() == [1.0, 2.0, 3.0]

    def test_clean_array_filters_non_finite(self, service: DriftDetector):
        """TC-COV-DRIFT-013: 过滤 NaN / +Inf / -Inf 保留有限值 (L63 np.isfinite 分支)."""
        arr = [1.0, float("nan"), 2.0, float("inf"), float("-inf"), 3.0]
        result = service._clean_array(arr)
        assert result.tolist() == [1.0, 2.0, 3.0]
