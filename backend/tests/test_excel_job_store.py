"""PERF-P1-005: Excel 任务存储单元测试.

覆盖范围 (与 pdf_job_store 镜像模式一致):
1. ExcelJob.to_status_dict 不含 excel_bytes (避免响应体过大)
2. ExcelJobStore CRUD: create / get / update / delete
3. update 对不存在任务的幂等性
4. delete 对不存在任务的幂等性
5. count 触发 TTL 清理
6. list_jobs 全量 / 按 created_by 过滤
7. _cleanup_expired 移除过期任务
8. _cleanup_expired 保留未过期任务
9. excel_bytes 存储与读取
10. 全局 excel_job_store 实例可访问
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.excel_job_store import (
    JOB_TTL_SECONDS,
    MAX_EXCEL_JOBS,
    ExcelJob,
    ExcelJobStore,
    excel_job_store,
)


class TestExcelJob:
    """ExcelJob 数据类测试."""

    def test_to_status_dict_excludes_excel_bytes(self):
        """to_status_dict 不包含 excel_bytes (避免状态响应过大)."""
        job = ExcelJob(
            id="job-1",
            status="completed",
            filename="report.xlsx",
            created_by=1,
            created_at="2026-07-10T00:00:00Z",
            excel_bytes=b"PK\x03\x04 fake xlsx",
            file_size=12,
            row_count=100,
            column_count=5,
        )
        d = job.to_status_dict()
        assert "excel_bytes" not in d
        assert d["id"] == "job-1"
        assert d["status"] == "completed"
        assert d["filename"] == "report.xlsx"
        assert d["progress"] == 0
        assert d["file_size"] == 12
        assert d["row_count"] == 100
        assert d["column_count"] == 5

    def test_to_status_dict_default_progress(self):
        """默认 progress=0 出现在 to_status_dict 中."""
        job = ExcelJob(
            id="j",
            status="queued",
            filename="f",
            created_by=1,
            created_at="2026-07-10T00:00:00Z",
        )
        d = job.to_status_dict()
        assert d["progress"] == 0
        assert d["started_at"] is None
        assert d["completed_at"] is None
        assert d["error"] is None
        assert d["file_size"] == 0
        assert d["row_count"] == 0
        assert d["column_count"] == 0


class TestExcelJobStore:
    """ExcelJobStore 进程内存储测试."""

    @pytest.fixture
    def store(self) -> ExcelJobStore:
        return ExcelJobStore()

    def test_create_and_get(self, store: ExcelJobStore) -> None:
        """创建任务后可立即获取."""
        job = store.create("job-1", "report_a.xlsx", created_by=1)
        assert job.id == "job-1"
        assert job.status == "queued"
        assert job.filename == "report_a.xlsx"
        assert job.created_by == 1
        assert job.created_at  # 自动填充 ISO 格式时间字符串
        fetched = store.get("job-1")
        assert fetched is job

    def test_get_nonexistent_returns_none(self, store: ExcelJobStore) -> None:
        """获取不存在任务返回 None."""
        assert store.get("nonexistent") is None

    def test_update_fields(self, store: ExcelJobStore) -> None:
        """update 支持批量更新字段."""
        store.create("job-2", "report_b.xlsx", created_by=2)
        store.update(
            "job-2",
            status="running",
            progress=50,
            started_at="2026-07-10T00:01:00Z",
        )
        job = store.get("job-2")
        assert job is not None
        assert job.status == "running"
        assert job.progress == 50
        assert job.started_at == "2026-07-10T00:01:00Z"

    def test_update_unknown_field_ignored(self, store: ExcelJobStore) -> None:
        """update 未知字段被忽略 (使用 hasattr 检查)."""
        store.create("job-3", "report_c.xlsx", created_by=3)
        # 不应抛错, 也不应被设置
        store.update("job-3", nonexistent_attr="value")
        job = store.get("job-3")
        assert job is not None
        assert not hasattr(job, "nonexistent_attr")

    def test_update_nonexistent_is_noop(self, store: ExcelJobStore) -> None:
        """更新不存在的任务不抛错."""
        store.update("nonexistent", status="running")
        # 不应抛错

    def test_delete(self, store: ExcelJobStore) -> None:
        """delete 移除任务."""
        store.create("job-4", "report_d.xlsx", created_by=4)
        assert store.get("job-4") is not None
        store.delete("job-4")
        assert store.get("job-4") is None

    def test_delete_nonexistent_is_noop(self, store: ExcelJobStore) -> None:
        """delete 不存在任务不抛错."""
        store.delete("nonexistent")  # 不应抛错

    def test_count_initial_zero(self, store: ExcelJobStore) -> None:
        """初始 count 为 0."""
        assert store.count() == 0

    def test_count_after_creates(self, store: ExcelJobStore) -> None:
        """创建任务后 count 递增."""
        store.create("j1", "u1.xlsx", created_by=1)
        store.create("j2", "u2.xlsx", created_by=2)
        assert store.count() == 2

    def test_list_jobs_all(self, store: ExcelJobStore) -> None:
        """list_jobs 返回所有任务状态."""
        store.create("j1", "u1.xlsx", created_by=1)
        store.create("j2", "u2.xlsx", created_by=2)
        jobs = store.list_jobs()
        assert len(jobs) == 2
        # to_status_dict 不应包含 excel_bytes
        assert all("excel_bytes" not in j for j in jobs)

    def test_list_jobs_filtered_by_creator(self, store: ExcelJobStore) -> None:
        """list_jobs 按 created_by 过滤."""
        store.create("j1", "u1.xlsx", created_by=1)
        store.create("j2", "u2.xlsx", created_by=2)
        jobs = store.list_jobs(created_by=1)
        assert len(jobs) == 1
        assert jobs[0]["filename"] == "u1.xlsx"

    def test_list_jobs_no_filter_returns_all(self, store: ExcelJobStore) -> None:
        """list_jobs 不传 created_by 返回全部."""
        store.create("j1", "u1.xlsx", created_by=1)
        store.create("j2", "u2.xlsx", created_by=2)
        store.create("j3", "u3.xlsx", created_by=3)
        assert len(store.list_jobs()) == 3

    def test_ttl_cleanup_removes_expired_jobs(self, store: ExcelJobStore) -> None:
        """过期任务在下次操作时被清理."""
        store.create("j1", "u1.xlsx", created_by=1)
        # 手动篡改 created_at 为 2 小时前 (超过 TTL)
        job = store.get("j1")
        assert job is not None
        expired_time = (
            datetime.now(timezone.utc) - timedelta(seconds=JOB_TTL_SECONDS + 60)
        ).isoformat()
        job.created_at = expired_time
        # 触发清理 (count 调用 _cleanup_expired)
        assert store.count() == 0
        assert store.get("j1") is None

    def test_ttl_cleanup_keeps_fresh_jobs(self, store: ExcelJobStore) -> None:
        """未过期任务不受清理影响."""
        store.create("j1", "u1.xlsx", created_by=1)
        # 刚创建, 不应被清理
        assert store.count() == 1
        assert store.get("j1") is not None

    def test_ttl_cleanup_skips_invalid_timestamp(self, store: ExcelJobStore) -> None:
        """无效时间戳 (非 ISO 格式) 在清理时被跳过, 不抛错."""
        store.create("j1", "u1.xlsx", created_by=1)
        job = store.get("j1")
        assert job is not None
        # 模拟 corrupted created_at
        job.created_at = "not-a-valid-iso-timestamp"
        # 触发清理, 不应抛错
        count = store.count()
        # 由于 _cleanup_expired 跳过该任务, 它仍然存在
        assert count >= 1
        assert store.get("j1") is not None

    def test_excel_bytes_stored_in_memory(self, store: ExcelJobStore) -> None:
        """Excel 字节存储在内存中, get 可读取."""
        store.create("j1", "u1.xlsx", created_by=1)
        fake_xlsx = b"PK\x03\x04 fake xlsx content"
        store.update(
            "j1",
            status="completed",
            excel_bytes=fake_xlsx,
            file_size=len(fake_xlsx),
            row_count=50,
            column_count=3,
        )
        job = store.get("j1")
        assert job is not None
        assert job.excel_bytes == fake_xlsx
        assert job.file_size == len(fake_xlsx)
        assert job.row_count == 50
        assert job.column_count == 3


class TestExcelJobStoreModuleConstants:
    """模块级常量和全局实例."""

    def test_job_ttl_seconds_default(self) -> None:
        """JOB_TTL_SECONDS = 3600 (1 小时)."""
        assert JOB_TTL_SECONDS == 3600

    def test_max_excel_jobs_default(self) -> None:
        """MAX_EXCEL_JOBS = 20 (与 PDF 一致, 防止内存耗尽)."""
        assert MAX_EXCEL_JOBS == 20

    def test_global_excel_job_store_instance(self) -> None:
        """全局 excel_job_store 是 ExcelJobStore 实例."""
        assert isinstance(excel_job_store, ExcelJobStore)
