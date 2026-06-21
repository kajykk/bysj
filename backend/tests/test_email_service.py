"""Tests for email service."""

from __future__ import annotations

import logging
from unittest.mock import patch, MagicMock

import pytest

from app.services.email_service import EmailService


class TestEmailService:
    """Test email service."""

    async def test_smtp_not_configured(self, caplog):
        """TC-COV-EMAIL-001: SMTP not configured logs warning."""
        with caplog.at_level(logging.WARNING):
            svc = EmailService()
            await svc.send_password_reset_email("test@test.com", "token123")
        # P1-E 修复：日志消息已脱敏，不再记录含 token 的 reset_link
        assert "smtp_not_configured" in caplog.text
        assert "token" not in caplog.text.lower() or "token generated but not delivered" in caplog.text

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
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp

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
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp

        svc = EmailService()
        await svc.send_password_reset_email("to@test.com", "token123")
        mock_smtp.starttls.assert_not_called()
