"""ISS-02 第七轮: app.tasks.pdf_report 纯逻辑聚焦测试.

覆盖点 (ISS-048 控制字符清洗, 安全关键):
- _sanitize_text (过滤 C0 控制字符, 保留 \\t \\n \\r, 非 str 透传)
- _sanitize_param (递归清洗 str/list/dict)
- _count_pdf_pages (基于 /Type /Page 正则计数, 至少 1)
- _job_key / _bytes_key (Redis key 前缀)
无需 DB / celery / redis 实时连接.
"""
from __future__ import annotations

from app.tasks.pdf_report import (
    _bytes_key,
    _count_pdf_pages,
    _job_key,
    _sanitize_param,
    _sanitize_text,
)


# ===== _sanitize_text (ISS-048) =====
def test_sanitize_text_none_passthrough():
    assert _sanitize_text(None) is None


def test_sanitize_text_int_passthrough():
    assert _sanitize_text(123) == 123


def test_sanitize_text_plain_unchanged():
    assert _sanitize_text("hello world") == "hello world"


def test_sanitize_text_strips_c0_control_chars():
    # \x00 \x01 \x02 被移除
    assert _sanitize_text("a\x00b\x01c\x02d") == "abcd"


def test_sanitize_text_preserves_tab_newline_cr():
    # \t \n \r 保留 (正则排除 \x09 \x0a \x0d)
    assert _sanitize_text("a\tb\nc\rd") == "a\tb\nc\rd"


def test_sanitize_text_strips_del():
    # \x7f (DEL) 被移除
    assert _sanitize_text("a\x7fb") == "ab"


# ===== _sanitize_param (ISS-048 递归) =====
def test_sanitize_param_nested_dict():
    inp = {"k1": "a\x00b", "k2": ["c\x01d", {"k3": "e\x02f"}]}
    out = _sanitize_param(inp)
    assert out == {"k1": "ab", "k2": ["cd", {"k3": "ef"}]}


def test_sanitize_param_list_of_str():
    assert _sanitize_param(["a\x00", "b\x01"]) == ["a", "b"]


def test_sanitize_param_none():
    assert _sanitize_param(None) is None


def test_sanitize_param_int():
    assert _sanitize_param(42) == 42


# ===== _count_pdf_pages =====
def test_count_pdf_pages_three():
    data = b"/Type /Page /Type /Page /Type /Page"
    assert _count_pdf_pages(data) == 3


def test_count_pdf_pages_excludes_pages_keyword():
    # /Type /Pages 不应计入 (负向预测 (?![a-zA-Z]))
    data = b"/Type /Pages"
    assert _count_pdf_pages(data) == 1  # max(1, 0)


def test_count_pdf_pages_empty():
    assert _count_pdf_pages(b"") == 1


def test_count_pdf_pages_mixed():
    data = b"/Type /Page /Type /Pages /Type /Page"
    assert _count_pdf_pages(data) == 2


# ===== key 前缀 =====
def test_job_key_prefix():
    assert _job_key("j1") == "pdf:job:j1"


def test_bytes_key_prefix():
    assert _bytes_key("j1") == "pdf:bytes:j1"
