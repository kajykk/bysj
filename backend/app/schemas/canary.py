from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CanaryCreateRequest(BaseModel):
    """Request to create a canary deployment."""

    version: str = Field(..., description="Canary version", min_length=1, max_length=50)
    traffic_percent: int = Field(default=1, ge=1, le=100, description="Initial traffic percentage")
    thresholds: dict[str, float] | None = Field(
        default=None,
        description="Auto-rollback thresholds",
    )


class CanaryTrafficUpdateRequest(BaseModel):
    """Request to update canary traffic percentage."""

    traffic_percent: int = Field(..., ge=1, le=100, description="New traffic percentage")


class CanaryRollbackRequest(BaseModel):
    """Request to rollback a canary deployment."""

    reason: str = Field(..., min_length=1, max_length=500, description="Rollback reason")


class CanaryDeploymentResponse(BaseModel):
    """Canary deployment response."""

    id: int
    version: str
    traffic_percent: int
    status: str
    started_at: str | None
    created_at: str | None


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


class CanaryListResponse(BaseModel):
    """Canary list response."""

    total: int
    limit: int
    offset: int
    items: list[dict[str, Any]]
