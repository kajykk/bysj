from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from app.core.config import settings
from app.core.degradation import record_silent_degradation
from app.core.metrics import http_request_duration_seconds, http_requests_total
from app.core.request_id import REQUEST_ID_HEADER, get_or_create_request_id

# L-13 修复：将 tracing 导入移到模块顶部，避免每次请求都执行 import 语句
# tracing 模块仅依赖标准库，无循环导入风险
# ISS-100 修复：同时设置 request_id ContextVar，供日志 Filter 注入
from app.core.tracing import (
    extract_or_new_trace,
    set_current_request_id,
    set_current_trace,
)

logger = logging.getLogger(__name__)


def _normalize_metrics_path(path: str) -> str:
    """ISS-037: 无路由模板时的标签路径归一化, 防止高基数标签.

    数字段折叠为 {id}, 连续重复段合并, 长度超限截断.
    """
    if not path:
        return "unknown"
    parts: list[str] = []
    for seg in path.split("/"):
        if seg == "":
            continue
        if seg.isdigit():
            seg = "{id}"
        if parts and parts[-1] == seg:
            continue
        parts.append(seg)
    if len(parts) > 6:
        parts = parts[:6] + ["..."]
    normalized = "/".join(parts)
    if not normalized:
        return "unknown"
    if path.startswith("/") and not normalized.startswith("/"):
        normalized = "/" + normalized
    return normalized


async def request_id_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    request_id = get_or_create_request_id(request)
    request.state.request_id = request_id
    # ISS-100 修复：同步设置到 ContextVar，使日志 Filter 能注入 request_id
    set_current_request_id(request_id)

    # v1.33: W3C Trace Context 集成
    traceparent_header = request.headers.get("traceparent")
    trace = extract_or_new_trace(traceparent_header)
    set_current_trace(trace)
    request.state.trace_id = trace.trace_id
    request.state.span_id = trace.span_id

    try:
        response = await call_next(request)
        # H-Core-9 修复：将 headers 设置移到 try 块内（call_next 成功后、finally 之前），
        # 避免 call_next 抛异常时 response 未定义导致 UnboundLocalError
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers["X-Trace-Id"] = trace.trace_id
        response.headers["X-Span-Id"] = trace.span_id
    finally:
        # 清理当前 trace context 和 request_id (避免泄漏到下一个请求)
        set_current_trace(None)
        set_current_request_id(None)
    return response


async def metrics_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """记录 HTTP 请求指标 (v1.30).

    收集:
    - http_requests_total{method, path, status}
    - http_request_duration_seconds{method, path}

    路径归一化: 用 URL path 模板 (避免高基数), 但 fastapi router 提供的
    request.scope['route'].path 可拿到模板如 /users/{user_id}, 优先使用.
    """
    start = time.perf_counter()
    # OPT-P1-001：下游中间件/路由抛出异常时也必须记录指标，
    # 否则错误请求不计入 http_requests_total，导致 SLO 可用性偏乐观。
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration = time.perf_counter() - start

        # 提取 path 模板 (如果可用)
        route = request.scope.get("route")
        path_template = getattr(route, "path", None)
        if not path_template:
            # ISS-037 修复：无路由模板 (404/中间件直接响应) 时归一化路径,
            # 避免完整 URL path 成为高基数标签
            path_template = _normalize_metrics_path(request.url.path)

        # 排除 /metrics 自身以避免自激
        if path_template != "/api/v1/metrics":
            try:
                method = request.method
                status = str(status_code)
                http_requests_total.inc(method=method, path=path_template, status=status)
                http_request_duration_seconds.observe(duration, method=method, path=path_template)
            except Exception as exc:
                # P1-E 修复：HTTP 指标记录失败必须记录日志，便于发现指标系统异常
                logger.warning(
                    "HTTP metrics recording failed for %s %s: %s",
                    request.method,
                    path_template,
                    exc,
                )


async def security_headers_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """添加安全响应头中间件 (v1.10 增强版).

    SEC-P2-009: CSP 由 nginx 统一设置 (frontend/nginx.conf:81), 后端不再设置.
    原因:
    1. nginx 的 add_header Content-Security-Policy ... always 对 proxy_pass 响应也追加,
       若后端也设置会导致浏览器收到两个 CSP header, 行为不确定
    2. nginx 静态 CSP 与后端 nonce-based CSP 取交集会让所有内联脚本被阻塞
       (因为 nginx CSP 的 script-src 'self' 没有对应 nonce)
    3. API 响应为 JSON, 不需要 CSP; 前端 HTML 由 nginx 服务, nginx CSP 已覆盖

    后端保留: X-Content-Type-Options, X-XSS-Protection, Referrer-Policy,
    Permissions-Policy, X-DNS-Prefetch-Control, HSTS (生产环境)
    """
    response = await call_next(request)

    # 基础安全头（所有环境）
    # SEC-P2-010: X-Frame-Options 由 nginx 统一设置 (SAMEORIGIN), 避免前后端双重 header 冲突
    # nginx add_header 对 proxy_pass 响应也会追加, 若后端也设置会导致浏览器收到两个 X-Frame-Options
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "0"  # 现代浏览器使用CSP
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=(), payment=(), usb=()"
    response.headers["X-DNS-Prefetch-Control"] = "off"

    # SEC-P2-009: CSP 由 nginx 统一设置 (frontend/nginx.conf:81), 后端不再设置
    # 详见函数 docstring 说明

    # HSTS（仅生产环境）
    if settings.app_env.lower() == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    return response


