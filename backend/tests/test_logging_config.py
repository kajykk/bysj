"""RES-P0-002 测试：日志轮转配置

验证要点：
1. ``get_log_dir()`` 路径解析正确
2. ``configure_logging()`` 幂等性
3. 启用文件日志后，RotatingFileHandler 被正确配置
4. 日志文件实际被创建并可写入
5. ``error.log`` 只记录 ERROR+ 级别
6. logger ``propagate=False`` 避免重复打印
7. 默认配置（log_to_file=False）不创建文件 handler
8. 轮转触发后产生备份文件
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core import logging_config
from app.core.logging_config import (
    configure_logging,
    get_log_dir,
    reset_logging_state,
)


@pytest.fixture(autouse=True)
def _reset_logging_state_fixture():
    """每个测试前后重置 logging_config 模块的 _CONFIGURED 标记。

    避免前一个测试的配置状态影响后一个测试。
    """
    reset_logging_state()
    # 保存当前 root logger 的 handler，测试后恢复
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    yield
    # 清理测试中可能添加的 handler，避免污染其他测试
    for h in root.handlers[:]:
        try:
            h.close()
        except Exception:
            pass
        root.removeHandler(h)
    for h in original_handlers:
        root.addHandler(h)
    root.setLevel(original_level)
    reset_logging_state()


class TestGetLogDir:
    """测试 get_log_dir() 路径解析。"""

    def test_default_log_dir_is_under_backend(self):
        """默认 log_dir='logs' 应解析为 backend/logs/。"""
        from app.core.config import BACKEND_DIR, settings

        with patch.object(settings, "log_dir", "logs"):
            result = get_log_dir()
            assert result == (BACKEND_DIR / "logs").resolve()

    def test_relative_log_dir(self, tmp_path: Path):
        """相对路径应相对于 BACKEND_DIR 解析。"""
        from app.core.config import BACKEND_DIR, settings

        with patch.object(settings, "log_dir", "custom_logs"):
            result = get_log_dir()
            assert result == (BACKEND_DIR / "custom_logs").resolve()

    def test_absolute_log_dir(self, tmp_path: Path):
        """绝对路径应原样使用。"""
        from app.core.config import settings

        abs_path = tmp_path / "absolute_logs"
        with patch.object(settings, "log_dir", str(abs_path)):
            result = get_log_dir()
            assert result == abs_path.resolve()


class TestConfigureLoggingIdempotent:
    """测试 configure_logging() 幂等性。"""

    def test_default_call_does_not_create_file(self, tmp_path: Path, monkeypatch):
        """默认配置（log_to_file=False）不应创建文件 handler。"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "log_to_file", False)
        monkeypatch.setattr(settings, "log_console", True)
        monkeypatch.setattr(settings, "log_dir", str(tmp_path))

        configure_logging()

        root = logging.getLogger()
        file_handlers = [
            h
            for h in root.handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert file_handlers == [], "默认配置不应创建 RotatingFileHandler"

    def test_idempotent_without_force(self, tmp_path: Path, monkeypatch):
        """多次调用 configure_logging() 不带 force 应只配置一次。"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "log_to_file", False)
        monkeypatch.setattr(settings, "log_console", True)
        monkeypatch.setattr(settings, "log_dir", str(tmp_path))

        configure_logging()
        handlers_after_first = list(logging.getLogger().handlers)

        configure_logging()  # 第二次调用，不应重新配置
        handlers_after_second = list(logging.getLogger().handlers)

        # handler 数量应相同（未重新配置）
        assert len(handlers_after_second) == len(handlers_after_first)

    def test_force_reconfigures(self, tmp_path: Path, monkeypatch):
        """configure_logging(force=True) 应强制重新配置。"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "log_to_file", False)
        monkeypatch.setattr(settings, "log_console", True)
        monkeypatch.setattr(settings, "log_dir", str(tmp_path))

        configure_logging()
        assert logging_config._CONFIGURED is True

        # force=True 应重新配置
        reset_logging_state()
        configure_logging(force=True)
        assert logging_config._CONFIGURED is True


class TestFileHandlerConfiguration:
    """测试 RotatingFileHandler 配置。"""

    def test_file_handlers_created_when_enabled(self, tmp_path: Path, monkeypatch):
        """启用文件日志后应创建 app_file 和 error_file 两个 handler。"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "log_to_file", True)
        monkeypatch.setattr(settings, "log_console", False)
        monkeypatch.setattr(settings, "log_dir", str(tmp_path))
        monkeypatch.setattr(settings, "log_max_bytes", 1024 * 10)
        monkeypatch.setattr(settings, "log_backup_count", 3)

        configure_logging(force=True)

        root = logging.getLogger()
        file_handlers = [
            h
            for h in root.handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert (
            len(file_handlers) == 2
        ), f"应有 2 个 RotatingFileHandler, 实际 {len(file_handlers)}"

        # 验证日志目录被创建
        assert tmp_path.exists()
        assert tmp_path.is_dir()

    def test_app_log_file_created_on_write(self, tmp_path: Path, monkeypatch):
        """写入日志后 app.log 文件应被创建。"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "log_to_file", True)
        monkeypatch.setattr(settings, "log_console", False)
        monkeypatch.setattr(settings, "log_dir", str(tmp_path))
        monkeypatch.setattr(settings, "log_level", "INFO")

        configure_logging(force=True)

        test_logger = logging.getLogger("app.test_module")
        test_logger.info("test log message for app.log creation")

        # flush 所有 handler
        for h in logging.getLogger().handlers:
            try:
                h.flush()
            except Exception:
                pass

        app_log = tmp_path / "app.log"
        assert app_log.exists(), f"app.log 应被创建于 {app_log}"
        content = app_log.read_text(encoding="utf-8")
        assert "test log message for app.log creation" in content

    def test_error_log_only_captures_error_and_above(self, tmp_path: Path, monkeypatch):
        """error.log 应只记录 ERROR 及以上级别的日志。"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "log_to_file", True)
        monkeypatch.setattr(settings, "log_console", False)
        monkeypatch.setattr(settings, "log_dir", str(tmp_path))
        monkeypatch.setattr(settings, "log_level", "DEBUG")  # root 级别设为 DEBUG

        configure_logging(force=True)

        test_logger = logging.getLogger("app.test_error_filter")
        test_logger.debug("debug message should not appear in error.log")
        test_logger.info("info message should not appear in error.log")
        test_logger.warning("warning message should not appear in error.log")
        test_logger.error("error message should appear in error.log")
        test_logger.critical("critical message should appear in error.log")

        # flush
        for h in logging.getLogger().handlers:
            try:
                h.flush()
            except Exception:
                pass

        error_log = tmp_path / "error.log"
        assert error_log.exists()
        error_content = error_log.read_text(encoding="utf-8")

        assert "error message should appear in error.log" in error_content
        assert "critical message should appear in error.log" in error_content
        assert "info message should not appear in error.log" not in error_content
        assert "warning message should not appear in error.log" not in error_content

    def test_rotating_handler_max_bytes_and_backup_count(
        self, tmp_path: Path, monkeypatch
    ):
        """RotatingFileHandler 的 maxBytes 和 backupCount 应与 settings 一致。"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "log_to_file", True)
        monkeypatch.setattr(settings, "log_console", False)
        monkeypatch.setattr(settings, "log_dir", str(tmp_path))
        monkeypatch.setattr(settings, "log_max_bytes", 2048)
        monkeypatch.setattr(settings, "log_backup_count", 7)

        configure_logging(force=True)

        root = logging.getLogger()
        file_handlers = [
            h
            for h in root.handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert len(file_handlers) == 2
        for h in file_handlers:
            assert h.maxBytes == 2048, f"maxBytes 应为 2048, 实际 {h.maxBytes}"
            assert h.backupCount == 7, f"backupCount 应为 7, 实际 {h.backupCount}"

    def test_rotation_creates_backup_files(self, tmp_path: Path, monkeypatch):
        """超过 maxBytes 后应触发轮转，生成 .1 备份文件。"""
        from app.core.config import settings

        # 使用很小的 maxBytes 触发轮转
        monkeypatch.setattr(settings, "log_to_file", True)
        monkeypatch.setattr(settings, "log_console", False)
        monkeypatch.setattr(settings, "log_dir", str(tmp_path))
        monkeypatch.setattr(settings, "log_max_bytes", 512)  # 512 字节，很快触发轮转
        monkeypatch.setattr(settings, "log_backup_count", 3)
        monkeypatch.setattr(settings, "log_level", "INFO")

        configure_logging(force=True)

        test_logger = logging.getLogger("app.test_rotation")
        # 写入足够多的日志触发轮转
        for i in range(50):
            test_logger.info("rotation test line %d: %s", i, "X" * 50)

        # flush
        for h in logging.getLogger().handlers:
            try:
                h.flush()
            except Exception:
                pass

        # 应存在 app.log 和至少一个 app.log.1 备份
        app_log = tmp_path / "app.log"
        assert app_log.exists()
        backup_files = list(tmp_path.glob("app.log.*"))
        assert len(backup_files) >= 1, f"应至少有一个轮转备份文件, 实际: {backup_files}"


class TestLoggerPropagation:
    """测试 logger propagate 配置。"""

    def test_app_logger_does_not_propagate_to_root(self, tmp_path: Path, monkeypatch):
        """app logger 的 propagate 应为 False，避免重复打印。"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "log_to_file", False)
        monkeypatch.setattr(settings, "log_console", True)
        monkeypatch.setattr(settings, "log_dir", str(tmp_path))

        configure_logging(force=True)

        app_logger = logging.getLogger("app")
        assert app_logger.propagate is False, "app logger 的 propagate 应为 False"

    def test_sqlalchemy_logger_level_is_warning(self, tmp_path: Path, monkeypatch):
        """sqlalchemy logger 级别应为 WARNING，避免 SQL 噪音。"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "log_to_file", False)
        monkeypatch.setattr(settings, "log_console", True)
        monkeypatch.setattr(settings, "log_dir", str(tmp_path))

        configure_logging(force=True)

        sa_logger = logging.getLogger("sqlalchemy")
        assert sa_logger.level == logging.WARNING

    def test_uvicorn_logger_propagate_false(self, tmp_path: Path, monkeypatch):
        """uvicorn logger 的 propagate 应为 False。"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "log_to_file", False)
        monkeypatch.setattr(settings, "log_console", True)
        monkeypatch.setattr(settings, "log_dir", str(tmp_path))

        configure_logging(force=True)

        for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
            uv_logger = logging.getLogger(name)
            assert uv_logger.propagate is False, f"{name} logger propagate 应为 False"


class TestDegradedMode:
    """测试降级场景。"""

    def test_all_handlers_disabled_uses_null_handler(self, tmp_path: Path, monkeypatch):
        """log_to_file=False 且 log_console=False 时应使用 NullHandler。"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "log_to_file", False)
        monkeypatch.setattr(settings, "log_console", False)
        monkeypatch.setattr(settings, "log_dir", str(tmp_path))

        configure_logging(force=True)

        root = logging.getLogger()
        # 应有至少一个 handler（NullHandler），避免 "No handlers" 警告
        assert len(root.handlers) >= 1
        # 不应有 StreamHandler 或 RotatingFileHandler
        for h in root.handlers:
            assert not isinstance(h, logging.StreamHandler) or isinstance(
                h, logging.NullHandler
            ), f"不应有 StreamHandler（NullHandler 除外），实际: {h}"

    def test_log_dir_creation_failure_degrades_gracefully(
        self, tmp_path: Path, monkeypatch
    ):
        """日志目录创建失败时应降级为仅控制台输出，不抛异常。"""
        from app.core.config import settings

        # 使用一个无法创建的路径（例如在文件上创建子目录）
        impossible_dir = tmp_path / "not_a_dir" / "sub"
        # 先创建一个文件占位，使 mkdir 失败
        (tmp_path / "not_a_dir").write_text("i am a file not a dir")

        monkeypatch.setattr(settings, "log_to_file", True)
        monkeypatch.setattr(settings, "log_console", True)
        monkeypatch.setattr(settings, "log_dir", str(impossible_dir))

        # 不应抛异常
        configure_logging(force=True)

        # 应降级为仅控制台输出
        root = logging.getLogger()
        file_handlers = [
            h
            for h in root.handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert file_handlers == [], "目录创建失败后不应有文件 handler"


class TestEncodingConfiguration:
    """测试日志文件编码。"""

    def test_log_file_uses_utf8_encoding(self, tmp_path: Path, monkeypatch):
        """日志文件应使用 UTF-8 编码，支持中文。"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "log_to_file", True)
        monkeypatch.setattr(settings, "log_console", False)
        monkeypatch.setattr(settings, "log_dir", str(tmp_path))
        monkeypatch.setattr(settings, "log_level", "INFO")

        configure_logging(force=True)

        test_logger = logging.getLogger("app.test_utf8")
        test_logger.info("测试中文日志消息：抑郁症预警系统")

        for h in logging.getLogger().handlers:
            try:
                h.flush()
            except Exception:
                pass

        app_log = tmp_path / "app.log"
        content = app_log.read_text(encoding="utf-8")
        assert "抑郁症预警系统" in content

        # 验证 handler 的 encoding 属性
        file_handlers = [
            h
            for h in logging.getLogger().handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        for h in file_handlers:
            # RotatingFileHandler 的 stream.encoding 应为 utf-8
            assert h.stream.encoding.lower() in (
                "utf-8",
                "utf8",
            ), f"文件编码应为 utf-8, 实际 {h.stream.encoding}"
