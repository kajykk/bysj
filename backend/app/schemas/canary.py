from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CanaryCreateRequest(BaseModel):
    """Request to create a canary deployment."""

    version: str = Field(..., description="Canary version", min_length=1, max_length=50)
    traffic_percent: int = Field(
        default=1, ge=1, le=100, description="Initial traffic percentage"
    )
    thresholds: dict[str, float] | None = Field(
        default=None,
        description="Auto-rollback thresholds",
    )
    # STAB-P2-006: 路由前缀分流 (None=全局覆盖所有路由, 非 None=仅覆盖该路由前缀)
    route_prefix: str | None = Field(
        default=None,
        max_length=100,
        description="STAB-P2-006: 路由前缀分流 (None=全局, 如 '/api/v1/reports')",
    )


class CanaryTrafficUpdateRequest(BaseModel):
    """Request to update canary traffic percentage."""

    traffic_percent: int = Field(
        ..., ge=1, le=100, description="New traffic percentage"
    )


class CanaryRollbackRequest(BaseModel):
    """Request to rollback a canary deployment."""

    reason: str = Field(
        ..., min_length=1, max_length=500, description="Rollback reason"
    )


class CanaryDeploymentResponse(BaseModel):
    """Canary deployment response."""

    id: int
    version: str
    traffic_percent: int
    status: str
    started_at: str | None
    created_at: str | None
    # STAB-P2-006: 路由前缀分流
    route_prefix: str | None = None


class CanaryListItem(BaseModel):
    """Canary list item."""

    id: int
    version: str
    traffic_percent: int
    status: str
    auto_rollback_thresholds: dict[str, Any] | None
    triggered_by: int | None
    started_at: str | None
    ended_at: str | None
    rollback_reason: str | None
    created_at: str | None
    # STAB-P2-006: 路由前缀分流
    route_prefix: str | None = None


class CanaryListResponse(BaseModel):
    """Canary list response."""

    total: int
    limit: int
    offset: int
    items: list[dict[str, Any]]
