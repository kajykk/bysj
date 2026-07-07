"""v1.33: W3C Trace Context 测试"""

from __future__ import annotations

from app.core.tracing import (
    TraceContext,
    TraceLogFilter,
    extract_or_new_trace,
    get_current_trace,
    new_trace_context,
    parse_traceparent,
    set_current_trace,
    span_context,
)


def test_parse_traceparent_valid() -> None:
    """v1.33: 有效 traceparent 应被正确解析."""
    tc = parse_traceparent("00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01")
    assert tc is not None
    assert tc.trace_id == "0af7651916cd43dd8448eb211c80319c"
    assert tc.span_id == "b7ad6b7169203331"
    assert tc.sampled is True
    assert tc.trace_flags == "01"


def test_parse_traceparent_invalid_format() -> None:
    """v1.33: 无效格式应返回 None."""
    assert parse_traceparent(None) is None
    assert parse_traceparent("") is None
    assert parse_traceparent("garbage") is None
    assert (
        parse_traceparent("00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331")
        is None
    )
    assert (
        parse_traceparent("01-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01")
        is None
    )  # 非 00 version


def test_parse_traceparent_invalid_ids() -> None:
    """v1.33: 全 0 的 trace_id / span_id 应被拒绝."""
    zero_trace = "00-" + "0" * 32 + "-" + "0" * 16 + "-01"
    assert parse_traceparent(zero_trace) is None


def test_new_trace_context() -> None:
    """v1.33: 新 trace 应有 32 hex trace_id 和 16 hex span_id."""
    tc = new_trace_context()
    assert len(tc.trace_id) == 32
    assert len(tc.span_id) == 16
    assert all(c in "0123456789abcdef" for c in tc.trace_id)
    assert all(c in "0123456789abcdef" for c in tc.span_id)
    assert tc.parent_span_id is None
    assert tc.sampled is True


def test_new_trace_context_unique() -> None:
    """v1.33: 多次调用应生成不同 trace_id."""
    tc1 = new_trace_context()
    tc2 = new_trace_context()
    assert tc1.trace_id != tc2.trace_id
    assert tc1.span_id != tc2.span_id


def test_trace_context_to_traceparent() -> None:
    """v1.33: to_traceparent 应生成 W3C 格式."""
    tc = TraceContext(
        trace_id="0af7651916cd43dd8448eb211c80319c",
        span_id="b7ad6b7169203331",
        trace_flags="01",
    )
    assert (
        tc.to_traceparent() == "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    )


def test_trace_context_child_span() -> None:
    """v1.33: 子 span 应共享 trace_id, 新 span_id, parent 指向当前."""
    parent = new_trace_context()
    child = parent.child_span("test")
    assert child.trace_id == parent.trace_id
    assert child.span_id != parent.span_id
    assert child.parent_span_id == parent.span_id
    assert child.sampled == parent.sampled


def test_extract_or_new_trace_with_parent() -> None:
    """v1.33: extract_or_new_trace 应继承上游 trace_id."""
    upstream = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    tc = extract_or_new_trace(upstream)
    assert tc.trace_id == "0af7651916cd43dd8448eb211c80319c"
    assert tc.span_id != "b7ad6b7169203331"  # 新 span_id
    assert tc.parent_span_id == "b7ad6b7169203331"


def test_extract_or_new_trace_without_parent() -> None:
    """v1.33: 无 traceparent 时应生成新 trace."""
    tc = extract_or_new_trace(None)
    assert len(tc.trace_id) == 32
    assert tc.parent_span_id is None


def test_span_context_creates_child() -> None:
    """v1.33: span_context 应创建子 span."""
    parent = new_trace_context()
    set_current_trace(parent)
    try:
        with span_context("test") as child:
            assert child.trace_id == parent.trace_id
            assert child.span_id != parent.span_id
            assert child.parent_span_id == parent.span_id
            assert get_current_trace() == child
        # 退出后恢复父
        assert get_current_trace() == parent
    finally:
        set_current_trace(None)


def test_span_context_nested() -> None:
    """v1.33: 嵌套 span 应形成树形结构."""
    root = new_trace_context()
    set_current_trace(root)
    try:
        with span_context("level1") as l1:
            assert l1.parent_span_id == root.span_id
            with span_context("level2") as l2:
                assert l2.parent_span_id == l1.span_id
                assert l2.trace_id == root.trace_id
    finally:
        set_current_trace(None)


def test_span_context_exception_cleanup() -> None:
    """v1.33: span 内部异常应正确清理 context."""
    parent = new_trace_context()
    set_current_trace(parent)
    try:
        try:
            with span_context("test"):
                raise ValueError("test")
        except ValueError:
            pass
        # 退出后仍应恢复父
        assert get_current_trace() == parent
    finally:
        set_current_trace(None)


def test_trace_log_filter() -> None:
    """v1.33: TraceLogFilter 应注入 trace_id / span_id 到日志."""
    import logging

    tc = new_trace_context()
    set_current_trace(tc)
    try:
        log_filter = TraceLogFilter()
        record = logging.LogRecord("test", logging.INFO, "/path", 1, "msg", (), None)
        assert log_filter.filter(record) is True
        assert record.trace_id == tc.trace_id
        assert record.span_id == tc.span_id
    finally:
        set_current_trace(None)


def test_trace_log_filter_no_trace() -> None:
    """v1.33: 无 trace 时应填充占位符."""
    import logging

    set_current_trace(None)
    log_filter = TraceLogFilter()
    record = logging.LogRecord("test", logging.INFO, "/path", 1, "msg", (), None)
    log_filter.filter(record)
    assert record.trace_id == "-"
    assert record.span_id == "-"


def test_to_dict() -> None:
    """v1.33: to_dict 应返回可序列化 dict."""
    tc = new_trace_context()
    d = tc.to_dict()
    assert "trace_id" in d
    assert "span_id" in d
    assert "parent_span_id" in d
    assert "sampled" in d
    assert "trace_flags" in d
