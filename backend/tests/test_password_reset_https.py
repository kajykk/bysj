"""SEC-P1-002: 密码重置链接 HTTPS 强制校验测试.

原问题:
    password_reset_base_url 默认 http://localhost:5173/reset-password
    生产环境若未配置或配置为 HTTP, 重置链接中的 token 可被中间人攻击窃取

修复方案:
    1. config.py model_validator: 生产环境强制 HTTPS, 否则启动失败
    2. email_service.py 运行时防御: 非 localhost HTTP 拒绝发送, 防止 token 泄露

测试覆盖:
    - TestConfigProductionHttpsCheck: 生产环境 HTTPS 启动校验 (4 个)
    - TestEmailServiceRuntimeDefense: 运行时 HTTPS 防御 (5 个)
    - TestSourceStructure: 源码静态结构验证 (4 个)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.services.email_service import EmailService


@pytest.fixture(autouse=True)
def _isolate_smtp_tls():
    """每个测试隔离 thread-local SMTP 连接, 避免工作线程间的 TLS 状态泄漏."""
    with patch("app.services.email_service._get_thread_smtp", return_value=None):
        yield


# ──────────────────────────────────────────────────────────────────────────
# 1. Config 生产环境 HTTPS 强制校验
# ──────────────────────────────────────────────────────────────────────────


class TestConfigProductionHttpsCheck:
    """验证 Settings 在生产环境强制 password_reset_base_url 使用 HTTPS."""

    def test_production_http_rejected(self):
        """生产环境 + HTTP 链接应启动失败."""
        from app.core.config import Settings

        with pytest.raises(ValidationError) as exc_info:
            Settings(
                app_env="production",
                database_url="postgresql://user:pass@localhost/db",
                jwt_secret_key="production-secure-secret-key-32-chars-long",
                pii_encryption_key="production-pii-key",
                alertmanager_webhook_secret="prod-webhook-secret",
                metrics_access_token="prod-metrics-token",
                password_reset_base_url="http://example.com/reset-password",
            )
        assert "PASSWORD_RESET_BASE_URL" in str(exc_info.value)
        assert "HTTPS" in str(exc_info.value)

    def test_production_https_accepted(self):
        """生产环境 + HTTPS 链接应通过校验."""
        from app.core.config import Settings

        # 不应抛出异常
        settings = Settings(
            app_env="production",
            database_url="postgresql://user:pass@localhost/db",
            jwt_secret_key="production-secure-secret-key-32-chars-long",
            pii_encryption_key="production-pii-key",
            alertmanager_webhook_secret="prod-webhook-secret",
            metrics_access_token="prod-metrics-token",
            password_reset_base_url="https://example.com/reset-password",
        )
        assert settings.password_reset_base_url == "https://example.com/reset-password"

    def test_development_http_accepted(self):
        """开发环境 + HTTP 链接应通过 (向后兼容)."""
        from app.core.config import Settings

        settings = Settings(
            app_env="development",
            password_reset_base_url="http://localhost:5173/reset-password",
        )
        assert (
            settings.password_reset_base_url == "http://localhost:5173/reset-password"
        )

    def test_production_empty_url_rejected(self):
        """生产环境 + 空 URL 应启动失败 (不以 https:// 开头)."""
        from app.core.config import Settings

        with pytest.raises(ValidationError):
            Settings(
                app_env="production",
                database_url="postgresql://user:pass@localhost/db",
                jwt_secret_key="production-secure-secret-key-32-chars-long",
                pii_encryption_key="production-pii-key",
                alertmanager_webhook_secret="prod-webhook-secret",
                metrics_access_token="prod-metrics-token",
                password_reset_base_url="",
            )


# ──────────────────────────────────────────────────────────────────────────
# 2. EmailService 运行时 HTTPS 防御
# ──────────────────────────────────────────────────────────────────────────


class TestEmailServiceRuntimeDefense:
    """验证 EmailService 在运行时对 HTTP 链接的防御行为."""

    @patch("app.services.email_service.logger")
    @patch("app.services.email_service.smtplib.SMTP")
    @patch("app.services.email_service.settings")
    async def test_https_link_sends_normally(
        self, mock_settings, mock_smtp_class, mock_logger
    ):
        """HTTPS 链接应正常发送邮件, 无 warning."""
        mock_settings.smtp_host = "smtp.test.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_from_email = "from@test.com"
        mock_settings.smtp_use_tls = True
        mock_settings.smtp_user = "user"
        mock_settings.smtp_password = "pass"
        mock_settings.password_reset_base_url = "https://example.com/reset"
        mock_settings.password_reset_token_expire_minutes = 30

        mock_smtp = MagicMock()
        mock_smtp_class.return_value = mock_smtp

        svc = EmailService()
        await svc.send_password_reset_email("to@test.com", "token123")

        # HTTPS 链接不应触发 insecure_http warning 或 blocked error
        mock_logger.warning.assert_not_called()
        mock_logger.error.assert_not_called()
        mock_smtp.send_message.assert_called_once()

    @patch("app.services.email_service.logger")
    @patch("app.services.email_service.smtplib.SMTP")
    @patch("app.services.email_service.settings")
    async def test_http_localhost_warns_but_sends(
        self, mock_settings, mock_smtp_class, mock_logger
    ):
        """HTTP + localhost 应记录 warning 但仍发送邮件 (开发环境调试)."""
        mock_settings.smtp_host = "smtp.test.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_from_email = "from@test.com"
        mock_settings.smtp_use_tls = True
        mock_settings.smtp_user = "user"
        mock_settings.smtp_password = "pass"
        mock_settings.password_reset_base_url = "http://localhost:5173/reset-password"
        mock_settings.password_reset_token_expire_minutes = 30

        mock_smtp = MagicMock()
        mock_smtp_class.return_value = mock_smtp

        svc = EmailService()
        await svc.send_password_reset_email("to@test.com", "token123")

        # 应记录 warning (含 reset_link_insecure_http 标识)
        warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
        assert any(
            "reset_link_insecure_http" in c for c in warning_calls
        ), f"Expected reset_link_insecure_http warning, got: {warning_calls}"
        assert any("localhost" in c for c in warning_calls)
        # 不应有 error
        mock_logger.error.assert_not_called()
        # 仍应发送邮件
        mock_smtp.send_message.assert_called_once()

    @patch("app.services.email_service.logger")
    @patch("app.services.email_service.smtplib.SMTP")
    @patch("app.services.email_service.settings")
    async def test_http_127001_warns_but_sends(
        self, mock_settings, mock_smtp_class, mock_logger
    ):
        """HTTP + 127.0.0.1 应记录 warning 但仍发送邮件."""
        mock_settings.smtp_host = "smtp.test.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_from_email = "from@test.com"
        mock_settings.smtp_use_tls = True
        mock_settings.smtp_user = "user"
        mock_settings.smtp_password = "pass"
        mock_settings.password_reset_base_url = "http://127.0.0.1:5173/reset-password"
        mock_settings.password_reset_token_expire_minutes = 30

        mock_smtp = MagicMock()
        mock_smtp_class.return_value = mock_smtp

        svc = EmailService()
        await svc.send_password_reset_email("to@test.com", "token123")

        warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
        assert any("reset_link_insecure_http" in c for c in warning_calls)
        mock_logger.error.assert_not_called()
        mock_smtp.send_message.assert_called_once()

    @patch("app.services.email_service.logger")
    @patch("app.services.email_service.smtplib.SMTP")
    @patch("app.services.email_service.settings")
    async def test_http_non_localhost_rejected(
        self, mock_settings, mock_smtp_class, mock_logger
    ):
        """HTTP + 非 localhost 域名应拒绝发送, raise ValueError."""
        mock_settings.smtp_host = "smtp.test.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_from_email = "from@test.com"
        mock_settings.smtp_use_tls = True
        mock_settings.smtp_user = "user"
        mock_settings.smtp_password = "pass"
        mock_settings.password_reset_base_url = "http://example.com/reset-password"
        mock_settings.password_reset_token_expire_minutes = 30

        mock_smtp = MagicMock()
        mock_smtp_class.return_value = mock_smtp

        svc = EmailService()
        with pytest.raises(ValueError, match="HTTPS"):
            await svc.send_password_reset_email("to@test.com", "token123")

        # 应记录 error (含 reset_link_blocked 标识)
        error_calls = [str(c) for c in mock_logger.error.call_args_list]
        assert any(
            "reset_link_blocked" in c for c in error_calls
        ), f"Expected reset_link_blocked error, got: {error_calls}"
        # 不应实际发送邮件
        mock_smtp.send_message.assert_not_called()

    @patch("app.services.email_service.logger")
    @patch("app.services.email_service.smtplib.SMTP")
    @patch("app.services.email_service.settings")
    async def test_http_staging_domain_rejected(
        self, mock_settings, mock_smtp_class, mock_logger
    ):
        """HTTP + staging 域名也应拒绝 (防止 staging 误配置泄露 token)."""
        mock_settings.smtp_host = "smtp.test.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_from_email = "from@test.com"
        mock_settings.smtp_use_tls = True
        mock_settings.smtp_user = "user"
        mock_settings.smtp_password = "pass"
        mock_settings.password_reset_base_url = (
            "http://staging.example.com/reset-password"
        )
        mock_settings.password_reset_token_expire_minutes = 30

        mock_smtp = MagicMock()
        mock_smtp_class.return_value = mock_smtp

        svc = EmailService()
        with pytest.raises(ValueError, match="HTTPS"):
            await svc.send_password_reset_email("to@test.com", "token123")

        error_calls = [str(c) for c in mock_logger.error.call_args_list]
        assert any("reset_link_blocked" in c for c in error_calls)
        mock_smtp.send_message.assert_not_called()


# ──────────────────────────────────────────────────────────────────────────
# 3. 源码静态结构验证
# ──────────────────────────────────────────────────────────────────────────


class TestSourceStructure:
    """源码静态扫描, 验证修复已落地."""

    def test_config_has_https_validator(self):
        """config.py 应包含 HTTPS 校验逻辑."""
        from app.core import config

        source = __import__("inspect").getsource(config.Settings.apply_env_defaults)
        assert "password_reset_base_url" in source
        assert "https://" in source.lower() or "HTTPS" in source
        assert "production" in source

    def test_email_service_has_runtime_defense(self):
        """email_service.py 应包含运行时 HTTPS 防御逻辑."""
        from app.services import email_service

        source = __import__("inspect").getsource(
            email_service.EmailService.send_password_reset_email
        )
        assert "https://" in source.lower()
        assert "localhost" in source or "127.0.0.1" in source
        # 应使用 urlparse 提取 host
        assert "urlparse" in source
        # 应有拒绝发送的逻辑 (raise ValueError)
        assert "raise ValueError" in source

    def test_env_example_documents_https_requirement(self):
        """backend/.env.example 应文档化 HTTPS 要求."""
        from pathlib import Path

        env_path = Path(__file__).resolve().parent.parent / ".env.example"
        content = env_path.read_text(encoding="utf-8")
        # 应包含 SEC-P1-002 或 HTTPS 相关提示
        assert "SEC-P1-002" in content or "HTTPS" in content or "https://" in content

    def test_password_reset_base_url_field_documented(self):
        """config.py 中 password_reset_base_url 字段应有 SEC-P1-002 注释."""
        from app.core import config

        source = __import__("inspect").getsource(config.Settings)
        # 找到 password_reset_base_url 字段定义附近
        idx = source.find("password_reset_base_url")
        assert idx >= 0
        # 检查前后 200 字符内是否有 SEC-P1-002 或 HTTPS 提示
        context = source[max(0, idx - 200) : idx + 200]
        assert (
            "SEC-P1-002" in context
            or "HTTPS" in context
            or "https://" in context.lower()
        )
