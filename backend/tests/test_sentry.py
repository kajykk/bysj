"""Tests for app/core/sentry.py.

Covers Sentry init / capture_exception / capture_message with SDK unavailable
and unavailable DSN paths.
"""
from __future__ import annotations

import logging
import sys
from unittest.mock import MagicMock


def _install_mock_sdk() -> tuple[MagicMock, MagicMock, MagicMock]:
    """Install mock sentry_sdk + FastApiIntegration + SqlalchemyIntegration.

    Returns (sdk_mock, fastapi_integration_mock, sqlalchemy_integration_mock)
    so callers can assert on the specific integration instances.
    """
    mock_sdk = MagicMock()
    mock_scope = MagicMock()
    mock_sdk.new_scope.return_value.__enter__ = MagicMock(return_value=mock_scope)
    mock_sdk.new_scope.return_value.__exit__ = MagicMock(return_value=False)
    mock_sdk._scope = mock_scope

    # Pre-create specific integration mocks so init_sentry uses the SAME instance
    fastapi_int_mock = MagicMock()
    sqlalchemy_int_mock = MagicMock()

    # Create module mocks that have FastApiIntegration/SqlalchemyIntegration as attrs
    fastapi_module = MagicMock()
    fastapi_module.FastApiIntegration = fastapi_int_mock
    sqlalchemy_module = MagicMock()
    sqlalchemy_module.SqlalchemyIntegration = sqlalchemy_int_mock

    # The integrations submodule mock (also referenced)
    integrations_module = MagicMock()
    integrations_module.FastApiIntegration = fastapi_int_mock
    integrations_module.SqlalchemyIntegration = sqlalchemy_int_mock

    sys.modules["sentry_sdk"] = mock_sdk
    sys.modules["sentry_sdk.integrations"] = integrations_module
    sys.modules["sentry_sdk.integrations.fastapi"] = fastapi_module
    sys.modules["sentry_sdk.integrations.sqlalchemy"] = sqlalchemy_module

    return mock_sdk, fastapi_int_mock, sqlalchemy_int_mock


def _uninstall_mock_sdk() -> None:
    """Remove mock sentry_sdk modules from sys.modules."""
    for mod in list(sys.modules.keys()):
        if mod == "sentry_sdk" or mod.startswith("sentry_sdk."):
            del sys.modules[mod]


class TestInitSentry:
    """Test init_sentry() with various DSN and SDK states."""

    def test_no_dsn_skips_initialization(self, caplog) -> None:
        """Without DSN (no env var, no arg), should log warning and return."""
        import os

        from app.core.sentry import init_sentry

        # Ensure SENTRY_DSN is not set in env
        saved_dsn = os.environ.pop("SENTRY_DSN", None)
        try:
            with caplog.at_level(logging.WARNING):
                init_sentry(dsn=None)

            assert any("SENTRY_DSN not set" in r.message for r in caplog.records)
        finally:
            if saved_dsn is not None:
                os.environ["SENTRY_DSN"] = saved_dsn

    def test_sdk_import_failure_does_not_raise(self, caplog) -> None:
        """If sentry_sdk cannot be imported, should log warning and return gracefully."""
        from app.core.sentry import init_sentry

        _uninstall_mock_sdk()
        with caplog.at_level(logging.WARNING):
            # Should not raise even though sentry_sdk is unavailable
            init_sentry(dsn="https://key@sentry.io/123")

    def test_init_with_explicit_dsn_calls_sdk(self) -> None:
        """With explicit DSN and SDK available, should call sentry_sdk.init()."""
        from app.core.sentry import init_sentry

        mock_sdk, _, _ = _install_mock_sdk()
        try:
            init_sentry(
                dsn="https://key@sentry.io/123",
                environment="production",
                release="v1.0.0",
                traces_sample_rate=0.5,
                profiles_sample_rate=0.2,
            )
            assert mock_sdk.init.called
            call_kwargs = mock_sdk.init.call_args.kwargs
            assert call_kwargs["dsn"] == "https://key@sentry.io/123"
            assert call_kwargs["environment"] == "production"
            assert call_kwargs["release"] == "v1.0.0"
            assert call_kwargs["traces_sample_rate"] == 0.5
            assert call_kwargs["profiles_sample_rate"] == 0.2
            assert call_kwargs["send_default_pii"] is False
        finally:
            _uninstall_mock_sdk()

    def test_init_passes_failed_request_status_codes(self) -> None:
        """failed_request_status_codes should include 5xx range (M-Core-13 fix)."""
        from app.core.sentry import init_sentry

        mock_sdk, fastapi_int, _ = _install_mock_sdk()
        try:
            init_sentry(dsn="https://key@sentry.io/123")
            init_kwargs = mock_sdk.init.call_args.kwargs
            integrations = init_kwargs["integrations"]
            # Both integrations should be passed
            assert len(integrations) == 2
            # FastApiIntegration called with transaction_style="endpoint"
            assert fastapi_int.call_args.kwargs.get("transaction_style") == "endpoint"
            codes = fastapi_int.call_args.kwargs.get("failed_request_status_codes")
            assert codes is not None
            # M-Core-13: range(500, 600) should include 599
            assert 403 in codes
            assert 599 in codes
        finally:
            _uninstall_mock_sdk()


