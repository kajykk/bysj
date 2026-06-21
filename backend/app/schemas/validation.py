from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ValidationRunRequest(BaseModel):
    """Request to start a validation run."""

    model_version: str = Field(..., description="Model version to validate")
    dataset_path: str = Field(..., description="Path to validation dataset")
    baseline_version: str | None = Field(default=None, description="Baseline model version for comparison")
    baseline_dataset_path: str | None = Field(default=None, description="Path to baseline dataset")


class ValidationStatusResponse(BaseModel):
    """Validation job status response."""

    id: str
    status: str
    progress: int
    model_version: str
    error: str | None = None


class ValidationResultResponse(BaseModel):
    """Validation result response."""

    model_version: str
    metrics: dict[str, Any]
    baseline_metrics: dict[str, Any] | None = None
    delta: dict[str, Any] | None = None
    predictions_count: int
    errors: list[str]
