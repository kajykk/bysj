"""STAB-P1-002 修复：ML 推理熔断器 + asyncio.wait_for 超时

原问题：``predict_*`` 端点无熔断器与超时，ML 推理卡死（模型加载阻塞、
GIL 死锁、外部依赖 hang）会耗尽线程池/事件循环，导致级联失败。

本模块复用 ``CircuitBreaker`` 状态机，并提供：

1. ML 专用失败分类器 ``_is_ml_failure``:
   - 视为 ML 推理失败 (触发熔断): TimeoutError, OSError, FileNotFoundError,
     RuntimeError, MemoryError, ImportError
   - 视为业务异常 (不触发熔断): ValueError (输入校验), TypeError,
     KeyError, AttributeError
2. ``call_with_ml_breaker(coro, timeout=None)`` 异步包装:
   - 熔断器 OPEN 时抛 503 (CircuitBreakerOpenError)
   - ``asyncio.wait_for`` 超时则触发熔断计数
   - 推理成功/失败分别回调 ``on_success``/``on_failure``
3. 全局 ``ml_breaker`` 实例 + ``init_ml_breaker()`` 初始化

使用方式 (集成到 ModelPredictService):

.. code-block:: python

    from app.core.ml_breaker import call_with_ml_breaker

    async def predict_tabular(self, features):
        return await call_with_ml_breaker(model_engine.predict_structured(features))
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, TypeVar

from app.core.db_breaker import (
    CircuitBreaker,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


# 业务异常类型 (输入校验类, 不代表 ML 服务不可用)
# 这些异常通常由用户输入引起, 不应触发熔断器
_BUSINESS_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    LookupError,
    ArithmeticError,
)

# ML 推理失败异常类型 (代表模型/依赖不可用或卡死)
# TimeoutError: asyncio.wait_for 超时
# OSError/FileNotFoundError: 模型文件加载失败
# RuntimeError: 框架内部错误 (PyTorch/TF)
# MemoryError: OOM
# ImportError: 依赖缺失
_INFRA_EXCEPTIONS: tuple[type[BaseException], ...] = (
    TimeoutError,
    OSError,
    FileNotFoundError,
    RuntimeError,
    MemoryError,
    ImportError,
    ConnectionError,
)


def _is_ml_failure(exc: BaseException | None) -> bool:
    """判断异常是否为 ML 推理失败 (应触发熔断器)。

    业务异常 (ValueError/TypeError/KeyError 等输入校验类) 不触发熔断器。
    基础设施异常 (TimeoutError/OSError/RuntimeError 等) 触发熔断器。
    未知异常默认视为 ML 失败 (保守策略, 避免漏判导致卡死)。

    异常链检查优先: 若异常本身或其 __cause__/__context__ 包含基础设施异常,
    即使外层是业务异常 (如 ValueError 包装 OSError), 也视为 ML 失败。
    """
    if exc is None:
        return True  # 显式调用 on_failure(None) 时强制计数

    # 1. 优先检查异常链中的基础设施异常
    #    场景: ValueError("wrapper") from OSError("model locked")
    #    此时外层是业务异常, 但根因是基础设施故障, 应触发熔断
    for cause in (exc, exc.__cause__, exc.__context__):
        if cause is not None and cause is not exc:
            if isinstance(cause, _INFRA_EXCEPTIONS):
                return True

    # 2. 异常本身是已知基础设施异常: 触发
    if isinstance(exc, _INFRA_EXCEPTIONS):
        return True

    # 3. 业务异常: 输入校验类, 不触发
    if isinstance(exc, _BUSINESS_EXCEPTIONS):
        return False

    # 4. HTTPException 是 FastAPI 业务异常, 不触发
    try:
        from fastapi import HTTPException

        if isinstance(exc, HTTPException):
            return False
    except ImportError:
        pass

    # 5. 未知异常: 保守策略, 视为 ML 失败 (避免漏判导致卡死)
    return True


# ── 全局 ML 熔断器实例 ──
ml_breaker: CircuitBreaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=30,
    half_open_max_calls=1,
    name="ml",
    failure_classifier=_is_ml_failure,
)


def init_ml_breaker() -> None:
    """根据 settings 重新初始化 ML 熔断器参数。

    在应用启动时调用, 确保使用最新的配置值。
    """
    global ml_breaker
    from app.core.config import settings

    ml_breaker = CircuitBreaker(
        failure_threshold=settings.ml_failure_threshold,
        recovery_timeout=settings.ml_recovery_timeout,
        half_open_max_calls=settings.ml_half_open_max_calls,
        name="ml",
        failure_classifier=_is_ml_failure,
    )
    logger.info(
        "circuit_breaker.ml.init threshold=%d recovery=%ds half_open_max=%d timeout=%ds",
        settings.ml_failure_threshold,
        settings.ml_recovery_timeout,
        settings.ml_half_open_max_calls,
        settings.ml_inference_timeout,
    )


async def call_with_ml_breaker(
    coro: Awaitable[T],
    timeout: float | None = None,
) -> T:
    """在 ML 熔断器 + asyncio.wait_for 保护下执行推理协程。

    流程:
        1. ``ml_breaker.before_request()`` — OPEN 时抛 503
        2. ``asyncio.wait_for(coro, timeout)`` — 超时则取消并触发熔断
        3. 成功 → ``on_success()``; 失败 → ``on_failure(exc)`` 后重新抛出

    参数:
        coro: ML 推理协程 (如 ``model_engine.predict_text(text)``)
        timeout: 超时秒数. None 时使用 ``settings.ml_inference_timeout``

    抛出:
        CircuitBreakerOpenError: 熔断器打开时 (HTTP 503)
        asyncio.TimeoutError: 推理超时
        原始异常: 推理失败时透传
    """
    from app.core.config import settings

    if not settings.ml_circuit_breaker_enabled:
        # 熔断器禁用时直接执行 (仍保留超时保护)
        effective_timeout = (
            timeout if timeout is not None else settings.ml_inference_timeout
        )
        return await asyncio.wait_for(coro, timeout=effective_timeout)

    effective_timeout = (
        timeout if timeout is not None else settings.ml_inference_timeout
    )

    # 1. 熔断器前置检查
    await ml_breaker.before_request()

    try:
        # 2. 带超时执行推理
        result = await asyncio.wait_for(coro, timeout=effective_timeout)
        # 3. 成功: 重置计数
        await ml_breaker.on_success()
        return result
    except BaseException as exc:
        # 4. 失败: 记录并重新抛出 (业务异常不会被计数)
        await ml_breaker.on_failure(exc)
        if isinstance(exc, asyncio.TimeoutError):
            logger.warning(
                "ml_inference.timeout after %ss (breaker failures=%d/%d)",
                effective_timeout,
                ml_breaker.failure_count,
                ml_breaker.failure_threshold,
            )
        raise


__all__ = [
    "call_with_ml_breaker",
    "init_ml_breaker",
    "ml_breaker",
    "_is_ml_failure",
]
