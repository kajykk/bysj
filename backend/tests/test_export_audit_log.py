"""SEC-P1-003 回归测试：数据导出端点审计日志

验证 4 个数据导出端点在导出成功后写入 OperationLog 审计日志：

| 端点                                    | 函数                  | action_type                       | 角色   |
|-----------------------------------------|----------------------|-----------------------------------|--------|
| GET  /api/v1/user/gdpr/export           | export_my_data       | user.gdpr.export_self             | user   |
| GET  /api/v1/user/risk/export           | export_risk          | user.risk.export                  | user   |
| POST /api/v1/reports/batch-export/excel | batch_export_excel   | admin.report.batch_export_excel   | admin  |
| GET  /api/v1/admin/crisis-events/export | export_crisis_events | admin.crisis.export               | admin  |

每个测试验证：
- HTTP 状态码 200/422 校验
- OperationLog 写入 (action_type / operator_id / operator_role / target_type)
- detail 字段为合法 JSON
- ip_address 在测试客户端中可能为 None (TestClient 无 client.host)
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import OperationLog
from tests.conftest import run

# ===== 1. GDPR 自助导出 =====


class TestGdprExportAuditLog:
    """GET /api/v1/user/gdpr/export → user.gdpr.export_self"""

    def test_export_writes_audit_log(
        self, client: TestClient, as_role, seeded_user_id, db_session: AsyncSession
    ):
        """用户导出自己的数据 → 写入 user.gdpr.export_self 审计日志."""
        as_role("user", seeded_user_id)
        res = client.get("/api/v1/user/gdpr/export")
        assert res.status_code == 200
        # 流式 JSON 响应应包含 export_metadata
        body = res.json()
        assert "export_metadata" in body

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "user.gdpr.export_self",
                    OperationLog.operator_id == seeded_user_id,
                )
            )
            return result.scalar_one_or_none()

        log = run(_check())
        assert log is not None, "审计日志未写入: user.gdpr.export_self"
        assert log.operator_role == "user"
        assert log.target_type == "user"
        assert log.target_id == seeded_user_id
        # detail 应为合法 JSON, 包含 export_id
        detail = json.loads(log.detail)
        assert "export_id" in detail

    def test_export_audit_log_detail_truncated(
        self, client: TestClient, as_role, seeded_user_id, db_session: AsyncSession
    ):
        """detail 字段长度不超过 5000 字符 (与 admin.py 其他审计日志一致)."""
        as_role("user", seeded_user_id)
        res = client.get("/api/v1/user/gdpr/export")
        assert res.status_code == 200

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "user.gdpr.export_self"
                )
            )
            return result.scalar_one()

        log = run(_check())
        assert log.detail is not None
        assert len(log.detail) <= 5000


# ===== 2. 用户风险数据导出 =====


class TestUserRiskExportAuditLog:
    """GET /api/v1/user/risk/export → user.risk.export"""

    def test_export_json_writes_audit_log(
        self, client: TestClient, as_role, seeded_user_id, db_session: AsyncSession
    ):
        """用户导出自己的风险数据 (json) → 写入 user.risk.export 审计日志."""
        as_role("user", seeded_user_id)
        res = client.get("/api/v1/user/risk/export?format=json&days=30")
        assert res.status_code == 200

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "user.risk.export",
                    OperationLog.operator_id == seeded_user_id,
                )
            )
            return result.scalar_one_or_none()

        log = run(_check())
        assert log is not None, "审计日志未写入: user.risk.export"
        assert log.operator_role == "user"
        assert log.target_type == "user"
        assert log.target_id == seeded_user_id
        detail = json.loads(log.detail)
        assert detail["format"] == "json"
        assert detail["days"] == 30

    def test_export_csv_writes_audit_log(
        self, client: TestClient, as_role, seeded_user_id, db_session: AsyncSession
    ):
        """用户导出自己的风险数据 (csv) → 同样写入审计日志."""
        as_role("user", seeded_user_id)
        res = client.get("/api/v1/user/risk/export?format=csv&days=7")
        assert res.status_code == 200

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "user.risk.export",
                    OperationLog.operator_id == seeded_user_id,
                )
            )
            return result.scalar_one()

        log = run(_check())
        detail = json.loads(log.detail)
        assert detail["format"] == "csv"
        assert detail["days"] == 7

    def test_export_days_param_recorded(
        self, client: TestClient, as_role, seeded_user_id, db_session: AsyncSession
    ):
        """审计日志 detail 中应记录请求的 days 参数."""
        as_role("user", seeded_user_id)
        res = client.get("/api/v1/user/risk/export?format=json&days=90")
        assert res.status_code == 200

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "user.risk.export"
                )
            )
            return result.scalar_one()

        log = run(_check())
        detail = json.loads(log.detail)
        assert detail["days"] == 90


# ===== 3. 管理员批量 Excel 导出 =====


class TestBatchExportExcelAuditLog:
    """POST /api/v1/reports/batch-export/excel → admin.report.batch_export_excel"""

    def _make_payload(self, **overrides) -> dict:
        payload = {
            "data": [{"data": {"name": "alice", "score": 80}}],
            "columns": ["name", "score"],
            "filters": {"risk_level": 3},
            "filename": "test_export",
        }
        payload.update(overrides)
        return payload

    def test_batch_export_writes_audit_log(
        self, client: TestClient, as_role, seeded_user_id, db_session: AsyncSession
    ):
        """管理员批量导出 Excel → 写入 admin.report.batch_export_excel 审计日志."""
        as_role("admin", 3)
        res = client.post(
            "/api/v1/reports/batch-export/excel",
            json=self._make_payload(),
        )
        assert res.status_code == 200, f"导出失败: {res.text}"

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "admin.report.batch_export_excel",
                    OperationLog.operator_id == 3,
                )
            )
            return result.scalar_one_or_none()

        log = run(_check())
        assert log is not None, "审计日志未写入: admin.report.batch_export_excel"
        assert log.operator_role == "admin"
        assert log.target_type == "report"
        # target_id 为 None (报告类导出无特定目标对象)
        assert log.target_id is None
        detail = json.loads(log.detail)
        assert detail["filename"] == "test_export"
        assert detail["row_count"] == 1
        assert "name" in detail["columns"]
        assert detail["filters"] == {"risk_level": 3}
        assert detail["file_size"] > 0

    def test_batch_export_failure_no_audit_log(
        self,
        client: TestClient,
        as_role,
        seeded_user_id,
        db_session: AsyncSession,
        monkeypatch,
    ):
        """导出失败时 (service 返回 success=False) 不应写入审计日志."""
        from app.services import excel_export_service as exc_svc_mod
        from app.services.excel_export_service import ExcelExportResult

        def _fail_export(self, **kwargs):
            return ExcelExportResult(success=False, error_message="mock failure")

        monkeypatch.setattr(exc_svc_mod.ExcelExportService, "export", _fail_export)

        as_role("admin", 3)
        res = client.post(
            "/api/v1/reports/batch-export/excel",
            json=self._make_payload(),
        )
        assert res.status_code == 500

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "admin.report.batch_export_excel"
                )
            )
            return result.scalars().all()

        logs = run(_check())
        assert len(logs) == 0, "失败导出不应写入审计日志"

    def test_batch_export_records_filename_sanitized(
        self, client: TestClient, as_role, seeded_user_id, db_session: AsyncSession
    ):
        """filename 中的特殊字符应被清洗后写入 detail."""
        as_role("admin", 3)
        res = client.post(
            "/api/v1/reports/batch-export/excel",
            json=self._make_payload(filename="../../etc/passwd"),
        )
        assert res.status_code == 200

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "admin.report.batch_export_excel"
                )
            )
            return result.scalar_one()

        log = run(_check())
        detail = json.loads(log.detail)
        # 文件名中的 / 和 . 应被替换为 _
        assert "/" not in detail["filename"]
        assert ".." not in detail["filename"]


# ===== 4. 管理员危机事件 CSV 导出 =====


class TestCrisisEventsExportAuditLog:
    """GET /api/v1/admin/crisis-events/export → admin.crisis.export"""

    def test_export_writes_audit_log(
        self, client: TestClient, as_role, seeded_user_id, db_session: AsyncSession
    ):
        """管理员导出危机事件 CSV → 写入 admin.crisis.export 审计日志."""
        as_role("admin", 3)
        end = date.today()
        start = end - timedelta(days=7)
        res = client.get(
            f"/api/v1/admin/crisis-events/export?start_date={start.isoformat()}&end_date={end.isoformat()}"
        )
        assert res.status_code == 200, f"导出失败: {res.text}"
        # 应返回 CSV 文本
        assert "crisis_events_" in res.headers.get("content-disposition", "")

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "admin.crisis.export",
                    OperationLog.operator_id == 3,
                )
            )
            return result.scalar_one_or_none()

        log = run(_check())
        assert log is not None, "审计日志未写入: admin.crisis.export"
        assert log.operator_role == "admin"
        assert log.target_type == "crisis_event"
        assert log.target_id is None
        detail = json.loads(log.detail)
        assert detail["start_date"] == start.isoformat()
        assert detail["end_date"] == end.isoformat()
        assert "filename" in detail
        assert "content_size" in detail
        assert detail["content_size"] > 0

    def test_export_invalid_date_range_422_no_audit_log(
        self, client: TestClient, as_role, seeded_user_id, db_session: AsyncSession
    ):
        """日期范围校验失败 (start > end) → 422, 不写入审计日志."""
        as_role("admin", 3)
        # 故意让 start_date > end_date
        res = client.get(
            "/api/v1/admin/crisis-events/export?start_date=2026-01-10&end_date=2026-01-01"
        )
        assert res.status_code == 422

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "admin.crisis.export"
                )
            )
            return result.scalars().all()

        logs = run(_check())
        assert len(logs) == 0, "日期校验失败不应写入审计日志"

    def test_export_range_exceeds_90_days_422(
        self, client: TestClient, as_role, seeded_user_id, db_session: AsyncSession
    ):
        """日期范围超过 90 天 → 422, 不写入审计日志."""
        as_role("admin", 3)
        end = date.today()
        start = end - timedelta(days=100)  # 超过 90 天
        res = client.get(
            f"/api/v1/admin/crisis-events/export?start_date={start.isoformat()}&end_date={end.isoformat()}"
        )
        assert res.status_code == 422

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "admin.crisis.export"
                )
            )
            return result.scalars().all()

        logs = run(_check())
        assert len(logs) == 0, "超过 90 天范围校验失败不应写入审计日志"

    def test_export_records_filename(
        self, client: TestClient, as_role, seeded_user_id, db_session: AsyncSession
    ):
        """审计日志 detail 应记录 filename 字段."""
        as_role("admin", 3)
        end = date.today()
        start = end - timedelta(days=1)
        res = client.get(
            f"/api/v1/admin/crisis-events/export?start_date={start.isoformat()}&end_date={end.isoformat()}"
        )
        assert res.status_code == 200

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "admin.crisis.export"
                )
            )
            return result.scalar_one()

        log = run(_check())
        detail = json.loads(log.detail)
        assert "crisis_events_" in detail["filename"]
        assert detail["filename"].endswith(".csv")


# ===== 5. 跨端点: 权限校验 =====


class TestExportEndpointPermission:
    """非授权角色访问导出端点 → 403, 不写入审计日志."""

    def test_user_cannot_access_admin_crisis_export(
        self, client: TestClient, as_role, seeded_user_id, db_session: AsyncSession
    ):
        """普通用户访问管理员危机事件导出 → 403, 无审计日志."""
        as_role("user", seeded_user_id)
        end = date.today()
        start = end - timedelta(days=7)
        res = client.get(
            f"/api/v1/admin/crisis-events/export?start_date={start.isoformat()}&end_date={end.isoformat()}"
        )
        assert res.status_code == 403

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "admin.crisis.export"
                )
            )
            return result.scalars().all()

        logs = run(_check())
        assert len(logs) == 0

    def test_user_cannot_access_admin_batch_export(
        self, client: TestClient, as_role, seeded_user_id, db_session: AsyncSession
    ):
        """普通用户访问管理员批量 Excel 导出 → 403, 无审计日志."""
        as_role("user", seeded_user_id)
        res = client.post(
            "/api/v1/reports/batch-export/excel",
            json={"data": [{"data": {"x": 1}}]},
        )
        assert res.status_code == 403

        async def _check():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "admin.report.batch_export_excel"
                )
            )
            return result.scalars().all()

        logs = run(_check())
        assert len(logs) == 0


# ===== 6. 源代码结构校验 =====


class TestSourceStructure:
    """静态校验 4 个端点源码中均包含审计日志写入代码."""

    def test_gdpr_export_has_audit_log(self):
        import inspect

        from app.api.v1 import gdpr

        src = inspect.getsource(gdpr.export_my_data)
        assert "OperationLog" in src
        assert "user.gdpr.export_self" in src
        assert "await db.commit()" in src

    def test_user_risk_export_has_audit_log(self):
        import inspect

        from app.api.v1 import user_risk

        src = inspect.getsource(user_risk.export_risk)
        assert "OperationLog" in src
        assert "user.risk.export" in src
        assert "await db.commit()" in src

    def test_reports_batch_export_has_audit_log(self):
        import inspect

        from app.api.v1 import reports

        src = inspect.getsource(reports.batch_export_excel)
        assert "OperationLog" in src
        assert "admin.report.batch_export_excel" in src
        assert "await db.commit()" in src

    def test_admin_crisis_export_has_audit_log(self):
        import inspect

        from app.api.v1 import admin

        src = inspect.getsource(admin.export_crisis_events)
        assert "OperationLog" in src
        assert "admin.crisis.export" in src
        assert "await db.commit()" in src

    def test_all_action_types_distinct(self):
        """4 个 action_type 应互不相同, 避免审计日志聚合时混淆."""
        action_types = [
            "user.gdpr.export_self",
            "user.risk.export",
            "admin.report.batch_export_excel",
            "admin.crisis.export",
        ]
        assert len(set(action_types)) == 4
