"""P1-4: PDF 任务存储单元测试."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.pdf_job_store import (
    JOB_TTL_SECONDS,
    PdfJob,
    PdfJobStore,
)


class TestPdfJob:
    def test_to_status_dict_excludes_pdf_bytes(self):
        """to_status_dict 不包含 pdf_bytes (避免状态响应过大)."""
        job = PdfJob(
            id="job-1",
            status="completed",
            user_name="test_user",
            created_by=1,
            created_at="2026-06-27T00:00:00Z",
            pdf_bytes=b"%PDF-1.4 fake",
            file_size=12,
            page_count=2,
        )
        d = job.to_status_dict()
        assert "pdf_bytes" not in d
        assert d["id"] == "job-1"
        assert d["status"] == "completed"
        assert d["file_size"] == 12
        assert d["page_count"] == 2


class TestPdfJobStore:
    @pytest.fixture
    def store(self):
        return PdfJobStore()

    def test_create_and_get(self, store):
        """创建任务后可立即获取."""
        job = store.create("job-1", "user_a", created_by=1)
        assert job.id == "job-1"
        assert job.status == "queued"
        assert job.user_name == "user_a"
        assert job.created_by == 1
        fetched = store.get("job-1")
        assert fetched is job

    def test_get_nonexistent_returns_none(self, store):
        assert store.get("nonexistent") is None

    def test_update_fields(self, store):
        """update 支持批量更新字段."""
        store.create("job-2", "user_b", created_by=2)
        store.update(
            "job-2",
            status="running",
            progress=50,
            started_at="2026-06-27T00:01:00Z",
        )
        job = store.get("job-2")
        assert job.status == "running"
        assert job.progress == 50
        assert job.started_at == "2026-06-27T00:01:00Z"

    def test_update_nonexistent_is_noop(self, store):
        """更新不存在的任务不抛错."""
        store.update("nonexistent", status="running")

    def test_delete(self, store):
        store.create("job-3", "user_c", created_by=3)
        assert store.get("job-3") is not None
        store.delete("job-3")
        assert store.get("job-3") is None

    def test_delete_nonexistent_is_noop(self, store):
        store.delete("nonexistent")  # 不应抛错

    def test_count(self, store):
        assert store.count() == 0
        store.create("j1", "u1", created_by=1)
        store.create("j2", "u2", created_by=2)
        assert store.count() == 2

    def test_list_jobs_all(self, store):
        store.create("j1", "u1", created_by=1)
        store.create("j2", "u2", created_by=2)
        jobs = store.list_jobs()
        assert len(jobs) == 2
        assert all("pdf_bytes" not in j for j in jobs)

    def test_list_jobs_filtered_by_creator(self, store):
        """list_jobs 按 created_by 过滤."""
        store.create("j1", "u1", created_by=1)
        store.create("j2", "u2", created_by=2)
        jobs = store.list_jobs(created_by=1)
        assert len(jobs) == 1
        assert jobs[0]["user_name"] == "u1"

    def test_ttl_cleanup_removes_expired_jobs(self, store):
        """过期任务在下次操作时被清理."""
        store.create("j1", "u1", created_by=1)
        # 手动篡改 created_at 为 2 小时前 (超过 TTL)
        job = store.get("j1")
        expired_time = (
            datetime.now(timezone.utc) - timedelta(seconds=JOB_TTL_SECONDS + 60)
        ).isoformat()
        job.created_at = expired_time
        # 触发清理 (count 调用 _cleanup_expired)
        assert store.count() == 0
        assert store.get("j1") is None

    def test_ttl_cleanup_keeps_fresh_jobs(self, store):
        """未过期任务不受清理影响."""
        store.create("j1", "u1", created_by=1)
        assert store.count() == 1
        assert store.get("j1") is not None

    def test_pdf_bytes_stored_in_memory(self, store):
        """PDF 字节存储在内存中, get 可读取."""
        store.create("j1", "u1", created_by=1)
        fake_pdf = b"%PDF-1.4 fake content"
        store.update(
            "j1", status="completed", pdf_bytes=fake_pdf, file_size=len(fake_pdf)
        )
        job = store.get("j1")
        assert job.pdf_bytes == fake_pdf
        assert job.file_size == len(fake_pdf)
