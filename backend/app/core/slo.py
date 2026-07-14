"""STAB-P2-011: SLO/SLI 定义与错误预算计算.

提供 Service Level Objective (SLO) 目标常量、Service Level Indicator (SLI)
计算函数和 Error Budget (错误预算) 计算函数, 用于服务稳定性度量.

SLO 定义 (基于 Google SRE 实践):
- **可用性 SLO**: 99.9% (30 天允许 43.2 分钟 5xx 停机)
  - SLI: ``http_requests_total{status !~ 5xx}`` / ``http_requests_total``
  - 错误预算: ``(1 - 0.999) * total_requests = 0.1% * total``
- **延迟 SLO**: 99% 的请求 p99 < 500ms
  - SLI: ``http_request_duration_seconds`` 的 p99
  - 错误预算: ``(1 - 0.99) * total_requests = 1% * total`` (允许 1% 请求超 500ms)
- **模型推理 SLO**: 99% 的推理 < 2s
  - SLI: ``model_inference_duration_seconds`` 的 p99

错误预算计算:
- ``remaining_ratio`` = 1.0 - (actual_error_rate / allowed_error_rate)
  - 1.0 = 完全未消耗, 0.0 = 已耗尽, <0 = 已超支
- ``burn_rate`` = actual_error_rate / allowed_error_rate
  - 1.0 = 正常消耗速率, >1 = 快速消耗 (告警), <1 = 慢速消耗

设计原则:
- 复用现有 Prometheus 指标 (http_requests_total / http_request_duration_seconds /
  model_inference_duration_seconds), 不引入新数据源
- 计算函数纯函数式, 不修改全局状态, 便于测试
- SLO 目标常量集中定义, 通过 settings 可配置 (未来扩展)
- 错误预算窗口默认 30 天 (与 SLO 评估周期一致)

使用方式:

.. code-block:: python

    from app.core.slo import compute_sli, SLO_AVAILABILITY_TARGET

    sli = compute_sli()
    print(f"当前可用性: {sli.availability:.4f}")
    print(f"错误预算剩余: {sli.error_budget_remaining:.2%}")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.metrics import (
    http_request_duration_seconds,
    http_requests_total,
    model_inference_duration_seconds,
)

# STAB-P2-011: SLO 目标常量
# 可用性 SLO: 99.9% (允许 0.1% 5xx 错误率)
SLO_AVAILABILITY_TARGET: float = 0.999
# 延迟 SLO: 99% 请求 p99 < 500ms (允许 1% 请求超 500ms)
SLO_LATENCY_TARGET: float = 0.99
SLO_LATENCY_THRESHOLD_SECONDS: float = 0.5
# 模型推理延迟 SLO: 99% 推理 p99 < 2s
SLO_MODEL_INFERENCE_LATENCY_TARGET: float = 0.99
SLO_MODEL_INFERENCE_LATENCY_THRESHOLD_SECONDS: float = 2.0
# SLO 评估窗口 (天), 默认 30 天
SLO_WINDOW_DAYS: int = 30


@dataclass(frozen=True)
class SLIResult:
    """SLI 计算结果.

    Attributes:
        availability: 可用性 (0-1), 成功请求数 / 总请求数.
        total_requests: 总请求数 (累计).
        error_requests: 5xx 错误请求数 (累计).
        p99_latency_seconds: p99 延迟 (秒). None 表示无数据.
        p99_model_latency_seconds: 模型推理 p99 延迟 (秒). None 表示无数据.
        error_budget_remaining_ratio: 错误预算剩余比例 (1.0=满, 0.0=耗尽, 负值=超支).
        error_budget_burn_rate: 错误预算消耗速率 (1.0=正常, >1=快速消耗).
    """

    availability: float
    total_requests: int
    error_requests: int
    p99_latency_seconds: float | None
    p99_model_latency_seconds: float | None
    error_budget_remaining_ratio: float
    error_budget_burn_rate: float


def _compute_p99(histogram: Any) -> float | None:
    """从 Histogram 指标计算 p99 延迟.

    Args:
        histogram: Histogram 实例 (http_request_duration_seconds 或
            model_inference_duration_seconds).

    Returns:
        p99 延迟 (秒). 若无观测数据, 返回 None.
    """
    entries = histogram.collect()
    if not entries:
        return None

    # 聚合所有 label 组的 bucket 数据
    # 注意: Histogram 的 bucket count 本身就是累积计数 (obs <= b), 聚合后仍是累积计数,
    # 不应再累加 (否则 double-count). 例如 entry[bucket=0.025] = 50 表示 50 个 obs <= 0.025.
    total_count = 0
    bucket_counts: dict[float, int] = {b: 0 for b in histogram.buckets}
    for _labels, bucket_data in entries:
        for b in histogram.buckets:
            bucket_counts[b] += int(bucket_data.get(b, 0))
        total_count += int(bucket_data.get("_count", 0))

    if total_count == 0:
        return None

    # p99: 找到第一个 bucket (累积计数 >= 99% * total_count)
    target_count = total_count * 0.99
    for b in histogram.buckets:
        if bucket_counts.get(b, 0) >= target_count:
            return float(b) if b != float("inf") else None
    return None


def _compute_availability() -> tuple[float, int, int]:
    """从 http_requests_total 计算可用性.

    Returns:
        (availability, total_requests, error_requests) 三元组.
        availability = 1.0 当 total_requests == 0.
    """
    entries = http_requests_total.collect()
    total = 0
    errors = 0
    for labels, value in entries:
        count = int(value)
        total += count
        status = labels.get("status", "")
        # 5xx 视为错误
        if status.startswith("5"):
            errors += count

    if total == 0:
        return 1.0, 0, 0
    return (total - errors) / total, total, errors


def compute_sli() -> SLIResult:
    """STAB-P2-011: 计算当前 SLI 指标 + 错误预算.

    Returns:
        SLIResult 数据类. 包含可用性、p99 延迟、错误预算剩余比例、消耗速率.
    """
    availability, total, errors = _compute_availability()
    p99_latency = _compute_p99(http_request_duration_seconds)
    p99_model_latency = _compute_p99(model_inference_duration_seconds)

    # 错误预算计算 (基于可用性 SLO)
    # 允许的错误率 = 1 - SLO_AVAILABILITY_TARGET
    # 实际错误率 = 1 - availability
    # burn_rate = 实际错误率 / 允许错误率
    allowed_error_rate = 1.0 - SLO_AVAILABILITY_TARGET
    if allowed_error_rate <= 0:
        # 防御性: SLO=100% 时无错误预算
        burn_rate = float("inf") if errors > 0 else 0.0
        remaining = 0.0
    else:
        actual_error_rate = 1.0 - availability
        burn_rate = actual_error_rate / allowed_error_rate
        # remaining = 1 - burn_rate (负值表示超支)
        remaining = max(-1.0, 1.0 - burn_rate)

    return SLIResult(
        availability=availability,
        total_requests=total,
        error_requests=errors,
        p99_latency_seconds=p99_latency,
        p99_model_latency_seconds=p99_model_latency,
        error_budget_remaining_ratio=remaining,
        error_budget_burn_rate=burn_rate,
    )


__all__ = [
    "SLO_AVAILABILITY_TARGET",
    "SLO_LATENCY_TARGET",
    "SLO_LATENCY_THRESHOLD_SECONDS",
    "SLO_MODEL_INFERENCE_LATENCY_TARGET",
    "SLO_MODEL_INFERENCE_LATENCY_THRESHOLD_SECONDS",
    "SLO_WINDOW_DAYS",
    "SLIResult",
    "compute_sli",
]