# ===== P2-34: 末道脱敏中间件 =====
#
# 背景（审查报告 P2-34）：`HTTPException(detail=str(exc))` 把异常原文直接出网。
# 即使逐点改成 ServiceError，也挡不住"下一个作者再写一处 detail=str(e)"。
# 因此需要一道**不依赖调用方自觉**的末道闸门：对错误响应的 JSON 体做敏感特征
# 扫描，命中即替换为通用文案并记录脱敏事件。
#
# 设计约束（均有测试把守）：
# 1. **只处理 4xx/5xx 的 JSON 响应**。成功响应（2xx）不解析、不改写。
# 2. **判据是确定性特征清单**（见 _SENSITIVE_PATTERNS），不是"看起来像内部信息"的
#    启发式 —— 启发式会把正当的用户可读文案误伤（如"路径不合法"这类安全提示）。
# 3. **替换后必须留痕**：logger.warning + `error_sanitized_total` 计数，
#    便于发现"谁在绕过统一方言"。
# 4. 响应体解析失败（非 JSON / 流式）时**原样放行**，不猜、不抛。

import json as _json
import re as _re
from typing import Any as _Any

from starlette.responses import StreamingResponse

# 确定性敏感特征：命中任一即判定为"内部信息泄漏到错误响应"
_SENSITIVE_PATTERNS: tuple[_re.Pattern[str], ...] = tuple(
    _re.compile(p)
    for p in (
        r"Traceback \(most recent call last\)",
        r'File "[^"]*\.py", line \d+',
        r"\b(INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|SELECT\s+.+?\s+FROM)\b",
        r"\b(psycopg|psycopg2|sqlalchemy\.exc|asyncpg)\b",
        r"\bErrno\s*\d+",
        r"\b(ConnectionRefusedError|ConnectionResetError|BrokenPipeError)\b",
        r"\b(OSError|socket\.timeout|TimeoutError)\b",
        r"\bredis\.exceptions\b|\bRedisError\b",
        r"(?:^|[\s\"'])(?:/home/|/Users/|/var/|[A-Z]:\\)[^\s\"']*",
        r"\bapp\.[a-z_]+\.[a-z_]+:[A-Za-z_]+Error\b",
        r"\bnull value in column\b|\bduplicate key value violates\b",
        r"\bUNIQUE constraint failed\b|\bFOREIGN KEY constraint failed\b",
    )
)

# 错误响应里承载消息的字段：命中任一字段即检查
_MESSAGE_FIELDS = ("message", "detail", "error_detail", "reason")

_GENERIC_CLIENT_MESSAGE = "请求处理失败，请稍后重试或联系管理员"

# 短文本一律不判敏感：既防误伤（"404"/"不存在"这类正当文案），也省 CPU
_MIN_SENSITIVE_LEN = 8


def _looks_sensitive(value: _Any) -> bool:
    """确定性判据：只认特征清单，不做语义猜测。"""
    if not isinstance(value, str) or len(value) < _MIN_SENSITIVE_LEN:
        return False
    return any(p.search(value) for p in _SENSITIVE_PATTERNS)


def _scrub_error_body(body: bytes) -> tuple[bytes, bool]:
    """扫描错误响应体，命中敏感特征则替换为通用文案。"""
    try:
        data = _json.loads(body.decode("utf-8"))
    except Exception:
        return body, False  # 非 JSON / 流式：原样放行，不猜不抛
    if not isinstance(data, dict):
        return body, False

    scrubbed = False
    for key in _MESSAGE_FIELDS:
        if key in data and _looks_sensitive(data[key]):
            data[key] = _GENERIC_CLIENT_MESSAGE
            scrubbed = True
    err = data.get("error")
    if isinstance(err, dict):
        for key in _MESSAGE_FIELDS:
            if key in err and _looks_sensitive(err[key]):
                err[key] = _GENERIC_CLIENT_MESSAGE
                scrubbed = True
        details = err.get("details")
        if isinstance(details, dict):
            for dk, dv in list(details.items()):
                if _looks_sensitive(dv):
                    details[dk] = _GENERIC_CLIENT_MESSAGE
                    scrubbed = True

    if not scrubbed:
        return body, False
    return _json.dumps(data, ensure_ascii=False).encode("utf-8"), True


async def error_sanitizer_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """P2-34 末道脱敏：错误响应里的内部信息一律换成通用文案。

    位置：必须包在路由/异常处理器**之外**（否则覆盖不到未捕获异常与限流 429 的
    响应体），又必须在 request_id **之内**（脱敏日志要带 request_id）。
    """
    response = await call_next(request)

    if response.status_code < 400:
        return response
    if isinstance(response, StreamingResponse):
        return response

    body = getattr(response, "body", None)
    if not body:
        return response

    new_body, scrubbed = _scrub_error_body(body)
    if not scrubbed:
        return response

    try:
        from app.core.metrics import error_sanitized_total

        error_sanitized_total.inc()
    except Exception as exc:
        # P2-35：指标上报失败不得影响脱敏主流程，但必须留痕
        # （"旁路失败不影响主流程"不等于"失败不留痕"）
        logger.debug("error_sanitized_total.inc failed: %s", exc)
        record_silent_degradation("core.middlewares.error_sanitizer")
    logger.warning(
        "P2-34 末道脱敏命中: path=%s status=%s request_id=%s",
        request.url.path,
        response.status_code,
        getattr(request.state, "request_id", None),
    )

    headers = dict(response.headers)
    headers.pop("content-length", None)
    return Response(
        content=new_body,
        status_code=response.status_code,
        headers=headers,
        media_type=response.media_type,
    )
