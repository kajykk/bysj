"""运营看板 API 响应模型."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class OpsDashboardOverview(BaseModel):
    """运营看板总览响应体（聚合结构，字段保持可选以兼容历史数据）."""

    generated_at: str | None = None
    review: dict[str, Any] | None = None
    crisis: dict[str, Any] | None = None
    feedback: dict[str, Any] | None = None
    kill_switch: dict[str, Any] | None = None
    audit_events: list[dict[str, Any]] | None = None
    content: dict[str, Any] | None = None


class ReviewMetricsResult(BaseModel):
    """复核任务详细指标响应体."""

    period_days: int | None = None
    since: str | None = None
    status_distribution: dict[str, Any] | None = None
    total_pending: int | None = None
    crisis_pending: int | None = None
    recent_7d_count: int | None = None
    avg_response_hours_7d: float | None = None
    sla_target_hours: int | None = None
    sla_met: bool | None = None
