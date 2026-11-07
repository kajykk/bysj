from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ValidationRunRequest(BaseModel):
    """Request to start a validation run."""

    # L-21 修复：版本/路径字段补长度上限，避免超长值原样写入 Redis job 并回显
    model_version: str = Field(
        ..., max_length=64, description="Model version to validate"
    )
    dataset_path: str = Field(
        ..., max_length=512, description="Path to validation dataset"
    )
    baseline_version: str | None = Field(
        default=None, max_length=64, description="Baseline model version for comparison"
    )
    baseline_dataset_path: str | None = Field(
        default=None, max_length=512, description="Path to baseline dataset"
    )


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
