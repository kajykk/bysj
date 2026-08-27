"""GDPR API 响应模型."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class GdprDeleteResult(BaseModel):
    """匿名化账户响应体（覆盖 anonymize_user 全量返回字段）."""

    user_id: int | None = None
    anonymized_at: str | None = None
    original_email_masked: str | None = None
    contacts_anonymized: int | None = None
    sessions_revoked: int | None = None
    risk_assessments_deleted: int | None = None
    pii_text_anonymized: dict[str, Any] | None = None
    legal_records_retained: bool | None = None
    warning: str | None = None
    status: str | None = None
    message: str | None = None