class TestCaptureException:
    """Test capture_exception() function."""

    def test_capture_exception_with_context(self) -> None:
        """Should call sentry_sdk.new_scope and set context, then capture."""
        from app.core.sentry import capture_exception

        mock_sdk, _, _ = _install_mock_sdk()
        try:
            exc = ValueError("test error")
            capture_exception(exc, user_id=123, request_id="req-abc")

            mock_sdk.capture_exception.assert_called_once_with(exc)
            mock_scope = mock_sdk._scope
            assert mock_scope.set_extra.call_count == 2
            mock_scope.set_extra.assert_any_call("user_id", 123)
            mock_scope.set_extra.assert_any_call("request_id", "req-abc")
        finally:
            _uninstall_mock_sdk()

    def test_capture_exception_without_context(self) -> None:
        """Should work when called with no extra context."""
        from app.core.sentry import capture_exception

        mock_sdk, _, _ = _install_mock_sdk()
        try:
            capture_exception(RuntimeError("boom"))

            mock_sdk.capture_exception.assert_called_once()
            mock_scope = mock_sdk._scope
            assert mock_scope.set_extra.call_count == 0
        finally:
            _uninstall_mock_sdk()

    def test_capture_exception_sdk_unavailable(self, caplog) -> None:
        """If sentry_sdk is unavailable, should log warning and not raise."""
        from app.core.sentry import capture_exception

        _uninstall_mock_sdk()
        with caplog.at_level(logging.WARNING):
            # Should not raise
            capture_exception(ValueError("test"))


class TestCaptureMessage:
    """Test capture_message() function."""

    def test_capture_message_default_level(self) -> None:
        """Default level should be 'info'."""
        from app.core.sentry import capture_message

        mock_sdk, _, _ = _install_mock_sdk()
        try:
            capture_message("test message")
            mock_sdk.capture_message.assert_called_once_with(
                "test message", level="info"
            )
        finally:
            _uninstall_mock_sdk()

    def test_capture_message_custom_level(self) -> None:
        """Custom level should be passed through."""
        from app.core.sentry import capture_message

        mock_sdk, _, _ = _install_mock_sdk()
        try:
            capture_message("critical issue", level="error")
            mock_sdk.capture_message.assert_called_once_with(
                "critical issue", level="error"
            )
        finally:
            _uninstall_mock_sdk()

    def test_capture_message_sdk_unavailable(self) -> None:
        """If sentry_sdk is unavailable, should not raise."""
        from app.core.sentry import capture_message

        _uninstall_mock_sdk()
        # Should not raise
        capture_message("hello", level="warning")
