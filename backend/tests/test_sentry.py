"""Tests for Sentry integration."""

from __future__ import annotations

import pytest

from app.core.sentry import capture_exception, capture_message, init_sentry

pytestmark = pytest.mark.requires_external


class TestSentry:
    """Test Sentry integration."""

    def test_init_sentry_no_dsn(self):
        """TC-COV-SEN-001: init_sentry with no DSN does not raise."""
        # Should not raise when DSN is not provided
        init_sentry(dsn=None)

    def test_capture_exception_without_sentry(self):
        """TC-COV-SEN-002: capture_exception without Sentry init."""
        try:
            capture_exception(ValueError("test error"))
        except Exception:
            pytest.fail("capture_exception should not raise")

    def test_capture_message_without_sentry(self):
        """TC-COV-SEN-003: capture_message without Sentry init."""
        try:
            capture_message("test message", level="info")
        except Exception:
            pytest.fail("capture_message should not raise")

    def test_init_sentry_with_dsn(self, monkeypatch):
        """TC-COV-SEN-004: init_sentry with DSN."""
        monkeypatch.setenv("SENTRY_DSN", "https://test@example.com/1")
        # Should not raise
        init_sentry()
