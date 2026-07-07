"""STAB-P1-005 修复：Celery broker 熔断器

原问题：``check_celery_worker`` 通过 ``celery_app.control.inspect().stats()``
检查 broker 连通性，但 Redis broker 宕机时该调用会阻塞至 timeout (1.5s)，
后台健康监控任务每 10s 调用一次，5 次连续失败后仍持续重试，无法快速失败。
同理，``train_bert_model_task.delay()`` 在 broker 宕机时也会阻塞。

本模块复用 ``CircuitBreaker`` 状态机，并提供：

1. Celery broker 专用失败分类器 ``_is_celery_failure``:
   - 视为 broker 基础设施故障 (触发熔断): ``kombu.exceptions.OperationalError``,
     ``celery.exceptions.TimeoutError``, ``OSError``, ``ConnectionError``,
     ``TimeoutError``, ``redis.exceptions.ConnectionError``,
     ``redis.exceptions.BusyLoadingError``
   - 视为业务异常 (不触发熔断): ``ValueError``, ``TypeError``, ``KeyError``
2. ``call_with_celery_breaker(coro)`` 异步包装:
   - 熔断器 OPEN 时抛 503 (CircuitBreakerOpenError)
   - broker 调用成功/失败分别回调 ``on_success``/``on_failure``
   - 不附加 ``asyncio.wait_for`` (调用方已有 ``inspect(timeout=1.5)`` 超时)
3. 全局 ``celery_breaker`` 实例 + ``init_celery_breaker()`` 初始化

使用方式 (集成到 check_celery_worker):

.. code-block:: python

    from app.core.celery_breaker import call_with_celery_breaker, CircuitBreakerOpenError

    async def check_celery_worker(redis_url: str, timeout_seconds: float = 1.5) -> bool:
        try:
            inspect = celery_app.control.inspect(timeout=timeout_seconds)
            stats = await call_with_celery_breaker(
                asyncio.to_thread(inspect.stats)
            )
            return bool(stats)
        except CircuitBreakerOpenError:
            # 熔断中, 快速返回 False
            return False
        except Exception:
            return False
"""

from __future__ import annotations

import logging
from typing import Awaitable, TypeVar

from app.core.db_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    FailureClassifier,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


# 业务异常类型 (输入校验类, 不代表 broker 服务不可用)
# 这些异常通常由调用方参数错误引起, 不应触发熔断器
_BUSINESS_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    LookupError,
    ArithmeticError,
)


# Celery broker 基础设施故障异常类型 (代表 broker 不可用或网络故障)
# 动态收集: kombu / celery / redis 三类异常, 缺失则跳过 (依赖未安装场景)
def _collect_infra_exceptions() -> tuple[type[BaseException], ...]:
    """收集 Celery broker 基础设施异常类型.

    分别尝试导入 kombu / celery / redis 三个库的连接级异常,
    任一缺失则跳过 (兼容未安装这些库的环境, 如纯测试环境).
    """
    exceptions: list[type[BaseException]] = [
        OSError,  # 底层 socket 错误 (含 ConnectionRefusedError/ConnectionResetError)
        ConnectionError,  # TCP 连接失败 (OSError 子类, 显式列出便于阅读)
        TimeoutError,  # socket 超时 (OSError 子类, 显式列出便于阅读)
    ]

    # kombu: Celery broker 底层传输库
    try:
        from kombu.exceptions import OperationalError as KombuOperationalError

        exceptions.append(KombuOperationalError)
    except ImportError:
        pass

    # celery: 任务队列框架自身的超时异常
    try:
        from celery.exceptions import TimeoutError as CeleryTimeoutError

        exceptions.append(CeleryTimeoutError)
    except ImportError:
        pass

    # redis: broker 后端连接异常
    try:
        from redis.exceptions import BusyLoadingError as RedisBusyLoadingError
        from redis.exceptions import ConnectionError as RedisConnectionError

        exceptions.append(RedisConnectionError)
        exceptions.append(RedisBusyLoadingError)
    except ImportError:
        pass

    return tuple(exceptions)


_INFRA_EXCEPTIONS: tuple[type[BaseException], ...] = _collect_infra_exceptions()


