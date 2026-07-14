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
            # STAB-P2-010: traces_sample_rate 固定为 1.0, 由 before_send_transaction 过滤
            assert call_kwargs["traces_sample_rate"] == 1.0
            assert call_kwargs["profiles_sample_rate"] == 0.2
            # STAB-P2-010: before_send_transaction 回调必须存在
            assert "before_send_transaction" in call_kwargs
            assert callable(call_kwargs["before_send_transaction"])
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


class TestExtractStatusCode:
    """Test _extract_status_code() for STAB-P2-010."""

    def test_extract_from_request_response_status_code(self) -> None:
        """Should extract status code from event["request"]["response_status_code"]."""
        from app.core.sentry import _extract_status_code

        event = {"request": {"response_status_code": 500}}
        assert _extract_status_code(event) == 500

    def test_extract_from_tags_http_status_code(self) -> None:
        """Should extract status code from event["tags"]["http.status_code"]."""
        from app.core.sentry import _extract_status_code

        event = {"tags": {"http.status_code": 404}}
        assert _extract_status_code(event) == 404

    def test_extract_from_contexts_trace_tags(self) -> None:
        """Should extract status code from event["contexts"]["trace"]["tags"]."""
        from app.core.sentry import _extract_status_code

        event = {"contexts": {"trace": {"tags": {"http.response.status_code": 503}}}}
        assert _extract_status_code(event) == 503

    def test_extract_returns_none_when_missing(self) -> None:
        """Should return None when no status code found."""
        from app.core.sentry import _extract_status_code

        assert _extract_status_code({}) is None
        assert _extract_status_code({"request": {}}) is None

    def test_extract_handles_invalid_code_gracefully(self) -> None:
        """Should return None for non-numeric status code values."""
        from app.core.sentry import _extract_status_code

        event = {"request": {"response_status_code": "not-a-number"}}
        assert _extract_status_code(event) is None

    def test_extract_priority_request_over_tags(self) -> None:
        """Request response_status_code should take priority over tags."""
        from app.core.sentry import _extract_status_code

        event = {
            "request": {"response_status_code": 500},
            "tags": {"http.status_code": 200},
        }
        assert _extract_status_code(event) == 500


class TestBeforeSendTransaction:
    """Test _make_before_send_transaction() for STAB-P2-010."""

    def test_5xx_always_retained(self) -> None:
        """5xx transactions should always be retained (100% sampling)."""
        from app.core.sentry import _make_before_send_transaction

        callback = _make_before_send_transaction(base_sample_rate=0.0)
        for code in [500, 501, 502, 503, 504, 599]:
            event = {"request": {"response_status_code": code}}
            result = callback(event, {})
            assert result is event, f"5xx (code={code}) should be retained"

    def test_non_5xx_with_zero_sample_rate_dropped(self) -> None:
        """Non-5xx with base_sample_rate=0.0 should always be dropped."""
        from app.core.sentry import _make_before_send_transaction

        callback = _make_before_send_transaction(base_sample_rate=0.0)
        for code in [200, 301, 404, 403]:
            event = {"request": {"response_status_code": code}}
            result = callback(event, {})
            assert result is None, f"non-5xx (code={code}) with rate=0 should be dropped"

    def test_non_5xx_with_full_sample_rate_retained(self) -> None:
        """Non-5xx with base_sample_rate=1.0 should always be retained."""
        from app.core.sentry import _make_before_send_transaction

        callback = _make_before_send_transaction(base_sample_rate=1.0)
        event = {"request": {"response_status_code": 200}}
        result = callback(event, {})
        assert result is event

    def test_non_5xx_with_partial_sample_rate(self) -> None:
        """Non-5xx with base_sample_rate=0.5 should roughly 50% retained."""
        from app.core.sentry import _make_before_send_transaction

        callback = _make_before_send_transaction(base_sample_rate=0.5)
        # Run many times to verify probability
        retained = 0
        total = 1000
        for _ in range(total):
            event = {"request": {"response_status_code": 200}}
            if callback(event, {}) is not None:
                retained += 1
        # Should be roughly 50% (allow ±10% tolerance)
        ratio = retained / total
        assert 0.4 < ratio < 0.6, f"retained ratio {ratio:.2f} should be ~0.5"

    def test_no_status_code_uses_base_sample_rate(self) -> None:
        """Events without status code should use base_sample_rate."""
        from app.core.sentry import _make_before_send_transaction

        callback = _make_before_send_transaction(base_sample_rate=0.0)
        event = {}
        assert callback(event, {}) is None

        callback_full = _make_before_send_transaction(base_sample_rate=1.0)
        assert callback_full(event, {}) is event

    def test_5xx_retained_even_with_zero_base_rate(self) -> None:
        """5xx should be retained even when base_sample_rate is 0.0."""
        from app.core.sentry import _make_before_send_transaction

        callback = _make_before_send_transaction(base_sample_rate=0.0)
        event = {"request": {"response_status_code": 500}}
        assert callback(event, {}) is event

    def test_4xx_not_treated_as_5xx(self) -> None:
        """4xx should NOT be treated as 5xx (only 500-599 retained always)."""
        from app.core.sentry import _make_before_send_transaction

        callback = _make_before_send_transaction(base_sample_rate=0.0)
        for code in [400, 401, 403, 404, 422, 429]:
            event = {"request": {"response_status_code": code}}
            result = callback(event, {})
            assert result is None, f"4xx (code={code}) with rate=0 should be dropped"

    def test_status_code_from_tags_path(self) -> None:
        """5xx status code in tags path should also be retained."""
        from app.core.sentry import _make_before_send_transaction

        callback = _make_before_send_transaction(base_sample_rate=0.0)
        event = {"tags": {"http.status_code": 503}}
        assert callback(event, {}) is event

    def test_returns_callable(self) -> None:
        """_make_before_send_transaction should return a callable."""
        from app.core.sentry import _make_before_send_transaction

        callback = _make_before_send_transaction(base_sample_rate=0.1)
        assert callable(callback)


