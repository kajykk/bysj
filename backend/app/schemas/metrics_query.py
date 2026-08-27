"""Prometheus HTTP API 兼容端点响应模型."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PrometheusQueryResult(BaseModel):
    """Prometheus vector 查询结果项."""

    metric: dict[str, str] | None = None
    value: list[Any] | None = None


class PrometheusQueryData(BaseModel):
    resultType: str | None = None
    result: list[PrometheusQueryResult] | None = None


class PrometheusQueryResponse(BaseModel):
    status: str | None = None
    data: PrometheusQueryData | None = None
