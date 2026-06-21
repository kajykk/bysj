from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_permission
from app.core.response import ok
from app.models.monitoring import CanaryRecord, DriftAlert, DriftSeverity, MonitoringLog, MonitoringEventType
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.monitoring import (
    DashboardSummaryResponse,
    DriftAlertListResponse,
    FallbackStatsResponse,
    ModelSuccessRateResponse,
    RequestDetailsResponse,
)
from app.services.observability_service import observability_collector
from app.core.model_engine import model_engine as engine

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/model-success-rate", response_model=ApiResponse)
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
        group_format = "%Y-%m-%d %H:00"
    elif granularity == "day":
        start_time = now - timedelta(days=30)
        group_format = "%Y-%m-%d"
    elif granularity == "week":
        start_time = now - timedelta(weeks=12)
        group_format = "%Y-%W"
    else:
        start_time = now - timedelta(days=30)
        group_format = "%Y-%m-%d"

    # Query inference events
    stmt = select(MonitoringLog).where(
        MonitoringLog.event_type == MonitoringEventType.INFERENCE,
        MonitoringLog.created_at >= start_time,
    )
    if model_version:
        stmt = stmt.where(MonitoringLog.model_version == model_version)

    result = await db.execute(stmt)
    logs = result.scalars().all()

    # Group by time bucket
    from collections import defaultdict

    buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "success": 0, "fallback": 0})

    for log in logs:
        bucket = log.created_at.strftime(group_format) if log.created_at else "unknown"
        buckets[bucket]["total"] += 1
        if log.fallback_reason:
            buckets[bucket]["fallback"] += 1
        else:
            buckets[bucket]["success"] += 1

    data = [
        {
            "time_bucket": bucket,
            "total": stats["total"],
            "success": stats["success"],
            "fallback": stats["fallback"],
            "success_rate": round(stats["success"] / max(1, stats["total"]) * 100, 2),
        }
        for bucket, stats in sorted(buckets.items())
    ]

    return ok(ModelSuccessRateResponse(granularity=granularity, data=data).model_dump())


@router.get("/fallback-stats", response_model=ApiResponse)
async def fallback_stats(
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    model_version: Annotated[str | None, Query(description="模型版本过滤")] = None,
) -> dict:
    """Get fallback statistics grouped by reason."""
    stmt = select(MonitoringLog).where(MonitoringLog.event_type == MonitoringEventType.FALLBACK)
    if model_version:
        stmt = stmt.where(MonitoringLog.model_version == model_version)

    result = await db.execute(stmt)
    logs = result.scalars().all()

    from collections import defaultdict

    reason_counts: dict[str, int] = defaultdict(int)
    for log in logs:
        reason = log.fallback_reason or "unknown"
        reason_counts[reason] += 1

    total = sum(reason_counts.values())
    data = [
        {
            "reason": reason,
            "count": count,
            "percentage": round(count / max(1, total) * 100, 2),
        }
        for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1])
    ]

    return ok(FallbackStatsResponse(total=total, reasons=data).model_dump())


@router.get("/drift-alerts", response_model=ApiResponse)
async def drift_alerts(
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    severity: Annotated[str | None, Query(description="严重程度过滤: LOW, MEDIUM, HIGH, CRITICAL")] = None,
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


@router.get("/dashboard-summary", response_model=ApiResponse)
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
        fallback_rate=round(fallback_count_24h / max(1, inference_count_24h + fallback_count_24h) * 100, 2),
        active_drift_alerts=active_drift_count,
        drift_by_severity=severity_counts,
        avg_latency_ms=avg_latency,
        live_metrics=live_metrics,
    )

    return ok(data.model_dump())


@router.get("/request-details/{log_id}", response_model=ApiResponse)
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


@router.get("/request-details", response_model=ApiResponse)
async def request_details_list(
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    event_type: Annotated[str | None, Query(description="事件类型过滤")] = None,
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


@router.get("/engine-snapshot", response_model=ApiResponse)
async def engine_metrics_snapshot(
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    snapshot = engine.get_metrics_snapshot()
    return ok(snapshot)
