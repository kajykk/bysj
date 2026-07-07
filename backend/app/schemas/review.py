from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReviewStatus(str, Enum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    ARCHIVED = "archived"


class ReviewPriority(str, Enum):
    NORMAL_REVIEW = "normal_review"
    HIGH_RISK_REVIEW = "high_risk_review"
    CRISIS_REVIEW = "crisis_review"


class ResolutionAction(str, Enum):
    MARK_RESOLVED = "mark_resolved"
    ESCALATE = "escalate"


class ReviewTaskCreate(BaseModel):
    user_id: int
    risk_report_id: int | None = None
    risk_level: int
    risk_score: float
    review_triggers: list[str] = Field(default_factory=list)
    crisis_override: bool = False
    priority: ReviewPriority = ReviewPriority.NORMAL_REVIEW


class ReviewTaskUpdate(BaseModel):
    status: ReviewStatus | None = None
    assigned_to: int | None = None
    resolved_by: int | None = None
    resolution_note: str | None = None
    resolved_at: datetime | None = None


class ReviewTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    risk_report_id: int | None = None
    risk_level: int
    risk_score: float
    review_triggers: list[str]
    crisis_override: bool
    status: str
    priority: str
    assigned_to: int | None = None
    resolved_by: int | None = None
    resolution_note: str | None = None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None

    # P0-D3 修复：模型中 review_triggers 存储为 Text(JSON 字符串)，Schema 期望 list[str]。
    # from_attributes=True 时 Pydantic 无法自动转换 str -> list[str]，需手动解析。
    @field_validator("review_triggers", mode="before")
    @classmethod
    def _parse_review_triggers(cls, v: Any) -> list[str]:
        if v is None or v == "":
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError):
                return []
        return []


class ReviewTaskListResponse(BaseModel):
    items: list[ReviewTaskResponse]
    total: int
    page: int
    page_size: int


class ReviewTaskFilter(BaseModel):
    status: ReviewStatus | None = None
    priority: ReviewPriority | None = None
    assigned_to: int | None = None
    user_id: int | None = None
    page: int = 1
    page_size: int = 20


class ReviewStats(BaseModel):
    total: int
    pending: int
    in_review: int
    resolved: int
    escalated: int
    crisis_count: int
    high_risk_count: int


class CrisisEventCreate(BaseModel):
    user_id: int
    report_id: int | None = None
    trigger_source: str
    crisis_keywords: list[str] = Field(default_factory=list)
    crisis_score: float | None = None
    input_summary: str | None = None
    review_task_id: int | None = None


class CrisisEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    report_id: int | None = None
    trigger_source: str
    crisis_keywords: list[str]
    crisis_score: float | None = None
    input_summary: str | None = None
    review_task_id: int | None = None
    status: str
    handled_by: int | None = None
    handled_action: str | None = None
    created_at: datetime
    handled_at: datetime | None = None

    # P0-D3 修复：模型中 crisis_keywords 存储为 Text(JSON 字符串)，Schema 期望 list[str]。
    # from_attributes=True 时 Pydantic 无法自动转换 str -> list[str]，需手动解析。
    @field_validator("crisis_keywords", mode="before")
    @classmethod
    def _parse_crisis_keywords(cls, v: Any) -> list[str]:
        if v is None or v == "":
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError):
                return []
        return []


class CrisisEventFilter(BaseModel):
    status: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    page: int = 1
    page_size: int = 20


# M10 修复：复核处理/升级请求体模型，避免长文本作为 query 参数
class ReviewResolveRequest(BaseModel):
    """复核任务处理请求体."""

    resolution_note: str = Field(
        ..., max_length=2000, description="处理说明"
    )  # L-19 修复：限制最大长度，防止超长文本


class ReviewEscalateRequest(BaseModel):
    """复核任务升级请求体."""

    reason: str = Field(
        ..., max_length=2000, description="升级原因"
    )  # L-19 修复：限制最大长度


# ISS-072 修复：危机事件状态流转请求体（处理/升级/关闭）
class CrisisHandleRequest(BaseModel):
    """危机事件处理请求体.

    action 取自 _ALLOWED_CRISIS_ACTIONS 白名单：
    escalate / notify_counselor / emergency_contact / resolved
    """

    action: str = Field(..., description="处理动作（白名单校验）")
    note: str | None = Field(default=None, max_length=2000, description="处理备注")


class CrisisEscalateRequest(BaseModel):
    """危机事件升级请求体."""

    reason: str = Field(..., max_length=2000, description="升级原因")


class CrisisCloseRequest(BaseModel):
    """危机事件关闭请求体."""

    note: str | None = Field(default=None, max_length=2000, description="关闭备注")
