"""内容治理 API 响应模型."""

from __future__ import annotations

from pydantic import BaseModel


class GovernanceActionResult(BaseModel):
    """审核/下架/恢复动作确认体."""

    content_id: int | None = None
    status: str | None = None
    reviewed_by: int | None = None
    reviewed_at: str | None = None
    review_cycle_days: int | None = None
    next_review_due: str | None = None
    takedown_by: int | None = None
    takedown_at: str | None = None
    restored_by: int | None = None
    restored_at: str | None = None
    reason: str | None = None


class PendingContentItem(BaseModel):
    """待审核/待复审内容项."""

    id: int | None = None
    title: str | None = None
    content_type: str | None = None
    category: str | None = None
    status: str | None = None
    created_at: str | None = None
    needs_review_reason: str | None = None
    days_since_creation: int | None = None


class PendingContentList(BaseModel):
    items: list[PendingContentItem] | None = None
    total: int | None = None
    page: int | None = None
    page_size: int | None = None
    review_cycle_days: int | None = None


class ContentHistoryItem(BaseModel):
    id: int | None = None
    action: str | None = None
    operator_id: int | None = None
    operator_role: str | None = None
    detail: str | None = None
    created_at: str | None = None


class ContentHistoryResult(BaseModel):
    content_id: int | None = None
    history: list[ContentHistoryItem] | None = None
    total_events: int | None = None
