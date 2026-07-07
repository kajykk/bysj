"""STAB-P1-004 修复：SMTP 邮件熔断器

原问题：``EmailService.send_password_reset_email`` 无熔断器，SMTP 服务器
宕机时每次请求都会重试 2 次 (每次 15s 超时)，导致密码重置接口阻塞 30s+，
在高并发场景下耗尽事件循环线程池，级联影响其他接口。

本模块复用 ``CircuitBreaker`` 状态机，并提供：

1. SMTP 专用失败分类器 ``_is_smtp_failure``:
   - 视为 SMTP 基础设施故障 (触发熔断): ``smtplib.SMTPException``,
     ``OSError``, ``ConnectionError``, ``TimeoutError``
   - 视为业务异常 (不触发熔断): ``ValueError`` (输入校验),
     ``TypeError``, ``KeyError``
2. ``call_with_smtp_breaker(coro)`` 异步包装:
   - 熔断器 OPEN 时抛 503 (CircuitBreakerOpenError)
   - SMTP 调用成功/失败分别回调 ``on_success``/``on_failure``
   - 不再附加 ``asyncio.wait_for`` (SMTP 已有 15s 超时/次 + 2 次重试)
3. 全局 ``smtp_breaker`` 实例 + ``init_smtp_breaker()`` 初始化

使用方式 (集成到 EmailService):

.. code-block:: python

    from app.core.smtp_breaker import call_with_smtp_breaker

    async def send_password_reset_email(self, email, token):
        ...
        try:
            await call_with_smtp_breaker(asyncio.to_thread(self._send_smtp, message))
        except CircuitBreakerOpenError:
            raise  # 503 快速失败
        except Exception as exc:
            raise ValueError("重置邮件发送失败，请稍后重试") from exc
"""

from __future__ import annotations

import logging
import smtplib
from typing import Awaitable, TypeVar

from app.core.db_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    FailureClassifier,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


# 业务异常类型 (输入校验类, 不代表 SMTP 服务不可用)
# 这些异常通常由调用方参数错误引起, 不应触发熔断器
_BUSINESS_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    LookupError,
    ArithmeticError,
)

# SMTP 基础设施故障异常类型 (代表 SMTP 服务不可用或网络故障)
# smtplib.SMTPException: SMTP 协议级错误 (认证失败/邮箱不存在/被拒)
#   注意: SMTPAuthenticationError/SMTPResponseException 均为其子类
# OSError: 网络层错误 (含 ConnectionRefusedError/ConnectionResetError/timeout)
# ConnectionError: TCP 连接失败 (OSError 子类, 显式列出便于阅读)
# TimeoutError: socket 超时 (OSError 子类, 显式列出便于阅读)
_INFRA_EXCEPTIONS: tuple[type[BaseException], ...] = (
    smtplib.SMTPException,
    OSError,  # 包含 ConnectionError/ConnectionRefusedError/TimeoutError
    ConnectionError,
    TimeoutError,
)


def _is_smtp_failure(exc: BaseException | None) -> bool:
    """判断异常是否为 SMTP 基础设施故障 (应触发熔断器)。

    业务异常 (ValueError/TypeError/KeyError 等输入校验类) 不触发熔断器。
    基础设施异常 (smtplib.SMTPException/OSError/ConnectionError/TimeoutError)
    触发熔断器。未知异常默认视为 SMTP 故障 (保守策略, 避免漏判导致持续阻塞)。

    异常链检查优先: 若异常本身或其 __cause__/__context__ 包含基础设施异常,
    即使外层是业务异常 (如 ValueError 包装 SMTPException), 也视为 SMTP 故障。
    """
    if exc is None:
        return True  # 显式调用 on_failure(None) 时强制计数

    # 1. 优先检查异常链中的基础设施异常
    #    场景: ValueError("wrapper") from SMTPException("auth failed")
    #    此时外层是业务异常, 但根因是 SMTP 故障, 应触发熔断
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

    # 5. 未知异常: 保守策略, 视为 SMTP 故障 (避免漏判导致持续阻塞)
    return True


# ── 全局 SMTP 熔断器实例 ──
smtp_breaker: CircuitBreaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60,
    half_open_max_calls=1,
    name="smtp",
    failure_classifier=_is_smtp_failure,
)


def init_smtp_breaker() -> None:
    """根据 settings 重新初始化 SMTP 熔断器参数。

    在应用启动时调用, 确保使用最新的配置值。
    """
    global smtp_breaker
    from app.core.config import settings

    smtp_breaker = CircuitBreaker(
        failure_threshold=settings.smtp_failure_threshold,
        recovery_timeout=settings.smtp_recovery_timeout,
        half_open_max_calls=settings.smtp_half_open_max_calls,
        name="smtp",
        failure_classifier=_is_smtp_failure,
    )
    logger.info(
        "circuit_breaker.smtp.init threshold=%d recovery=%ds half_open_max=%d",
        settings.smtp_failure_threshold,
        settings.smtp_recovery_timeout,
        settings.smtp_half_open_max_calls,
    )


async def call_with_smtp_breaker(coro: Awaitable[T]) -> T:
    """在 SMTP 熔断器保护下执行邮件发送协程。

    流程:
        1. ``smtp_breaker.before_request()`` — OPEN 时抛 503
        2. 等待协程完成 (不加额外超时, SMTP 内部已有 15s 超时/次 + 2 次重试)
        3. 成功 → ``on_success()``; 失败 → ``on_failure(exc)`` 后重新抛出

    参数:
        coro: SMTP 发送协程 (如 ``asyncio.to_thread(self._send_smtp, msg)``)

    抛出:
        CircuitBreakerOpenError: 熔断器打开时 (HTTP 503)
        原始异常: SMTP 发送失败时透传 (供调用方包装为 ValueError)
    """
    from app.core.config import settings

    if not settings.smtp_circuit_breaker_enabled:
        # 熔断器禁用时直接执行
        return await coro

    # 1. 熔断器前置检查
    await smtp_breaker.before_request()

    try:
        # 2. 执行 SMTP 调用 (内部已有重试 + 超时)
        result = await coro
        # 3. 成功: 重置计数
        await smtp_breaker.on_success()
        return result
    except BaseException as exc:
        # 4. 失败: 记录并重新抛出 (业务异常不会被计数)
        await smtp_breaker.on_failure(exc)
        if smtp_breaker.failure_count >= smtp_breaker.failure_threshold:
            logger.warning(
                "smtp.send.failure breaker failures=%d/%d (state=%s)",
                smtp_breaker.failure_count,
                smtp_breaker.failure_threshold,
                smtp_breaker.state,
            )
        raise


__all__ = [
    "call_with_smtp_breaker",
    "init_smtp_breaker",
    "smtp_breaker",
    "_is_smtp_failure",
    "CircuitBreakerOpenError",
    "FailureClassifier",
]
