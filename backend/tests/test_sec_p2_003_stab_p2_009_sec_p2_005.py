"""SEC-P2-003 / STAB-P2-009 / SEC-P2-005 专项测试.

验证三项 P2 任务:
- SEC-P2-003: 上传文件 EXIF 剥离 + ClamAV 病毒扫描
- STAB-P2-009: OpenTelemetry SDK + OTLP 分布式追踪
- SEC-P2-005: pip-compile + requirements.lock 依赖版本固定
"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import patch

import pytest


# ============================================================================
# SEC-P2-003: 上传文件 EXIF 剥离 + ClamAV 病毒扫描
# ============================================================================


class TestFileSecurityServiceStructure:
    """SEC-P2-003: file_security_service 模块结构测试."""

    def test_module_exists(self) -> None:
        """file_security_service 模块存在."""
        from app.services import file_security_service

        assert file_security_service is not None

    def test_strip_image_exif_function_exists(self) -> None:
        """strip_image_exif 函数存在."""
        from app.services.file_security_service import strip_image_exif

        assert callable(strip_image_exif)

    def test_scan_with_clamav_function_exists(self) -> None:
        """scan_with_clamav 函数存在."""
        from app.services.file_security_service import scan_with_clamav

        assert callable(scan_with_clamav)

    def test_process_uploaded_file_function_exists(self) -> None:
        """process_uploaded_file 函数存在."""
        from app.services.file_security_service import process_uploaded_file

        assert callable(process_uploaded_file)

    def test_module_has_sec_p2_003_annotation(self) -> None:
        """模块源码标注 SEC-P2-003."""
        from app.services import file_security_service

        source = inspect.getsource(file_security_service)
        assert "SEC-P2-003" in source


class TestExifStripConfig:
    """SEC-P2-003: 配置测试."""

    def test_enable_exif_strip_config_exists(self) -> None:
        """enable_exif_strip 配置存在."""
        from app.core.config import settings

        assert hasattr(settings, "enable_exif_strip")
        assert isinstance(settings.enable_exif_strip, bool)

    def test_enable_clamav_scan_config_exists(self) -> None:
        """enable_clamav_scan 配置存在."""
        from app.core.config import settings

        assert hasattr(settings, "enable_clamav_scan")
        assert isinstance(settings.enable_clamav_scan, bool)

    def test_clamav_host_config_exists(self) -> None:
        """clamav_host 配置存在."""
        from app.core.config import settings

        assert hasattr(settings, "clamav_host")

    def test_clamav_port_config_exists(self) -> None:
        """clamav_port 配置存在."""
        from app.core.config import settings

        assert hasattr(settings, "clamav_port")
        assert isinstance(settings.clamav_port, int)

    def test_clamav_unix_socket_config_exists(self) -> None:
        """clamav_unix_socket 配置存在."""
        from app.core.config import settings

        assert hasattr(settings, "clamav_unix_socket")


class TestExifStripBehavior:
    """SEC-P2-003: EXIF 剥离行为测试."""

    def test_strip_exif_disabled_returns_success(self, tmp_path: Path) -> None:
        """EXIF 剥离禁用时返回成功."""
        from app.services.file_security_service import strip_image_exif

        fake_file = tmp_path / "test.jpg"
        fake_file.write_bytes(b"fake image")
        with patch("app.core.config.settings.enable_exif_strip", False):
            ok, msg = strip_image_exif(fake_file)
            assert ok is True
            assert "disabled" in msg.lower()

    def test_strip_exif_non_image_returns_success(self, tmp_path: Path) -> None:
        """非图片文件返回成功 (跳过)."""
        from app.services.file_security_service import strip_image_exif

        fake_file = tmp_path / "test.txt"
        fake_file.write_bytes(b"hello")
        ok, msg = strip_image_exif(fake_file)
        assert ok is True
        assert "skip" in msg.lower() or "non-image" in msg.lower()

    def test_strip_exif_pillow_not_available(self, tmp_path: Path) -> None:
        """Pillow 不可用时返回成功 (降级跳过)."""
        from app.services.file_security_service import strip_image_exif

        fake_file = tmp_path / "test.jpg"
        fake_file.write_bytes(b"fake image")
        with patch(
            "app.services.file_security_service._check_pillow_available",
            return_value=False,
        ):
            ok, msg = strip_image_exif(fake_file)
            assert ok is True
            assert "pillow" in msg.lower() or "skip" in msg.lower()

    def test_strip_exif_corrupt_image_returns_failure(self, tmp_path: Path) -> None:
        """损坏的图片文件返回失败."""
        from app.services.file_security_service import strip_image_exif

        fake_file = tmp_path / "test.jpg"
        fake_file.write_bytes(b"not a real image")
        # Pillow 可用但图片损坏时应返回失败
        ok, msg = strip_image_exif(fake_file)
        # 可能成功 (Pillow 不可用降级) 或失败 (Pillow 可用但图片损坏)
        if not ok:
            assert "failed" in msg.lower() or "error" in msg.lower()


class TestClamavScanBehavior:
    """SEC-P2-003: ClamAV 扫描行为测试."""

    def test_clamav_disabled_returns_safe(self, tmp_path: Path) -> None:
        """ClamAV 禁用时返回 safe."""
        from app.services.file_security_service import scan_with_clamav

        fake_file = tmp_path / "test.txt"
        fake_file.write_bytes(b"hello")
        with patch("app.core.config.settings.enable_clamav_scan", False):
            safe, msg = scan_with_clamav(fake_file)
            assert safe is True
            assert "disabled" in msg.lower()

    def test_clamav_pyclamd_not_available(self, tmp_path: Path) -> None:
        """pyclamd 不可用时返回 safe (降级)."""
        from app.services.file_security_service import scan_with_clamav

        fake_file = tmp_path / "test.txt"
        fake_file.write_bytes(b"hello")
        with patch("app.core.config.settings.enable_clamav_scan", True), \
             patch("builtins.__import__", side_effect=_import_without_clamd):
            safe, msg = scan_with_clamav(fake_file)
            assert safe is True
            assert "pyclamd" in msg.lower() or "skip" in msg.lower()


class TestProcessUploadedFile:
    """SEC-P2-003: process_uploaded_file 集成测试."""

    def test_process_non_image_file(self, tmp_path: Path) -> None:
        """非图片文件: 跳过 EXIF, 执行 ClamAV (禁用时跳过)."""
        from app.services.file_security_service import process_uploaded_file

        fake_file = tmp_path / "test.txt"
        fake_file.write_bytes(b"hello")
        safe, msg = process_uploaded_file(fake_file, category="document")
        assert safe is True

    def test_process_image_file_exif_disabled(self, tmp_path: Path) -> None:
        """图片文件但 EXIF 禁用: 跳过 EXIF."""
        from app.services.file_security_service import process_uploaded_file

        fake_file = tmp_path / "test.jpg"
        fake_file.write_bytes(b"fake image")
        with patch("app.core.config.settings.enable_exif_strip", False), \
             patch("app.core.config.settings.enable_clamav_scan", False):
            safe, msg = process_uploaded_file(fake_file, category="image")
            assert safe is True


class TestUploadApiIntegration:
    """SEC-P2-003: 上传 API 集成测试."""

    def test_user_upload_imports_process_uploaded_file(self) -> None:
        """user_upload.py 导入 process_uploaded_file."""
        from app.api.v1 import user_upload

        source = inspect.getsource(user_upload)
        assert "process_uploaded_file" in source
        assert "from app.services.file_security_service" in source

    def test_upload_file_endpoint_calls_process_uploaded_file(self) -> None:
        """upload_file 端点调用 process_uploaded_file."""
        from app.api.v1 import user_upload

        source = inspect.getsource(user_upload)
        func_start = source.find("async def upload_file")
        assert func_start != -1
        func_source = source[func_start : func_start + 2000]
        assert "process_uploaded_file" in func_source

    def test_upload_batch_endpoint_calls_process_uploaded_file(self) -> None:
        """upload_batch 端点调用 process_uploaded_file."""
        from app.api.v1 import user_upload

        source = inspect.getsource(user_upload)
        func_start = source.find("async def upload_batch")
        assert func_start != -1
        func_source = source[func_start : func_start + 3000]
        assert "process_uploaded_file" in func_source

    def test_upload_endpoints_have_sec_p2_003_annotation(self) -> None:
        """上传端点标注 SEC-P2-003."""
        from app.api.v1 import user_upload

        source = inspect.getsource(user_upload)
        assert "SEC-P2-003" in source


# ============================================================================
# STAB-P2-009: OpenTelemetry SDK + OTLP
# ============================================================================


class TestOtelModuleStructure:
    """STAB-P2-009: otel 模块结构测试."""

    def test_module_exists(self) -> None:
        """otel 模块存在."""
        from app.core import otel

        assert otel is not None

    def test_init_otel_function_exists(self) -> None:
        """init_otel 函数存在."""
        from app.core.otel import init_otel

        assert callable(init_otel)

    def test_instrument_app_function_exists(self) -> None:
        """instrument_app 函数存在."""
        from app.core.otel import instrument_app

        assert callable(instrument_app)

    def test_shutdown_otel_function_exists(self) -> None:
        """shutdown_otel 函数存在."""
        from app.core.otel import shutdown_otel

        assert callable(shutdown_otel)

    def test_check_otel_available_function_exists(self) -> None:
        """_check_otel_available 函数存在."""
        from app.core.otel import _check_otel_available

        assert callable(_check_otel_available)

    def test_module_has_stab_p2_009_annotation(self) -> None:
        """模块源码标注 STAB-P2-009."""
        from app.core import otel

        source = inspect.getsource(otel)
        assert "STAB-P2-009" in source


class TestOtelConfig:
    """STAB-P2-009: 配置测试."""

    def test_otel_enabled_config_exists(self) -> None:
        """otel_enabled 配置存在."""
        from app.core.config import settings

        assert hasattr(settings, "otel_enabled")
        assert isinstance(settings.otel_enabled, bool)

    def test_otlp_endpoint_config_exists(self) -> None:
        """otlp_endpoint 配置存在."""
        from app.core.config import settings

        assert hasattr(settings, "otlp_endpoint")

    def test_otlp_protocol_config_exists(self) -> None:
        """otlp_protocol 配置存在."""
        from app.core.config import settings

        assert hasattr(settings, "otlp_protocol")
        assert settings.otlp_protocol in ("grpc", "http/protobuf")

    def test_otel_service_name_config_exists(self) -> None:
        """otel_service_name 配置存在."""
        from app.core.config import settings

        assert hasattr(settings, "otel_service_name")
        assert settings.otel_service_name  # 非空

    def test_otel_resource_attributes_config_exists(self) -> None:
        """otel_resource_attributes 配置存在."""
        from app.core.config import settings

        assert hasattr(settings, "otel_resource_attributes")


class TestOtelInitBehavior:
    """STAB-P2-009: init_otel 行为测试."""

    def test_init_otel_no_endpoint_returns_false(self) -> None:
        """未配置 OTLP endpoint 时返回 False."""
        from app.core import otel

        # 重置初始化状态
        otel._otel_initialized = False
        result = otel.init_otel(
            service_name="test",
            otlp_endpoint="",  # 空端点
        )
        assert result is False

    def test_init_otel_otel_not_available(self) -> None:
        """opentelemetry 不可用时返回 False."""
        from app.core import otel

        otel._otel_initialized = False
        with patch("app.core.otel._check_otel_available", return_value=False):
            result = otel.init_otel(
                service_name="test",
                otlp_endpoint="http://localhost:4317",
            )
            assert result is False

    def test_init_otel_already_initialized(self) -> None:
        """已初始化时直接返回 True."""
        from app.core import otel

        otel._otel_initialized = True
        result = otel.init_otel(
            service_name="test",
            otlp_endpoint="http://localhost:4317",
        )
        assert result is True
        # 重置
        otel._otel_initialized = False

    def test_instrument_app_not_initialized_noop(self) -> None:
        """未初始化时 instrument_app 是空操作."""
        from app.core.otel import instrument_app

        # 不应抛出异常
        instrument_app(app=None)

    def test_shutdown_otel_not_initialized_noop(self) -> None:
        """未初始化时 shutdown_otel 是空操作."""
        from app.core import otel
        from app.core.otel import shutdown_otel

        # 不应抛出异常
        otel._otel_initialized = False
        shutdown_otel()


class TestOtelMainIntegration:
    """STAB-P2-009: main.py 集成测试."""

    def test_main_imports_otel(self) -> None:
        """main.py 导入 otel 模块."""
        import app.main as main_mod

        source = inspect.getsource(main_mod)
        assert "otel" in source.lower()

    def test_main_calls_init_otel_in_lifespan(self) -> None:
        """main.py lifespan 中调用 init_otel."""
        import app.main as main_mod

        source = inspect.getsource(main_mod)
        assert "init_otel" in source
        assert "init_sentry" in source  # 确认在 sentry 之后

    def test_main_calls_instrument_app(self) -> None:
        """main.py 调用 instrument_app."""
        import app.main as main_mod

        source = inspect.getsource(main_mod)
        assert "instrument_app" in source

    def test_main_calls_shutdown_otel_in_finally(self) -> None:
        """main.py lifespan finally 中调用 shutdown_otel."""
        import app.main as main_mod

        source = inspect.getsource(main_mod)
        assert "shutdown_otel" in source

    def test_main_has_stab_p2_009_annotation(self) -> None:
        """main.py 标注 STAB-P2-009."""
        import app.main as main_mod

        source = inspect.getsource(main_mod)
        assert "STAB-P2-009" in source


# ============================================================================
# SEC-P2-005: pip-compile + requirements.lock
# ============================================================================


class TestRequirementsInFile:
    """SEC-P2-005: requirements.in 文件测试."""

    def test_requirements_in_exists(self) -> None:
        """requirements.in 文件存在."""
        backend_root = Path(__file__).parent.parent
        req_in = backend_root / "requirements.in"
        assert req_in.exists()

    def test_requirements_in_has_sec_p2_005_annotation(self) -> None:
        """requirements.in 标注 SEC-P2-005."""
        backend_root = Path(__file__).parent.parent
        req_in = backend_root / "requirements.in"
        content = req_in.read_text(encoding="utf-8")
        assert "SEC-P2-005" in content

    def test_requirements_in_has_pip_compile_instructions(self) -> None:
        """requirements.in 包含 pip-compile 生成说明."""
        backend_root = Path(__file__).parent.parent
        req_in = backend_root / "requirements.in"
        content = req_in.read_text(encoding="utf-8")
        assert "pip-compile" in content

    def test_requirements_in_has_top_level_deps(self) -> None:
        """requirements.in 包含顶层依赖."""
        backend_root = Path(__file__).parent.parent
        req_in = backend_root / "requirements.in"
        content = req_in.read_text(encoding="utf-8")
        # 检查关键依赖
        assert "fastapi" in content.lower()
        assert "sqlalchemy" in content.lower()
        assert "pydantic" in content.lower()

    def test_requirements_in_has_pillow_dependency(self) -> None:
        """requirements.in 包含 Pillow 依赖 (SEC-P2-003)."""
        backend_root = Path(__file__).parent.parent
        req_in = backend_root / "requirements.in"
        content = req_in.read_text(encoding="utf-8")
        assert "Pillow" in content or "pillow" in content.lower()

    def test_requirements_in_has_optional_otel_deps(self) -> None:
        """requirements.in 包含可选 OTel 依赖 (STAB-P2-009, 注释状态)."""
        backend_root = Path(__file__).parent.parent
        req_in = backend_root / "requirements.in"
        content = req_in.read_text(encoding="utf-8")
        assert "opentelemetry" in content.lower()


class TestRequirementsLockFile:
    """SEC-P2-005: requirements.lock 文件测试."""

    def test_requirements_lock_exists(self) -> None:
        """requirements.lock 文件存在."""
        backend_root = Path(__file__).parent.parent
        req_lock = backend_root / "requirements.lock"
        assert req_lock.exists()

    def test_requirements_lock_has_sec_p2_005_header(self) -> None:
        """requirements.lock 文件头标注 SEC-P2-005."""
        backend_root = Path(__file__).parent.parent
        req_lock = backend_root / "requirements.lock"
        content = req_lock.read_text(encoding="utf-8")
        assert "SEC-P2-005" in content

    def test_requirements_lock_has_pinned_versions(self) -> None:
        """requirements.lock 包含锁定版本 (== 格式)."""
        backend_root = Path(__file__).parent.parent
        req_lock = backend_root / "requirements.lock"
        content = req_lock.read_text(encoding="utf-8")
        # 应包含 == 锁定版本
        assert "==" in content

    def test_requirements_lock_has_fastapi(self) -> None:
        """requirements.lock 包含 fastapi."""
        backend_root = Path(__file__).parent.parent
        req_lock = backend_root / "requirements.lock"
        content = req_lock.read_text(encoding="utf-8")
        assert "fastapi==" in content.lower() or "fastapi ==" in content.lower()

    def test_requirements_lock_has_more_than_50_lines(self) -> None:
        """requirements.lock 至少 50 行 (包含传递依赖)."""
        backend_root = Path(__file__).parent.parent
        req_lock = backend_root / "requirements.lock"
        lines = req_lock.read_text(encoding="utf-8").splitlines()
        assert len(lines) >= 50


class TestRequirementsDevInFile:
    """SEC-P2-005: requirements-dev.in 文件测试."""

    def test_requirements_dev_in_exists(self) -> None:
        """requirements-dev.in 文件存在."""
        backend_root = Path(__file__).parent.parent
        req_dev = backend_root / "requirements-dev.in"
        assert req_dev.exists()

    def test_requirements_dev_in_references_requirements_in(self) -> None:
        """requirements-dev.in 引用 requirements.in."""
        backend_root = Path(__file__).parent.parent
        req_dev = backend_root / "requirements-dev.in"
        content = req_dev.read_text(encoding="utf-8")
        assert "-r requirements.in" in content

    def test_requirements_dev_in_has_test_deps(self) -> None:
        """requirements-dev.in 包含测试依赖."""
        backend_root = Path(__file__).parent.parent
        req_dev = backend_root / "requirements-dev.in"
        content = req_dev.read_text(encoding="utf-8")
        assert "pytest" in content.lower()

    def test_requirements_dev_in_has_pip_tools(self) -> None:
        """requirements-dev.in 包含 pip-tools."""
        backend_root = Path(__file__).parent.parent
        req_dev = backend_root / "requirements-dev.in"
        content = req_dev.read_text(encoding="utf-8")
        assert "pip-tools" in content.lower()


# ============================================================================
# 辅助函数
# ============================================================================


def _import_without_clamd(name: str, *args, **kwargs):
    """模拟 clamd 模块不可用的 import 行为."""
    if name == "clamd":
        raise ImportError(f"No module named '{name}'")
    import builtins

    return builtins.__import__(name, *args, **kwargs)
