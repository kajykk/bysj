"""Celery request_id 传播的闸门测试(AUDIT-2026-10-05)。

背景: request_id 原先只由 HTTP 中间件写入 ContextVar。Celery 任务运行在
独立 worker 进程/线程, ContextVar 从未被设置 -> 任务内所有日志 req_id="-",
`risk_assessments` 表也无该列。对医疗心理健康系统属合规审计缺口:
无法回答"某次风险评分由哪次请求产生"。

本测试锁定三段链路: 入队补齐 / 执行前绑定 / 结束后还原。
"""
from __future__ import annotations

import pytest

from app.core.request_id import (
    TASK_REQUEST_ID_HEADER,
    bind_task_request_id,
    new_request_id,
    resolve_task_request_id,
    unbind_task_request_id,
)
from app.core.tracing import get_current_request_id


@pytest.fixture(autouse=True)
def _clean_context():
    """每个用例前后确保 ContextVar 干净, 避免用例间泄漏。"""
    yield
    unbind_task_request_id()


class TestResolveTaskRequestId:
    """从任务 headers 解析 request_id。"""

    def test_missing_headers_generates_new(self):
        rid = resolve_task_request_id(None)
        assert rid and len(rid) >= 8
        assert get_current_request_id() is None  # 纯生成, 不改ContextVar

    def test_empty_headers_generates_new(self):
        assert resolve_task_request_id({})

    def test_valid_header_is_preserved(self):
        """合法 ID 必须原样保留 —— 这是"能回答由哪次请求产生"的前提。"""
        given = "abc12345-6789-4def-8abc-1234567890ab"
        assert resolve_task_request_id({TASK_REQUEST_ID_HEADER: given}) == given

    def test_legacy_request_id_key_also_accepted(self):
        given = "legacy-key-12345678"
        assert resolve_task_request_id({"request_id": given}) == given

    def test_malformed_value_is_replaced(self):
        """非法格式必须丢弃重建, 不能放行进日志(与 HTTP 链路一致)。"""
        for bad in ["short", "a" * 200, "bad\r\nInjected: x", "中文id中文id中文id"]:
            got = resolve_task_request_id({TASK_REQUEST_ID_HEADER: bad})
            assert got != bad, f"非法值 {bad!r} 未被替换"
            assert len(got) >= 8

    def test_non_string_value_is_coerced_then_validated(self):
        got = resolve_task_request_id({TASK_REQUEST_ID_HEADER: 12345678901234})
        assert isinstance(got, str)


class TestBindUnbind:
    """worker 侧 ContextVar 绑定与还原。"""

    def test_bind_sets_context_var(self):
        rid = new_request_id()
        bind_task_request_id(rid)
        assert get_current_request_id() == rid, (
            "bind 后ContextVar 未生效 —— 任务日志 req_id 仍会是 '-'"
        )

    def test_unbind_clears_context_var(self):
        """还原是防泄漏的关键: 同一 worker 线程的下一个任务不能继承上一个 ID。"""
        bind_task_request_id(new_request_id())
        unbind_task_request_id()
        assert get_current_request_id() is None

    def test_bind_none_clears(self):
        bind_task_request_id("some-id-value-1234")
        bind_task_request_id(None)
        assert get_current_request_id() is None

    def test_rebind_overwrites_previous(self):
        """连续两个任务: 第二个的 ID 必须覆盖第一个, 不能残留。"""
        first = new_request_id()
        second = new_request_id()
        bind_task_request_id(first)
        bind_task_request_id(second)
        assert get_current_request_id() == second


class TestCelerySignalHandlers:
    """三个 Celery 信号处理器的行为。"""

    def test_publish_adds_header_when_absent(self):
        from app.core.celery_app import _propagate_request_id

        headers: dict = {}
        _propagate_request_id(headers=headers)
        assert TASK_REQUEST_ID_HEADER in headers
        assert headers[TASK_REQUEST_ID_HEADER]

    def test_publish_preserves_existing_id(self):
        """上游已带 ID 时不得覆盖 —— 那是调用方的真实链路 ID。"""
        from app.core.celery_app import _propagate_request_id

        given = "caller-supplied-id-9876"
        headers = {TASK_REQUEST_ID_HEADER: given}
        _propagate_request_id(headers=headers)
        assert headers[TASK_REQUEST_ID_HEADER] == given

    def test_publish_inherits_http_request_id(self):
        """fire-and-forget: 应继承 HTTP 链路的 request_id 而非另生成。"""
        from app.core.celery_app import _propagate_request_id
        from app.core.tracing import set_current_request_id

        http_rid = new_request_id()
        set_current_request_id(http_rid)
        try:
            headers: dict = {}
            _propagate_request_id(headers=headers)
            assert headers[TASK_REQUEST_ID_HEADER] == http_rid
        finally:
            set_current_request_id(None)

    def test_publish_tolerates_none_headers(self):
        from app.core.celery_app import _propagate_request_id

        _propagate_request_id(headers=None)  # 不应抛异常

    def test_prerun_binds_and_logs(self, caplog):
        """prerun 必须让任务内日志带上 request_id。"""
        from app.core.celery_app import _bind_request_id

        rid = new_request_id()

        class _Req:
            headers = {TASK_REQUEST_ID_HEADER: rid}

        class _Task:
            name = "app.tasks.scheduler.daily_intervention_check"
            request = _Req()
            headers = None

        with caplog.at_level("INFO"):
            _bind_request_id(task_id="task-123", task=_Task())

        assert get_current_request_id() == rid
        assert rid in caplog.text, "任务启动日志未含 request_id, 无法关联调用方"
        assert "task-123" in caplog.text

    def test_prerun_generates_when_task_has_no_headers(self):
        """beat 定时触发的任务本就没有上游 ID, 应自造一个而非留空。"""
        from app.core.celery_app import _bind_request_id

        class _Task:
            name = "some.task"
            request = None
            headers = None

        _bind_request_id(task_id="t1", task=_Task())
        assert get_current_request_id(), "prerun 后 ContextVar 仍为空"

    def test_postrun_clears_context(self):
        from app.core.celery_app import _bind_request_id, _unbind_request_id

        class _Task:
            name = "x"
            request = None
            headers = None

        _bind_request_id(task_id="t1", task=_Task())
        assert get_current_request_id()
        _unbind_request_id(task_id="t1", task=_Task())
        assert get_current_request_id() is None, (
            "postrun 未还原 ContextVar —— 会把上一个任务的 ID 泄漏给下一个"
        )

    def test_signal_handlers_swallow_exceptions(self):
        """信号回调抛异常会影响 Celery 内部状态, 必须自我吞掉。"""
        from app.core.celery_app import (
            _bind_request_id,
            _propagate_request_id,
            _unbind_request_id,
        )

        class _Boom:
            @property
            def headers(self):
                raise RuntimeError("boom")

        class _Task:
            name = "x"
            request = _Boom()
            headers = None

        # 均不应抛
        _propagate_request_id(headers={})
        _bind_request_id(task_id="t", task=_Task())
        _unbind_request_id(task_id="t", task=_Task())