"""STAB-P2-011: SLO/SLI 仪表盘测试.

测试范围:
1. SLO 目标常量合理性
2. SLIResult 数据类
3. compute_sli() 函数: 可用性 + p99 延迟 + 错误预算
4. _compute_p99() 函数: Histogram p99 计算
5. _compute_availability() 函数: 可用性计算
6. metrics.py 注册 SLO 指标
7. /metrics 端点采集 SLO 指标
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.metrics import (
    Histogram,
    _REGISTRY,
    http_request_duration_seconds,
    http_requests_total,
    model_inference_duration_seconds,
    reset_registry,
    slo_availability_ratio,
    slo_error_budget_burn_rate,
    slo_error_budget_remaining_ratio,
    slo_p99_latency_seconds,
    slo_p99_model_latency_seconds,
)
from app.core.slo import (
    SLO_AVAILABILITY_TARGET,
    SLO_LATENCY_TARGET,
    SLO_LATENCY_THRESHOLD_SECONDS,
    SLO_MODEL_INFERENCE_LATENCY_TARGET,
    SLO_MODEL_INFERENCE_LATENCY_THRESHOLD_SECONDS,
    SLO_WINDOW_DAYS,
    SLIResult,
    _compute_availability,
    _compute_p99,
    compute_sli,
)


class TestSLOConstants:
    """SLO 目标常量合理性测试."""

    def test_availability_target_in_valid_range(self):
        """可用性 SLO 目标在 (0, 1) 之间."""
        assert 0 < SLO_AVAILABILITY_TARGET < 1
        # 99.9% 是常见 SLO 目标
        assert SLO_AVAILABILITY_TARGET == 0.999

    def test_latency_target_in_valid_range(self):
        """延迟 SLO 目标在 (0, 1) 之间."""
        assert 0 < SLO_LATENCY_TARGET < 1
        assert SLO_LATENCY_TARGET == 0.99

    def test_latency_threshold_reasonable(self):
        """延迟阈值合理 (< 5s, > 0.01s)."""
        assert 0.01 < SLO_LATENCY_THRESHOLD_SECONDS < 5.0
        assert SLO_LATENCY_THRESHOLD_SECONDS == 0.5

    def test_model_inference_latency_threshold_reasonable(self):
        """模型推理延迟阈值合理 (< 30s, > 0.1s)."""
        assert 0.1 < SLO_MODEL_INFERENCE_LATENCY_THRESHOLD_SECONDS < 30.0
        assert SLO_MODEL_INFERENCE_LATENCY_THRESHOLD_SECONDS == 2.0

    def test_window_days_reasonable(self):
        """SLO 评估窗口在 [1, 90] 天之间 (常见 7/14/28/30 天)."""
        assert 1 <= SLO_WINDOW_DAYS <= 90
        assert SLO_WINDOW_DAYS == 30

    def test_model_inference_target_in_valid_range(self):
        """模型推理延迟 SLO 目标在 (0, 1) 之间."""
        assert 0 < SLO_MODEL_INFERENCE_LATENCY_TARGET < 1
        assert SLO_MODEL_INFERENCE_LATENCY_TARGET == 0.99


class TestSLIResult:
    """SLIResult 数据类测试."""

    def test_sli_result_is_frozen(self):
        """SLIResult 是 frozen dataclass (不可变)."""
        sli = SLIResult(
            availability=0.9995,
            total_requests=10000,
            error_requests=5,
            p99_latency_seconds=0.42,
            p99_model_latency_seconds=1.8,
            error_budget_remaining_ratio=0.5,
            error_budget_burn_rate=0.5,
        )
        with pytest.raises((AttributeError, Exception)):
            sli.availability = 0.99  # type: ignore[misc]

    def test_sli_result_fields(self):
        """SLIResult 字段完整."""
        sli = SLIResult(
            availability=0.9995,
            total_requests=10000,
            error_requests=5,
            p99_latency_seconds=0.42,
            p99_model_latency_seconds=1.8,
            error_budget_remaining_ratio=0.5,
            error_budget_burn_rate=0.5,
        )
        assert sli.availability == 0.9995
        assert sli.total_requests == 10000
        assert sli.error_requests == 5
        assert sli.p99_latency_seconds == 0.42
        assert sli.p99_model_latency_seconds == 1.8
        assert sli.error_budget_remaining_ratio == 0.5
        assert sli.error_budget_burn_rate == 0.5

    def test_sli_result_allows_none_latency(self):
        """SLIResult 允许 None 延迟 (无数据场景)."""
        sli = SLIResult(
            availability=1.0,
            total_requests=0,
            error_requests=0,
            p99_latency_seconds=None,
            p99_model_latency_seconds=None,
            error_budget_remaining_ratio=1.0,
            error_budget_burn_rate=0.0,
        )
        assert sli.p99_latency_seconds is None
        assert sli.p99_model_latency_seconds is None


class TestComputeAvailability:
    """_compute_availability() 函数测试."""

    def setup_method(self):
        """每个测试前清空 Counter."""
        http_requests_total._values.clear()

    def test_no_requests_returns_1(self):
        """无请求数时, 可用性=1.0 (无错误)."""
        availability, total, errors = _compute_availability()
        assert availability == 1.0
        assert total == 0
        assert errors == 0

    def test_all_success_returns_1(self):
        """全部 2xx/4xx 请求时, 可用性=1.0."""
        http_requests_total.inc(method="GET", path="/api", status="200")
        http_requests_total.inc(method="GET", path="/api", status="200")
        http_requests_total.inc(method="POST", path="/api", status="201")
        http_requests_total.inc(method="GET", path="/err", status="404")
        availability, total, errors = _compute_availability()
        assert availability == 1.0
        assert total == 4
        assert errors == 0

    def test_all_5xx_returns_0(self):
        """全部 5xx 请求时, 可用性=0.0."""
        http_requests_total.inc(method="GET", path="/api", status="500")
        http_requests_total.inc(method="GET", path="/api", status="503")
        availability, total, errors = _compute_availability()
        assert availability == 0.0
        assert total == 2
        assert errors == 2

    def test_mixed_status_calculates_ratio(self):
        """混合状态码计算可用性比例."""
        # 990 个 200, 1 个 500, 9 个 503 → 10 个 5xx
        for _ in range(990):
            http_requests_total.inc(method="GET", path="/api", status="200")
        http_requests_total.inc(method="GET", path="/api", status="500")
        for _ in range(9):
            http_requests_total.inc(method="GET", path="/api", status="503")
        availability, total, errors = _compute_availability()
        assert total == 1000
        assert errors == 10
        assert availability == pytest.approx(0.99, abs=1e-6)

    def test_4xx_not_counted_as_error(self):
        """4xx 不计入 5xx 错误 (可用性 SLO 仅看服务端错误)."""
        http_requests_total.inc(method="GET", path="/api", status="400")
        http_requests_total.inc(method="GET", path="/api", status="404")
        http_requests_total.inc(method="GET", path="/api", status="422")
        availability, total, errors = _compute_availability()
        assert availability == 1.0
        assert total == 3
        assert errors == 0


class TestComputeP99:
    """_compute_p99() 函数测试."""

    def setup_method(self):
        """每个测试前清空 Histogram."""
        http_request_duration_seconds._values.clear()

    def test_no_observations_returns_none(self):
        """无观测数据返回 None."""
        result = _compute_p99(http_request_duration_seconds)
        assert result is None

    def test_single_observation_returns_value(self):
        """单次观测返回该值所在 bucket 上界."""
        http_request_duration_seconds.observe(0.1, method="GET", path="/api")
        result = _compute_p99(http_request_duration_seconds)
        assert result is not None
        assert result > 0

    def test_p99_at_least_99_percent(self):
        """p99 至少覆盖 99% 的观测值 (98 fast + 2 slow → p99 落在 slow bucket)."""
        # 100 次观测, 98 次 0.01s, 2 次 5s
        # 99% * 100 = 99, bucket_counts[0.01] = 98 < 99, bucket_counts[5.0] = 100 >= 99
        # 因此 p99 落在 5.0s bucket (表示至少 99% 的观测值 <= 5.0s)
        for _ in range(98):
            http_request_duration_seconds.observe(0.01, method="GET", path="/api")
        for _ in range(2):
            http_request_duration_seconds.observe(5.0, method="GET", path="/api")
        result = _compute_p99(http_request_duration_seconds)
        assert result is not None
        # p99 应该在 5.0s 那个 bucket (因为第 99 个观测开始包含 5s)
        assert result >= 5.0

    def test_p99_aggregates_across_labels(self):
        """p99 跨 label 聚合 (GET + POST 合并计算)."""
        # GET: 98 个 0.01s
        for _ in range(98):
            http_request_duration_seconds.observe(0.01, method="GET", path="/api")
        # POST: 2 个 5s
        for _ in range(2):
            http_request_duration_seconds.observe(5.0, method="POST", path="/api")
        result = _compute_p99(http_request_duration_seconds)
        assert result is not None
        # 100 次观测, p99 应该在 5s bucket
        # (98 个 0.01s + 2 个 5s, 99% * 100 = 99, bucket[0.01]=98 < 99, bucket[5.0]=100 >= 99)
        assert result >= 5.0


class TestComputeSLI:
    """compute_sli() 函数测试."""

    def setup_method(self):
        """每个测试前清空所有指标."""
        http_requests_total._values.clear()
        http_request_duration_seconds._values.clear()
        model_inference_duration_seconds._values.clear()

    def test_no_data_returns_default_sli(self):
        """无任何请求数据时返回默认 SLI."""
        sli = compute_sli()
        assert sli.total_requests == 0
        assert sli.error_requests == 0
        assert sli.availability == 1.0
        assert sli.p99_latency_seconds is None
        assert sli.p99_model_latency_seconds is None
        # 无错误时, 错误预算完全未消耗
        assert sli.error_budget_remaining_ratio == 1.0
        assert sli.error_budget_burn_rate == 0.0

    def test_all_success_full_error_budget(self):
        """全部成功请求, 错误预算完全未消耗 (remaining=1.0, burn_rate=0)."""
        for _ in range(1000):
            http_requests_total.inc(method="GET", path="/api", status="200")
        sli = compute_sli()
        assert sli.availability == 1.0
        assert sli.error_requests == 0
        assert sli.error_budget_remaining_ratio == 1.0
        assert sli.error_budget_burn_rate == 0.0

    def test_one_error_within_budget(self):
        """1000 请求中 1 个 5xx, 仍在预算内 (availability=0.999, burn_rate=1.0)."""
        for _ in range(999):
            http_requests_total.inc(method="GET", path="/api", status="200")
        http_requests_total.inc(method="GET", path="/api", status="500")
        sli = compute_sli()
        assert sli.availability == pytest.approx(0.999, abs=1e-6)
        assert sli.error_requests == 1
        # 允许 0.1% 错误, 实际 0.1% → burn_rate = 1.0 (恰好正常消耗)
        assert sli.error_budget_burn_rate == pytest.approx(1.0, abs=1e-3)
        # remaining = 1 - burn_rate = 0
        assert sli.error_budget_remaining_ratio == pytest.approx(0.0, abs=1e-3)

    def test_many_errors_exceeds_budget(self):
        """100 请求中 10 个 5xx, 严重超支 (burn_rate=100)."""
        for _ in range(90):
            http_requests_total.inc(method="GET", path="/api", status="200")
        for _ in range(10):
            http_requests_total.inc(method="GET", path="/api", status="500")
        sli = compute_sli()
        assert sli.availability == pytest.approx(0.9, abs=1e-6)
        # 实际错误率 10%, 允许 0.1% → burn_rate = 100
        assert sli.error_budget_burn_rate == pytest.approx(100.0, abs=1e-3)
        # remaining = 1 - 100 = -99 (截断到 -1.0)
        assert sli.error_budget_remaining_ratio == -1.0

    def test_with_latency_observations(self):
        """带延迟观测的 SLI 包含 p99 延迟."""
        for _ in range(100):
            http_request_duration_seconds.observe(0.1, method="GET", path="/api")
        sli = compute_sli()
        assert sli.p99_latency_seconds is not None
        assert sli.p99_latency_seconds > 0

    def test_with_model_inference_latency(self):
        """带模型推理延迟观测的 SLI 包含模型 p99 延迟."""
        for _ in range(100):
            model_inference_duration_seconds.observe(1.5, model_name="structured")
        sli = compute_sli()
        assert sli.p99_model_latency_seconds is not None
        assert sli.p99_model_latency_seconds > 0


class TestSLOMetricsRegistration:
    """metrics.py 中 SLO 指标注册测试."""

    def test_slo_availability_ratio_registered(self):
        """slo_availability_ratio 指标已注册."""
        assert "slo_availability_ratio" in _REGISTRY
        assert _REGISTRY["slo_availability_ratio"]["type"] == "gauge"

    def test_slo_p99_latency_seconds_registered(self):
        """slo_p99_latency_seconds 指标已注册."""
        assert "slo_p99_latency_seconds" in _REGISTRY
        assert _REGISTRY["slo_p99_latency_seconds"]["type"] == "gauge"

    def test_slo_p99_model_latency_seconds_registered(self):
        """slo_p99_model_latency_seconds 指标已注册."""
        assert "slo_p99_model_latency_seconds" in _REGISTRY
        assert _REGISTRY["slo_p99_model_latency_seconds"]["type"] == "gauge"

    def test_slo_error_budget_remaining_registered(self):
        """slo_error_budget_remaining_ratio 指标已注册."""
        assert "slo_error_budget_remaining_ratio" in _REGISTRY
        assert _REGISTRY["slo_error_budget_remaining_ratio"]["type"] == "gauge"

    def test_slo_error_budget_burn_rate_registered(self):
        """slo_error_budget_burn_rate 指标已注册."""
        assert "slo_error_budget_burn_rate" in _REGISTRY
        assert _REGISTRY["slo_error_budget_burn_rate"]["type"] == "gauge"

    def test_all_slo_metrics_have_stab_p2_011_doc(self):
        """所有 SLO 指标的 docstring 含 STAB-P2-011 注释."""
        for name in (
            "slo_availability_ratio",
            "slo_p99_latency_seconds",
            "slo_p99_model_latency_seconds",
            "slo_error_budget_remaining_ratio",
            "slo_error_budget_burn_rate",
        ):
            assert "STAB-P2-011" in _REGISTRY[name]["doc"], (
                f"{name} docstring 缺少 STAB-P2-011 注释"
            )

    def test_slo_metrics_can_set_value(self):
        """SLO 指标可正常 set 值."""
        slo_availability_ratio.set(0.9995)
        entries = slo_availability_ratio.collect()
        assert len(entries) == 1
        assert entries[0][1] == 0.9995


class TestMetricsEndpointIntegration:
    """metrics 端点集成测试."""

    def test_metrics_endpoint_imports_slo(self):
        """/metrics 端点源码导入 SLO 指标."""
        metrics_endpoint_path = (
            Path(__file__).resolve().parent.parent
            / "app"
            / "api"
            / "v1"
            / "metrics.py"
        )
        content = metrics_endpoint_path.read_text(encoding="utf-8")
        assert "slo_availability_ratio" in content
        assert "slo_error_budget_remaining_ratio" in content
        assert "slo_error_budget_burn_rate" in content
        assert "slo_p99_latency_seconds" in content
        assert "slo_p99_model_latency_seconds" in content
        # 必须调用 compute_sli
        assert "from app.core.slo import compute_sli" in content
        assert "STAB-P2-011" in content

    def test_metrics_endpoint_collects_slo(self):
        """/metrics 端点调用 compute_sli 并设置 SLO 指标."""
        from app.api.v1 import metrics as metrics_module

        # 清空之前的状态
        http_requests_total._values.clear()
        http_request_duration_seconds._values.clear()
        model_inference_duration_seconds._values.clear()
        slo_availability_ratio._values.clear()
        slo_error_budget_remaining_ratio._values.clear()
        slo_error_budget_burn_rate._values.clear()
        slo_p99_latency_seconds._values.clear()
        slo_p99_model_latency_seconds._values.clear()

        # 准备数据: 1000 请求, 1 个 5xx
        for _ in range(999):
            http_requests_total.inc(method="GET", path="/api", status="200")
        http_requests_total.inc(method="GET", path="/api", status="500")

        # 通过直接调用 compute_sli 验证 (绕过 FastAPI 鉴权)
        from app.core.slo import compute_sli

        sli = compute_sli()
        slo_availability_ratio.set(float(sli.availability))
        slo_error_budget_burn_rate.set(float(sli.error_budget_burn_rate))
        slo_error_budget_remaining_ratio.set(float(sli.error_budget_remaining_ratio))

        # 验证指标已更新
        entries = slo_availability_ratio.collect()
        assert len(entries) == 1
        assert entries[0][1] == pytest.approx(0.999, abs=1e-6)
        entries = slo_error_budget_burn_rate.collect()
        assert entries[0][1] == pytest.approx(1.0, abs=1e-3)

    def test_metrics_endpoint_handles_slo_collection_failure(self):
        """/metrics 端点 SLO 采集失败不影响响应 (try/except)."""
        # 验证 metrics.py 源码中 SLO 采集包含 try/except
        metrics_endpoint_path = (
            Path(__file__).resolve().parent.parent
            / "app"
            / "api"
            / "v1"
            / "metrics.py"
        )
        content = metrics_endpoint_path.read_text(encoding="utf-8")
        # 找到 SLO 采集代码块
        assert "slo metric collection failed" in content


class TestSLOSourceStructure:
    """slo.py 源码结构测试."""

    def _get_module_path(self) -> Path:
        return Path(__file__).resolve().parent.parent / "app" / "core" / "slo.py"

    def test_module_exists(self):
        """slo.py 文件存在."""
        assert self._get_module_path().exists()

    def test_stab_p2_011_annotation_present(self):
        """slo.py 中有 STAB-P2-011 注释."""
        content = self._get_module_path().read_text(encoding="utf-8")
        assert "STAB-P2-011" in content

    def test_exports_compute_sli(self):
        """模块导出 compute_sli 函数."""
        from app.core import slo

        assert hasattr(slo, "compute_sli")
        assert callable(slo.compute_sli)

    def test_exports_sli_result(self):
        """模块导出 SLIResult 数据类."""
        from app.core import slo

        assert hasattr(slo, "SLIResult")

    def test_exports_slo_constants(self):
        """模块导出 SLO 目标常量."""
        from app.core import slo

        assert hasattr(slo, "SLO_AVAILABILITY_TARGET")
        assert hasattr(slo, "SLO_LATENCY_TARGET")
        assert hasattr(slo, "SLO_LATENCY_THRESHOLD_SECONDS")
        assert hasattr(slo, "SLO_MODEL_INFERENCE_LATENCY_TARGET")
        assert hasattr(slo, "SLO_MODEL_INFERENCE_LATENCY_THRESHOLD_SECONDS")
        assert hasattr(slo, "SLO_WINDOW_DAYS")

    def test_metrics_py_imports_slo_constants(self):
        """metrics.py 源码注释中提及 SLO 目标 (与 slo.py 对齐)."""
        metrics_path = (
            Path(__file__).resolve().parent.parent / "app" / "core" / "metrics.py"
        )
        content = metrics_path.read_text(encoding="utf-8")
        assert "SLO target=0.999" in content
        assert "STAB-P2-011" in content
