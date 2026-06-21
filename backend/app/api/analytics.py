"""Analytics API endpoints for web vitals and performance metrics."""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.deps import get_current_active_user
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analytics", tags=["analytics"])

# In-memory storage for web vitals (replace with database in production)
_web_vitals_store: list[dict[str, Any]] = []
_MAX_STORE_SIZE = 10000


class WebVitalsPayload(BaseModel):
    """Web Vitals metric payload."""

    name: str = Field(..., description="Metric name (CLS, FID, FCP, LCP, TTFB)")
    value: float = Field(..., description="Metric value")
    rating: str = Field(..., description="Metric rating: good, needs-improvement, poor")
    delta: float | None = Field(None, description="Metric delta")
    url: str | None = Field(None, description="Page URL")
    user_agent: str | None = Field(None, description="User agent")


class PerformancePayload(BaseModel):
    """Performance metric payload."""

    metric_type: str = Field(..., description="Metric type")
    value: float = Field(..., description="Metric value")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


@router.post("/web-vitals", summary="Receive web vitals metrics")
async def receive_web_vitals(
    payload: WebVitalsPayload,
    request: Request,
) -> dict[str, str]:
    """Receive and store web vitals metrics from frontend.

    Args:
        payload: Web vitals metric data
        request: FastAPI request object

    Returns:
        Success status
    """
    record = {
        "name": payload.name,
        "value": payload.value,
        "rating": payload.rating,
        "delta": payload.delta,
        "url": payload.url,
        "user_agent": payload.user_agent,
        "client_host": request.client.host if request.client else None,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Store in memory (with size limit)
    _web_vitals_store.append(record)
    if len(_web_vitals_store) > _MAX_STORE_SIZE:
        _web_vitals_store.pop(0)  # Remove oldest

    logger.info(
        "Web Vital: %s=%.3f (rating: %s) from %s",
        payload.name,
        payload.value,
        payload.rating,
        request.client.host if request.client else "unknown",
    )

    return {"status": "recorded"}


@router.post("/performance", summary="Receive performance metrics")
async def receive_performance(
    payload: PerformancePayload,
    request: Request,
    current_user: User = Depends(get_current_active_user),
) -> dict[str, str]:
    """Receive and process custom performance metrics.
    
    Args:
        payload: Performance metric data
        request: FastAPI request object
        current_user: Current authenticated user
        
    Returns:
        Success status
    """
    logger.info(
        "Performance: %s=%s by user %s",
        payload.metric_type,
        payload.value,
        current_user.id,
    )

    return {"status": "ok"}


@router.get("/web-vitals", summary="Get web vitals metrics")
async def get_web_vitals(
    metric_name: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Get stored web vitals metrics.

    Args:
        metric_name: Filter by metric name (optional)
        limit: Maximum number of records to return

    Returns:
        List of web vitals records
    """
    records = _web_vitals_store
    if metric_name:
        records = [r for r in records if r["name"] == metric_name]

    return {
        "metrics": records[-limit:],
        "total": len(records),
    }


@router.get("/health", summary="Analytics service health check")
async def analytics_health() -> dict[str, Any]:
    """Check analytics service health.
    
    Returns:
        Health status and timestamp
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "analytics",
    }
