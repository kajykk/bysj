"""W3C Trace Context 集成 (v1.33).

实现 W3C Trace Context 规范 (https://www.w3.org/TR/trace-context/):
- 解析 `traceparent` header 格式: `00-{trace_id}-{span_id}-{flags}`
- 生成新 trace_id (16 字节 hex) / span_id (8 字节 hex)
- 嵌套 span_context 上下文管理器
- 与 request_id 集成

设计原则:
- 零外部依赖 (不引入 OpenTelemetry SDK)
- 线程安全 (使用 contextvars)
- 与 Sentry trace_id 格式兼容 (16 字节 hex)
"""
from __future__ import annotations

import logging
import re
import secrets
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator

# W3C traceparent 格式: 00-{32 hex}-{16 hex}-{2 hex}
_TRACEPARENT_PATTERN = re.compile(r"^([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")
_TRACE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_SPAN_ID_PATTERN = re.compile(r"^[0-9a-f]{16}$")

# 零 trace_id (16 字节全 0) 是无效的, 必须重新生成
_INVALID_TRACE_ID = "0" * 32
# 零 span_id (8 字节全 0) 是无效的
_INVALID_SPAN_ID = "0" * 16


@dataclass(frozen=True)
class TraceContext:
    """W3C Trace Context.

    Attributes:
        trace_id: 32 hex chars (16 bytes)
        span_id: 16 hex chars (8 bytes)
        parent_span_id: 父 span_id (用于构造 trace tree)
        sampled: 是否采样 (1 = 采样, 0 = 不采样)
        trace_flags: 原始 flags 字节
    """

    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    sampled: bool = True
    trace_flags: str = "01"

    def to_traceparent(self) -> str:
        """生成 W3C traceparent header 值.

        格式: 00-{trace_id}-{span_id}-{flags}
        """
        return f"00-{self.trace_id}-{self.span_id}-{self.trace_flags}"

    def child_span(self, name: str | None = None) -> "TraceContext":
        """创建子 span (新 span_id, 共享 trace_id, parent_span_id = 当前 span_id)."""
        return TraceContext(
            trace_id=self.trace_id,
            span_id=_generate_span_id(),
            parent_span_id=self.span_id,
            sampled=self.sampled,
            trace_flags=self.trace_flags,
        )

    def to_dict(self) -> dict:
        """导出为可序列化 dict."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "sampled": self.sampled,
            "trace_flags": self.trace_flags,
        }


# 当前 trace context (线程/协程安全)
_current_trace: ContextVar[TraceContext | None] = ContextVar("current_trace", default=None)
_lock = threading.Lock()


def _generate_trace_id() -> str:
    """生成 32 字符 hex trace_id (16 字节)."""
    return secrets.token_hex(16)


def _generate_span_id() -> str:
    """生成 16 字符 hex span_id (8 字节)."""
    return secrets.token_hex(8)


def new_trace_context(sampled: bool = True) -> TraceContext:
    """生成新的 root trace context."""
    flags = "01" if sampled else "00"
    return TraceContext(
        trace_id=_generate_trace_id(),
        span_id=_generate_span_id(),
        parent_span_id=None,
        sampled=sampled,
        trace_flags=flags,
    )


def parse_traceparent(header_value: str | None) -> TraceContext | None:
    """解析 W3C traceparent header.

    Args:
        header_value: `traceparent` header 的值, 例如 `00-{trace_id}-{span_id}-01`

    Returns:
        解析成功返回 TraceContext, 解析失败返回 None
    """
    if not header_value:
        return None
    header_value = header_value.strip()
    match = _TRACEPARENT_PATTERN.match(header_value)
    if not match:
        return None
    version, trace_id, span_id, flags = match.groups()
    # v1.33: 仅支持 version 00
    if version != "00":
        return None
    # 验证 trace_id 和 span_id 有效
    if trace_id == _INVALID_TRACE_ID or span_id == _INVALID_SPAN_ID:
        return None
    if not _TRACE_ID_PATTERN.match(trace_id) or not _SPAN_ID_PATTERN.match(span_id):
        return None
    return TraceContext(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=None,  # 解析时无 parent 信息
        sampled=(flags == "01"),
        trace_flags=flags,
    )


def get_current_trace() -> TraceContext | None:
    """获取当前协程/线程的 trace context."""
    return _current_trace.get()


def set_current_trace(tc: TraceContext | None) -> None:
    """设置当前 trace context."""
    _current_trace.set(tc)


@contextmanager
def span_context(name: str | None = None) -> Iterator[TraceContext]:
    """创建子 span 上下文.

    Usage:
        with span_context("db_query") as span:
            do_db_work()
            # span.span_id 是新生成的子 span
        # 退出后自动恢复父 span

    Args:
        name: span 名称 (用于日志/调试, 当前不强制使用)

    Yields:
        子 TraceContext
    """
    parent = _current_trace.get()
    if parent is None:
        # 无父 context, 创建 root
        child = new_trace_context()
    else:
        child = parent.child_span(name)

    token = _current_trace.set(child)
    try:
        yield child
    finally:
        _current_trace.reset(token)


def inject_trace_into_headers(headers: dict) -> dict:
    """将当前 trace 注入到 headers (用于跨服务调用).

    Args:
        headers: 目标请求 headers dict

    Returns:
        注入后的 headers
    """
    tc = _current_trace.get()
    if tc is not None:
        headers["traceparent"] = tc.to_traceparent()
    return headers


def extract_or_new_trace(traceparent_header: str | None) -> TraceContext:
    """从 traceparent header 提取 trace, 或创建新 trace.

    Args:
        traceparent_header: 上游服务的 traceparent header

    Returns:
        TraceContext (继承或新建)
    """
    parsed = parse_traceparent(traceparent_header)
    if parsed is not None:
        # 上游传入有效 trace, 但需要新 span_id (我们是新 span)
        return TraceContext(
            trace_id=parsed.trace_id,
            span_id=_generate_span_id(),
            parent_span_id=parsed.span_id,
            sampled=parsed.sampled,
            trace_flags=parsed.trace_flags,
        )
    return new_trace_context()


class TraceLogFilter:
    """v1.33: 自动注入 trace_id / span_id 到日志记录.

    Usage:
        import logging
        handler = logging.StreamHandler()
        handler.addFilter(TraceLogFilter())
        logger.addHandler(handler)
    """

    def filter(self, record: logging.LogRecord) -> bool:
        tc = _current_trace.get()
        if tc is not None:
            record.trace_id = tc.trace_id
            record.span_id = tc.span_id
        else:
            record.trace_id = "-"
            record.span_id = "-"
        return True
