"""P-D: PDF 生成 Celery 队列化测试.

覆盖范围:
1. Redis 状态存储 (save/get/update job)
2. PDF 字节存储 (save/get/delete bytes, 含 TTL)
3. Celery 任务 generate_pdf_report (成功/失败/重试)
4. _count_pdf_pages 页数统计
5. create_initial_job 初始状态生成
"""

from __future__ import annotations

# 在导入被测模块前确保 PII 密钥存在 (避免 config 加载失败)
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "PII_ENCRYPTION_KEY", "test-pii-key-for-unit-tests-1234567890abcdef=="
)


@pytest.fixture
def mock_redis():
    """Mock Redis 客户端, 模拟进程内字典存储."""
    store: dict = {}
    r = MagicMock()
    r.set = MagicMock(side_effect=lambda k, v: store.__setitem__(k, v))
    r.setex = MagicMock(side_effect=lambda k, ttl, v: store.__setitem__(k, v))
    r.get = MagicMock(side_effect=lambda k: store.get(k))
    r.delete = MagicMock(side_effect=lambda k: store.pop(k, None))
    r.sadd = MagicMock()
    return r, store


@pytest.fixture(autouse=True)
def reset_sync_redis():
    """每个测试前重置 _sync_redis_client 单例."""
    import app.tasks.pdf_report as pdf_task

    orig = pdf_task._sync_redis_client
    pdf_task._sync_redis_client = None
    yield
    pdf_task._sync_redis_client = orig


class TestRedisJobStorage:
    """1. Redis 任务状态存储."""

    def test_save_and_get_job(self, mock_redis):
        """保存的任务状态可读取."""
        r, store = mock_redis
        from app.tasks.pdf_report import get_job_from_redis, save_job_to_redis

        with patch("app.tasks.pdf_report._get_sync_redis", return_value=r):
            job_data = {"job_id": "j1", "status": "queued", "user_name": "u1"}
            save_job_to_redis("j1", job_data)

            fetched = get_job_from_redis("j1")
            assert fetched is not None
            assert fetched["job_id"] == "j1"
            assert fetched["status"] == "queued"

    def test_get_nonexistent_returns_none(self, mock_redis):
        """读取不存在的任务返回 None."""
        r, _ = mock_redis
        from app.tasks.pdf_report import get_job_from_redis

        with patch("app.tasks.pdf_report._get_sync_redis", return_value=r):
            assert get_job_from_redis("nonexistent") is None

    def test_update_job_merges_fields(self, mock_redis):
        """update_job_in_redis 合并字段并更新 updated_at."""
        r, _ = mock_redis
        from app.tasks.pdf_report import (
            get_job_from_redis,
            save_job_to_redis,
            update_job_in_redis,
        )

        with patch("app.tasks.pdf_report._get_sync_redis", return_value=r):
            save_job_to_redis(
                "j2", {"job_id": "j2", "status": "queued", "updated_at": 100}
            )
            update_job_in_redis("j2", status="running", progress=50)

            job = get_job_from_redis("j2")
            assert job["status"] == "running"
            assert job["progress"] == 50
            assert job["updated_at"] > 100

    def test_update_nonexistent_is_noop(self, mock_redis):
        """更新不存在的任务不抛错."""
        r, _ = mock_redis
        from app.tasks.pdf_report import update_job_in_redis

        with patch("app.tasks.pdf_report._get_sync_redis", return_value=r):
            update_job_in_redis("nonexistent", status="running")

    def test_redis_failure_does_not_raise(self, mock_redis):
        """Redis 异常不抛出, 仅记录日志 (避免影响业务)."""
        r = MagicMock()
        r.set = MagicMock(side_effect=Exception("Redis down"))
        r.sadd = MagicMock(side_effect=Exception("Redis down"))
        from app.tasks.pdf_report import save_job_to_redis

        with patch("app.tasks.pdf_report._get_sync_redis", return_value=r):
            save_job_to_redis("j3", {"job_id": "j3"})  # 不应抛异常


