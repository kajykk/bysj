from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from app.core.config import settings
from app.core.metrics import http_request_duration_seconds, http_requests_total
from app.core.request_id import REQUEST_ID_HEADER, get_or_create_request_id

logger = logging.getLogger(__name__)


async def request_id_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    request_id = get_or_create_request_id(request)
    request.state.request_id = request_id

    # v1.33: W3C Trace Context 集成
    from app.core.tracing import extract_or_new_trace, set_current_trace
    traceparent_header = request.headers.get("traceparent")
    trace = extract_or_new_trace(traceparent_header)
    set_current_trace(trace)
    request.state.trace_id = trace.trace_id
    request.state.span_id = trace.span_id

    try:
        response = await call_next(request)
    finally:
        # 清理当前 trace context (避免泄漏到下一个请求)
        set_current_trace(None)
    response.headers[REQUEST_ID_HEADER] = request_id
    response.headers["X-Trace-Id"] = trace.trace_id
    response.headers["X-Span-Id"] = trace.span_id
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
    response = await call_next(request)
    duration = time.perf_counter() - start

    # 提取 path 模板 (如果可用)
    route = request.scope.get("route")
    path_template = getattr(route, "path", None) or request.url.path

    # 排除 /metrics 自身以避免自激
    if path_template != "/api/v1/metrics":
        try:
            method = request.method
            status = str(response.status_code)
            http_requests_total.inc(method=method, path=path_template, status=status)
            http_request_duration_seconds.observe(duration, method=method, path=path_template)
        except Exception as exc:
            # P1-E 修复：HTTP 指标记录失败必须记录日志，便于发现指标系统异常
            logger.warning("HTTP metrics recording failed for %s %s: %s", request.method, path_template, exc)

    return response


async def security_headers_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """添加安全响应头中间件 (v1.10 增强版)"""
    response = await call_next(request)

    # 基础安全头（所有环境）
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "0"  # 现代浏览器使用CSP
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=(), payment=(), usb=()"
    response.headers["X-DNS-Prefetch-Control"] = "off"

    # CSP 策略 (v1.27 强化: 生产环境强制执行；非生产环境 Report-Only 以便调试)
    nonce = getattr(request.state, 'csp_nonce', "")
    script_src = f"script-src 'self' 'nonce-{nonce}'; " if nonce else "script-src 'self'; "
    style_src = f"style-src 'self' 'nonce-{nonce}'; " if nonce else "style-src 'self'; "
    csp_value = (
        "default-src 'self'; "
        + script_src
        + style_src
        + "img-src 'self' data: blob:; "
        + "connect-src 'self' https://sentry.io; "
        + "font-src 'self'; "
        + "frame-ancestors 'none'; "
        + "base-uri 'self'; "
        + "form-action 'self'; "
        + "upgrade-insecure-requests; "
        + "report-uri /api/v1/csp-report"
    )
    if settings.app_env.lower() == "production":
        # 生产环境: 强制执行（违规将被浏览器阻止）
        response.headers["Content-Security-Policy"] = csp_value
    else:
        # 非生产环境: Report-Only 以便调试，不阻断开发体验
        response.headers["Content-Security-Policy-Report-Only"] = csp_value

    # HSTS（仅生产环境）
    if settings.app_env.lower() == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    return response
