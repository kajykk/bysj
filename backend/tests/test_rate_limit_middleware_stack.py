"""OPT-A1 回归测试：限流中间件全栈行为。

验证中间件栈重构（main.py OPT-A1 + rate_limit.SafeRateLimitMiddleware）后：
1. 超出 default_limits 的请求返回 429 JSON，而非冒泡为 500
   （异常处理器在内层 ExceptionMiddleware，无法捕获用户中间件层抛出的
   RateLimitExceeded —— 由外层 SafeRateLimitMiddleware 就地转换）
2. 429 响应携带 X-Request-ID（request_id 中间件位于最外层）
3. 429 响应携带 CORS 头（CORS 内移后错误响应不再被浏览器拦截）
"""

from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.testclient import TestClient

import app.core.rate_limit as rl
from app.core.middlewares import request_id_middleware
from app.core.rate_limit import Limiter, get_remote_address, install_rate_limiter
from app.core.request_id import REQUEST_ID_HEADER


def _build_app() -> FastAPI:
    """按 main.py OPT-A1 的相对顺序构建最小化应用（不含租户/DB）。"""
    test_limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["2/minute"],
    )
    original_limiter = rl.limiter
    rl.limiter = test_limiter
    try:
        app = FastAPI()

        @app.get("/ping")
        async def ping() -> dict:
            return {"ok": True}

        # 注册顺序与 main.py 一致（后注册者在外层）：
        # install(safe→slowapi) → CORS → request_id(最外)
        install_rate_limiter(app)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["https://example.com"],
            allow_credentials=True,
            allow_methods=["GET"],
            allow_headers=["Authorization", "Content-Type"],
        )
        app.middleware("http")(request_id_middleware)
    finally:
        rl.limiter = original_limiter
    return app


class TestRateLimitMiddlewareStack:
    def test_over_default_limit_returns_429_json(self):
        """超出 default_limits 应返回 429 统一结构，而非 500。"""
        client = TestClient(_build_app())
        assert client.get("/ping", headers={"Origin": "https://example.com"}).status_code == 200
        assert client.get("/ping", headers={"Origin": "https://example.com"}).status_code == 200

        third = client.get("/ping", headers={"Origin": "https://example.com"})
        assert third.status_code == 429
        data = third.json()
        assert data["code"] == 429
        assert data["error"]["code"] == "RATE_LIMIT_EXCEEDED"

    def test_429_response_carries_request_id_and_cors(self):
        """限流拒绝响应必须带 X-Request-ID 与 CORS 头（错误响应可观测且不被浏览器拦截）。"""
        client = TestClient(_build_app())
        for _ in range(2):
            client.get("/ping", headers={"Origin": "https://example.com"})

        rejected = client.get("/ping", headers={"Origin": "https://example.com"})
        assert rejected.status_code == 429
        assert rejected.headers.get(REQUEST_ID_HEADER)
        assert rejected.headers.get("access-control-allow-origin") == "https://example.com"
