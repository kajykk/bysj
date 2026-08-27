"""T5-B2：分析事件端点响应 Schema。

为 /analytics 四个端点补充具体 ``ApiResponse[T]`` 数据模型，
使 OpenAPI 契约中 data 字段可导航（此前为裸 dict，data 类型未知）。
字段与各端点 ok() 实际返回严格对齐。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EventsSubmitResponse(BaseModel):
    """POST /analytics/events —— 事件入库确认."""

    stored: int = Field(..., description="实际接收的事件数量")
    retention_days: int = Field(..., description="事件保留期限（天）")


class ConsentStatusResponse(BaseModel):
    """GET /analytics/consent —— 同意状态查询."""

    consented: bool = Field(..., description="当前是否同意采集")
    retention_days: int = Field(..., description="事件保留期限（天）")
    event_types: list[str] = Field(..., description="允许的事件类型白名单（排序后）")


class ConsentUpdateResponse(BaseModel):
    """PUT /analytics/consent —— 同意状态更新."""

    consented: bool = Field(..., description="更新后的同意状态")
    changed: bool = Field(..., description="本次调用是否实际发生变更")


class AnalyticsEventRecord(BaseModel):
    """单条已存储的分析事件（管理员审计视图）."""

    user_id: int
    event_type: str
    timestamp: int = Field(..., description="客户端时间戳（毫秒）")
    metadata: dict[str, Any] = Field(default_factory=dict)
    client_ip: str | None = None
    received_at: str
    retention_expires_at: str


class EventsQueryResponse(BaseModel):
    """GET /analytics/events —— 事件审计查询."""

    events: list[AnalyticsEventRecord] = Field(default_factory=list)
    total: int = Field(..., description="清理过期后仓库中的事件总数（过滤前）")
