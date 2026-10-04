"""决策四: app/tasks/pdf_report.py 危险路径测试 (app/tasks 中唯一无测试模块).

覆盖:
- 任务注册与装饰器配置 (max_retries=3 / time_limit / soft_time_limit)
- ISS-048 清洗函数 (_sanitize_text / _sanitize_param)
- OPT-T4-P1 时间规范化 (_epoch_to_iso) / Redis key 前缀
- _count_pdf_pages 页数统计
- Redis 任务状态存取 (save/get/update/list) 与 PDF 字节存取 (setex TTL)
  —— 全部走 FakeSyncRedis, 不依赖真实 Redis
- Redis 不可用时的容错契约 (吞异常, 不打断 celery worker)
- _notify_progress 状态字段组装 + WebSocket 推送容错
- generate_pdf_report 四条路径: 成功 / 服务报告失败 / 异常重试 / 重试耗尽

驱动方式: bound task 经 request_stack.push(Context(retries=N)) 后调
task.run(...), self.request.retries 精确可控 (Task.request 为 property,
读 request_stack 栈顶).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from celery.app.task import Context
from celery.exceptions import Retry

import app.tasks.pdf_report as pdf_task_module
from app.core.celery_app import celery_app
from app.tasks.pdf_report import (
    _PDF_BYTES_TTL_SECONDS,
    _PDF_JOB_INDEX_KEY,
    _bytes_key,
    _count_pdf_pages,
    _epoch_to_iso,
    _job_key,
    _sanitize_param,
    _sanitize_text,
    create_initial_job,
    delete_pdf_bytes_from_redis,
    generate_pdf_report,
    get_job_from_redis,
    get_pdf_bytes_from_redis,
    list_jobs_from_redis,
    save_job_to_redis,
    save_pdf_bytes_to_redis,
    update_job_in_redis,
)

PDF_TASK_NAME = "app.tasks.pdf_report.generate_pdf_report"


def _real_task():
    """PromiseProxy 之下的真实 Task 实例 (patch.retry 必须落在实例上)."""
    return celery_app.tasks[PDF_TASK_NAME]


def _run_task(job_id: str = "job-1", user_name: str = "alice", retries: int = 0, **kwargs):
    """以受控的 request.retries 执行 bound task 函数体."""
    generate_pdf_report.request_stack.push(Context(retries=retries))
    try:
        return generate_pdf_report.run(job_id, user_name, **kwargs)
    finally:
        generate_pdf_request_popped = generate_pdf_report.request_stack.pop()
        assert generate_pdf_request_popped is not None


class FakeSyncRedis:
    """同步 Redis 假实现 (decode_responses=False 的二进制语义)."""

    def __init__(self) -> None:
        self.strings: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}
        self.sets: dict[str, set[bytes]] = {}

    def set(self, key, value):
        self.strings[key] = value

    def setex(self, key, ttl, value):
        self.strings[key] = value
        self.ttls[key] = ttl

    def get(self, key):
        return self.strings.get(key)

    def sadd(self, key, member):
        # redis-py binary 模式: str 参数会被编码为 bytes 存储
        self.sets.setdefault(key, set()).add(
            member if isinstance(member, bytes) else member.encode("utf-8")
        )

    def smembers(self, key):
        return set(self.sets.get(key, set()))

    def delete(self, key):
        self.strings.pop(key, None)


# ---------- 任务注册与装饰器配置 ----------


def test_task_registered_in_celery():
    """PR-001: 任务以声明名注册."""
    assert PDF_TASK_NAME in celery_app.tasks


def test_task_decorator_options():
    """PR-002: 重试/超时配置钉死 (3 次重试, 硬超时 300s, 软超时 270s)."""
    task = _real_task()
    assert task.max_retries == 3
    assert task.time_limit == 300
    assert task.soft_time_limit == 270


# ---------- ISS-048 清洗函数 ----------


def test_sanitize_text_keeps_tab_newline_cr():
    """PR-003: \\t \\n \\r 保留."""
    s = "a\tb\nc\rd"
    assert _sanitize_text(s) == s


def test_sanitize_text_strips_control_chars():
    """PR-004: \\x00-\\x08/\\x0b/\\x0c/\\x0e-\\x1f/\\x7f 移除."""
    s = "a\x00b\x08c\x0bd\x0ce\x1ff\x7fg"
    assert _sanitize_text(s) == "abcdefg"


def test_sanitize_text_non_string_passthrough():
    """PR-005: 非字符串原样返回."""
    sentinel = {"k": 1}
    assert _sanitize_text(None) is None
    assert _sanitize_text(5) == 5
    assert _sanitize_text(sentinel) is sentinel


def test_sanitize_param_recursive():
    """PR-006: str/list/dict 递归清洗."""
    value = {
        "name": "u\x00i",
        "tags": ["t\x07a", {"deep": "v\x1fb"}],
        "score": 3,
        "flag": None,
    }
    cleaned = _sanitize_param(value)
    assert cleaned == {"name": "ui", "tags": ["ta", {"deep": "vb"}], "score": 3, "flag": None}


def test_sanitize_param_non_str_non_container():
    """PR-007: 标量原样返回."""
    assert _sanitize_param(1.5) == 1.5
    assert _sanitize_param(True) is True


# ---------- 时间规范化 / key 前缀 ----------


def test_epoch_to_iso_none():
    assert _epoch_to_iso(None) is None


def test_epoch_to_iso_epoch_zero():
    assert _epoch_to_iso(0) == "1970-01-01T00:00:00+00:00"


def test_epoch_to_iso_float_epoch():
    iso = _epoch_to_iso(1700000000.5)
    assert iso == "2023-11-14T22:13:20.500000+00:00"


def test_epoch_to_iso_string_passthrough():
    assert _epoch_to_iso("2026-01-01T00:00:00") == "2026-01-01T00:00:00"


def test_job_and_bytes_key_prefixes():
    assert _job_key("abc") == "pdf:job:abc"
    assert _bytes_key("abc") == "pdf:bytes:abc"


# ---------- _count_pdf_pages ----------


def test_count_pdf_pages_counts():
    pdf = b"%PDF-1.4 ... /Type /Page ... /Type /Page ..."
    assert _count_pdf_pages(pdf) == 2


def test_count_pdf_pages_negative_lookahead():
    """/Type /Pages 不应被计入 (?![a-zA-Z])."""
    pdf = b"/Type /Pages /Type /Page"
    assert _count_pdf_pages(pdf) == 1


def test_count_pdf_pages_zero_clamped_to_one():
    assert _count_pdf_pages(b"no page markers here") == 1


# ---------- Redis 任务状态存取 ----------


def test_job_roundtrip_binary_mode():
    """RR-001: bytes 模式存取 (decode_responses=False), get 端解 bytes."""
    fake = FakeSyncRedis()
    with patch.object(pdf_task_module, "_get_sync_redis", return_value=fake):
        job = create_initial_job("j1", "alice", created_by=7)
        save_job_to_redis("j1", job)
        assert "pdf:job:j1" in fake.strings
        loaded = get_job_from_redis("j1")
    assert loaded["job_id"] == "j1"
    assert loaded["status"] == "queued"
    assert loaded["created_by"] == 7


def test_update_job_merges_and_touches_updated_at():
    fake = FakeSyncRedis()
    with patch.object(pdf_task_module, "_get_sync_redis", return_value=fake):
        save_job_to_redis("j1", create_initial_job("j1", "alice", created_by=7))
        created_at = get_job_from_redis("j1")["created_at"]
        update_job_in_redis("j1", status="completed", file_size=123)
        updated = get_job_from_redis("j1")
    assert updated["status"] == "completed"
    assert updated["file_size"] == 123
    assert updated["updated_at"] >= created_at


def test_update_missing_job_is_noop():
    """RR-002: 更新不存在的任务 -> 警告但不抛异常."""
    fake = FakeSyncRedis()
    with patch.object(pdf_task_module, "_get_sync_redis", return_value=fake):
        update_job_in_redis("ghost", status="completed")  # 不应 raise
    assert get_job_from_redis("ghost") is None


def test_list_jobs_filters_and_normalizes():
    """RR-003: created_by 过滤 + epoch->ISO 规范化 + backend=celery 标记."""
    fake = FakeSyncRedis()
    job_a = create_initial_job("ja", "alice", created_by=7)
    job_b = create_initial_job("jb", "bob", created_by=8)
    job_b["started_at"] = 1700000000.0
    with patch.object(pdf_task_module, "_get_sync_redis", return_value=fake):
        save_job_to_redis("ja", job_a)
        save_job_to_redis("jb", job_b)
        items_all = list_jobs_from_redis()
        items_a = list_jobs_from_redis(created_by=7)
    by_id = {i["job_id"]: i for i in items_all}
    assert set(by_id) == {"ja", "jb"}
    assert by_id["jb"]["backend"] == "celery"
    assert by_id["jb"]["started_at"] == "2023-11-14T22:13:20+00:00"
    assert by_id["jb"]["created_at"].endswith("+00:00")
    assert [i["job_id"] for i in items_a] == ["ja"]


def test_list_jobs_skips_missing_index_entries():
    """RR-004: 索引里有但 job key 已过期 -> 跳过该条 (不炸)."""
    fake = FakeSyncRedis()
    fake.sets[_PDF_JOB_INDEX_KEY] = {b"ja", b"expired"}
    with patch.object(pdf_task_module, "_get_sync_redis", return_value=fake):
        save_job_to_redis("ja", create_initial_job("ja", "alice", created_by=7))
        items = list_jobs_from_redis()
    assert [i["job_id"] for i in items] == ["ja"]


def test_pdf_bytes_setex_ttl_and_delete():
    """RR-005: 字节存取走 setex 且 TTL=3600; delete 释放."""
    fake = FakeSyncRedis()
    with patch.object(pdf_task_module, "_get_sync_redis", return_value=fake):
        save_pdf_bytes_to_redis("j1", b"%PDF-fake")
        assert fake.ttls["pdf:bytes:j1"] == _PDF_BYTES_TTL_SECONDS == 3600
        assert get_pdf_bytes_from_redis("j1") == b"%PDF-fake"
        delete_pdf_bytes_from_redis("j1")
        assert get_pdf_bytes_from_redis("j1") is None


def test_redis_unavailable_error_tolerance():
    """RR-006: Redis 不可用时全部吞异常 —— save 不炸, get->None, list->[]."""
    with patch.object(
        pdf_task_module, "_get_sync_redis", side_effect=RuntimeError("no redis")
    ):
        save_job_to_redis("j1", {"a": 1})  # 不 raise
        assert get_job_from_redis("j1") is None
        assert list_jobs_from_redis() == []
        save_pdf_bytes_to_redis("j1", b"x")  # 不 raise
        assert get_pdf_bytes_from_redis("j1") is None
        delete_pdf_bytes_from_redis("j1")  # 不 raise


# ---------- _notify_progress ----------


def test_notify_progress_running_adds_started_at():
    with patch.object(pdf_task_module, "update_job_in_redis") as m_upd, patch.object(
        pdf_task_module, "get_job_from_redis", return_value=None
    ):
        pdf_task_module._notify_progress("j1", status="running", progress=10)
    updates = m_upd.call_args.kwargs
    assert m_upd.call_args.args[0] == "j1"
    assert updates["status"] == "running"
    assert updates["progress"] == 10
    assert isinstance(updates["started_at"], float)
    assert "completed_at" not in updates


def test_notify_progress_completed_adds_completed_at_and_extra():
    with patch.object(pdf_task_module, "update_job_in_redis") as m_upd, patch.object(
        pdf_task_module, "get_job_from_redis", return_value=None
    ):
        pdf_task_module._notify_progress(
            "j1",
            status="completed",
            progress=100,
            extra_updates={"file_size": 9, "page_count": 2},
        )
    updates = m_upd.call_args.kwargs
    assert updates["status"] == "completed"
    assert isinstance(updates["completed_at"], float)
    assert updates["file_size"] == 9
    assert updates["page_count"] == 2


def test_notify_progress_error_included_only_when_given():
    with patch.object(pdf_task_module, "update_job_in_redis") as m_upd, patch.object(
        pdf_task_module, "get_job_from_redis", return_value=None
    ):
        pdf_task_module._notify_progress("j1", status="failed", progress=100, error="boom")
        updates = m_upd.call_args.kwargs
        assert updates["error"] == "boom"
        m_upd.reset_mock()
        pdf_task_module._notify_progress("j1", status="running", progress=50)
        assert "error" not in m_upd.call_args.kwargs


def test_notify_progress_pushes_websocket_to_creator():
    """NP-004: 从 job_data 读 created_by 推送 WebSocket."""
    job = {"created_by": 42}
    with patch.object(pdf_task_module, "update_job_in_redis"), patch.object(
        pdf_task_module, "get_job_from_redis", return_value=job
    ), patch("app.core.ws.notify_task_progress") as m_notify, patch.object(
        pdf_task_module, "_run_async"
    ) as m_run_async:
        pdf_task_module._notify_progress("j1", status="running", progress=30)
    m_notify.assert_called_once_with(
        user_id=42,
        job_id="j1",
        status="running",
        progress=30,
        job_type="pdf",
        error=None,
    )
    m_run_async.assert_called_once()


def test_notify_progress_no_created_by_skips_ws():
    with patch.object(pdf_task_module, "update_job_in_redis"), patch.object(
        pdf_task_module, "get_job_from_redis", return_value={"status": "queued"}
    ), patch("app.core.ws.notify_task_progress") as m_notify, patch.object(
        pdf_task_module, "_run_async"
    ) as m_run_async:
        pdf_task_module._notify_progress("j1", status="running", progress=30)
    m_run_async.assert_not_called()
    m_notify.assert_not_called()


def test_notify_progress_ws_failure_swallowed():
    """NP-006: WebSocket 推送失败不影响任务 (吞异常)."""
    with patch.object(pdf_task_module, "update_job_in_redis"), patch.object(
        pdf_task_module, "get_job_from_redis", return_value={"created_by": 42}
    ), patch("app.core.ws.notify_task_progress"), patch.object(
        pdf_task_module, "_run_async", side_effect=RuntimeError("ws down")
    ):
        pdf_task_module._notify_progress("j1", status="running", progress=30)  # 不 raise


# ---------- generate_pdf_report 任务路径 ----------


def _service_mock(**overrides) -> MagicMock:
    svc = MagicMock()
    svc.generate_user_risk_report.return_value = SimpleNamespace(
        success=True, pdf_bytes=b"%PDF-fake", file_size=9, page_count=2, **overrides
    )
    return svc


def test_generate_pdf_report_success_path():
    """GT-001: 成功 -> completed + 字节入 Redis + file_size/page_count 上报."""
    svc = _service_mock()
    with patch(
        "app.services.pdf_report_service.pdf_report_service", svc
    ), patch.object(pdf_task_module, "_notify_progress") as m_notify, patch.object(
        pdf_task_module, "save_pdf_bytes_to_redis"
    ) as m_save:
        result = _run_task(job_id="job-1", user_name="alice")

    assert result == {"job_id": "job-1", "status": "completed", "file_size": 9, "page_count": 2}
    m_save.assert_called_once_with("job-1", b"%PDF-fake")
    last = m_notify.call_args_list[-1]
    assert last.kwargs["status"] == "completed"
    assert last.kwargs["progress"] == 100
    assert last.kwargs["extra_updates"] == {"file_size": 9, "page_count": 2}


def test_generate_pdf_report_service_reports_failure():
    """GT-002: 生成器返回 success=False -> failed + error 上报, 字节不落 Redis."""
    svc = MagicMock()
    svc.generate_user_risk_report.return_value = SimpleNamespace(
        success=False, pdf_bytes=b"", file_size=0, page_count=0, error_message="render boom"
    )
    with patch(
        "app.services.pdf_report_service.pdf_report_service", svc
    ), patch.object(pdf_task_module, "_notify_progress") as m_notify, patch.object(
        pdf_task_module, "save_pdf_bytes_to_redis"
    ) as m_save:
        result = _run_task(job_id="job-2", user_name="bob")

    assert result["status"] == "failed"
    assert result["error"] == "render boom"
    m_save.assert_not_called()
    last = m_notify.call_args_list[-1]
    assert last.kwargs["status"] == "failed"
    assert last.kwargs["error"] == "render boom"


def test_generate_pdf_report_exception_retries():
    """GT-003: 未耗尽重试 (retries=0) -> 状态置 failed 后 self.retry 触发."""
    svc = MagicMock()
    svc.generate_user_risk_report.side_effect = RuntimeError("kaboom")
    real = _real_task()
    with patch(
        "app.services.pdf_report_service.pdf_report_service", svc
    ), patch.object(pdf_task_module, "_notify_progress") as m_notify, patch.object(
        real, "retry", side_effect=Retry()
    ) as m_retry:
        with pytest.raises(Retry):
            _run_task(job_id="job-3", user_name="carol", retries=0)

    m_retry.assert_called_once()
    last = m_notify.call_args_list[-1]
    assert last.kwargs["status"] == "failed"
    assert last.kwargs["error"] == "kaboom"


def test_generate_pdf_report_retries_exhausted_returns_failed():
    """GT-004: retries>=3 -> 不再重试, 返回 failed dict."""
    svc = MagicMock()
    svc.generate_user_risk_report.side_effect = RuntimeError("kaboom")
    real = _real_task()
    with patch(
        "app.services.pdf_report_service.pdf_report_service", svc
    ), patch.object(pdf_task_module, "_notify_progress"), patch.object(
        real, "retry"
    ) as m_retry:
        result = _run_task(job_id="job-4", user_name="dave", retries=3)

    m_retry.assert_not_called()
    assert result == {"job_id": "job-4", "status": "failed", "error": "kaboom"}


def test_generate_pdf_report_sanitizes_inputs():
    """GT-005: ISS-048 —— 入口对字符串参数做控制字符清洗后再调生成器."""
    svc = _service_mock()
    with patch(
        "app.services.pdf_report_service.pdf_report_service", svc
    ), patch.object(pdf_task_module, "_notify_progress"), patch.object(
        pdf_task_module, "save_pdf_bytes_to_redis"
    ):
        _run_task(
            job_id="job-5",
            user_name="a\x00b\x1fc\td\ne",
            risk_level="high\x07",
            risk_trend=[{"name": "p\x02q"}],
            recommendations=["ok\x0bx"],
        )

    kwargs = svc.generate_user_risk_report.call_args.kwargs
    assert kwargs["user_name"] == "abc\td\ne"
    assert kwargs["risk_level"] == "high"
    assert kwargs["risk_trend"] == [{"name": "pq"}]
    assert kwargs["recommendations"] == ["okx"]
