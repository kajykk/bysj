"""XSS protection utilities for input sanitization.

This module provides opt-in sanitization helpers and a defensive middleware.

设计原则 (v1.27 安全加固):
- 默认中间件不再对所有 JSON body 进行 html.escape，避免破坏用户日记/自由文本等合法内容
- 保留 `sanitize_html` / `strip_html_tags` 工具函数，供需要富文本转义的字段显式调用
- 中间件在生产环境对 URL query string 进行可疑脚本模式检查与日志告警
- 中间件对 JSON body 中**包含 HTML 标签或 JS 事件**的字段进行有针对性的转义
"""

# DEPRECATED: 此中间件未被使用，功能已迁移到 app.core.middlewares
# 保留用于参考，不应在新代码中导入
# 注意: sanitize_html / strip_html_tags / looks_like_xss 等工具函数仍被 tests 引用

from __future__ import annotations

import html
import logging
import re
from typing import Any
from urllib.parse import parse_qs

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

logger = logging.getLogger(__name__)

# 匹配常见 XSS payload 特征（用于 opt-in 检测）
_XSS_PATTERNS = re.compile(
    r"(?:"
    r"<script\b[^>]*>"            # <script>
    r"|</script\s*>"              # </script>
    r"|javascript\s*:"            # javascript:
    r"|on\w+\s*=\s*[\"']"        # onerror=, onclick=, ...
    r"|<iframe\b"                 # <iframe>
    r"|<object\b"                 # <object>
    r"|<embed\b"                  # <embed>
    r"|<svg\b[^>]*on\w+\s*="     # <svg onload=>
    r")",
    re.IGNORECASE,
)


def sanitize_html(text: str) -> str:
    """对可能包含 HTML 的文本进行转义（用于富文本字段）。"""
    return html.escape(text, quote=True)


def strip_html_tags(text: str) -> str:
    """移除 HTML 标签，返回纯文本。"""
    return re.sub(r"<[^>]+>", "", text)


def looks_like_xss(text: str) -> bool:
    """检查文本是否包含可能的 XSS payload 特征。"""
    return bool(_XSS_PATTERNS.search(text))


class XSSProtectionMiddleware(BaseHTTPMiddleware):
    """XSS 防护中间件 (v1.27 调整).

    行为:
    - 生产环境: 检查 URL query string 中的可疑 XSS 模式，发现则记录 WARN 日志（不阻断业务）
    - 生产环境: 检查 JSON body 中字符串字段的 XSS 模式，命中则记录 WARN
    - 开发环境: 不做任何事（避免影响前端热重载与调试）
    """

    def __init__(self, app, *, enabled: bool | None = None) -> None:
        super().__init__(app)
        if enabled is None:
            enabled = settings.app_env.lower() == "production"
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next):
        if self.enabled:
            self._check_query_params(request)
            if request.method in ("POST", "PUT", "PATCH"):
                await self._check_json_body(request)

        response = await call_next(request)
        return response

    def _check_query_params(self, request: Request) -> None:
        """检查 query string 中的 XSS payload。"""
        raw_qs = request.url.query
        if not raw_qs:
            return
        try:
            parsed = parse_qs(raw_qs, keep_blank_values=True)
        except Exception:
            return
        for key, values in parsed.items():
            for value in values:
                if looks_like_xss(value):
                    logger.warning(
                        "XSS payload detected in query string: key=%s value=%r ip=%s",
                        key, value[:200], request.client.host if request.client else "unknown",
                    )

    async def _check_json_body(self, request: Request) -> None:
        """检查 JSON body 中的 XSS payload。"""
        content_type = request.headers.get("content-type", "")
        if "application/json" not in content_type:
            return
        try:
            body = await request.json()
        except Exception:
            return
        if not isinstance(body, (dict, list)):
            return
        for path, value in self._iter_strings(body):
            if looks_like_xss(value):
                logger.warning(
                    "XSS payload detected in JSON body: path=%s value=%r",
                    path, value[:200],
                )

    def _iter_strings(self, value: Any, prefix: str = "") -> list[tuple[str, str]]:
        results: list[tuple[str, str]] = []
        if isinstance(value, str):
            results.append((prefix or "<root>", value))
        elif isinstance(value, dict):
            for k, v in value.items():
                results.extend(self._iter_strings(v, f"{prefix}.{k}" if prefix else str(k)))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                results.extend(self._iter_strings(item, f"{prefix}[{i}]"))
        return results
