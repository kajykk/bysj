from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

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
        # STAB-P1-001: 统一响应体为 {code, message, data, error} 结构
        # 顶层 code/message/data 与成功响应对齐, error 承载结构化错误详情
        return {
            "code": self.status_code,
            "message": self.message,
            "data": None,
            "error": {
                "code": self.code,
                "message": self.message,
                "status_code": self.status_code,
                "layer": self.layer,
                "fallback_to": self.fallback_to,
                "timestamp": self.timestamp,
                "request_id": self.request_id,
                "details": self.details,
            },
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
    async def _app_exception_handler(
        request: Request, exc: AppException
    ) -> JSONResponse:
        # M-04 修复：复用中间件设置的 request_id，保持全链路追踪一致
        req_id = getattr(request.state, "request_id", None) or exc.request_id
        logger.error(
            "AppException: %s | request_id=%s | layer=%s | fallback_to=%s",
            exc.code,
            req_id,
            exc.layer,
            exc.fallback_to,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
        )

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        # P1-INFRA-044 修复：复用中间件设置的 request_id，保持全链路一致
        # STAB-P1-001: 统一响应体为 {code, message, data, error} 结构
        req_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
        message = str(exc.detail)
        # CONTRACT 修复: 保留 exc.headers (如 405 响应的 Allow header, RFC 9110 要求)
        headers = getattr(exc, "headers", None)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.status_code,
                "message": message,
                "data": None,
                "error": {
                    "code": f"HTTP_{exc.status_code}",
                    "message": message,
                    "status_code": exc.status_code,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "request_id": req_id,
                },
            },
            headers=headers,
        )

    # CONTRACT 修复: 同时注册 Starlette 的 HTTPException handler.
    # FastAPI routing 层在 body parsing 失败时抛出 starlette.exceptions.HTTPException
    # (而非 fastapi.HTTPException), 默认会走 Starlette 的 http_exception_handler
    # 返回 {"detail": "..."} 结构, 与 OpenAPI spec 中声明的 ErrorResponse 不符.
    # 注册同一个 _http_exception_handler 确保 body parsing error 也返回统一 ErrorResponse.
    @app.exception_handler(StarletteHTTPException)
    async def _starlette_http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return await _http_exception_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # P1-INFRA-045 修复：复用 request.state.request_id
        req_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
        # H-Core-8 修复：将 settings 导入与环境判断移到循环外，避免每个错误重复导入与比较
        from app.core.config import settings

        is_production = settings.app_env.lower() == "production"
        errors = exc.errors()
        serializable_errors: list[dict[str, Any]] = []
        for err in errors:
            ser_err = dict(err)
            if "ctx" in ser_err and "error" in ser_err["ctx"]:
                ser_err["ctx"]["error"] = str(ser_err["ctx"]["error"])
            # P1-SEC-020 修复：生产环境移除输入值（input 字段），防止信息泄露
            if is_production:
                ser_err.pop("input", None)
                ser_err.pop("url", None)
            serializable_errors.append(ser_err)

        return JSONResponse(
            status_code=422,
            content={
                # STAB-P1-001: 统一响应体为 {code, message, data, error} 结构
                "code": 422,
                "message": "请求参数校验失败",
                "data": None,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "请求参数校验失败",
                    "status_code": 422,
                    "details": {"errors": serializable_errors},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "request_id": req_id,
                },
            },
        )

    # STAB-P2-001: DB 异常分类处理
    # IntegrityError → 409 Conflict (唯一约束/外键约束/检查约束冲突)
    @app.exception_handler(IntegrityError)
    async def _integrity_error_handler(
        request: Request, exc: IntegrityError
    ) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
        logger.warning(
            "IntegrityError: request_id=%s | orig=%s",
            req_id,
            exc.orig,
        )
        from app.core.config import settings

        is_production = settings.app_env.lower() == "production"
        error_data: dict[str, Any] = {
            "code": "INTEGRITY_ERROR",
            "message": "数据冲突，请检查唯一性约束或关联关系",
            "status_code": 409,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": req_id,
        }
        if not is_production:
            error_data["detail"] = str(exc.orig) if exc.orig else str(exc)
        return JSONResponse(
            status_code=409,
            content={
                "code": 409,
                "message": "数据冲突，请检查唯一性约束或关联关系",
                "data": None,
                "error": error_data,
            },
        )

    # STAB-P2-001: OperationalError → 503 Service Unavailable (连接错误/超时/数据库不可用)
    @app.exception_handler(OperationalError)
    async def _operational_error_handler(
        request: Request, exc: OperationalError
    ) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
        logger.error(
            "OperationalError: request_id=%s | orig=%s",
            req_id,
            exc.orig,
        )
        from app.core.config import settings

        is_production = settings.app_env.lower() == "production"
        error_data: dict[str, Any] = {
            "code": "DB_OPERATIONAL_ERROR",
            "message": "数据库暂时不可用，请稍后重试",
            "status_code": 503,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": req_id,
        }
        if not is_production:
            error_data["detail"] = str(exc.orig) if exc.orig else str(exc)
        return JSONResponse(
            status_code=503,
            content={
                "code": 503,
                "message": "数据库暂时不可用，请稍后重试",
                "data": None,
                "error": error_data,
            },
        )

    @app.exception_handler(Exception)
    async def _generic_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
        logger.exception("Unhandled exception: request_id=%s", request_id)
        # L-Core-3 修复：开发环境返回更多调试信息便于定位问题，生产环境保持笼统消息避免信息泄露
        from app.core.config import settings

        is_production = settings.app_env.lower() == "production"
        error_data: dict[str, Any] = {
            "code": "INTERNAL_ERROR",
            "message": "服务器内部错误，请稍后重试",
            "status_code": 500,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
        }
        if not is_production:
            # 开发环境附加异常类型和详情，便于快速定位问题
            error_data["detail"] = str(exc)
            error_data["exception_type"] = type(exc).__name__
        return JSONResponse(
            status_code=500,
            content={
                # STAB-P1-001: 统一响应体为 {code, message, data, error} 结构
                "code": 500,
                "message": "服务器内部错误，请稍后重试",
                "data": None,
                "error": error_data,
            },
        )
