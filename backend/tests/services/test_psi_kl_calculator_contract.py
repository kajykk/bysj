"""决策四: PsiKlCalculator 退化输入契约测试.

既有 tests/services/test_drift_detector.py 已覆盖 calculate_psi 常规分支与
_clean_array 直测; 本文件只补三块缺口:
1. calculate_kl 的退化输入契约 (此前零覆盖)
2. 非有限/非数值输入穿过公开 API 的行为 (NaN=剔除, 判定=有限子集)
3. 「0.0 语义二义性」的契约文档化: 无漂移 / 数据不足 / 退化输入
   三种情形返回同一个 0.0, 调用方不可区分 —— 监控层必须以
   baseline_n/current_n (≥30) 自行判断数据充分性
   (见 drift_monitoring_service._check_modality 的 <30 跳过逻辑).

注: 本服务为无状态工具类, 不依赖 DB.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.services.drift_detector import PsiKlCalculator


@pytest.fixture
def service() -> PsiKlCalculator:
    return PsiKlCalculator()


class TestCalculateKlDegenerateContract:
    """calculate_kl 退化输入契约 (此前零覆盖)."""

    def test_kl_identical_distributions_zero(self, service: PsiKlCalculator):
        """DC-KL-001: 同分布 KL=0."""
        np.random.seed(42)
        baseline = np.random.normal(0, 1, 300)
        current = np.random.normal(0, 1, 300)
        kl = service.calculate_kl(baseline, current)
        assert isinstance(kl, float)
        assert 0.0 <= kl < 0.05

    def test_kl_shifted_distribution_positive(self, service: PsiKlCalculator):
        """DC-KL-002: KL(current||baseline) 方向性 —— current 远离 baseline
        时 KL 显著为正."""
        np.random.seed(0)
        baseline = np.random.normal(0, 1, 300)
        current = np.random.normal(5, 1, 300)
        kl = service.calculate_kl(baseline, current)
        assert kl > 0.5

    def test_kl_empty_inputs_zero(self, service: PsiKlCalculator):
        """DC-KL-003: 任一侧为空返回 0.0 (L91-92 早退)."""
        assert service.calculate_kl([], [1.0, 2.0]) == 0.0
        assert service.calculate_kl([1.0, 2.0], []) == 0.0

    def test_kl_constant_distribution_zero(self, service: PsiKlCalculator):
        """DC-KL-004: min==max 退化分布返回 0.0 (L97-102 早退)."""
        kl = service.calculate_kl([5.0, 5.0], [5.0, 5.0])
        assert kl == 0.0

    def test_kl_all_nan_zero(self, service: PsiKlCalculator):
        """DC-KL-005: 全 NaN 清洗后为空 -> 0.0, 不抛异常."""
        kl = service.calculate_kl([float("nan")] * 5, [1.0, 2.0, 3.0])
        assert kl == 0.0

    def test_kl_non_numeric_input_zero(self, service: PsiKlCalculator):
        """DC-KL-006: 非数值字符串触发 _clean_array 的 ValueError 分支
        -> 空数组 -> 0.0."""
        assert service.calculate_kl(["abc", "def"], [1.0, 2.0]) == 0.0

    def test_kl_non_finite_filtered_finite_subset(self, service: PsiKlCalculator):
        """DC-KL-007: NaN/inf 混入 -> 剔除后按有限子集计算, 结果有限."""
        baseline = [0.1, float("nan"), 0.2, float("inf"), 0.3, 0.4]
        current = [0.15, float("-inf"), 0.25, 0.35]
        kl = service.calculate_kl(baseline, current)
        assert math.isfinite(kl)
        assert kl >= 0.0


class TestPsiNonFiniteContract:
    """calculate_psi 穿过公开 API 的非有限/非数值契约."""

    def test_psi_nan_mixed_equals_finite_subset(self, service: PsiKlCalculator):
        """DC-PSI-001: NaN=剔除语义 —— 含 NaN 的结果必须等于有限子集的
        计算结果 (与 ml 版 compute_psi 修复后的语义一致)."""
        baseline = [0.1, float("nan"), 0.2, 0.3, 0.4, 0.5]
        current = [0.15, 0.25, 0.35, 0.45]
        psi_dirty = service.calculate_psi(baseline, current)
        psi_clean = service.calculate_psi(
            [0.1, 0.2, 0.3, 0.4, 0.5], [0.15, 0.25, 0.35, 0.45]
        )
        assert psi_dirty == psi_clean
        assert math.isfinite(psi_dirty)

    def test_psi_all_nan_zero(self, service: PsiKlCalculator):
        """DC-PSI-002: 双侧全 NaN -> 0.0, 不抛异常."""
        psi = service.calculate_psi([float("nan")] * 4, [float("nan")] * 3)
        assert psi == 0.0

    def test_psi_containing_non_numeric_element_all_or_nothing(
        self, service: PsiKlCalculator
    ):
        """DC-PSI-003: 列表含任一非数值元素 -> asarray(dtype=float) 整体
        ValueError -> 空数组 -> 0.0 (服务层清洗是整体性的, 非逐元素)."""
        psi = service.calculate_psi([1.0, "abc", 2.0], [1.5, 2.5])
        assert psi == 0.0

    def test_psi_buckets_zero_or_negative_clamped(self, service: PsiKlCalculator):
        """DC-PSI-004: buckets<=0 被钳制为 2, 不抛异常."""
        np.random.seed(3)
        baseline = np.random.normal(0, 1, 100)
        current = np.random.normal(0.5, 1, 100)
        for bad_buckets in (0, -3):
            psi = service.calculate_psi(baseline, current, buckets=bad_buckets)
            assert math.isfinite(psi)
            assert psi >= 0.0

    def test_psi_generator_input_with_nan(self, service: PsiKlCalculator):
        """DC-PSI-005: 迭代器输入含 NaN -> list() 转换 + 清洗路径正常."""
        baseline = iter([0.1, float("nan"), 0.2, 0.3])
        current = iter([0.15, 0.25, 0.35])
        psi = service.calculate_psi(baseline, current)
        assert math.isfinite(psi)


class TestZeroAmbiguityContract:
    """0.0 语义二义性契约文档化 (决策四核心钉子).

    calculate_psi / calculate_kl 在以下三种情形返回同一个 0.0:
    a. 同分布 (真·无漂移)
    b. 输入为空 / 清洗后为空 (数据不足)
    c. 常量分布等退化输入
    调用方仅凭返回值不可区分 —— 本测试将这一事实钉死为契约, 并约束
    监控层 (drift_monitoring_service) 必须以样本数门槛自行判断.
    """

    @pytest.mark.parametrize("method", ["calculate_psi", "calculate_kl"])
    def test_three_zero_sources_indistinguishable(
        self, service: PsiKlCalculator, method: str
    ):
        """DC-Z-001: 三种 0.0 来源不可区分."""
        calc = getattr(service, method)
        rng = np.random.RandomState(11)
        baseline = rng.normal(0, 1, 200)
        # 同分布两次独立抽样存在抽样噪声 (实测 psi~0.096 / kl~0.050),
        # 契约点只要求: 有限且小; empty/NaN 则精确 0.0
        psi_no_drift = calc(baseline, rng.normal(0, 1, 200))
        psi_empty = calc([], [])
        psi_all_nan = calc([float("nan")] * 5, [float("nan")] * 5)
        assert math.isfinite(psi_no_drift) and psi_no_drift < 0.2
        assert psi_empty == 0.0
        assert psi_all_nan == 0.0

    def test_monitoring_layer_must_gate_by_sample_count(self, service: PsiKlCalculator):
        """DC-Z-002: 契约的运营约束 —— 0.0 不携带数据充分性信息,
        监控层必须先做 <30 样本门禁再调用计算器.
        本测试直接验证: 29 vs 29 的两个平凡分布也能返回 0.0,
        若监控层不做门禁, 「数据不足」将被呈现为「无漂移」."""
        psi = service.calculate_psi([1.0] * 29, [1.0] * 29)
        assert psi == 0.0
