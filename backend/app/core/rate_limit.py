from __future__ import annotations

import logging

from fastapi import Request, Response
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_limiter() -> Limiter:
    app_env = settings.app_env.lower()
    kwargs: dict = {}

    if app_env == "production":
        redis_url = settings.redis_url
        if redis_url and redis_url.startswith("redis"):
            kwargs["storage_uri"] = redis_url
            logger.info("Rate limiter using Redis backend: %s", redis_url)
        else:
            logger.warning(
                "PRODUCTION environment but REDIS_URL not properly configured. "
                "Rate limiter will use in-memory storage (state lost on restart)."
            )

    # v1.27 安全加固: 开发/测试环境也启用限流（更宽松），以便发现集成问题
    # 生产环境: 60/minute
    # 开发/测试环境: 600/minute（仅用于本地开发，不影响生产行为）
    if app_env == "production":
        default_limits = ["60/minute"]
    else:
        default_limits = ["600/minute"]
        if app_env in ("development", "test"):
            logger.info(
                "Rate limiter enabled in %s mode with relaxed limits (600/min). "
                "Production uses 60/min.", app_env,
            )

    limiter = Limiter(key_func=get_remote_address, default_limits=default_limits, **kwargs)
    # v1.27: 限流始终启用（不再仅在生产环境），但 dev/test 有更宽松的限制
    limiter.enabled = True
    return limiter


limiter = _build_limiter()


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=429,
        content={"code": 429, "message": "请求过于频繁，请稍后再试", "data": None},
    )


def install_rate_limiter(app) -> None:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
