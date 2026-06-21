from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppException(Exception):
    """Base application exception with structured error info.

    Attributes:
        code: Error code string (e.g., 'MODEL_LOAD_FAILED')
        message: Human-readable error message
        status_code: HTTP status code
        details: Additional error details
        layer: System layer where error occurred
        fallback_to: Fallback layer used (if any)
    """

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 500,
        details: dict[str, Any] | None = None,
        layer: str | None = None,
        fallback_to: str | None = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.layer = layer
        self.fallback_to = fallback_to
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.request_id = str(uuid.uuid4())
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "status_code": self.status_code,
                "layer": self.layer,
                "fallback_to": self.fallback_to,
                "timestamp": self.timestamp,
                "request_id": self.request_id,
                "details": self.details,
            }
        }


class ModelException(AppException):
    """Exception for model-related errors."""

    def __init__(self, code: str, message: str, **kwargs: Any):
        super().__init__(
            code=code,
            message=message,
            status_code=kwargs.get("status_code", 500),
            layer=kwargs.get("layer", "MODEL"),
            fallback_to=kwargs.get("fallback_to"),
            details=kwargs.get("details"),
        )


class ValidationException(AppException):
    """Exception for input validation errors."""

    def __init__(self, code: str, message: str, **kwargs: Any):
        super().__init__(
            code=code,
            message=message,
            status_code=kwargs.get("status_code", 422),
            layer=kwargs.get("layer", "VALIDATION"),
            details=kwargs.get("details"),
        )


class ServiceException(AppException):
    """Exception for service-layer errors."""

    def __init__(self, code: str, message: str, **kwargs: Any):
        super().__init__(
            code=code,
            message=message,
            status_code=kwargs.get("status_code", 500),
            layer=kwargs.get("layer", "SERVICE"),
            fallback_to=kwargs.get("fallback_to"),
            details=kwargs.get("details"),
        )


def install_exception_handlers(app: FastAPI) -> None:
    """Install unified exception handlers for FastAPI app."""

    @app.exception_handler(AppException)
    async def _app_exception_handler(_: Request, exc: AppException) -> JSONResponse:
        logger.error(
            "AppException: %s | request_id=%s | layer=%s | fallback_to=%s",
            exc.code,
            exc.request_id,
            exc.layer,
            exc.fallback_to,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
        )

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        # P1-INFRA-044 修复：复用中间件设置的 request_id，保持全链路一致
        req_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": f"HTTP_{exc.status_code}",
                    "message": str(exc.detail),
                    "status_code": exc.status_code,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "request_id": req_id,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # P1-INFRA-045 修复：复用 request.state.request_id
        req_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
        errors = exc.errors()
        serializable_errors: list[dict[str, Any]] = []
        for err in errors:
            ser_err = dict(err)
            if "ctx" in ser_err and "error" in ser_err["ctx"]:
                ser_err["ctx"]["error"] = str(ser_err["ctx"]["error"])
            # P1-SEC-020 修复：生产环境移除输入值（input 字段），防止信息泄露
            from app.core.config import settings
            if settings.app_env.lower() == "production":
                ser_err.pop("input", None)
                ser_err.pop("url", None)
            serializable_errors.append(ser_err)

        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "请求参数校验失败",
                    "status_code": 422,
                    "details": {"errors": serializable_errors},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "request_id": req_id,
                }
            },
        )

    @app.exception_handler(Exception)
    async def _generic_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        request_id = str(uuid.uuid4())
        logger.exception("Unhandled exception: request_id=%s", request_id)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "服务器内部错误，请稍后重试",
                    "status_code": 500,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "request_id": request_id,
                }
            },
        )
