"""PERF-P1-005: Excel 报告异步生成任务存储.

提供 Excel 生成任务的状态管理与结果存储.
任务状态与 Excel 字节存储在进程内字典中 (单实例部署足够),
支持 TTL 自动清理, 避免内存泄漏.

设计参照 pdf_job_store.py (镜像模式), 保持两套异步队列行为一致.
多实例部署时可升级为 Redis Hash + 对象存储 (参照 ValidationJobStore 模式).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# 任务 TTL: 1 小时后自动清理 (与 PdfJobStore 一致)
JOB_TTL_SECONDS = 3600
# 最大并发任务数 (防止内存耗尽, Excel 字节占用较大, 10000 行可达几 MB)
# ISS-045 说明：当前 Excel 导出为同步端点 (POST /reports/batch-export/excel)，
# 无异步作业队列，故 MAX_EXCEL_JOBS 暂未被任何端点引用。
# TODO(异步 Excel): 若新增异步 Excel 生成端点，应在创建作业时检查
#   excel_job_store.count() >= MAX_EXCEL_JOBS 并抛出 HTTPException(429)，
#   参照 reports.py 中 MAX_PDF_JOBS 的实现模式。
MAX_EXCEL_JOBS = 20


@dataclass
class ExcelJob:
    """Excel 生成任务."""

    id: str
    status: str  # queued | running | completed | failed
    filename: str
    created_by: int
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    progress: int = 0  # 0-100
    error: str | None = None
    # Excel 结果 (完成后填充)
    excel_bytes: bytes | None = None
    file_size: int = 0
    row_count: int = 0
    column_count: int = 0

    def to_status_dict(self) -> dict[str, Any]:
        """返回状态信息 (不含 Excel 字节, 避免响应体过大)."""
        return {
            "id": self.id,
            "status": self.status,
            "filename": self.filename,
            "progress": self.progress,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "file_size": self.file_size,
            "row_count": self.row_count,
            "column_count": self.column_count,
        }


class ExcelJobStore:
    """Excel 任务存储: 进程内字典 + TTL 清理.

    设计权衡:
    - 进程内存储: 单实例部署足够, 避免二进制数据在 Redis Hash 中 base64 编码的开销.
    - TTL 清理: 1 小时后自动清理, 防止内存泄漏.
    - 最大任务数限制: 超过 MAX_EXCEL_JOBS 时拒绝新任务 (429).
    """

    def __init__(self) -> None:
        self._jobs: dict[str, ExcelJob] = {}

    def create(self, job_id: str, filename: str, created_by: int) -> ExcelJob:
        """创建新任务."""
        job = ExcelJob(
            id=job_id,
            status="queued",
            filename=filename,
            created_by=created_by,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._jobs[job_id] = job
        self._cleanup_expired()
        return job

    def get(self, job_id: str) -> ExcelJob | None:
        """获取任务 (含 Excel 字节, 供下载端点使用)."""
        return self._jobs.get(job_id)

    def update(self, job_id: str, **fields: Any) -> None:
        """更新任务字段."""
        job = self._jobs.get(job_id)
        if job is None:
            return
        for k, v in fields.items():
            if hasattr(job, k):
                setattr(job, k, v)

    def delete(self, job_id: str) -> None:
        """删除任务 (下载后可选调用, 释放内存)."""
        self._jobs.pop(job_id, None)

    def count(self) -> int:
        """获取当前任务数量 (触发清理)."""
        self._cleanup_expired()
        return len(self._jobs)

    def list_jobs(self, created_by: int | None = None) -> list[dict[str, Any]]:
        """列出任务状态 (不含 Excel 字节)."""
        self._cleanup_expired()
        jobs = list(self._jobs.values())
        if created_by is not None:
            jobs = [j for j in jobs if j.created_by == created_by]
        return [j.to_status_dict() for j in jobs]

    def _cleanup_expired(self) -> None:
        """清理过期任务, 释放内存 (含 Excel 字节)."""
        now = datetime.now(timezone.utc)
        expired: list[str] = []
        for job_id, job in self._jobs.items():
            try:
                created = datetime.fromisoformat(job.created_at)
                if (now - created).total_seconds() > JOB_TTL_SECONDS:
                    expired.append(job_id)
            except (ValueError, TypeError):
                continue
        for job_id in expired:
            self._jobs.pop(job_id, None)
        if expired:
            logger.info("Cleaned up %d expired Excel jobs", len(expired))


# 全局实例
excel_job_store = ExcelJobStore()
