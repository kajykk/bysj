"""RES-P2-002 / RES-P2-003 / SEC-P2-001 专项测试.

验证三项 P2 任务:
- RES-P2-002: pdf_report_service 流式响应 (BytesIO + 分块 StreamingResponse)
- RES-P2-003: excel_export_service 流式输出 (export_to_stream + 自动切换)
- SEC-P2-001: JWT HS256 → RS256 非对称签名迁移
"""

from __future__ import annotations

import inspect
import io
from unittest.mock import patch

import pytest


# ============================================================================
# RES-P2-002: pdf_report_service 流式响应
# ============================================================================


class TestPdfStreamResult:
    """RES-P2-002: PDFStreamResult 数据类测试."""

    def test_pdf_stream_result_dataclass_exists(self) -> None:
        """PDFStreamResult dataclass 已定义."""
        from app.services.pdf_report_service import PDFStreamResult

        assert PDFStreamResult is not None

    def test_pdf_stream_result_fields(self) -> None:
        """PDFStreamResult 有必要字段."""
        from app.services.pdf_report_service import PDFStreamResult

        result = PDFStreamResult(success=True)
        assert hasattr(result, "success")
        assert hasattr(result, "stream")
        assert hasattr(result, "file_size")
        assert hasattr(result, "page_count")
        assert hasattr(result, "generation_time_ms")
        assert hasattr(result, "error_message")
        assert hasattr(result, "has_charts")

    def test_pdf_stream_result_to_dict(self) -> None:
        """PDFStreamResult.to_dict() 方法正常工作."""
        from app.services.pdf_report_service import PDFStreamResult

        result = PDFStreamResult(
            success=True,
            file_size=1024,
            page_count=5,
            generation_time_ms=100.5,
            has_charts=True,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["file_size"] == 1024
        assert d["page_count"] == 5
        assert d["has_charts"] is True


class TestPdfStreamService:
    """RES-P2-002: PDFReportService.generate_pdf_stream 测试."""

    def test_generate_pdf_stream_method_exists(self) -> None:
        """generate_pdf_stream 方法存在."""
        from app.services.pdf_report_service import PDFReportService

        assert hasattr(PDFReportService, "generate_pdf_stream")
        assert callable(getattr(PDFReportService, "generate_pdf_stream"))

    def test_generate_user_risk_report_stream_method_exists(self) -> None:
        """generate_user_risk_report_stream 方法存在."""
        from app.services.pdf_report_service import PDFReportService

        assert hasattr(PDFReportService, "generate_user_risk_report_stream")
        assert callable(getattr(PDFReportService, "generate_user_risk_report_stream"))

    def test_generate_pdf_stream_returns_stream_result(self) -> None:
        """generate_pdf_stream 返回 PDFStreamResult."""
        from app.services.pdf_report_service import (
            PDFReportService,
            PDFStreamResult,
            ReportData,
        )

        service = PDFReportService()
        report_data = ReportData(title="Test Report")
        result = service.generate_pdf_stream(report_data)
        assert isinstance(result, PDFStreamResult)

    def test_generate_pdf_stream_success_returns_bytesio(self) -> None:
        """成功时返回 BytesIO 流."""
        from app.services.pdf_report_service import (
            PDFReportService,
            ReportData,
        )

        service = PDFReportService()
        report_data = ReportData(
            title="Test Report",
            sections=[{"title": "Section 1", "content": "Content 1"}],
        )
        result = service.generate_pdf_stream(report_data)
        assert result.success is True
        assert result.stream is not None
        assert isinstance(result.stream, io.BytesIO)
        assert result.file_size > 0

    def test_generate_pdf_stream_no_getvalue_copy(self) -> None:
        """generate_pdf_stream 不调用 getvalue() (避免 bytes 拷贝).

        通过检查源码确认: 直接用 buffer.tell() 获取 size + buffer.seek(0) rewind.
        检查 .getvalue() 方法调用 (带点号), 排除 docstring 中的文字提及.
        """
        from app.services.pdf_report_service import PDFReportService

        source = inspect.getsource(PDFReportService.generate_pdf_stream)
        # 移除 docstring (三引号之间的内容) 后检查实际方法调用
        # 简单方案: 检查 .getvalue() (带点号的实际方法调用)
        assert ".getvalue()" not in source
        # 应包含 tell() 和 seek(0)
        assert "tell()" in source
        assert "seek(0)" in source

    def test_generate_pdf_stream_has_res_p2_002_annotation(self) -> None:
        """generate_pdf_stream docstring 标注 RES-P2-002."""
        from app.services.pdf_report_service import PDFReportService

        source = inspect.getsource(PDFReportService.generate_pdf_stream)
        assert "RES-P2-002" in source

    def test_generate_pdf_stream_rewinds_stream(self) -> None:
        """生成的 BytesIO 流指针已 rewind 到 0 (可供 StreamingResponse 读取)."""
        from app.services.pdf_report_service import (
            PDFReportService,
            ReportData,
        )

        service = PDFReportService()
        report_data = ReportData(title="Test")
        result = service.generate_pdf_stream(report_data)
        if result.success and result.stream:
            assert result.stream.tell() == 0


class TestPdfStreamApi:
    """RES-P2-002: API 端点流式响应测试."""

    def test_stream_bytes_helper_exists(self) -> None:
        """_stream_bytes 分块生成器 helper 已定义."""
        from app.api.v1 import reports

        assert hasattr(reports, "_stream_bytes")
        assert callable(reports._stream_bytes)

    def test_stream_bytes_yields_chunks(self) -> None:
        """_stream_bytes 正确分块读取 BytesIO."""
        from app.api.v1.reports import _stream_bytes

        buffer = io.BytesIO(b"x" * 1000)
        chunks = list(_stream_bytes(buffer, chunk_size=100))
        assert len(chunks) == 10
        assert all(len(c) == 100 for c in chunks)

    def test_stream_bytes_closes_buffer(self) -> None:
        """_stream_bytes 读取完成后关闭 buffer."""
        from app.api.v1.reports import _stream_bytes

        buffer = io.BytesIO(b"test data")
        list(_stream_bytes(buffer))
        assert buffer.closed

    def test_generate_user_risk_pdf_uses_stream(self) -> None:
        """generate_user_risk_pdf 端点使用流式方法."""
        from app.api.v1 import reports

        source = inspect.getsource(reports)
        func_start = source.find("async def generate_user_risk_pdf")
        assert func_start != -1
        func_source = source[func_start : func_start + 1500]
        # 应调用 generate_user_risk_report_stream (而非 generate_user_risk_report)
        assert "generate_user_risk_report_stream" in func_source
        # 应使用 _stream_bytes 分块生成器
        assert "_stream_bytes" in func_source


# ============================================================================
# RES-P2-003: excel_export_service 流式输出
# ============================================================================


class TestExcelStreamResult:
    """RES-P2-003: ExcelStreamResult 数据类测试."""

    def test_excel_stream_result_dataclass_exists(self) -> None:
        """ExcelStreamResult dataclass 已定义."""
        from app.services.excel_export_service import ExcelStreamResult

        assert ExcelStreamResult is not None

    def test_excel_stream_result_fields(self) -> None:
        """ExcelStreamResult 有必要字段."""
        from app.services.excel_export_service import ExcelStreamResult

        result = ExcelStreamResult(success=True)
        assert hasattr(result, "success")
        assert hasattr(result, "stream")
        assert hasattr(result, "file_size")
        assert hasattr(result, "row_count")
        assert hasattr(result, "column_count")
        assert hasattr(result, "error_message")


class TestExcelStreamService:
    """RES-P2-003: ExcelExportService.export_to_stream 测试."""

    def test_export_to_stream_method_exists(self) -> None:
        """export_to_stream 方法存在."""
        from app.services.excel_export_service import ExcelExportService

        assert hasattr(ExcelExportService, "export_to_stream")
        assert callable(getattr(ExcelExportService, "export_to_stream"))

    def test_should_use_stream_method_exists(self) -> None:
        """should_use_stream 方法存在."""
        from app.services.excel_export_service import ExcelExportService

        assert hasattr(ExcelExportService, "should_use_stream")
        assert callable(getattr(ExcelExportService, "should_use_stream"))

    def test_stream_threshold_rows_constant(self) -> None:
        """STREAM_THRESHOLD_ROWS 常量已定义且合理."""
        from app.services.excel_export_service import ExcelExportService

        assert hasattr(ExcelExportService, "STREAM_THRESHOLD_ROWS")
        assert ExcelExportService.STREAM_THRESHOLD_ROWS > 0
        # 合理范围: 1000-50000
        assert 1000 <= ExcelExportService.STREAM_THRESHOLD_ROWS <= 50000

    def test_should_use_stream_below_threshold(self) -> None:
        """数据量低于阈值时返回 False."""
        from app.services.excel_export_service import ExcelExportService

        service = ExcelExportService()
        assert service.should_use_stream(100) is False
        assert service.should_use_stream(4999) is False

    def test_should_use_stream_above_threshold(self) -> None:
        """数据量达到阈值时返回 True."""
        from app.services.excel_export_service import ExcelExportService

        service = ExcelExportService()
        assert service.should_use_stream(5000) is True
        assert service.should_use_stream(10000) is True

    def test_export_to_stream_returns_stream_result(self) -> None:
        """export_to_stream 返回 ExcelStreamResult."""
        from app.services.excel_export_service import (
            ExcelExportService,
            ExcelStreamResult,
        )

        service = ExcelExportService()
        data = [{"col1": "value1", "col2": "value2"}]
        result = service.export_to_stream(data=data)
        assert isinstance(result, ExcelStreamResult)

    def test_export_to_stream_success_returns_bytesio(self) -> None:
        """成功时返回 BytesIO 流."""
        from app.services.excel_export_service import ExcelExportService

        service = ExcelExportService()
        data = [
            {"col1": "value1", "col2": "value2"},
            {"col1": "value3", "col2": "value4"},
        ]
        result = service.export_to_stream(data=data)
        assert result.success is True
        assert result.stream is not None
        assert isinstance(result.stream, io.BytesIO)
        assert result.file_size > 0
        assert result.row_count == 2
        assert result.column_count == 2

    def test_export_to_stream_no_getvalue_copy(self) -> None:
        """export_to_stream 不调用 getvalue() (避免 bytes 拷贝).

        检查 .getvalue() 方法调用 (带点号), 排除 docstring 中的文字提及.
        """
        from app.services.excel_export_service import ExcelExportService

        source = inspect.getsource(ExcelExportService.export_to_stream)
        assert ".getvalue()" not in source
        assert "tell()" in source
        assert "seek(0)" in source

    def test_export_to_stream_has_res_p2_003_annotation(self) -> None:
        """export_to_stream docstring 标注 RES-P2-003."""
        from app.services.excel_export_service import ExcelExportService

        source = inspect.getsource(ExcelExportService.export_to_stream)
        assert "RES-P2-003" in source

    def test_export_to_stream_empty_data(self) -> None:
        """空数据返回失败结果."""
        from app.services.excel_export_service import ExcelExportService

        service = ExcelExportService()
        result = service.export_to_stream(data=[])
        assert result.success is False
        assert "No data" in (result.error_message or "")

    def test_export_to_stream_with_filters(self) -> None:
        """export_to_stream 支持过滤器."""
        from app.services.excel_export_service import ExcelExportService

        service = ExcelExportService()
        data = [
            {"col1": "a", "col2": 1},
            {"col1": "b", "col2": 2},
            {"col1": "a", "col2": 3},
        ]
        result = service.export_to_stream(data=data, filters={"col1": "a"})
        assert result.success is True
        assert result.row_count == 2

    def test_export_to_stream_rewinds_stream(self) -> None:
        """生成的 BytesIO 流指针已 rewind 到 0."""
        from app.services.excel_export_service import ExcelExportService

        service = ExcelExportService()
        data = [{"col1": "value1"}]
        result = service.export_to_stream(data=data)
        if result.success and result.stream:
            assert result.stream.tell() == 0


class TestExcelStreamApi:
    """RES-P2-003: API 端点自动切换测试."""

    def test_batch_export_excel_uses_should_use_stream(self) -> None:
        """batch_export_excel 端点调用 should_use_stream 判断."""
        from app.api.v1 import reports

        source = inspect.getsource(reports)
        func_start = source.find("async def batch_export_excel")
        assert func_start != -1
        func_source = source[func_start : func_start + 3000]
        assert "should_use_stream" in func_source
        assert "export_to_stream" in func_source

    def test_batch_export_excel_has_stream_mode_log(self) -> None:
        """batch_export_excel 审计日志记录 stream_mode 标志."""
        from app.api.v1 import reports

        source = inspect.getsource(reports)
        func_start = source.find("async def batch_export_excel")
        func_source = source[func_start : func_start + 5000]
        assert "stream_mode" in func_source


# ============================================================================
# SEC-P2-001: JWT HS256 → RS256 迁移
# ============================================================================


class TestJwtRs256Config:
    """SEC-P2-001: RS256 配置测试."""

    def test_jwt_algorithm_config_exists(self) -> None:
        """jwt_algorithm 配置存在 (默认 HS256, 向后兼容)."""
        from app.core.config import settings

        assert hasattr(settings, "jwt_algorithm")
        assert settings.jwt_algorithm in ("HS256", "RS256")

    def test_jwt_private_key_path_config_exists(self) -> None:
        """jwt_private_key_path 配置存在."""
        from app.core.config import settings

        assert hasattr(settings, "jwt_private_key_path")

    def test_jwt_public_key_path_config_exists(self) -> None:
        """jwt_public_key_path 配置存在."""
        from app.core.config import settings

        assert hasattr(settings, "jwt_public_key_path")

    def test_jwt_private_key_pem_config_exists(self) -> None:
        """jwt_private_key_pem 配置存在 (直接 PEM 内容)."""
        from app.core.config import settings

        assert hasattr(settings, "jwt_private_key_pem")

    def test_jwt_public_key_pem_config_exists(self) -> None:
        """jwt_public_key_pem 配置存在 (直接 PEM 内容)."""
        from app.core.config import settings

        assert hasattr(settings, "jwt_public_key_pem")


class TestJwtKeyLoading:
    """SEC-P2-001: JWT key 加载函数测试."""

    def test_load_private_key_function_exists(self) -> None:
        """_load_private_key 函数存在."""
        from app.core import security

        assert hasattr(security, "_load_private_key")
        assert callable(security._load_private_key)

    def test_load_public_key_function_exists(self) -> None:
        """_load_public_key 函数存在."""
        from app.core import security

        assert hasattr(security, "_load_public_key")
        assert callable(security._load_public_key)

    def test_get_signing_key_function_exists(self) -> None:
        """_get_signing_key 函数存在."""
        from app.core import security

        assert hasattr(security, "_get_signing_key")
        assert callable(security._get_signing_key)

    def test_get_verifying_key_function_exists(self) -> None:
        """_get_verifying_key 函数存在."""
        from app.core import security

        assert hasattr(security, "_get_verifying_key")
        assert callable(security._get_verifying_key)

    def test_get_signing_key_hs256_returns_secret(self) -> None:
        """HS256 模式下 _get_signing_key 返回 jwt_secret_key."""
        from app.core import security
        from app.core.config import settings

        with patch.object(settings, "jwt_algorithm", "HS256"):
            security._load_private_key.cache_clear()
            result = security._get_signing_key()
            assert result == settings.jwt_secret_key

    def test_get_verifying_key_hs256_returns_secret(self) -> None:
        """HS256 模式下 _get_verifying_key 返回 jwt_secret_key (对称)."""
        from app.core import security
        from app.core.config import settings

        with patch.object(settings, "jwt_algorithm", "HS256"):
            security._load_public_key.cache_clear()
            result = security._get_verifying_key()
            assert result == settings.jwt_secret_key

    def test_get_signing_key_rs256_returns_private_key(self) -> None:
        """RS256 模式下 _get_signing_key 返回私钥 PEM."""
        from app.core import security
        from app.core.config import settings

        # 生成测试用 RSA 密钥
        test_private_pem = _generate_test_rsa_private_key()
        with patch.object(settings, "jwt_algorithm", "RS256"), \
             patch.object(settings, "jwt_private_key_pem", test_private_pem), \
             patch.object(settings, "jwt_private_key_path", ""):
            security._load_private_key.cache_clear()
            result = security._get_signing_key()
            assert "BEGIN" in result  # PEM 格式
            assert "PRIVATE KEY" in result

    def test_get_verifying_key_rs256_returns_public_key(self) -> None:
        """RS256 模式下 _get_verifying_key 返回公钥 PEM."""
        from app.core import security
        from app.core.config import settings

        test_public_pem = _generate_test_rsa_public_key()
        with patch.object(settings, "jwt_algorithm", "RS256"), \
             patch.object(settings, "jwt_public_key_pem", test_public_pem), \
             patch.object(settings, "jwt_public_key_path", ""):
            security._load_public_key.cache_clear()
            result = security._get_verifying_key()
            assert "BEGIN" in result
            assert "PUBLIC KEY" in result


class TestJwtRs256TokenFlow:
    """SEC-P2-001: RS256 模式 token 签发和验证测试."""

    def test_rs256_create_and_decode_access_token(self) -> None:
        """RS256 模式: 签发 access_token 后能正确验证."""
        from app.core import security
        from app.core.config import settings

        private_pem, public_pem = _generate_test_rsa_keypair()
        with patch.object(settings, "jwt_algorithm", "RS256"), \
             patch.object(settings, "jwt_private_key_pem", private_pem), \
             patch.object(settings, "jwt_public_key_pem", public_pem), \
             patch.object(settings, "jwt_private_key_path", ""), \
             patch.object(settings, "jwt_public_key_path", ""):
            security._load_private_key.cache_clear()
            security._load_public_key.cache_clear()

            token = security.create_access_token({"sub": "user123", "role": "user"})
            payload = security.decode_token(token)
            assert payload["sub"] == "user123"
            assert payload["role"] == "user"
            assert payload["type"] == "access"
            assert "jti" in payload
            assert "exp" in payload

    def test_rs256_create_and_decode_refresh_token(self) -> None:
        """RS256 模式: 签发 refresh_token 后能正确验证."""
        from app.core import security
        from app.core.config import settings

        private_pem, public_pem = _generate_test_rsa_keypair()
        with patch.object(settings, "jwt_algorithm", "RS256"), \
             patch.object(settings, "jwt_private_key_pem", private_pem), \
             patch.object(settings, "jwt_public_key_pem", public_pem), \
             patch.object(settings, "jwt_private_key_path", ""), \
             patch.object(settings, "jwt_public_key_path", ""):
            security._load_private_key.cache_clear()
            security._load_public_key.cache_clear()

            token = security.create_refresh_token({"sub": "user123"})
            payload = security.decode_token(token)
            assert payload["sub"] == "user123"
            assert payload["type"] == "refresh"

    def test_rs256_create_and_decode_password_reset_token(self) -> None:
        """RS256 模式: 签发 password_reset_token 后能正确验证."""
        from app.core import security
        from app.core.config import settings

        private_pem, public_pem = _generate_test_rsa_keypair()
        with patch.object(settings, "jwt_algorithm", "RS256"), \
             patch.object(settings, "jwt_private_key_pem", private_pem), \
             patch.object(settings, "jwt_public_key_pem", public_pem), \
             patch.object(settings, "jwt_private_key_path", ""), \
             patch.object(settings, "jwt_public_key_path", ""):
            security._load_private_key.cache_clear()
            security._load_public_key.cache_clear()

            token = security.create_password_reset_token({"sub": "user123"})
            payload = security.decode_token(token)
            assert payload["sub"] == "user123"
            assert payload["type"] == "password_reset"

    def test_rs256_token_cannot_be_verified_with_hs256(self) -> None:
        """RS256 签发的 token 不能用 HS256 验证 (非对称安全性)."""
        import jwt as jwt_lib

        from app.core import security
        from app.core.config import settings

        private_pem, public_pem = _generate_test_rsa_keypair()
        with patch.object(settings, "jwt_algorithm", "RS256"), \
             patch.object(settings, "jwt_private_key_pem", private_pem), \
             patch.object(settings, "jwt_public_key_pem", public_pem), \
             patch.object(settings, "jwt_private_key_path", ""), \
             patch.object(settings, "jwt_public_key_path", ""):
            security._load_private_key.cache_clear()
            security._load_public_key.cache_clear()

            token = security.create_access_token({"sub": "user123"})
            # 尝试用 HS256 验证 RS256 token 应失败
            with pytest.raises(jwt_lib.PyJWTError):
                jwt_lib.decode(token, public_pem, algorithms=["HS256"])

    def test_hs256_mode_still_works(self) -> None:
        """HS256 模式 (默认) 仍正常工作 (向后兼容)."""
        from app.core import security
        from app.core.config import settings

        with patch.object(settings, "jwt_algorithm", "HS256"):
            security._load_private_key.cache_clear()
            security._load_public_key.cache_clear()

            token = security.create_access_token({"sub": "user123"})
            payload = security.decode_token(token)
            assert payload["sub"] == "user123"

    def test_create_access_token_uses_signing_key(self) -> None:
        """create_access_token 调用 _get_signing_key."""
        source = inspect.getsource(__import__("app.core.security", fromlist=["create_access_token"]).create_access_token)
        assert "_get_signing_key" in source

    def test_decode_token_uses_verifying_key(self) -> None:
        """decode_token 调用 _get_verifying_key."""
        from app.core.security import decode_token

        source = inspect.getsource(decode_token)
        assert "_get_verifying_key" in source

    def test_security_module_has_sec_p2_001_annotation(self) -> None:
        """security.py 源码标注 SEC-P2-001."""
        from app.core import security

        source = inspect.getsource(security)
        assert "SEC-P2-001" in source


# ============================================================================
# 辅助函数: 生成测试用 RSA 密钥
# ============================================================================


def _generate_test_rsa_private_key() -> str:
    """生成测试用 RSA 私钥 PEM (2048 位)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("utf-8")


def _generate_test_rsa_public_key() -> str:
    """生成测试用 RSA 公钥 PEM."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return pem.decode("utf-8")


def _generate_test_rsa_keypair() -> tuple[str, str]:
    """生成测试用 RSA 密钥对 (private_pem, public_pem)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem
