from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import _is_sqlite, get_db
from app.core.deps import require_permission
from app.core.model_engine import model_engine as engine
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.rate_limit import limiter
from app.core.response import ok
from app.models.monitoring import DriftAlert, MonitoringEventType, MonitoringLog
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.monitoring import (
    DashboardSummaryResponse,
    DriftAlertListResponse,
    FallbackStatsResponse,
    FrontendMetricsPayload,
    ModelSuccessRateResponse,
    RequestDetailsResponse,
)
from app.services.observability_service import observability_collector

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/monitoring", tags=["monitoring"])

# P3-2: 前端 Web Vitals 上报负载大小上限 (16KB)
_MAX_FRONTEND_METRICS_SIZE = 16 * 1024


def _time_bucket_expr(granularity: str):
    """H-07 修复：跨数据库兼容的时间分桶表达式.

    PostgreSQL 使用 ``to_char`` (生产环境)，SQLite 使用 ``strftime`` (测试环境)。
    两者返回的字符串格式保持一致，确保下游聚合结果可移植。
    """
    if _is_sqlite:
        fmt_map = {
            "hour": "%Y-%m-%d %H:00",
            "day": "%Y-%m-%d",
            "week": "%Y-W%W",
        }
        fmt = fmt_map.get(granularity, fmt_map["day"])
        return func.strftime(fmt, MonitoringLog.created_at).label("time_bucket")
    fmt_map = {
        "hour": "YYYY-MM-DD HH24:00",
        "day": "YYYY-MM-DD",
        "week": "IYYY-IW",
    }
    fmt = fmt_map.get(granularity, fmt_map["day"])
    return func.to_char(MonitoringLog.created_at, fmt).label("time_bucket")


@router.get(
    "/model-success-rate", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
async def model_success_rate(
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    granularity: Annotated[str, Query(description="时间粒度: hour, day, week")] = "day",
    model_version: Annotated[str | None, Query(description="模型版本过滤")] = None,
) -> dict:
    """Get model success rate over time."""
    now = datetime.now(timezone.utc)
    if granularity == "hour":
        start_time = now - timedelta(hours=24)
    elif granularity == "day":
        start_time = now - timedelta(days=30)
    elif granularity == "week":
        start_time = now - timedelta(weeks=12)
    else:
        start_time = now - timedelta(days=30)
    # H-07 修复：跨数据库兼容的时间分桶表达式（SQLite/PostgreSQL）
    time_expr = _time_bucket_expr(granularity)

    # H-07 修复：使用 SQL GROUP BY 聚合，避免加载原始记录到内存
    # 使用 PostgreSQL FILTER 子句统计 success/fallback
    total_expr = func.count().label("total")
    success_expr = (
        func.count().filter(MonitoringLog.fallback_reason.is_(None)).label("success")
    )
    fallback_expr = (
        func.count().filter(MonitoringLog.fallback_reason.isnot(None)).label("fallback")
    )

    stmt = (
        select(
            time_expr,
            total_expr,
            success_expr,
            fallback_expr,
        )
        .where(
            MonitoringLog.event_type == MonitoringEventType.INFERENCE,
            MonitoringLog.created_at >= start_time,
        )
        .group_by(time_expr)
        .order_by(time_expr)
    )
    if model_version:
        stmt = stmt.where(MonitoringLog.model_version == model_version)

    result = await db.execute(stmt)
    rows = result.all()

    data = [
        {
            "time_bucket": row.time_bucket,
            "total": row.total,
            "success": row.success,
            "fallback": row.fallback,
            "success_rate": round(row.success / max(1, row.total) * 100, 2),
        }
        for row in rows
    ]

    return ok(ModelSuccessRateResponse(granularity=granularity, data=data).model_dump())


@router.get(
    "/fallback-stats", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
async def fallback_stats(
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    model_version: Annotated[str | None, Query(description="模型版本过滤")] = None,
    days: Annotated[
        int, Query(ge=1, le=365, description="时间范围（天），默认30天")
    ] = 30,
) -> dict:
    """Get fallback statistics grouped by reason."""
    # P0-P1 修复：原实现无时间过滤，会加载全部 fallback 日志到内存聚合，
    # 生产环境可能导致 OOM。添加时间范围过滤（默认30天），并将聚合下推到 SQL。
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(days=days)

    # 使用 SQL GROUP BY 聚合，避免加载原始记录到内存
    fallback_reason_col = func.coalesce(MonitoringLog.fallback_reason, "unknown")
    stmt = (
        select(fallback_reason_col.label("reason"), func.count().label("count"))
        .where(
            MonitoringLog.event_type == MonitoringEventType.FALLBACK,
            MonitoringLog.created_at >= start_time,
        )
        .group_by(fallback_reason_col)
        .order_by(func.count().desc())
    )
    if model_version:
        stmt = stmt.where(MonitoringLog.model_version == model_version)

    result = await db.execute(stmt)
    rows = result.all()

    total = sum(row.count for row in rows)
    data = [
        {
            "reason": row.reason,
            "count": row.count,
            "percentage": round(row.count / max(1, total) * 100, 2),
        }
        for row in rows
    ]

    return ok(FallbackStatsResponse(total=total, reasons=data).model_dump())


@router.get(
    "/drift-alerts", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
async def drift_alerts(
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    severity: Annotated[
        str | None, Query(description="严重程度过滤: LOW, MEDIUM, HIGH, CRITICAL")
    ] = None,
    resolved: Annotated[bool | None, Query(description="是否已解决")] = None,
    model_version: Annotated[str | None, Query(description="模型版本过滤")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """Get drift alerts with filtering."""
    stmt = select(DriftAlert)

    if severity:
        stmt = stmt.where(DriftAlert.severity == severity)
    if resolved is not None:
        if resolved:
            stmt = stmt.where(DriftAlert.resolved_at.isnot(None))
        else:
            stmt = stmt.where(DriftAlert.resolved_at.is_(None))
    if model_version:
        stmt = stmt.where(DriftAlert.model_version == model_version)

    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # Get paginated results
    stmt = stmt.order_by(DriftAlert.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    alerts = result.scalars().all()

    data = [
        {
            "id": alert.id,
            "model_version": alert.model_version,
            "feature_name": alert.feature_name,
            "drift_type": alert.drift_type,
            "severity": alert.severity,
            "metric_value": alert.metric_value,
            "threshold": alert.threshold,
            "details": alert.details,
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
        }
        for alert in alerts
    ]

    return ok(
        DriftAlertListResponse(
            total=total,
            limit=limit,
            offset=offset,
            alerts=data,
        ).model_dump()
    )


@router.get(
    "/dashboard-summary", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
async def dashboard_summary(
    _: Annotated[User, Depends(require_permission("admin.dashboard.view"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Get aggregated dashboard summary data."""
    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    # Inference count (24h)
    inference_stmt = select(func.count()).where(
        MonitoringLog.event_type == MonitoringEventType.INFERENCE,
        MonitoringLog.created_at >= last_24h,
    )
    inference_result = await db.execute(inference_stmt)
    inference_count_24h = inference_result.scalar() or 0

    # Fallback count (24h)
    fallback_stmt = select(func.count()).where(
        MonitoringLog.event_type == MonitoringEventType.FALLBACK,
        MonitoringLog.created_at >= last_24h,
    )
    fallback_result = await db.execute(fallback_stmt)
    fallback_count_24h = fallback_result.scalar() or 0

    # Active drift alerts (unresolved)
    active_drift_stmt = select(func.count()).where(DriftAlert.resolved_at.is_(None))
    active_drift_result = await db.execute(active_drift_stmt)
    active_drift_count = active_drift_result.scalar() or 0

    # Drift alerts by severity (7d)
    severity_stmt = (
        select(DriftAlert.severity, func.count())
        .where(DriftAlert.created_at >= last_7d)
        .group_by(DriftAlert.severity)
    )
    severity_result = await db.execute(severity_stmt)
    severity_counts = {row[0]: row[1] for row in severity_result.all()}

    # Average latency (24h)
    latency_stmt = select(func.avg(MonitoringLog.latency_ms)).where(
        MonitoringLog.latency_ms.isnot(None),
        MonitoringLog.created_at >= last_24h,
    )
    latency_result = await db.execute(latency_stmt)
    avg_latency = round(latency_result.scalar() or 0, 2)

    # Live metrics from collector
    live_metrics = observability_collector.get_metrics_snapshot()

    data = DashboardSummaryResponse(
        inference_count_24h=inference_count_24h,
        fallback_count_24h=fallback_count_24h,
        fallback_rate=round(
            fallback_count_24h / max(1, inference_count_24h + fallback_count_24h) * 100,
            2,
        ),
        active_drift_alerts=active_drift_count,
        drift_by_severity=severity_counts,
        avg_latency_ms=avg_latency,
        live_metrics=live_metrics,
    )

    return ok(data.model_dump())


@router.get(
    "/request-details/{log_id}",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
async def request_details(
    log_id: int,
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Get detailed request information from a monitoring log."""
    result = await db.execute(select(MonitoringLog).where(MonitoringLog.id == log_id))
    log = result.scalar_one_or_none()

    if not log:
        raise HTTPException(status_code=404, detail="Log not found")

    data = RequestDetailsResponse(
        id=log.id,
        event_type=log.event_type,
        model_version=log.model_version,
        user_id=log.user_id,
        request_payload=log.request_payload,
        response_summary=log.response_summary,
        fallback_reason=log.fallback_reason,
        latency_ms=log.latency_ms,
        created_at=log.created_at.isoformat() if log.created_at else None,
    )

    return ok(data.model_dump())


@router.get(
    "/request-details", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
async def request_details_list(
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    # L-2 修复：使用 Literal 限制 event_type 为合法枚举值，避免用户传入任意字符串
    # 合法值需与 MonitoringEventType 枚举（app/models/monitoring.py）保持一致
    # 注：不使用 Annotated 包装 Literal，与 observability.py 一致，避免 from __future__ import
    # annotations 下 pydantic 解析 ForwardRef 失败
    event_type: (
        Literal[
            "inference",
            "fallback",
            "input_anomaly",
            "drift_alert",
            "model_load",
            "canary_switch",
        ]
        | None
    ) = Query(None, description="事件类型过滤"),
    model_version: Annotated[str | None, Query(description="模型版本过滤")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """Get list of request details with filtering."""
    stmt = select(MonitoringLog)

    if event_type:
        stmt = stmt.where(MonitoringLog.event_type == event_type)
    if model_version:
        stmt = stmt.where(MonitoringLog.model_version == model_version)

    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # Get paginated results
    stmt = stmt.order_by(MonitoringLog.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    logs = result.scalars().all()

    data = [
        {
            "id": log.id,
            "event_type": log.event_type,
            "model_version": log.model_version,
            "user_id": log.user_id,
            "fallback_reason": log.fallback_reason,
            "latency_ms": log.latency_ms,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]

    return ok({"total": total, "limit": limit, "offset": offset, "items": data})


@router.get(
    "/engine-snapshot", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
async def engine_metrics_snapshot(
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    snapshot = engine.get_metrics_snapshot()
    return ok(snapshot)


@router.post(
    "/frontend-metrics",
    summary="P3-2: 接收前端 Web Vitals 上报",
    status_code=204,
    response_class=Response,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("30/minute")
async def receive_frontend_metrics(request: Request) -> Response:
    """P3-2: 接收前端 usePerformanceMonitor 上报的 Core Web Vitals 指标.

    无需鉴权: Web Vitals 需从所有用户采集 (含登录页匿名用户), 通过限流防止滥用.
    存储策略: 结构化日志输出, 供日志聚合系统 (ELK/Promtail) 采集分析, 不落库.

    Returns:
        204 No Content (与 CSP report 端点一致, 无需返回 body)

    Raises:
        HTTPException: 413 payload 过大, 400 JSON 无效/字段校验失败
    """
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            cl_value = int(content_length)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid Content-Length header")
        if cl_value > _MAX_FRONTEND_METRICS_SIZE:
            raise HTTPException(status_code=413, detail="Payload too large")

    body_bytes = await request.body()
    if len(body_bytes) > _MAX_FRONTEND_METRICS_SIZE:
        raise HTTPException(status_code=413, detail="Payload too large")

    if not body_bytes:
        return Response(status_code=204)

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Invalid payload: expected object")

    try:
        payload = FrontendMetricsPayload.model_validate(data)
    except Exception as exc:
        logger.debug("frontend-metrics validation failed: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid metrics payload")

    # 结构化日志: 供日志聚合系统采集. 仅记录已采集到的指标 (非 None)
    logger.info(
        "frontend-metrics: fcp=%s lcp=%s inp=%s cls=%s ttfb=%s "
        "page_load=%s dom_ready=%s resources=%s/%s url=%s",
        payload.fcp,
        payload.lcp,
        payload.inp,
        payload.cls,
        payload.ttfb,
        payload.page_load_time,
        payload.dom_ready_time,
        payload.resource_count,
        payload.resource_size,
        payload.url,
    )

    return Response(status_code=204)
