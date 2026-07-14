"""STAB-P2-009: OpenTelemetry SDK + OTLP 分布式追踪.

初始化 OpenTelemetry SDK, 通过 OTLP 协议导出 trace 到外部 collector.
支持自动 instrumentation:
- FastAPI: HTTP 请求追踪
- SQLAlchemy: DB 查询追踪
- Redis: 缓存操作追踪 (如果可用)

配置项 (app/core/config.py):
- otel_enabled: 是否启用 (默认 False)
- otlp_endpoint: OTLP collector 端点 (如 "http://localhost:4317")
- otlp_protocol: 协议 ("grpc" 或 "http/protobuf")
- otel_service_name: 服务名 (默认 "mindcare-backend")

优雅降级: opentelemetry 库未安装时记录 warning 并跳过, 不影响应用启动.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_otel_initialized = False


def _check_otel_available() -> bool:
    """检查 OpenTelemetry SDK 是否可用."""
    try:
        import opentelemetry  # noqa: F401

        return True
    except ImportError:
        return False


def init_otel(
    service_name: str,
    service_version: str = "",
    otlp_endpoint: str = "",
    otlp_protocol: str = "grpc",
    environment: str = "",
) -> bool:
    """STAB-P2-009: 初始化 OpenTelemetry SDK + OTLP exporter.

    Args:
        service_name: 服务名 (如 "mindcare-backend").
        service_version: 服务版本 (如 "1.0.0").
        otlp_endpoint: OTLP collector 端点 (如 "http://localhost:4317").
        otlp_protocol: 协议 ("grpc" 或 "http/protobuf").
        environment: 部署环境 (如 "production").

    Returns:
        True if initialized successfully, False if skipped or failed.
    """
    global _otel_initialized

    if _otel_initialized:
        logger.debug("STAB-P2-009: OpenTelemetry already initialized, skipping")
        return True

    if not _check_otel_available():
        logger.warning(
            "STAB-P2-009: opentelemetry packages not installed, "
            "distributed tracing disabled. Install with: "
            "pip install opentelemetry-distro opentelemetry-exporter-otlp"
        )
        return False

    if not otlp_endpoint:
        logger.info(
            "STAB-P2-009: OTLP endpoint not configured, "
            "distributed tracing disabled"
        )
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter as GRPCExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        # 构建资源属性
        resource_attrs: dict[str, Any] = {
            "service.name": service_name,
        }
        if service_version:
            resource_attrs["service.version"] = service_version
        if environment:
            resource_attrs["deployment.environment"] = environment

        resource = Resource.create(resource_attrs)

        # 创建 TracerProvider
        provider = TracerProvider(resource=resource)

        # 配置 OTLP exporter
        if otlp_protocol == "http/protobuf":
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter as HTTPExporter,
            )

            exporter = HTTPExporter(endpoint=otlp_endpoint)
        else:
            exporter = GRPCExporter(endpoint=otlp_endpoint, insecure=True)

        # 配置 BatchSpanProcessor (批量导出, 减少网络开销)
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(provider=processor)

        # 设置全局 TracerProvider
        trace.set_tracer_provider(provider)

        _otel_initialized = True
        logger.info(
            "STAB-P2-009: OpenTelemetry initialized, service=%s, endpoint=%s, protocol=%s",
            service_name,
            otlp_endpoint,
            otlp_protocol,
        )

        # 自动 instrumentation
        _instrument_fastapi()
        _instrument_sqlalchemy()
        _instrument_redis()

        return True

    except Exception as exc:
        logger.warning(
            "STAB-P2-009: OpenTelemetry initialization failed, "
            "tracing disabled: %s",
            exc,
            exc_info=True,
        )
        return False


def _instrument_fastapi() -> None:
    """STAB-P2-009: 自动追踪 FastAPI HTTP 请求."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # noqa: F401

        # FastAPIInstrumentor.instrument_app 需要在 app 创建后调用
        # 这里仅标记可用的 instrumentation, 实际调用在 main.py 中
        logger.debug("STAB-P2-009: FastAPI instrumentation available")
    except ImportError:
        logger.debug(
            "STAB-P2-009: opentelemetry-instrumentation-fastapi not installed, "
            "HTTP request tracing disabled"
        )


def _instrument_sqlalchemy() -> None:
    """STAB-P2-009: 自动追踪 SQLAlchemy DB 查询."""
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor  # noqa: F401

        # 在 engine 创建后调用 instrument_engine
        # 这里仅标记可用的 instrumentation, 实际调用在 main.py 中
        logger.debug("STAB-P2-009: SQLAlchemy instrumentation available")
    except ImportError:
        logger.debug(
            "STAB-P2-009: opentelemetry-instrumentation-sqlalchemy not installed, "
            "DB query tracing disabled"
        )


def _instrument_redis() -> None:
    """STAB-P2-009: 自动追踪 Redis 操作."""
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()
        logger.debug("STAB-P2-009: Redis instrumentation enabled")
    except ImportError:
        logger.debug(
            "STAB-P2-009: opentelemetry-instrumentation-redis not installed, "
            "Redis tracing disabled"
        )


def instrument_app(app: Any) -> None:
    """STAB-P2-009: 对 FastAPI 应用启用自动 instrumentation.

    在 app 创建后调用 (main.py 中).

    Args:
        app: FastAPI 应用实例.
    """
    if not _otel_initialized:
        return

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        logger.debug("STAB-P2-009: FastAPI app instrumented")
    except ImportError:
        pass
    except Exception as exc:
        logger.warning(
            "STAB-P2-009: FastAPI instrumentation failed: %s", exc, exc_info=True
        )


def shutdown_otel() -> None:
    """STAB-P2-009: 关闭 OpenTelemetry, 刷新待导出的 span.

    在应用关闭时调用 (lifespan finally 块).
    """
    global _otel_initialized

    if not _otel_initialized:
        return

    try:
        from opentelemetry import trace

        provider = trace.get_tracer_provider()
        if hasattr(provider, "shutdown"):
            provider.shutdown()
            logger.debug("STAB-P2-009: OpenTelemetry shutdown complete")
    except Exception as exc:
        logger.warning("STAB-P2-009: OpenTelemetry shutdown failed: %s", exc)

    _otel_initialized = False
