"""Analytics API endpoints for web vitals and performance metrics."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.core.deps import get_current_user
from app.core.rate_limit import get_real_client_ip
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analytics", tags=["analytics"])

# In-memory storage for web vitals (replace with database in production)
# M-17 修复：使用 asyncio.Lock 保护并发写入，避免多协程竞争
_web_vitals_store: list[dict[str, Any]] = []
_web_vitals_lock = asyncio.Lock()
_MAX_STORE_SIZE = 10000


def _strip_url_query(url: str | None) -> str | None:
    """M-API-12 修复：去除 URL 中的 query string，防止跨用户敏感参数泄露."""
    if not url:
        return url
    try:
        parts = urlsplit(url)
        # 仅保留 scheme://netloc/path，丢弃 query 和 fragment
        return parts._replace(query="", fragment="").geturl()
    except Exception:
        return url


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
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


@router.post("/web-vitals", summary="Receive web vitals metrics")
async def receive_web_vitals(
    payload: WebVitalsPayload,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Receive and store web vitals metrics from frontend.

    Args:
        payload: Web vitals metric data
        request: FastAPI request object
        current_user: Current authenticated user

    Returns:
        Success status
    """
    record = {
        "name": payload.name,
        "value": payload.value,
        "rating": payload.rating,
        "delta": payload.delta,
        # M-API-12 修复：对 url 脱敏，去除 query string 防止跨用户泄露敏感参数
        "url": _strip_url_query(payload.url),
        "user_agent": payload.user_agent,
        "user_id": current_user.id,
        "client_host": get_real_client_ip(request),
        # M-17 修复：使用 timezone-aware datetime 替代已弃用的 naive utcnow
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # M-17 修复：使用锁保护并发写入，确保 append + trim 是原子操作
    async with _web_vitals_lock:
        _web_vitals_store.append(record)
        if len(_web_vitals_store) > _MAX_STORE_SIZE:
            _web_vitals_store.pop(0)  # Remove oldest

    logger.info(
        "Web Vital: %s=%.3f (rating: %s) from user_id=%s",
        payload.name,
        payload.value,
        payload.rating,
        current_user.id,
    )

    return {"status": "recorded"}


@router.post("/performance", summary="Receive performance metrics")
async def receive_performance(
    payload: PerformancePayload,
    request: Request,
    current_user: User = Depends(get_current_user),
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
    # M-API-12 修复：限制 limit 上限为 100，防止一次性返回过多数据
    limit: int = Query(default=100, ge=1, le=100),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get stored web vitals metrics.

    Args:
        metric_name: Filter by metric name (optional)
        limit: Maximum number of records to return
        current_user: Current authenticated user

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
        "timestamp": datetime.now(timezone.utc).isoformat(),
        # L-API-4 修复：移除 service 名，避免未鉴权端点泄露内部服务标识
    }
