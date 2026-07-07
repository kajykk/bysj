"""R-006 修复：启动失败结构化状态 (v1.40)

原问题: 多个后台组件启动失败仅日志记录，缺少结构化降级原因。
- 致命组件 (init_db / seed_database / ensure_pii_key / breaker init) 失败时
  异常冒泡导致 lifespan 中止，失败原因仅存日志，运维需登 Pod 翻日志定位。
- 非致命组件 (model preload / sentry / observability / health_monitor /
  ws_pubsub / canary_fallback) 失败时仅 `logger.exception`，未保存到任何
  全局状态，/health 端点无法获取这些失败信息。

本模块提供进程级单例 `startup_status`，集中收集每个启动组件的结果，
供 /health 与 /health/startup 端点暴露给运维 / k8s 探针。

设计原则:
- 零侵入业务: 仅在 lifespan 中包一层 record_step，不修改组件本身
- 致命与非致命区分: fatal=True 仍 raise，fatal=False 仅记录
- 线程安全: 仅在 lifespan 启动序列中写入，运行时只读
- 优雅降级: 即使 startup_status 写入失败也不影响启动
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(slots=True)
class ComponentStatus:
    """单个启动组件的状态记录."""

    name: str
    status: str  # "ok" | "failed" | "skipped"
    error_type: str = ""  # 异常类名 (e.g. "OperationalError")
    error_message: str = ""  # 异常摘要 (截断到 500 字符)
    started_at: float = 0.0  # monotonic 时间戳
    duration_ms: float = 0.0  # 耗时 (毫秒)

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化字典 (用于 health 端点)."""
        return {
            "status": self.status,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "duration_ms": round(self.duration_ms, 2),
        }


class StartupStatus:
    """进程级启动状态收集器 (单例)."""

    def __init__(self) -> None:
        self._components: dict[str, ComponentStatus] = {}
        self._fatal_error: str = ""  # 致命错误摘要 (lifespan 中止时设置)
        self._fatal_error_type: str = ""
        self._startup_completed: bool = False

    def record(
        self,
        name: str,
        status: str,
        error: BaseException | None = None,
        duration_ms: float = 0.0,
        fatal: bool = False,
    ) -> None:
        """记录一个组件的启动结果.

        Args:
            name: 组件名 (e.g. "init_db", "model_preload")
            status: "ok" | "failed" | "skipped"
            error: 失败时的异常对象 (status="failed" 时必填)
            duration_ms: 耗时 (毫秒)
            fatal: 是否致命失败 (用于 metrics 标签)
        """
        error_type = ""
        error_message = ""
        if error is not None:
            error_type = type(error).__name__
            error_message = str(error)[:500]
        self._components[name] = ComponentStatus(
            name=name,
            status=status,
            error_type=error_type,
            error_message=error_message,
            started_at=time.monotonic(),
            duration_ms=duration_ms,
        )
        # R-006: 失败时同步递增 Prometheus 指标 (供 AR-209 告警)
        if status == "failed":
            try:
                from app.core.metrics import startup_component_failures_total

                startup_component_failures_total.inc(
                    component=name, fatal="true" if fatal else "false"
                )
            except Exception:
                # 优雅降级: metrics 注册失败不影响启动状态收集
                logger.debug(
                    "startup.metrics.increment.failed for %s", name, exc_info=True
                )

    def set_fatal(self, error: BaseException | str) -> None:
        """设置致命错误 (lifespan 最外层捕获时调用).

        Args:
            error: 异常对象或错误消息字符串
        """
        if isinstance(error, BaseException):
            self._fatal_error_type = type(error).__name__
            self._fatal_error = str(error)[:1000]
        else:
            self._fatal_error_type = "FatalError"
            self._fatal_error = str(error)[:1000]

    def mark_completed(self) -> None:
        """标记启动序列完成 (lifespan yield 前调用)."""
        self._startup_completed = True

    @property
    def fatal_error(self) -> str:
        return self._fatal_error

    @property
    def fatal_error_type(self) -> str:
        return self._fatal_error_type

    @property
    def has_fatal_error(self) -> bool:
        return bool(self._fatal_error)

    @property
    def startup_completed(self) -> bool:
        return self._startup_completed

    @property
    def failed_components(self) -> list[str]:
        """失败组件名列表 (status="failed")."""
        return [name for name, c in self._components.items() if c.status == "failed"]

    @property
    def components(self) -> dict[str, ComponentStatus]:
        """所有组件状态 (只读视图)."""
        return dict(self._components)

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化字典 (用于 /health/startup 端点)."""
        return {
            "startup_completed": self._startup_completed,
            "fatal_error": self._fatal_error,
            "fatal_error_type": self._fatal_error_type,
            "failed_components": self.failed_components,
            "components": {name: c.to_dict() for name, c in self._components.items()},
        }

    def to_summary_dict(self) -> dict[str, Any]:
        """转换为摘要字典 (用于 /health 与 /health/ready 端点).

        仅暴露失败组件列表与致命错误，避免冗余。
        """
        return {
            "startup_failed_components": self.failed_components,
            "startup_fatal_error": self._fatal_error,
        }

    def reset(self) -> None:
        """重置状态 (仅用于测试)."""
        self._components.clear()
        self._fatal_error = ""
        self._fatal_error_type = ""
        self._startup_completed = False


# ── 进程级单例 ──
startup_status = StartupStatus()


async def record_step_async(
    name: str,
    coro: Awaitable[T],
    *,
    fatal: bool = True,
) -> T:
    """包装异步启动步骤，记录状态与耗时.

    Args:
        name: 组件名
        coro: 待执行的协程
        fatal: True=失败时 re-raise (致命组件)；False=失败时仅记录 (非致命组件)

    Returns:
        协程结果

    Raises:
        原异常 (fatal=True 时)
    """
    start = time.monotonic()
    try:
        result = await coro
        duration_ms = (time.monotonic() - start) * 1000
        startup_status.record(name, "ok", duration_ms=duration_ms, fatal=fatal)
        return result
    except BaseException as exc:
        duration_ms = (time.monotonic() - start) * 1000
        startup_status.record(
            name, "failed", error=exc, duration_ms=duration_ms, fatal=fatal
        )
        logger.error(
            "startup.component.failed name=%s fatal=%s error=%s: %s",
            name,
            fatal,
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        if fatal:
            startup_status.set_fatal(exc)
            raise
        return None  # type: ignore[return-value]


def record_step_sync(
    name: str,
    func: Callable[[], T],
    *,
    fatal: bool = True,
) -> T:
    """包装同步启动步骤，记录状态与耗时.

    Args:
        name: 组件名
        func: 待执行的函数 (无参)
        fatal: True=失败时 re-raise (致命组件)；False=失败时仅记录 (非致命组件)

    Returns:
        函数结果

    Raises:
        原异常 (fatal=True 时)
    """
    start = time.monotonic()
    try:
        result = func()
        duration_ms = (time.monotonic() - start) * 1000
        startup_status.record(name, "ok", duration_ms=duration_ms, fatal=fatal)
        return result
    except BaseException as exc:
        duration_ms = (time.monotonic() - start) * 1000
        startup_status.record(
            name, "failed", error=exc, duration_ms=duration_ms, fatal=fatal
        )
        logger.error(
            "startup.component.failed name=%s fatal=%s error=%s: %s",
            name,
            fatal,
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        if fatal:
            startup_status.set_fatal(exc)
            raise
        return None  # type: ignore[return-value]
