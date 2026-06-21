from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RiskTrendItem(BaseModel):
    """Risk trend data item."""

    date: str
    score: float
    level: str


class UserRiskReportRequest(BaseModel):
    """Request to generate user risk PDF report."""

    user_id: int = Field(..., description="User ID")
    # P1-SEC-030 修复：限制 user_name 长度，防止生成超长文件名
    user_name: str = Field(..., min_length=1, max_length=100, description="User name")
    risk_level: str = Field(..., description="Current risk level")
    risk_trend: list[RiskTrendItem] = Field(default_factory=list, description="Risk trend data")
    recommendations: list[str] = Field(default_factory=list, description="Recommendations")


class BatchExportDataItem(BaseModel):
    """Data item for batch export."""

    data: dict[str, Any]


class BatchExportRequest(BaseModel):
    """Request to export data to Excel."""

    data: list[BatchExportDataItem] = Field(..., min_length=1, description="Data to export")
    columns: list[str] | None = Field(default=None, description="Columns to include")
    filters: dict[str, Any] | None = Field(default=None, description="Filters to apply")
    # P1-SEC-030 修复：限制 filename 长度，防止生成超长文件名
    filename: str | None = Field(
        default=None, max_length=100, description="Output filename (without extension)"
    )
