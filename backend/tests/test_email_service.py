"""Tests for email service."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from app.services.email_service import EmailService


@pytest.fixture(autouse=True)
def _isolate_smtp_tls():
    """每个测试隔离 thread-local SMTP 连接, 避免工作线程间的 TLS 状态泄漏."""
    with patch("app.services.email_service._get_thread_smtp", return_value=None):
        yield


class TestEmailService:
    """Test email service."""

    async def test_smtp_not_configured(self, caplog):
        """TC-COV-EMAIL-001: SMTP not configured logs warning."""
        with caplog.at_level(logging.WARNING):
            svc = EmailService()
            await svc.send_password_reset_email("test@test.com", "token123")
        # P1-E 修复：日志消息已脱敏，不再记录含 token 的 reset_link
        assert "smtp_not_configured" in caplog.text
        assert (
            "token" not in caplog.text.lower()
            or "token generated but not delivered" in caplog.text
        )

    @patch("app.services.email_service.smtplib.SMTP")
    @patch("app.services.email_service.settings")
    async def test_send_email_success(self, mock_settings, mock_smtp_class):
        """TC-COV-EMAIL-002: Send email successfully."""
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

        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with("user", "pass")
        mock_smtp.send_message.assert_called_once()

    @patch("app.services.email_service.smtplib.SMTP")
    @patch("app.services.email_service.settings")
    async def test_send_email_failure_raises(self, mock_settings, mock_smtp_class):
        """TC-COV-EMAIL-003: SMTP failure raises ValueError."""
        mock_settings.smtp_host = "smtp.test.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_from_email = "from@test.com"
        mock_settings.smtp_use_tls = False
        mock_settings.smtp_user = ""
        mock_settings.smtp_password = ""
        mock_settings.password_reset_base_url = "https://example.com/reset"
        mock_settings.password_reset_token_expire_minutes = 30

        mock_smtp_class.side_effect = ConnectionRefusedError

        svc = EmailService()
        with pytest.raises(ValueError, match="重置邮件发送失败"):
            await svc.send_password_reset_email("to@test.com", "token123")

    @patch("app.services.email_service.smtplib.SMTP")
    @patch("app.services.email_service.settings")
    async def test_send_email_no_tls(self, mock_settings, mock_smtp_class):
        """TC-COV-EMAIL-004: Send email without TLS."""
        mock_settings.smtp_host = "smtp.test.com"
        mock_settings.smtp_port = 25
        mock_settings.smtp_from_email = "from@test.com"
        mock_settings.smtp_use_tls = False
        mock_settings.smtp_user = ""
        mock_settings.smtp_password = ""
        mock_settings.password_reset_base_url = "https://example.com/reset"
        mock_settings.password_reset_token_expire_minutes = 30

        mock_smtp = MagicMock()
        mock_smtp_class.return_value = mock_smtp

        svc = EmailService()
        await svc.send_password_reset_email("to@test.com", "token123")
        mock_smtp.starttls.assert_not_called()

    @patch("app.services.email_service._close_thread_smtp")
    @patch("app.services.email_service.smtplib.SMTP")
    @patch("app.services.email_service.settings")
    async def test_send_email_reuses_cached_connection(
        self, mock_settings, mock_smtp_class, mock_close
    ):
        """RES-P1-009: 已有缓存的活跃连接应被复用, 不新建连接."""
        mock_settings.smtp_host = "smtp.test.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_from_email = "from@test.com"
        mock_settings.smtp_use_tls = False
        mock_settings.smtp_user = ""
        mock_settings.smtp_password = ""
        mock_settings.password_reset_base_url = "https://example.com/reset"
        mock_settings.password_reset_token_expire_minutes = 30

        mock_cached = MagicMock()
        mock_cached.noop.return_value = (250, b"OK")

        svc = EmailService()
        with patch(
            "app.services.email_service._get_thread_smtp", return_value=mock_cached
        ):
            await svc.send_password_reset_email("to@test.com", "token123")

        # 缓存连接的 noop 与 send_message 被调用, 未新建连接
        mock_cached.noop.assert_called_once()
        mock_cached.send_message.assert_called_once()
        mock_smtp_class.assert_not_called()

    @patch("app.services.email_service._close_thread_smtp")
    @patch("app.services.email_service.smtplib.SMTP")
    @patch("app.services.email_service.settings")
    async def test_send_email_reconnects_on_noop_failure(
        self, mock_settings, mock_smtp_class, mock_close
    ):
        """RES-P1-009: 缓存连接 NOOP 失败时应重建连接."""
        mock_settings.smtp_host = "smtp.test.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_from_email = "from@test.com"
        mock_settings.smtp_use_tls = False
        mock_settings.smtp_user = ""
        mock_settings.smtp_password = ""
        mock_settings.password_reset_base_url = "https://example.com/reset"
        mock_settings.password_reset_token_expire_minutes = 30

        mock_stale = MagicMock()
        mock_stale.noop.side_effect = OSError("connection reset")
        mock_fresh = MagicMock()
        mock_smtp_class.return_value = mock_fresh

        svc = EmailService()
        with patch(
            "app.services.email_service._get_thread_smtp", return_value=mock_stale
        ):
            await svc.send_password_reset_email("to@test.com", "token123")

        # 旧连接被清理, 新连接被创建并使用
        mock_stale.noop.assert_called_once()
        mock_close.assert_called_once()
        mock_smtp_class.assert_called_once()
        mock_fresh.send_message.assert_called_once()