class TestInitSentryBeforeSend:
    """Test init_sentry() passes before_send_transaction for STAB-P2-010."""

    def test_init_passes_before_send_transaction(self) -> None:
        """init_sentry should pass before_send_transaction to sentry_sdk.init."""
        from app.core.sentry import init_sentry

        mock_sdk, _, _ = _install_mock_sdk()
        try:
            init_sentry(dsn="https://key@sentry.io/123", traces_sample_rate=0.3)
            call_kwargs = mock_sdk.init.call_args.kwargs
            assert "before_send_transaction" in call_kwargs
            assert callable(call_kwargs["before_send_transaction"])
        finally:
            _uninstall_mock_sdk()

    def test_init_traces_sample_rate_always_one(self) -> None:
        """traces_sample_rate passed to SDK should always be 1.0 regardless of input."""
        from app.core.sentry import init_sentry

        mock_sdk, _, _ = _install_mock_sdk()
        try:
            for input_rate in [0.0, 0.1, 0.5, 1.0]:
                mock_sdk.reset_mock()
                init_sentry(
                    dsn="https://key@sentry.io/123",
                    traces_sample_rate=input_rate,
                )
                call_kwargs = mock_sdk.init.call_args.kwargs
                assert call_kwargs["traces_sample_rate"] == 1.0, (
                    f"traces_sample_rate should be 1.0 for input {input_rate}"
                )
        finally:
            _uninstall_mock_sdk()

    def test_init_before_send_transaction_filters_5xx(self) -> None:
        """The before_send_transaction from init should retain 5xx."""
        from app.core.sentry import init_sentry

        mock_sdk, _, _ = _install_mock_sdk()
        try:
            init_sentry(dsn="https://key@sentry.io/123", traces_sample_rate=0.0)
            callback = mock_sdk.init.call_args.kwargs["before_send_transaction"]

            # 5xx should be retained even with base_sample_rate=0.0
            event_500 = {"request": {"response_status_code": 500}}
            assert callback(event_500, {}) is event_500

            # non-5xx with base_sample_rate=0.0 should be dropped
            event_200 = {"request": {"response_status_code": 200}}
            assert callback(event_200, {}) is None
        finally:
            _uninstall_mock_sdk()

    def test_log_message_mentions_5xx_traces(self, caplog) -> None:
        """Log message should mention '5xx traces=1.0'."""
        from app.core.sentry import init_sentry

        mock_sdk, _, _ = _install_mock_sdk()
        try:
            with caplog.at_level(logging.INFO):
                init_sentry(dsn="https://key@sentry.io/123", traces_sample_rate=0.1)
            assert any("5xx traces=1.0" in r.message for r in caplog.records)
            assert any("non-5xx traces=0.1" in r.message for r in caplog.records)
        finally:
            _uninstall_mock_sdk()
