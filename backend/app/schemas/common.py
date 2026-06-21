from __future__ import annotations

from datetime import datetime
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

# P1-E 修复：使用 Generic TypeVar 替代裸 Any，允许调用方指定具体数据类型
T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 200
    message: str = "success"
    data: T | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    status_code: int
    layer: Optional[str] = None
    fallback_to: Optional[str] = None
    timestamp: datetime
    request_id: str
    # P2 修复：使用 Field(default_factory=dict) 替代可变默认值 {}
    details: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail
