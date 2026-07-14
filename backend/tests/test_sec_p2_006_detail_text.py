"""SEC-P2-006: OperationLog.detail 字段类型 + 截断移除测试.

验证:
1. SQLAlchemy 模型层 detail 字段为 Text 类型 (无长度限制)
2. 业务代码中所有 [:5000] 截断已移除 (28 处)
3. 创建 OperationLog 时不再有截断逻辑
"""

from __future__ import annotations

import inspect
from pathlib import Path

from app.models.admin import OperationLog
from app.services.admin_service import AdminService


class TestDetailFieldType:
    """detail 字段类型测试."""

    def test_detail_is_text_type(self):
        """detail 字段应为 Text 类型 (无长度限制)."""
        from sqlalchemy import Text

        detail_col = OperationLog.__table__.columns.get("detail")
        assert detail_col is not None
        assert isinstance(detail_col.type, Text)

    def test_detail_no_length_attribute(self):
        """Text 类型不应有 length 属性 (与 String 区分)."""
        detail_col = OperationLog.__table__.columns.get("detail")
        # Text 类型没有 length 属性, String(N) 有 length=N
        assert not hasattr(detail_col.type, "length") or detail_col.type.length is None

    def test_detail_nullable(self):
        """detail 字段允许为 NULL."""
        detail_col = OperationLog.__table__.columns.get("detail")
        assert detail_col.nullable is True

    def test_ip_address_is_string(self):
        """ip_address 字段为 String(50) (区分于 detail 的 Text)."""
        from sqlalchemy import String

        ip_col = OperationLog.__table__.columns.get("ip_address")
        assert isinstance(ip_col.type, String)
        assert ip_col.type.length == 50


class TestNoTruncationInBusinessCode:
    """业务代码中不应有 [:5000] 截断逻辑."""

    def _get_app_files(self) -> list[Path]:
        """获取 backend/app 下所有 .py 文件."""
        backend_app = Path(__file__).resolve().parent.parent / "app"
        return list(backend_app.rglob("*.py"))

    def test_no_5000_truncation_in_app(self):
        """app/ 目录下不应有 [:5000] 字符串截断 (SEC-P2-006)."""
        offending_files = []
        for py_file in self._get_app_files():
            content = py_file.read_text(encoding="utf-8")
            if "[:5000]" in content:
                offending_files.append(str(py_file.relative_to(py_file.parents[2])))
        assert not offending_files, (
            f"SEC-P2-006: 发现遗留的 [:5000] 截断: {offending_files}"
        )

    def test_no_5000_truncation_in_admin_service(self):
        """admin_service.py 中不应有 [:5000] 截断."""
        source = inspect.getsource(AdminService)
        assert "[:5000]" not in source

    def test_no_truncation_in_mask_old_ips(self):
        """mask_old_ips 方法不应有截断 (新代码不应引入截断)."""
        if hasattr(AdminService, "mask_old_ips"):
            source = inspect.getsource(AdminService.mask_old_ips)
            assert "[:5000]" not in source
            assert "[:1000]" not in source
            assert "[:2000]" not in source


class TestOperationLogCreationNoTruncation:
    """OperationLog 创建时不应截断 detail."""

    def test_admin_service_log_methods_no_truncation(self):
        """AdminService 中所有 OperationLog 创建处无截断."""
        # 检查整个 AdminService 源码, 不应出现 detail=...[:5000]
        source = inspect.getsource(AdminService)
        # 检查是否有 detail=...[:N] 模式
        lines = source.split("\n")
        for i, line in enumerate(lines):
            if "detail=" in line and "[:5000]" in line:
                pytest_fail_line = line.strip()
                raise AssertionError(
                    f"SEC-P2-006: AdminService 行 {i + 1} 仍有截断: {pytest_fail_line}"
                )


class TestDetailTextTypeValidation:
    """Text 类型字段写入验证 (确认支持大文本)."""

    def test_long_text_can_be_assigned(self):
        """OperationLog.detail 可以接受任意长度的字符串 (Text 类型)."""
        # 创建实例但不入库, 仅验证字段赋值
        long_text = "x" * 100000  # 100KB
        log = OperationLog(
            operator_id=1,
            operator_role="admin",
            action_type="test",
            detail=long_text,
        )
        assert log.detail == long_text
        assert len(log.detail) == 100000

    def test_short_text_can_be_assigned(self):
        """OperationLog.detail 接受短文本."""
        log = OperationLog(
            operator_id=1,
            operator_role="admin",
            action_type="test",
            detail="short",
        )
        assert log.detail == "short"

    def test_none_can_be_assigned(self):
        """OperationLog.detail 接受 None (nullable)."""
        log = OperationLog(
            operator_id=1,
            operator_role="admin",
            action_type="test",
            detail=None,
        )
        assert log.detail is None
