"""Prometheus /metrics 端点 (v1.30)

提供 HTTP API `/api/v1/metrics`, 以 Prometheus exposition format 输出系统指标。

CRIT-007 修复：添加访问令牌鉴权，防止未授权访问系统内部指标。
"""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.core.metrics import (
    alert_mttr_seconds,
    alert_resolved_total,
    alert_unresolved_count,
    celery_circuit_failure_count,
    celery_circuit_state,
    db_circuit_failure_count,
    db_circuit_state,
    db_pool_size,
    db_pool_utilization,
    ml_circuit_failure_count,
    ml_circuit_state,
    model_fallback_rate,
    redis_circuit_state,
    render_exposition,
    smtp_circuit_failure_count,
    smtp_circuit_state,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_class=PlainTextResponse)
async def get_metrics(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> PlainTextResponse:
    """Prometheus exposition 端点.

    CRIT-007 修复：添加访问令牌鉴权。
    生产环境必须配置 METRICS_ACCESS_TOKEN，Prometheus 需在
    Authorization header 中发送 "Bearer <token>"。

    包含:
    - http_requests_total{method,path,status}
    - http_request_duration_seconds{method,path}
    - model_inference_total{model_name,status}
    - model_inference_duration_seconds{model_name}
    - websocket_connections_active
    - db_pool_size
    - app_info
    """
    # CRIT-007 修复：Metrics 端点鉴权
    expected_token = settings.metrics_access_token
    if not expected_token:
        if settings.app_env.lower() == "production":
            # 生产环境且未配置令牌：拒绝访问
            raise HTTPException(
                status_code=503,
                detail="Metrics disabled: METRICS_ACCESS_TOKEN not configured",
            )
        # C-API-2 修复：非生产环境使用默认 dev token，不再完全开放。
        # 原实现开发环境完全开放，泄露 http_requests_total{path}、db_pool_size、
        # model_inference_total 等内部运行时指标，暴露 API 表面和基础设施拓扑。
        expected_token = "dev-only-metrics-token"
    # 所有环境统一鉴权校验
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Unauthorized: missing bearer token"
        )
    provided = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(provided, expected_token):
        raise HTTPException(status_code=403, detail="Forbidden: invalid metrics token")

    # 抓取 DB 连接池状态 (如果有)
    try:
        from app.core.database import engine

        pool = engine.pool
        db_pool_size.set(float(pool.size()))
        # STAB-P1-015: 暴露连接池使用率, 触发 AR-103 告警
        pool_max = getattr(pool, "maxsize", 0) or 1
        db_pool_utilization.set(min(pool.size() / pool_max, 1.0))
    except Exception as exc:
        # P1-E 修复：监控指标采集失败必须记录日志，便于运维发现 DB 连接池监控失效
        logger.warning("db_pool_size metric collection failed: %s", exc)

    # STAB-P1-015: 暴露 DB 熔断器状态, 触发 AR-201 告警
    try:
        from app.core.db_breaker import db_breaker

        snapshot = db_breaker.get_state_snapshot()
        db_circuit_failure_count.set(float(snapshot.get("failure_count", 0)))
        state = snapshot.get("state")
        # 0=closed, 1=half_open, 2=open
        state_value = {"closed": 0, "half_open": 1, "open": 2}.get(state, 0)
        db_circuit_state.set(state_value)
    except Exception as exc:
        logger.warning("db_circuit metric collection failed: %s", exc)

    # STAB-P1-002: 暴露 ML 推理熔断器状态
    try:
        from app.core.ml_breaker import ml_breaker

        snapshot = ml_breaker.get_state_snapshot()
        ml_circuit_failure_count.set(float(snapshot.get("failure_count", 0)))
        state = snapshot.get("state")
        state_value = {"closed": 0, "half_open": 1, "open": 2}.get(state, 0)
        ml_circuit_state.set(state_value)
    except Exception as exc:
        logger.warning("ml_circuit metric collection failed: %s", exc)

    # STAB-P1-004: 暴露 SMTP 邮件熔断器状态
    try:
        from app.core.smtp_breaker import smtp_breaker

        snapshot = smtp_breaker.get_state_snapshot()
        smtp_circuit_failure_count.set(float(snapshot.get("failure_count", 0)))
        state = snapshot.get("state")
        state_value = {"closed": 0, "half_open": 1, "open": 2}.get(state, 0)
        smtp_circuit_state.set(state_value)
    except Exception as exc:
        logger.warning("smtp_circuit metric collection failed: %s", exc)

    # STAB-P1-005: 暴露 Celery broker 熔断器状态
    try:
        from app.core.celery_breaker import celery_breaker

        snapshot = celery_breaker.get_state_snapshot()
        celery_circuit_failure_count.set(float(snapshot.get("failure_count", 0)))
        state = snapshot.get("state")
        state_value = {"closed": 0, "half_open": 1, "open": 2}.get(state, 0)
        celery_circuit_state.set(state_value)
    except Exception as exc:
        logger.warning("celery_circuit metric collection failed: %s", exc)

    # STAB-P1-016: 暴露 Redis 熔断状态, 触发 AR-202 告警
    # 本系统 Redis 仅有降级 (无熔断器), 通过检测 Redis 连通性推断状态
    try:
        import redis

        client = redis.from_url(
            settings.redis_url, socket_connect_timeout=1, socket_timeout=1
        )
        client.ping()
        redis_circuit_state.set(0)  # closed
    except Exception:
        redis_circuit_state.set(2)  # open (不可用)

    # STAB-P1-017: 暴露模型 fallback 率, 触发 AR-203 告警
    try:
        from app.core.model_engine import model_engine

        snapshot = model_engine.get_metrics_snapshot()
        monitoring = snapshot.get("monitoring", {})
        fallback_ratio = monitoring.get("fallback_ratio", 0)
        model_fallback_rate.set(float(fallback_ratio))
    except Exception as exc:
        logger.warning("model_fallback_rate metric collection failed: %s", exc)

    # STAB-P1-008: 暴露 MTTR 指标, 触发 AR-206/AR-207 告警
    try:
        from app.core.database import AsyncSessionLocal
        from app.services.mttr_service import mttr_service

        async with AsyncSessionLocal() as mttr_session:
            stats = await mttr_service.compute_mttr(mttr_session, window_hours=24)
        # 按 severity 设置 MTTR
        if stats.severity_breakdown:
            for severity, bucket in stats.severity_breakdown.items():
                alert_mttr_seconds.set(float(bucket["mttr_seconds"]), severity=severity)
        else:
            # 无数据时设置 0 (避免指标缺失)
            alert_mttr_seconds.set(0.0, severity="critical")
            alert_mttr_seconds.set(0.0, severity="warning")
            alert_mttr_seconds.set(0.0, severity="info")
        alert_resolved_total.set(float(stats.resolved_count))
        alert_unresolved_count.set(float(stats.unresolved_count))
    except Exception as exc:
        logger.warning("mttr metric collection failed: %s", exc)

    body = render_exposition()
    return PlainTextResponse(
        content=body, media_type="text/plain; version=0.0.4; charset=utf-8"
    )