def _is_celery_failure(exc: BaseException | None) -> bool:
    """判断异常是否为 Celery broker 基础设施故障 (应触发熔断器)。

    业务异常 (ValueError/TypeError/KeyError 等输入校验类) 不触发熔断器。
    基础设施异常 (kombu.OperationalError/celery.TimeoutError/OSError/
    ConnectionError/TimeoutError/redis.ConnectionError/redis.BusyLoadingError)
    触发熔断器。未知异常默认视为 broker 故障 (保守策略, 避免漏判导致持续阻塞)。

    异常链检查优先: 若异常本身或其 __cause__/__context__ 包含基础设施异常,
    即使外层是业务异常 (如 ValueError 包装 kombu.OperationalError), 也视为 broker 故障。
    """
    if exc is None:
        return True  # 显式调用 on_failure(None) 时强制计数

    # 1. 优先检查异常链中的基础设施异常
    #    场景: ValueError("wrapper") from kombu.OperationalError("broker down")
    #    此时外层是业务异常, 但根因是 broker 故障, 应触发熔断
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
    #    (CircuitBreakerOpenError 继承自 HTTPException, 此处避免自反馈循环)
    try:
        from fastapi import HTTPException

        if isinstance(exc, HTTPException):
            return False
    except ImportError:
        pass

    # 5. 未知异常: 保守策略, 视为 broker 故障 (避免漏判导致持续阻塞)
    return True


# ── 全局 Celery broker 熔断器实例 ──
celery_breaker: CircuitBreaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=30,
    half_open_max_calls=1,
    name="celery",
    failure_classifier=_is_celery_failure,
)


def init_celery_breaker() -> None:
    """根据 settings 重新初始化 Celery broker 熔断器参数。

    在应用启动时调用, 确保使用最新的配置值。
    """
    global celery_breaker
    from app.core.config import settings

    celery_breaker = CircuitBreaker(
        failure_threshold=settings.celery_failure_threshold,
        recovery_timeout=settings.celery_recovery_timeout,
        half_open_max_calls=settings.celery_half_open_max_calls,
        name="celery",
        failure_classifier=_is_celery_failure,
    )
    logger.info(
        "circuit_breaker.celery.init threshold=%d recovery=%ds half_open_max=%d",
        settings.celery_failure_threshold,
        settings.celery_recovery_timeout,
        settings.celery_half_open_max_calls,
    )


async def call_with_celery_breaker(coro: Awaitable[T]) -> T:
    """在 Celery broker 熔断器保护下执行 broker 调用协程。

    流程:
        1. ``celery_breaker.before_request()`` — OPEN 时抛 503
        2. 等待协程完成 (不加额外超时, 调用方已有 inspect(timeout=1.5) 超时)
        3. 成功 → ``on_success()``; 失败 → ``on_failure(exc)`` 后重新抛出

    参数:
        coro: broker 调用协程 (如 ``asyncio.to_thread(inspect.stats)``)

    抛出:
        CircuitBreakerOpenError: 熔断器打开时 (HTTP 503)
        原始异常: broker 调用失败时透传 (供调用方处理)
    """
    from app.core.config import settings

    if not settings.celery_circuit_breaker_enabled:
        # 熔断器禁用时直接执行
        return await coro

    # 1. 熔断器前置检查
    await celery_breaker.before_request()

    try:
        # 2. 执行 broker 调用 (调用方已有 timeout 保护)
        result = await coro
        # 3. 成功: 重置计数
        await celery_breaker.on_success()
        return result
    except BaseException as exc:
        # 4. 失败: 记录并重新抛出 (业务异常不会被计数)
        await celery_breaker.on_failure(exc)
        if celery_breaker.failure_count >= celery_breaker.failure_threshold:
            logger.warning(
                "celery.broker.failure breaker failures=%d/%d (state=%s)",
                celery_breaker.failure_count,
                celery_breaker.failure_threshold,
                celery_breaker.state,
            )
        raise


__all__ = [
    "call_with_celery_breaker",
    "init_celery_breaker",
    "celery_breaker",
    "_is_celery_failure",
    "CircuitBreakerOpenError",
    "FailureClassifier",
]
