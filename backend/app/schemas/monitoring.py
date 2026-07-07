from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FrontendMetricsPayload(BaseModel):
    """P3-2: 前端 Web Vitals 上报负载.

    接收 usePerformanceMonitor composable 通过 fetch/sendBeacon 上报的 Core Web Vitals.
    字段名使用 camelCase alias 以匹配前端 JSON 结构.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    # Core Web Vitals (可选 - 未采集到时为 None)
    fcp: float | None = Field(
        None, description="First Contentful Paint (ms)", ge=0, le=60000
    )
    lcp: float | None = Field(
        None, description="Largest Contentful Paint (ms)", ge=0, le=60000
    )
    inp: float | None = Field(
        None, description="Interaction to Next Paint (ms)", ge=0, le=60000
    )
    cls: float | None = Field(None, description="Cumulative Layout Shift", ge=0, le=10)
    ttfb: float | None = Field(
        None, description="Time to First Byte (ms)", ge=0, le=60000
    )

    # 自定义指标 (camelCase alias 匹配前端字段)
    page_load_time: float | None = Field(None, alias="pageLoadTime", ge=0, le=60000)
    dom_ready_time: float | None = Field(None, alias="domReadyTime", ge=0, le=60000)
    resource_count: int | None = Field(None, alias="resourceCount", ge=0, le=10000)
    resource_size: int | None = Field(None, alias="resourceSize", ge=0, le=100_000_000)

    # 导航信息 (必填)
    url: str = Field(..., min_length=1, max_length=2048)
    timestamp: int = Field(..., ge=0, le=2_000_000_000_000)
    user_agent: str = Field(..., alias="userAgent", max_length=512)


class ModelSuccessRateItem(BaseModel):
    time_bucket: str
    total: int
    success: int
    fallback: int
    success_rate: float


class ModelSuccessRateResponse(BaseModel):
    granularity: str
    data: list[ModelSuccessRateItem]


class FallbackReasonItem(BaseModel):
    reason: str
    count: int
    percentage: float


class FallbackStatsResponse(BaseModel):
    total: int
    reasons: list[FallbackReasonItem]


class DriftAlertItem(BaseModel):
    id: int
    model_version: str | None
    feature_name: str | None
    drift_type: str
    severity: str
    metric_value: float | None
    threshold: float | None
    details: dict[str, Any] | None
    resolved_at: str | None
    created_at: str | None


class DriftAlertListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    alerts: list[DriftAlertItem]


class DashboardSummaryResponse(BaseModel):
    inference_count_24h: int
    fallback_count_24h: int
    fallback_rate: float
    active_drift_alerts: int
    drift_by_severity: dict[str, int]
    avg_latency_ms: float
    live_metrics: dict[str, Any]


class RequestDetailsResponse(BaseModel):
    id: int
    event_type: str
    model_version: str | None
    user_id: int | None
    request_payload: dict[str, Any] | None
    response_summary: dict[str, Any] | None
    fallback_reason: str | None
    latency_ms: float | None
    created_at: str | None
