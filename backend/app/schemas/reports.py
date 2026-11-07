from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

# L-20 修复：批量导出 payload 的嵌套约束，参照 schemas/admin.py 的
# validate_config_value 口径，防止 10000 行 × 任意大对象放大内存与导出耗时。
_ALLOWED_EXPORT_SCALAR_TYPES = (str, int, float, bool)
_MAX_EXPORT_DICT_KEYS = 100
_MAX_EXPORT_LIST_LEN = 100
_MAX_EXPORT_STR_LEN = 5000
_MAX_EXPORT_DEPTH = 3


def _validate_export_value(value: object, path: str, depth: int = 0) -> None:
    """递归校验导出值的键数、标量类型、字符串长度与嵌套深度。"""
    if depth > _MAX_EXPORT_DEPTH:
        raise ValueError(f"{path} nesting is too deep")
    if isinstance(value, dict):
        if len(value) > _MAX_EXPORT_DICT_KEYS:
            raise ValueError(f"{path} has too many keys")
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError(f"{path} keys must be non-empty strings")
            _validate_export_value(item, f"{path}.{key}", depth + 1)
        return
    if isinstance(value, list):
        if len(value) > _MAX_EXPORT_LIST_LEN:
            raise ValueError(f"{path} list is too long")
        for index, item in enumerate(value):
            _validate_export_value(item, f"{path}[{index}]", depth + 1)
        return
    if value is None:
        return
    if not isinstance(value, _ALLOWED_EXPORT_SCALAR_TYPES):
        raise ValueError(
            f"{path} contains unsupported type: {type(value).__name__}"
        )
    if isinstance(value, str) and len(value) > _MAX_EXPORT_STR_LEN:
        raise ValueError(f"{path} string value is too long")


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
    risk_trend: list[RiskTrendItem] = Field(
        default_factory=list, description="Risk trend data"
    )
    recommendations: list[str] = Field(
        default_factory=list, description="Recommendations"
    )


class BatchExportDataItem(BaseModel):
    """Data item for batch export."""

    data: dict[str, Any]

    @model_validator(mode="after")
    def validate_data(self) -> "BatchExportDataItem":
        # L-20 修复：行数据补键数/标量类型/字符串长度/嵌套深度约束
        _validate_export_value(self.data, "data")
        return self


class BatchExportRequest(BaseModel):
    """Request to export data to Excel."""

    # ISS-015 修复：添加 max_length 限制，防止超大批量导出导致 OOM
    data: list[BatchExportDataItem] = Field(
        ..., min_length=1, max_length=10000, description="Data to export"
    )
    columns: list[str] | None = Field(
        default=None, max_length=200, description="Columns to include"
    )
    filters: dict[str, Any] | None = Field(default=None, description="Filters to apply")
    # P1-SEC-030 修复：限制 filename 长度，防止生成超长文件名
    filename: str | None = Field(
        default=None, max_length=100, description="Output filename (without extension)"
    )

    @model_validator(mode="after")
    def validate_filters(self) -> "BatchExportRequest":
        # L-20 修复：filters 补键数/标量类型/字符串长度/嵌套深度约束
        if self.filters is not None:
            _validate_export_value(self.filters, "filters")
        return self