class TestRedisPdfBytesStorage:
    """2. PDF 字节存储."""

    def test_save_and_get_pdf_bytes(self, mock_redis):
        """保存的 PDF 字节可读取."""
        r, store = mock_redis
        from app.tasks.pdf_report import (
            get_pdf_bytes_from_redis,
            save_pdf_bytes_to_redis,
        )

        with patch("app.tasks.pdf_report._get_sync_redis", return_value=r):
            pdf_bytes = b"%PDF-1.4 fake content"
            save_pdf_bytes_to_redis("j1", pdf_bytes)

            fetched = get_pdf_bytes_from_redis("j1")
            assert fetched == pdf_bytes

    def test_get_nonexistent_returns_none(self, mock_redis):
        """读取不存在的 PDF 字节返回 None."""
        r, _ = mock_redis
        from app.tasks.pdf_report import get_pdf_bytes_from_redis

        with patch("app.tasks.pdf_report._get_sync_redis", return_value=r):
            assert get_pdf_bytes_from_redis("nonexistent") is None

    def test_delete_pdf_bytes(self, mock_redis):
        """删除后无法再读取."""
        r, store = mock_redis
        from app.tasks.pdf_report import (
            delete_pdf_bytes_from_redis,
            get_pdf_bytes_from_redis,
            save_pdf_bytes_to_redis,
        )

        with patch("app.tasks.pdf_report._get_sync_redis", return_value=r):
            save_pdf_bytes_to_redis("j2", b"%PDF content")
            delete_pdf_bytes_from_redis("j2")
            assert get_pdf_bytes_from_redis("j2") is None


class TestCountPdfPages:
    """4. _count_pdf_pages 页数统计."""

    def test_single_page(self):
        from app.tasks.pdf_report import _count_pdf_pages

        pdf_bytes = b"%PDF-1.4\n/Type /Page\n<< >>\n"
        assert _count_pdf_pages(pdf_bytes) == 1

    def test_multiple_pages(self):
        from app.tasks.pdf_report import _count_pdf_pages

        pdf_bytes = b"%PDF-1.4\n/Type /Page\n/Type /Page\n/Type /Page\n"
        assert _count_pdf_pages(pdf_bytes) == 3

    def test_excludes_pages_plural(self):
        """/Type /Pages (复数) 不应被计入."""
        from app.tasks.pdf_report import _count_pdf_pages

        pdf_bytes = b"%PDF-1.4\n/Type /Pages\n/Type /Page\n"
        assert _count_pdf_pages(pdf_bytes) == 1

    def test_excludes_page_label_and_mode(self):
        """/Type /PageLabel /PageMode 不应被计入."""
        from app.tasks.pdf_report import _count_pdf_pages

        pdf_bytes = b"%PDF-1.4\n/Type /PageLabel\n/Type /PageMode\n/Type /Page\n"
        assert _count_pdf_pages(pdf_bytes) == 1

    def test_empty_returns_one(self):
        """空 PDF 至少返回 1 页."""
        from app.tasks.pdf_report import _count_pdf_pages

        assert _count_pdf_pages(b"") == 1


class TestCreateInitialJob:
    """5. create_initial_job 初始状态生成."""

    def test_initial_status_is_queued(self):
        from app.tasks.pdf_report import create_initial_job

        job = create_initial_job("j1", "user_a", created_by=1)
        assert job["job_id"] == "j1"
        assert job["status"] == "queued"
        assert job["user_name"] == "user_a"
        assert job["created_by"] == 1
        assert job["progress"] == 0
        assert job["error"] is None
        assert job["started_at"] is None
        assert job["completed_at"] is None

    def test_initial_timestamps_present(self):
        from app.tasks.pdf_report import create_initial_job

        job = create_initial_job("j2", "user_b", created_by=2)
        assert "created_at" in job
        assert "updated_at" in job
        assert job["created_at"] == job["updated_at"]


class TestGeneratePdfReportTask:
    """3. Celery 任务 generate_pdf_report.

    注意: Celery task 的 `request` 是 property (无 setter/deleter),
    无法用 patch.object 直接 patch. 改用 push_request() + run() 模式:
    - push_request(retries=N) 设置 self.request.retries
    - task.run(...) 直接调用底层函数 (不经过 __call__, 不会 push 新 request)
    """

    def test_successful_generation(self, mock_redis):
        """成功生成 PDF 后状态为 completed."""
        r, store = mock_redis
        from app.tasks.pdf_report import (
            create_initial_job,
            generate_pdf_report,
            get_job_from_redis,
            get_pdf_bytes_from_redis,
            save_job_to_redis,
        )

        job_data = create_initial_job("j1", "user_a", created_by=1)
        with patch("app.tasks.pdf_report._get_sync_redis", return_value=r):
            save_job_to_redis("j1", job_data)

            mock_result = MagicMock()
            mock_result.success = True
            mock_result.pdf_bytes = b"%PDF-1.4 fake"
            mock_result.file_size = 14
            mock_result.page_count = 1

            with patch(
                "app.services.pdf_report_service.pdf_report_service.generate_user_risk_report",
                return_value=mock_result,
            ):
                generate_pdf_report.push_request(retries=0)
                try:
                    result = generate_pdf_report.run(
                        job_id="j1",
                        user_name="user_a",
                        risk_level="low",
                        risk_trend=[
                            {"date": "2026-07-03", "score": 30, "level": "low"}
                        ],
                        recommendations=["rest"],
                    )
                finally:
                    generate_pdf_report.pop_request()

            assert result["status"] == "completed"
            assert result["file_size"] == 14
            assert result["page_count"] == 1

            job = get_job_from_redis("j1")
            assert job["status"] == "completed"
            assert job["progress"] == 100

            pdf_bytes = get_pdf_bytes_from_redis("j1")
            assert pdf_bytes == b"%PDF-1.4 fake"

    def test_generation_failure_marks_failed(self, mock_redis):
        """PDFReportService 返回失败时状态为 failed."""
        r, _ = mock_redis
        from app.tasks.pdf_report import (
            create_initial_job,
            generate_pdf_report,
            get_job_from_redis,
            save_job_to_redis,
        )

        job_data = create_initial_job("j2", "user_b", created_by=2)
        with patch("app.tasks.pdf_report._get_sync_redis", return_value=r):
            save_job_to_redis("j2", job_data)

            mock_result = MagicMock()
            mock_result.success = False
            mock_result.error_message = "ReportLab not installed"

            with patch(
                "app.services.pdf_report_service.pdf_report_service.generate_user_risk_report",
                return_value=mock_result,
            ):
                generate_pdf_report.push_request(retries=0)
                try:
                    result = generate_pdf_report.run(
                        job_id="j2",
                        user_name="user_b",
                    )
                finally:
                    generate_pdf_report.pop_request()

            assert result["status"] == "failed"
            assert "ReportLab not installed" in result["error"]

            job = get_job_from_redis("j2")
            assert job["status"] == "failed"
            assert job["error"] == "ReportLab not installed"

    def test_exception_triggers_retry(self, mock_redis):
        """异常时调用 self.retry (重试次数 < 3)."""
        r, _ = mock_redis
        from app.tasks.pdf_report import (
            create_initial_job,
            generate_pdf_report,
            save_job_to_redis,
        )

        job_data = create_initial_job("j3", "user_c", created_by=3)
        with patch("app.tasks.pdf_report._get_sync_redis", return_value=r):
            save_job_to_redis("j3", job_data)

            with patch(
                "app.services.pdf_report_service.pdf_report_service.generate_user_risk_report",
                side_effect=Exception("DB connection lost"),
            ), patch.object(
                generate_pdf_report, "retry", side_effect=Exception("retrying")
            ) as mock_retry:
                generate_pdf_report.push_request(retries=0)
                try:
                    with pytest.raises(Exception, match="retrying"):
                        generate_pdf_report.run(
                            job_id="j3",
                            user_name="user_c",
                        )
                finally:
                    generate_pdf_report.pop_request()

                mock_retry.assert_called_once()

    def test_max_retries_exceeded_returns_failed(self, mock_redis):
        """重试次数达到上限后返回 failed (不抛异常)."""
        r, _ = mock_redis
        from app.tasks.pdf_report import (
            create_initial_job,
            generate_pdf_report,
            get_job_from_redis,
            save_job_to_redis,
        )

        job_data = create_initial_job("j4", "user_d", created_by=4)
        with patch("app.tasks.pdf_report._get_sync_redis", return_value=r):
            save_job_to_redis("j4", job_data)

            with patch(
                "app.services.pdf_report_service.pdf_report_service.generate_user_risk_report",
                side_effect=Exception("persistent error"),
            ), patch.object(generate_pdf_report, "retry") as mock_retry:
                generate_pdf_report.push_request(retries=3)
                try:
                    result = generate_pdf_report.run(
                        job_id="j4",
                        user_name="user_d",
                    )
                finally:
                    generate_pdf_report.pop_request()

            assert result["status"] == "failed"
            assert "persistent error" in result["error"]
            mock_retry.assert_not_called()

            job = get_job_from_redis("j4")
            assert job["status"] == "failed"
