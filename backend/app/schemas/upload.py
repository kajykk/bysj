"""文件上传 API 响应模型."""

from __future__ import annotations

from pydantic import BaseModel


class UploadResult(BaseModel):
    """单文件上传结果."""

    url: str | None = None
    filename: str | None = None
    original_name: str | None = None
    size: int | None = None
    content_type: str | None = None


class UploadBatchResult(BaseModel):
    """批量上传结果."""

    items: list[UploadResult] | None = None
    count: int | None = None
    total: int | None = None
    failed: int | None = None
