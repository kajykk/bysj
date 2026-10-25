"""STAB-P2-009: OpenTelemetry SDK + OTLP 分布式追踪.

初始化 OpenTelemetry SDK, 通过 OTLP 协议导出 trace 到外部 collector.
支持自动 instrumentation:
- FastAPI: HTTP 请求追踪
- SQLAlchemy: DB 查询追踪
- Redis: 缓存操作追踪 (如果可用)

配置项 (app/core/config.py):
- otel_enabled: 是否启用 (默认 False；ROUND_42 起为真开关)
- otlp_endpoint: OTLP collector 端点 (如 "http://localhost:4317")
- otlp_protocol: 协议 ("grpc" 或 "http/protobuf")
- otel_service_name: 服务名 (默认 "mindcare-backend")
- otel_resource_attributes: 附加资源属性 ("key1=value1,key2=value2")

ROUND_42: otel_enabled 是真正的开关 —— 默认 False 时在装配前直接跳过，
仅配置 otlp_endpoint 而不打开开关不再启用追踪（行为变更，见 CHANGELOG）。
资源属性中的畸形项（缺 "="、空 key）逐项跳过并 debug 留痕，不影响装配。

优雅降级: opentelemetry 库未安装时记录 warning 并跳过, 不影响应用启动.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class OtelInit(Enum):
    """init_otel 的三态结果：成功 / 未启用（跳过） / 已配置但初始化失败。"""

    OK = "ok"
    SKIPPED = "skipped"
    FAILED = "failed"


_otel_initialized = False


def _check_otel_available() -> bool:
    """检查 OpenTelemetry SDK 是否可用."""
    try:
        import opentelemetry  # noqa: F401

        return True
    except ImportError:
        return False


def _parse_resource_attributes(raw: str) -> dict[str, str]:
    """解析 "key1=value1,key2=value2" 形式的附加资源属性.

    逐项解析：空片段忽略；缺 "=" 或 key 为空的畸形项跳过并 debug 留痕。
    本函数对任意字符串输入都返回 dict —— 属性配置问题不得让整条装配失败。
    """
    attrs: dict[str, str] = {}
    for item in (raw or "").split(","):
        item = item.strip()
        if not item:
            continue
        key, sep, value = item.partition("=")
        key = key.strip()
        if not sep or not key:
            logger.debug(
                "STAB-P2-009: ignoring malformed resource attribute %r", item
            )
            continue
        attrs[key] = value.strip()
    return attrs


def init_otel(
    service_name: str,
    service_version: str = "",
    otlp_endpoint: str = "",
    otlp_protocol: str = "grpc",
    environment: str = "",
    enabled: bool = True,
    resource_attributes: str = "",
) -> OtelInit:
    """STAB-P2-009: 初始化 OpenTelemetry SDK + OTLP exporter.

    Args:
        service_name: 服务名 (如 "mindcare-backend").
        service_version: 服务版本 (如 "1.0.0").
        otlp_endpoint: OTLP collector 端点 (如 "http://localhost:4317").
        otlp_protocol: 协议 ("grpc" 或 "http/protobuf").
        environment: 部署环境 (如 "production").
        enabled: 配置开关（对应 otel_enabled）。False 时在依赖探测与装配前
            直接跳过。默认 True 保持库级直接调用的既有行为。
        resource_attributes: 附加资源属性 ("key1=value1,key2=value2")，
            畸形项跳过并 debug 留痕。

    Returns:
        OtelInit.OK: 初始化成功（已初始化时的幂等调用同样返回 OK）。
        OtelInit.SKIPPED: 未启用 —— ``enabled`` 为 False、顶层
            ``opentelemetry`` 不可导入，或 ``otlp_endpoint`` 未配置。
            属正常降级，调用方应记 skipped。
        OtelInit.FAILED: 已配置 endpoint 但装配过程抛异常。属初始化失败，
            调用方应记 failed（非致命，不阻断启动）。

    Note:
        失败 / 跳过路径不会置 ``_otel_initialized=True``。``enabled=False``
        是硬否决：即使本次调用前已存在初始化标记，也按配置返回 SKIPPED。
    """
    global _otel_initialized

    if not enabled:
        logger.info(
            "STAB-P2-009: OpenTelemetry disabled by configuration "
            "(otel_enabled=False)"
        )
        return OtelInit.SKIPPED

    if _otel_initialized:
        logger.debug("STAB-P2-009: OpenTelemetry already initialized, skipping")
        return OtelInit.OK

    if not _check_otel_available():
        logger.warning(
            "STAB-P2-009: opentelemetry packages not installed, "
            "distributed tracing disabled. Install with: "
            "pip install opentelemetry-distro opentelemetry-exporter-otlp"
        )
        return OtelInit.SKIPPED

    if not otlp_endpoint:
        logger.info(
            "STAB-P2-009: OTLP endpoint not configured, "
            "distributed tracing disabled"
        )
        return OtelInit.SKIPPED

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
        resource_attrs.update(_parse_resource_attributes(resource_attributes))

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

        return OtelInit.OK

    except Exception as exc:
        logger.warning(
            "STAB-P2-009: OpenTelemetry initialization failed, "
            "tracing disabled: %s",
            exc,
            exc_info=True,
        )
        return OtelInit.FAILED


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
