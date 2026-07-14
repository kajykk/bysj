from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from app.core.config import settings
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


async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
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


async def metrics_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
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
            http_request_duration_seconds.observe(
                duration, method=method, path=path_template
            )
        except Exception as exc:
            # P1-E 修复：HTTP 指标记录失败必须记录日志，便于发现指标系统异常
            logger.warning(
                "HTTP metrics recording failed for %s %s: %s",
                request.method,
                path_template,
                exc,
            )

    return response


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
    response.headers["Permissions-Policy"] = (
        "geolocation=(), microphone=(), camera=(), payment=(), usb=()"
    )
    response.headers["X-DNS-Prefetch-Control"] = "off"

    # SEC-P2-009: CSP 由 nginx 统一设置 (frontend/nginx.conf:81), 后端不再设置
    # 详见函数 docstring 说明

    # HSTS（仅生产环境）
    if settings.app_env.lower() == "production":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    return response
