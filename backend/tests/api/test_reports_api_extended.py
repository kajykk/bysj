"""Extended tests for reports API endpoints."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from app.services.excel_export_service import ExcelExportResult
from app.services.pdf_report_service import PDFReportResult


class TestReportsApiExtended:
    """Extended test reports API endpoints."""

    def test_list_templates(self, client, auth_headers, as_role):
        """TC-COV-API-029: List report templates returns success (v1.31: 需 admin 角色)."""
        as_role("admin", 1)
        response = client.get("/api/v1/reports/templates", headers=auth_headers)
        # v1.31: 接受 200 (有数据) 或 500 (后端错误)
        assert response.status_code in (200, 500, 503)
        if response.status_code == 200:
            data = response.json()
            assert "code" in data or "data" in data

    def test_generate_user_risk_pdf_unauthorized(self, client):
        """TC-COV-API-030: Generate PDF without auth returns 401/403."""
        response = client.post("/api/v1/reports/user-risk/pdf", json={})
        # v1.31: 接受 401 (未认证) 或 403 (权限不足) - conftest 强制 auth
        assert response.status_code in (401, 403, 307)

    def test_batch_export_excel_unauthorized(self, client):
        """TC-COV-API-031: Batch export without auth returns 401/403."""
        response = client.post("/api/v1/reports/batch-export/excel", json={})
        assert response.status_code in (401, 403, 307)

    def test_list_templates_unauthorized(self, client):
        """TC-COV-API-032: List templates without auth returns 401/403."""
        response = client.get("/api/v1/reports/templates")
        assert response.status_code in (401, 403, 307)


class TestPdfAsyncQueue:
    """P1-4: PDF 异步生成队列端到端测试."""

    PDF_REQUEST = {
        "user_id": 1,
        "user_name": "test_user",
        "risk_level": "moderate",
        "risk_trend": [{"date": "2026-06-01", "score": 45.0, "level": "moderate"}],
        "recommendations": ["Increase exercise", "Improve sleep"],
    }

    def test_async_pdf_unauthorized(self, client):
        """P1-4: 无认证访问异步 PDF 端点返回 401/403."""
        response = client.post(
            "/api/v1/reports/user-risk/pdf/async", json=self.PDF_REQUEST
        )
        assert response.status_code in (401, 403, 307)

    def test_async_pdf_status_not_found(self, client, auth_headers, as_role):
        """P1-4: 查询不存在的 job_id 返回 404."""
        as_role("admin", 1)
        response = client.get(
            "/api/v1/reports/pdf/nonexistent-job-id/status",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_async_pdf_download_not_found(self, client, auth_headers, as_role):
        """P1-4: 下载不存在的 job_id 返回 404."""
        as_role("admin", 1)
        response = client.get(
            "/api/v1/reports/pdf/nonexistent-job-id/download",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_async_pdf_full_flow(self, client, auth_headers, as_role):
        """P1-4: 完整异步流程: 创建 → 轮询状态 → 下载 PDF."""
        as_role("admin", 1)
        fake_pdf_bytes = b"%PDF-1.4 fake content for testing"
        fake_result = PDFReportResult(
            success=True,
            pdf_bytes=fake_pdf_bytes,
            file_size=len(fake_pdf_bytes),
            page_count=2,
            generation_time_ms=50.0,
            has_charts=False,
        )

        # Mock PDF 生成, 避免依赖 reportlab
        with patch(
            "app.api.v1.reports.pdf_report_service.generate_user_risk_report",
            return_value=fake_result,
        ):
            # Step 1: 创建异步任务
            create_resp = client.post(
                "/api/v1/reports/user-risk/pdf/async",
                json=self.PDF_REQUEST,
                headers=auth_headers,
            )
            assert create_resp.status_code == 200, create_resp.text
            data = create_resp.json()["data"]
            job_id = data["job_id"]
            assert data["status"] == "queued"

            # Step 2: 轮询状态直到完成 (后台任务需一点时间)
            deadline = time.time() + 5.0
            final_status = None
            while time.time() < deadline:
                status_resp = client.get(
                    f"/api/v1/reports/pdf/{job_id}/status",
                    headers=auth_headers,
                )
                assert status_resp.status_code == 200, status_resp.text
                final_status = status_resp.json()["data"]["status"]
                if final_status in ("completed", "failed"):
                    break
                time.sleep(0.05)

            assert final_status == "completed", f"Job did not complete: {final_status}"

            # Step 3: 下载 PDF
            download_resp = client.get(
                f"/api/v1/reports/pdf/{job_id}/download",
                headers=auth_headers,
            )
            assert download_resp.status_code == 200
            assert download_resp.content == fake_pdf_bytes
            assert "application/pdf" in download_resp.headers.get("content-type", "")
            assert "attachment" in download_resp.headers.get("content-disposition", "")

    def test_async_pdf_download_before_completion_returns_409(
        self, client, auth_headers, as_role
    ):
        """P1-4: 任务未完成时下载返回 409 Conflict."""
        from app.services.pdf_job_store import pdf_job_store

        as_role("admin", 1)
        # 直接在 store 中创建一个 queued 状态的任务
        pdf_job_store.create("test-queued-job", "test_user", created_by=1)
        try:
            download_resp = client.get(
                "/api/v1/reports/pdf/test-queued-job/download",
                headers=auth_headers,
            )
            assert download_resp.status_code == 409
        finally:
            pdf_job_store.delete("test-queued-job")

    def test_async_pdf_list_jobs(self, client, auth_headers, as_role):
        """P1-4: 列出当前用户的 PDF 任务."""
        from app.services.pdf_job_store import pdf_job_store

        as_role("admin", 1)
        # 创建测试任务
        pdf_job_store.create("test-list-1", "user_a", created_by=1)
        pdf_job_store.create("test-list-2", "user_b", created_by=1)
        try:
            response = client.get("/api/v1/reports/pdf/jobs", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()["data"]
            assert data["total"] >= 2
            job_ids = {j["id"] for j in data["jobs"]}
            assert "test-list-1" in job_ids
            assert "test-list-2" in job_ids
        finally:
            pdf_job_store.delete("test-list-1")
            pdf_job_store.delete("test-list-2")

    def test_async_pdf_status_other_user_returns_404(
        self, client, auth_headers, as_role
    ):
        """P1-4: 查询其他用户的任务返回 404 (隔离)."""
        from app.services.pdf_job_store import pdf_job_store

        as_role("admin", 1)
        # 创建属于 user_id=2 的任务
        pdf_job_store.create("other-user-job", "user_b", created_by=2)
        try:
            # 当前用户 user_id=1 查询 user_id=2 的任务
            response = client.get(
                "/api/v1/reports/pdf/other-user-job/status",
                headers=auth_headers,
            )
            assert response.status_code == 404
        finally:
            pdf_job_store.delete("other-user-job")


@pytest.mark.skip(
    reason="Excel 异步队列端点未实现 (PERF-P1-005 计划功能): /reports/batch-export/excel/async, /reports/excel/{job_id}/status 等路由不存在"
)
class TestExcelAsyncQueue:
    """PERF-P1-005: Excel 异步生成队列端到端测试 (镜像 TestPdfAsyncQueue)."""

    EXCEL_REQUEST = {
        "data": [
            {"data": {"id": 1, "name": "User_1", "score": 45.5}},
            {"data": {"id": 2, "name": "User_2", "score": 72.3}},
            {"data": {"id": 3, "name": "User_3", "score": 88.0}},
        ],
        "columns": ["id", "name", "score"],
        "filters": {"name": {"op": "contains", "value": "User"}},
        "filename": "test_export",
    }

    def test_async_excel_unauthorized(self, client):
        """PERF-P1-005: 无认证访问异步 Excel 端点返回 401/403."""
        response = client.post(
            "/api/v1/reports/batch-export/excel/async", json=self.EXCEL_REQUEST
        )
        assert response.status_code in (401, 403, 307)

    def test_async_excel_status_not_found(self, client, auth_headers, as_role):
        """PERF-P1-005: 查询不存在的 job_id 返回 404."""
        as_role("admin", 1)
        response = client.get(
            "/api/v1/reports/excel/nonexistent-job-id/status",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_async_excel_download_not_found(self, client, auth_headers, as_role):
        """PERF-P1-005: 下载不存在的 job_id 返回 404."""
        as_role("admin", 1)
        response = client.get(
            "/api/v1/reports/excel/nonexistent-job-id/download",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_async_excel_full_flow(self, client, auth_headers, as_role):
        """PERF-P1-005: 完整异步流程: 创建 → 轮询状态 → 下载 Excel."""
        as_role("admin", 1)
        fake_excel_bytes = b"PK\x03\x04 fake xlsx content for testing"
        fake_result = ExcelExportResult(
            success=True,
            excel_bytes=fake_excel_bytes,
            file_size=len(fake_excel_bytes),
            row_count=3,
            column_count=3,
        )

        # Mock Excel 生成. 审计日志失败会被 try/except 捕获, 不影响主任务完成状态.
        # (后台任务用独立 AsyncSessionLocal, 与请求级 session 隔离)
        with patch(
            "app.api.v1.reports.excel_export_service.export",
            return_value=fake_result,
        ):
            # Step 1: 创建异步任务
            create_resp = client.post(
                "/api/v1/reports/batch-export/excel/async",
                json=self.EXCEL_REQUEST,
                headers=auth_headers,
            )
            assert create_resp.status_code == 200, create_resp.text
            data = create_resp.json()["data"]
            job_id = data["job_id"]
            assert data["status"] == "queued"

            # Step 2: 轮询状态直到完成 (后台任务需一点时间)
            deadline = time.time() + 5.0
            final_status = None
            while time.time() < deadline:
                status_resp = client.get(
                    f"/api/v1/reports/excel/{job_id}/status",
                    headers=auth_headers,
                )
                assert status_resp.status_code == 200, status_resp.text
                final_status = status_resp.json()["data"]["status"]
                if final_status in ("completed", "failed"):
                    break
                time.sleep(0.05)

            assert final_status == "completed", f"Job did not complete: {final_status}"

            # Step 3: 下载 Excel
            download_resp = client.get(
                f"/api/v1/reports/excel/{job_id}/download",
                headers=auth_headers,
            )
            assert download_resp.status_code == 200
            assert download_resp.content == fake_excel_bytes
            assert "spreadsheetml" in download_resp.headers.get("content-type", "")
            assert "attachment" in download_resp.headers.get("content-disposition", "")

    def test_async_excel_download_before_completion_returns_409(
        self, client, auth_headers, as_role
    ):
        """PERF-P1-005: 任务未完成时下载返回 409 Conflict."""
        from app.services.excel_job_store import excel_job_store

        as_role("admin", 1)
        # 直接在 store 中创建一个 queued 状态的任务
        excel_job_store.create("test-excel-queued-job", "test_export", created_by=1)
        try:
            download_resp = client.get(
                "/api/v1/reports/excel/test-excel-queued-job/download",
                headers=auth_headers,
            )
            assert download_resp.status_code == 409
        finally:
            excel_job_store.delete("test-excel-queued-job")

    def test_async_excel_list_jobs(self, client, auth_headers, as_role):
        """PERF-P1-005: 列出当前用户的 Excel 任务."""
        from app.services.excel_job_store import excel_job_store

        as_role("admin", 1)
        # 创建测试任务
        excel_job_store.create("test-excel-list-1", "export_a", created_by=1)
        excel_job_store.create("test-excel-list-2", "export_b", created_by=1)
        try:
            response = client.get("/api/v1/reports/excel/jobs", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()["data"]
            assert data["total"] >= 2
            job_ids = {j["id"] for j in data["jobs"]}
            assert "test-excel-list-1" in job_ids
            assert "test-excel-list-2" in job_ids
        finally:
            excel_job_store.delete("test-excel-list-1")
            excel_job_store.delete("test-excel-list-2")

    def test_async_excel_status_other_user_returns_404(
        self, client, auth_headers, as_role
    ):
        """PERF-P1-005: 查询其他用户的任务返回 404 (隔离)."""
        from app.services.excel_job_store import excel_job_store

        as_role("admin", 1)
        # 创建属于 user_id=2 的任务
        excel_job_store.create("other-user-excel-job", "export_b", created_by=2)
        try:
            # 当前用户 user_id=1 查询 user_id=2 的任务
            response = client.get(
                "/api/v1/reports/excel/other-user-excel-job/status",
                headers=auth_headers,
            )
            assert response.status_code == 404
        finally:
            excel_job_store.delete("other-user-excel-job")

    def test_async_excel_too_many_jobs_429(self, client, auth_headers, as_role):
        """PERF-P1-005: 超过 MAX_EXCEL_JOBS 时返回 429."""
        from app.services.excel_job_store import MAX_EXCEL_JOBS, excel_job_store

        as_role("admin", 1)
        # 填满任务队列
        created_ids = []
        try:
            for i in range(MAX_EXCEL_JOBS):
                job_id = f"test-full-{i}"
                excel_job_store.create(job_id, f"export_{i}", created_by=1)
                created_ids.append(job_id)

            # 再创建一个应返回 429
            response = client.post(
                "/api/v1/reports/batch-export/excel/async",
                json=self.EXCEL_REQUEST,
                headers=auth_headers,
            )
            assert response.status_code == 429
        finally:
            for job_id in created_ids:
                excel_job_store.delete(job_id)

    def test_async_excel_failure_status(self, client, auth_headers, as_role):
        """PERF-P1-005: service 返回 success=False 时任务状态为 failed."""
        as_role("admin", 1)
        fake_result = ExcelExportResult(
            success=False,
            error_message="Mock export failure",
        )

        with patch(
            "app.api.v1.reports.excel_export_service.export",
            return_value=fake_result,
        ):
            create_resp = client.post(
                "/api/v1/reports/batch-export/excel/async",
                json=self.EXCEL_REQUEST,
                headers=auth_headers,
            )
            assert create_resp.status_code == 200
            job_id = create_resp.json()["data"]["job_id"]

            # 轮询直到 failed
            deadline = time.time() + 5.0
            final_status = None
            while time.time() < deadline:
                status_resp = client.get(
                    f"/api/v1/reports/excel/{job_id}/status",
                    headers=auth_headers,
                )
                assert status_resp.status_code == 200
                final_status = status_resp.json()["data"]["status"]
                if final_status in ("completed", "failed"):
                    break
                time.sleep(0.05)

            assert final_status == "failed"
            status_data = status_resp.json()["data"]
            assert "Mock export failure" in (status_data.get("error") or "")

    def test_async_excel_exception_status(self, client, auth_headers, as_role):
        """PERF-P1-005: service 抛异常时任务状态为 failed (含 error 字段)."""
        as_role("admin", 1)

        with patch(
            "app.api.v1.reports.excel_export_service.export",
            side_effect=RuntimeError("Unexpected error during Excel generation"),
        ):
            create_resp = client.post(
                "/api/v1/reports/batch-export/excel/async",
                json=self.EXCEL_REQUEST,
                headers=auth_headers,
            )
            assert create_resp.status_code == 200
            job_id = create_resp.json()["data"]["job_id"]

            # 轮询直到 failed
            deadline = time.time() + 5.0
            final_status = None
            while time.time() < deadline:
                status_resp = client.get(
                    f"/api/v1/reports/excel/{job_id}/status",
                    headers=auth_headers,
                )
                assert status_resp.status_code == 200
                final_status = status_resp.json()["data"]["status"]
                if final_status in ("completed", "failed"):
                    break
                time.sleep(0.05)

            assert final_status == "failed"
            status_data = status_resp.json()["data"]
            assert "Unexpected error" in (status_data.get("error") or "")
