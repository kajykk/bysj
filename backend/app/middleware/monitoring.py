"""Monitoring middleware for performance and error tracking."""

# DEPRECATED: 此中间件未被使用，功能已迁移到 app.core.middlewares
# 保留用于参考，不应在新代码中导入

import logging
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class MonitoringMiddleware(BaseHTTPMiddleware):
    """Middleware for monitoring request performance and errors."""

    def __init__(self, app, slow_request_threshold: float = 2.0):
        super().__init__(app)
        self.slow_request_threshold = slow_request_threshold

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        request_id = getattr(request.state, "request_id", None)
        
        try:
            response = await call_next(request)
            
            # Calculate request duration
            duration = time.time() - start_time
            
            # Add performance headers
            response.headers["X-Response-Time"] = f"{duration:.3f}s"
            if request_id:
                response.headers["X-Request-ID"] = request_id
            
            # Log slow requests
            if duration > self.slow_request_threshold:
                await self._log_slow_request(request, response, duration, request_id)
            
            return response
            
        except Exception as exc:
            duration = time.time() - start_time
            await self._log_error(request, exc, duration, request_id)
            raise

    async def _log_slow_request(self, request: Request, response: Response, duration: float, request_id: str | None = None):
        """Log slow request warning."""
        extra = {"request_id": request_id} if request_id else {}
        logger.warning(
            f"Slow request: {request.method} {request.url.path} "
            f"took {duration:.3f}s (threshold: {self.slow_request_threshold}s)",
            extra=extra,
        )

    async def _log_error(self, request: Request, exc: Exception, duration: float, request_id: str | None = None):
        """Log request error."""
        extra = {"request_id": request_id} if request_id else {}
        logger.error(
            f"Request error: {request.method} {request.url.path} "
            f"failed after {duration:.3f}s: {str(exc)}",
            extra=extra,
        )
