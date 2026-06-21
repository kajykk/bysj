from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
