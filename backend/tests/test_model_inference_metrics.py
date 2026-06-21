"""模型推理指标追踪测试 (v1.32)"""
from __future__ import annotations

import pytest

from app.core.metrics import (
    model_inference_duration_seconds,
    model_inference_total,
    render_exposition,
    reset_registry,
    track_model_inference,
)


@pytest.fixture(autouse=True)
def reset_metrics():
    reset_registry()
    yield


def test_track_model_inference_success() -> None:
    """v1.32: 成功推理应记录 success 状态."""
    with track_model_inference("test_model"):
        pass

    body = render_exposition()
    # 应有 success 计数
    assert 'model_inference_total{model_name="test_model",status="success"} 1.0' in body


def test_track_model_inference_error() -> None:
    """v1.32: 异常应记录 error 状态."""

    class _TestError(Exception):
        pass

    with pytest.raises(_TestError):
        with track_model_inference("test_model"):
            raise _TestError("simulated failure")

    body = render_exposition()
    assert 'model_inference_total{model_name="test_model",status="error"} 1.0' in body


def test_track_model_inference_duration() -> None:
    """v1.32: 推理耗时应被记录."""
    import time

    with track_model_inference("test_model"):
        time.sleep(0.01)

    body = render_exposition()
    # 应有 _sum 和 _count 行 (count 是 int 渲染, sum 是 float 6位小数)
    assert 'model_inference_duration_seconds_count{model_name="test_model"} 1' in body
    assert 'model_inference_duration_seconds_sum{model_name="test_model"}' in body
    # bucket 也应存在
    assert 'model_inference_duration_seconds_bucket{model_name="test_model",le="+Inf"} 1' in body


def test_track_model_inference_metrics_failure_does_not_break() -> None:
    """v1.32: 指标失败应被吞掉, 不影响主流程."""
    # 模拟指标异常 - 通过 monkey-patch

    def _explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("metrics failed")

    original = model_inference_total.inc
    model_inference_total.inc = _explode  # type: ignore[assignment]
    try:
        with track_model_inference("test_model"):
            pass
        # 不应抛错
    finally:
        model_inference_total.inc = original  # type: ignore[assignment]


def test_track_model_inference_nested() -> None:
    """v1.32: 嵌套调用应分别记录."""
    with track_model_inference("outer"):
        with track_model_inference("inner"):
            pass

    body = render_exposition()
    # 两次成功
    assert 'model_inference_total{model_name="outer",status="success"} 1.0' in body
    assert 'model_inference_total{model_name="inner",status="success"} 1.0' in body
