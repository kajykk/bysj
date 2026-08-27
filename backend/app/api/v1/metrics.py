"""Prometheus metrics and query endpoints."""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import PlainTextResponse

from app.api.v1.metrics_helpers import (
    build_prometheus_query_result,
    collect_prometheus_metrics,
)
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
    slo_availability_ratio,
    slo_error_budget_burn_rate,
    slo_error_budget_remaining_ratio,
    slo_p99_latency_seconds,
    slo_p99_model_latency_seconds,
    smtp_circuit_failure_count,
    smtp_circuit_state,
)
from app.schemas.metrics_query import PrometheusQueryResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["metrics"])
_DEV_METRICS_TOKEN = "dev-only-metrics-token"


def _require_metrics_token(authorization: str | None) -> None:
    expected_token = settings.metrics_access_token
    if not expected_token:
        if settings.app_env.lower() == "production":
            raise HTTPException(
                status_code=503,
                detail="Metrics disabled: METRICS_ACCESS_TOKEN not configured",
            )
        expected_token = _DEV_METRICS_TOKEN
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized: missing bearer token")
    provided = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(provided, expected_token):
        raise HTTPException(status_code=403, detail="Forbidden: invalid metrics token")


def _set_breaker_metrics() -> None:
    breaker_specs = (
        ("db", "app.core.db_breaker", db_circuit_failure_count, db_circuit_state),
        ("ml", "app.core.ml_breaker", ml_circuit_failure_count, ml_circuit_state),
        ("smtp", "app.core.smtp_breaker", smtp_circuit_failure_count, smtp_circuit_state),
        ("celery", "app.core.celery_breaker", celery_circuit_failure_count, celery_circuit_state),
    )
    for name, module_name, failure_metric, state_metric in breaker_specs:
        try:
            module = __import__(module_name, fromlist=[f"{name}_breaker"])
            breaker = getattr(module, f"{name}_breaker")
            snapshot = breaker.get_state_snapshot()
            failure_metric.set(float(snapshot.get("failure_count", 0)))
            state_metric.set({"closed": 0, "half_open": 1, "open": 2}.get(snapshot.get("state"), 0))
        except Exception as exc:
            logger.warning("%s circuit metric collection failed: %s", name, exc)


def _set_db_pool_metrics() -> None:
    try:
        from app.core.database import engine

        pool = engine.pool
        db_pool_size.set(float(pool.size()))
        pool_max = getattr(pool, "maxsize", 0) or 1
        db_pool_utilization.set(min(pool.size() / pool_max, 1.0))
    except Exception as exc:
        logger.warning("db_pool_size metric collection failed: %s", exc)


def _set_redis_metrics() -> None:
    try:
        import redis

        client = redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        redis_circuit_state.set(0)
    except Exception:
        redis_circuit_state.set(2)


def _set_model_fallback_metric() -> None:
    try:
        from app.core.model_engine import model_engine

        snapshot = model_engine.get_metrics_snapshot()
        model_fallback_rate.set(float(snapshot.get("monitoring", {}).get("fallback_ratio", 0)))
    except Exception as exc:
        logger.warning("model_fallback_rate metric collection failed: %s", exc)


async def _set_mttr_metrics() -> None:
    try:
        from app.core.database import AsyncSessionLocal
        from app.services.mttr_service import mttr_service

        async with AsyncSessionLocal() as session:
            stats = await mttr_service.compute_mttr(session, window_hours=24)
        if stats.severity_breakdown:
            for severity, bucket in stats.severity_breakdown.items():
                alert_mttr_seconds.set(float(bucket["mttr_seconds"]), severity=severity)
        else:
            for severity in ("critical", "warning", "info"):
                alert_mttr_seconds.set(0.0, severity=severity)
        alert_resolved_total.set(float(stats.resolved_count))
        alert_unresolved_count.set(float(stats.unresolved_count))
    except Exception as exc:
        logger.warning("mttr metric collection failed: %s", exc)


def _set_slo_metrics() -> None:
    try:
        from app.core.slo import compute_sli

        sli = compute_sli()
        slo_availability_ratio.set(float(sli.availability))
        if sli.p99_latency_seconds is not None:
            slo_p99_latency_seconds.set(float(sli.p99_latency_seconds))
        if sli.p99_model_latency_seconds is not None:
            slo_p99_model_latency_seconds.set(float(sli.p99_model_latency_seconds))
        slo_error_budget_remaining_ratio.set(float(sli.error_budget_remaining_ratio))
        slo_error_budget_burn_rate.set(float(sli.error_budget_burn_rate))
    except Exception as exc:
        logger.warning("slo metric collection failed: %s", exc)


async def _collect_metrics() -> None:
    _set_db_pool_metrics()
    _set_breaker_metrics()
    _set_redis_metrics()
    _set_model_fallback_metric()
    await _set_mttr_metrics()
    _set_slo_metrics()
    await collect_prometheus_metrics()


@router.get("/metrics", response_class=PlainTextResponse)
async def get_metrics(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> PlainTextResponse:
    """Return Prometheus exposition data after collecting current snapshots.

    The collection includes db_breaker, ml_breaker, smtp_breaker, and
    celery_breaker state through the shared breaker collector, including
    smtp_circuit_failure_count, smtp_circuit_state, celery_circuit_failure_count,
    and celery_circuit_state.
    """
    _require_metrics_token(authorization)
    await _collect_metrics()
    return PlainTextResponse(
        content=render_exposition(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get("/query", response_model=PrometheusQueryResponse)
async def prometheus_query(
    query: str = "",
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    """Return a small Prometheus HTTP API-compatible vector response."""
    _require_metrics_token(authorization)
    await collect_prometheus_metrics()
    return build_prometheus_query_result(query, render_exposition())
