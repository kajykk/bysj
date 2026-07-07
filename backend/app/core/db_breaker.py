"""STAB-P0-001 修复：数据库熔断器 (Circuit Breaker)

原问题：``database.py`` 中无熔断器，PostgreSQL 宕机时连接池耗尽导致级联失败。
所有请求持续尝试获取连接 → 超时 → 502/504，而非快速返回 503。

本模块实现轻量级异步熔断器 (无第三方依赖)：

状态机：
    CLOSED ──失败达 threshold──▶ OPEN
    OPEN ──经过 recovery_timeout──▶ HALF_OPEN
    HALF_OPEN ──测试请求成功──▶ CLOSED
    HALF_OPEN ──测试请求失败──▶ OPEN

使用方式 (集成到 get_db):

.. code-block:: python

    from app.core.db_breaker import db_breaker

    async def get_db():
        db_breaker.before_request()  # OPEN 时抛 HTTPException(503)
        try:
            session = ...
            yield session
        except OperationalError:
            db_breaker.on_failure()  # 记录失败
            raise
        else:
            db_breaker.on_success()  # 记录成功

只捕获连接级异常 (OperationalError/TimeoutError/OSError)，
业务异常 (IntegrityError/DataError) 不触发熔断器。

线程安全：使用 ``asyncio.Lock`` 保护状态转换，避免并发请求竞态。
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Callable

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# 失败分类器类型: 接收异常 (或 None), 返回是否应触发熔断器
FailureClassifier = Callable[[BaseException | None], bool]


class CircuitState(str, Enum):
    """熔断器状态。"""

    CLOSED = "closed"  # 正常放行
    OPEN = "open"  # 熔断, 拒绝所有请求
    HALF_OPEN = "half_open"  # 半开, 允许少量测试请求


# 视为连接级失败的异常类型 (业务异常如 IntegrityError 不在此列)
# 使用延迟 isinstance 检查, 避免在模块加载时触发 SQLAlchemy 完整导入


def _check_exception_is_connection_failure(exc: BaseException) -> bool:
    """判断单个异常是否为连接级失败。

    业务异常 (IntegrityError/DataError/ProgrammingError) 不触发熔断器。
    连接级异常 (OperationalError/InterfaceError/OSError/TimeoutError) 触发熔断器。
    """
    # 内置连接级异常 (无需延迟导入)
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True

    # SQLAlchemy 异常 (延迟导入, 避免循环依赖)
    try:
        from sqlalchemy.exc import (
            DataError,
            IntegrityError,
            NotSupportedError,
            ProgrammingError,
        )

        # 业务异常优先排除 (它们是 DBAPIError 的子类, 但不代表 DB 不可用)
        if isinstance(
            exc, (IntegrityError, DataError, ProgrammingError, NotSupportedError)
        ):
            return False

        from sqlalchemy.exc import DBAPIError as SADBAPIError
        from sqlalchemy.exc import InterfaceError as SAInterfaceError
        from sqlalchemy.exc import OperationalError as SAOperationalError

        # OperationalError/InterfaceError 是明确的连接级异常
        if isinstance(exc, (SAOperationalError, SAInterfaceError)):
            return True
        # 其他 DBAPIError 子类: 如果不是业务异常, 视为连接级失败
        if isinstance(exc, SADBAPIError):
            return True
    except ImportError:
        pass

    # asyncpg 异常 (延迟导入)
    try:
        from asyncpg import PostgresConnectionError

        if isinstance(exc, PostgresConnectionError):
            return True
    except ImportError:
        pass

    return False


def _is_connection_failure(exc: BaseException) -> bool:
    """判断异常是否为连接级失败 (应触发熔断器)。

    检查异常本身及其异常链 (__cause__/__context__)。
    业务异常 (如 IntegrityError/DataError/ProgrammingError) 不触发熔断器。
    """
    if _check_exception_is_connection_failure(exc):
        return True
    # 检查异常链 (cause/context)
    for cause in (exc.__cause__, exc.__context__):
        if cause is not None and cause is not exc:
            if _check_exception_is_connection_failure(cause):
                return True
    return False


class CircuitBreakerOpenError(HTTPException):
    """熔断器打开时抛出的异常 (HTTP 503)。"""

    def __init__(self, detail: str = "数据库熔断中, 请稍后重试") -> None:
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
            headers={"Retry-After": "30"},
        )


class CircuitBreaker:
    """异步熔断器实现。

    参数：
        failure_threshold: 连续失败次数阈值, 达到后打开熔断器
        recovery_timeout: OPEN 状态持续时间 (秒), 之后转为 HALF_OPEN
        half_open_max_calls: HALF_OPEN 状态允许的并发测试请求数
        name: 熔断器名称 (用于日志)
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
        half_open_max_calls: int = 1,
        name: str = "db",
        failure_classifier: FailureClassifier | None = None,
    ) -> None:
        self.failure_threshold = max(1, failure_threshold)
        self.recovery_timeout = max(1, recovery_timeout)
        self.half_open_max_calls = max(1, half_open_max_calls)
        self.name = name
        # 失败分类器: 判断异常是否应触发熔断器. None 时使用 DB 默认分类器
        self._failure_classifier: FailureClassifier = (
            failure_classifier or _is_connection_failure
        )

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls: int = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """当前熔断器状态 (无锁读取, 仅供监控/展示, 非精确)。"""
        return self._state

    @property
    def failure_count(self) -> int:
        """当前连续失败次数 (无锁读取, 仅供监控)。"""
        return self._failure_count

    def _should_transition_to_half_open(self) -> bool:
        """检查 OPEN 状态是否已超过 recovery_timeout, 应转为 HALF_OPEN。"""
        return (time.monotonic() - self._last_failure_time) >= self.recovery_timeout

    async def before_request(self) -> None:
        """请求前检查: 若熔断器打开则抛 503。

        状态转换:
        - OPEN + 超过 recovery_timeout → HALF_OPEN (允许测试请求)
        - OPEN + 未超时 → 拒绝 (503)
        - HALF_OPEN + 已达 max_calls → 拒绝 (503)
        - CLOSED → 放行
        """
        async with self._lock:
            if self._state == CircuitState.OPEN:
                if self._should_transition_to_half_open():
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    logger.warning(
                        "circuit_breaker.%s.transition open→half_open failures=%d",
                        self.name,
                        self._failure_count,
                    )
                else:
                    raise CircuitBreakerOpenError(
                        f"数据库熔断中 (连续失败 {self._failure_count} 次), "
                        f"请 {self.recovery_timeout}s 后重试"
                    )

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.half_open_max_calls:
                    raise CircuitBreakerOpenError("数据库半开状态测试中, 请稍后重试")
                self._half_open_calls += 1

    async def on_success(self) -> None:
        """请求成功: 重置失败计数, HALF_OPEN → CLOSED。"""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info(
                    "circuit_breaker.%s.transition half_open→closed",
                    self.name,
                )
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_calls = 0

    async def on_failure(self, exc: BaseException | None = None) -> None:
        """请求失败: 增加失败计数, 达阈值则 OPEN。

        参数:
            exc: 触发失败的异常。若提供且非连接级失败, 则忽略 (不计数)。
        """
        if exc is not None and not self._failure_classifier(exc):
            # 业务异常不触发熔断器
            return

        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # 半开状态测试失败 → 重新打开
                self._state = CircuitState.OPEN
                self._half_open_calls = 0
                logger.warning(
                    "circuit_breaker.%s.transition half_open→open (测试请求失败)",
                    self.name,
                )
            elif self._failure_count >= self.failure_threshold:
                if self._state != CircuitState.OPEN:
                    self._state = CircuitState.OPEN
                    logger.warning(
                        "circuit_breaker.%s.transition closed→open failures=%d threshold=%d",
                        self.name,
                        self._failure_count,
                        self.failure_threshold,
                    )

    async def reset(self) -> None:
        """手动重置熔断器到 CLOSED 状态 (管理/测试用)。"""
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_calls = 0
            logger.info("circuit_breaker.%s.reset → closed", self.name)

    def get_state_snapshot(self) -> dict[str, object]:
        """获取状态快照 (供 /metrics 或 /health 使用, 无锁读取)。"""
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "last_failure_time": self._last_failure_time,
        }


# ── 全局 DB 熔断器实例 ──
# 在模块加载时创建, 由 settings 配置。测试中可通过 reset() 重置。
db_breaker: CircuitBreaker = CircuitBreaker(
    failure_threshold=5,  # 默认值, 下方会被 settings 覆盖
    recovery_timeout=30,
    half_open_max_calls=1,
    name="db",
)


def init_db_breaker() -> None:
    """根据 settings 重新初始化熔断器参数。

    在应用启动时调用, 确保使用最新的配置值。
    """
    global db_breaker
    from app.core.config import settings

    db_breaker = CircuitBreaker(
        failure_threshold=settings.db_failure_threshold,
        recovery_timeout=settings.db_recovery_timeout,
        half_open_max_calls=settings.db_half_open_max_calls,
        name="db",
    )
    logger.info(
        "circuit_breaker.db.init threshold=%d recovery=%ds half_open_max=%d",
        settings.db_failure_threshold,
        settings.db_recovery_timeout,
        settings.db_half_open_max_calls,
    )


__all__ = [
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "CircuitState",
    "FailureClassifier",
    "db_breaker",
    "init_db_breaker",
]
