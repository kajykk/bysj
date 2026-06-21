"""Tests for app/core modules."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from app.core.response import ok
from app.core.contracts import (
    RISK_LEVEL_MAP,
    WARNING_ACTION_HANDLE,
    WARNING_ACTION_IGNORE,
    ACTION_TYPE_WARNING_HANDLE,
    ACTION_TYPE_WARNING_IGNORE,
    normalize_risk_level,
    resolve_warning_status,
)
from app.core.risk_thresholds import (
    RISK_LEVEL_THRESHOLDS,
    MODALITY_RISK_THRESHOLDS,
    RISK_LEVEL_LABELS,
    get_threshold_by_modality,
    get_fusion_threshold,
    should_fallback,
)
from app.core.states import BindingStatus
from app.core.request_id import get_or_create_request_id, REQUEST_ID_HEADER
from app.core.exceptions import (
    AppException,
    ModelException,
    ValidationException,
    ServiceException,
    install_exception_handlers,
)


class TestResponse:
    """Test response utility."""

    def test_ok_with_data(self):
        """TC-COV-CORE-001: ok() returns correct structure with data."""
        result = ok({"key": "value"})
        assert result["code"] == 200
        assert result["message"] == "success"
        assert result["data"] == {"key": "value"}

    def test_ok_with_custom_message(self):
        """TC-COV-CORE-002: ok() with custom message."""
        result = ok(None, message="custom")
        assert result["message"] == "custom"

    def test_ok_with_custom_code(self):
        """TC-COV-CORE-003: ok() with custom code."""
        result = ok(None, code=201)
        assert result["code"] == 201

    def test_ok_with_none_data(self):
        """TC-COV-CORE-004: ok() with None data."""
        result = ok()
        assert result["data"] is None


class TestContracts:
    """Test contracts module."""

    def test_normalize_risk_level_none(self):
        """TC-COV-CORE-005: normalize_risk_level with None returns none."""
        assert normalize_risk_level(None) == "none"

    def test_normalize_risk_level_valid(self):
        """TC-COV-CORE-006: normalize_risk_level with valid levels."""
        assert normalize_risk_level(0) == "none"
        assert normalize_risk_level(1) == "low"
        assert normalize_risk_level(2) == "medium"
        assert normalize_risk_level(3) == "high"
        assert normalize_risk_level(4) == "critical"

    def test_normalize_risk_level_invalid(self):
        """TC-COV-CORE-007: normalize_risk_level with invalid level returns critical."""
        assert normalize_risk_level(999) == "critical"
        assert normalize_risk_level(-1) == "critical"

    def test_resolve_warning_status_pending(self):
        """TC-COV-CORE-008: resolve_warning_status for unhandled warning."""
        assert resolve_warning_status(False, None) == "pending"
        assert resolve_warning_status(False, "handle") == "pending"

    def test_resolve_warning_status_ignored(self):
        """TC-COV-CORE-009: resolve_warning_status for ignored warning."""
        assert resolve_warning_status(True, WARNING_ACTION_IGNORE) == "ignored"

    def test_resolve_warning_status_handled(self):
        """TC-COV-CORE-010: resolve_warning_status for handled warning."""
        assert resolve_warning_status(True, WARNING_ACTION_HANDLE) == "handled"
        assert resolve_warning_status(True, None) == "handled"

    def test_constants(self):
        """TC-COV-CORE-011: Contract constants are defined."""
        assert WARNING_ACTION_HANDLE == "handle"
        assert WARNING_ACTION_IGNORE == "ignore"
        assert ACTION_TYPE_WARNING_HANDLE == "warning_handle"
        assert ACTION_TYPE_WARNING_IGNORE == "warning_ignore"


class TestRiskThresholds:
    """Test risk thresholds module."""

    def test_get_threshold_by_modality_structured(self):
        """TC-COV-CORE-012: get_threshold_by_modality for structured (v1.31: 使用 modality-specific)."""
        from app.core.risk_thresholds import MODALITY_RISK_THRESHOLDS
        result = get_threshold_by_modality("structured")
        # v1.31: 返回 modality 特定阈值 (25, 45, 65, 85)
        assert result == MODALITY_RISK_THRESHOLDS["structured"]
        assert result["mild"] == 25

    def test_get_threshold_by_modality_physiological(self):
        """TC-COV-CORE-013: get_threshold_by_modality for physiological."""
        result = get_threshold_by_modality("physiological")
        assert result == MODALITY_RISK_THRESHOLDS["physiological"]
        assert result["mild"] == 35
        assert result["critical"] == 90

    def test_get_threshold_by_modality_unknown(self):
        """TC-COV-CORE-014: get_threshold_by_modality for unknown returns default."""
        result = get_threshold_by_modality("unknown")
        assert result == RISK_LEVEL_THRESHOLDS

    def test_get_fusion_threshold_low_confidence(self):
        """TC-COV-CORE-015: get_fusion_threshold with low confidence."""
        result = get_fusion_threshold(50, confidence=0.3)
        assert result == MODALITY_RISK_THRESHOLDS["fusion"]["moderate"]

    def test_get_fusion_threshold_high_score(self):
        """TC-COV-CORE-016: get_fusion_threshold with high score."""
        result = get_fusion_threshold(90, confidence=0.9)
        assert result == MODALITY_RISK_THRESHOLDS["fusion"]["critical"]

    def test_get_fusion_threshold_no_confidence(self):
        """TC-COV-CORE-017: get_fusion_threshold without confidence."""
        result = get_fusion_threshold(50)
        assert result == MODALITY_RISK_THRESHOLDS["fusion"]["moderate"]

    def test_should_fallback_unavailable(self):
        """TC-COV-CORE-018: should_fallback when unavailable."""
        assert should_fallback(0.9, False) is True
        assert should_fallback(None, False) is True

    def test_should_fallback_available(self):
        """TC-COV-CORE-019: should_fallback when available."""
        assert should_fallback(0.9, True) is False
        assert should_fallback(0.3, True) is True
        assert should_fallback(None, True) is False

    def test_risk_level_labels(self):
        """TC-COV-CORE-020: Risk level labels are correct."""
        assert RISK_LEVEL_LABELS[0] == "none"
        assert RISK_LEVEL_LABELS[4] == "critical"


class TestBindingStatus:
    """Test BindingStatus enum."""

    def test_normalize_valid(self):
        """TC-COV-CORE-021: Normalize valid status."""
        assert BindingStatus.normalize("active") == BindingStatus.ACTIVE
        assert BindingStatus.normalize("inactive") == BindingStatus.INACTIVE
        assert BindingStatus.normalize("placeholder") == BindingStatus.PLACEHOLDER

    def test_normalize_invalid(self):
        """TC-COV-CORE-022: Normalize invalid status returns INACTIVE."""
        assert BindingStatus.normalize("invalid") == BindingStatus.INACTIVE
        assert BindingStatus.normalize(None) == BindingStatus.INACTIVE

    def test_is_code_usable(self):
        """TC-COV-CORE-023: is_code_usable checks."""
        assert BindingStatus.is_code_usable("active") is True
        assert BindingStatus.is_code_usable("placeholder") is True
        assert BindingStatus.is_code_usable("inactive") is False
        assert BindingStatus.is_code_usable(None) is False


class TestRequestId:
    """Test request_id module."""

    def test_get_or_create_request_id_from_header(self):
        """TC-COV-CORE-024: Get request ID from header."""
        from starlette.datastructures import Headers
        from starlette.requests import Request as StarletteRequest

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"x-request-id", b"test-id-123")],
        }
        request = StarletteRequest(scope)
        result = get_or_create_request_id(request)
        assert result == "test-id-123"

    def test_get_or_create_request_id_generates_new(self):
        """TC-COV-CORE-025: Generate new request ID when header missing."""
        from starlette.requests import Request as StarletteRequest

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
        }
        request = StarletteRequest(scope)
        result = get_or_create_request_id(request)
        assert len(result) > 0
        assert result != ""


class TestExceptions:
    """Test exception classes."""

    def test_app_exception_basic(self):
        """TC-COV-CORE-026: AppException basic creation."""
        exc = AppException("TEST_CODE", "Test message")
        assert exc.code == "TEST_CODE"
        assert exc.message == "Test message"
        assert exc.status_code == 500
        assert exc.layer is None
        assert exc.fallback_to is None

    def test_app_exception_full(self):
        """TC-COV-CORE-027: AppException with all fields."""
        exc = AppException(
            "TEST",
            "message",
            status_code=400,
            details={"key": "value"},
            layer="MODEL",
            fallback_to="RULE",
        )
        assert exc.status_code == 400
        assert exc.details == {"key": "value"}
        assert exc.layer == "MODEL"
        assert exc.fallback_to == "RULE"

    def test_app_exception_to_dict(self):
        """TC-COV-CORE-028: AppException to_dict."""
        exc = AppException("TEST", "message")
        result = exc.to_dict()
        assert "error" in result
        assert result["error"]["code"] == "TEST"
        assert result["error"]["message"] == "message"

    def test_model_exception(self):
        """TC-COV-CORE-029: ModelException creation."""
        exc = ModelException("MODEL_FAIL", "Model failed")
        assert exc.code == "MODEL_FAIL"
        assert exc.layer == "MODEL"

    def test_validation_exception(self):
        """TC-COV-CORE-030: ValidationException creation."""
        exc = ValidationException("INVALID", "Invalid input")
        assert exc.code == "INVALID"
        assert exc.layer == "VALIDATION"
        assert exc.status_code == 422

    def test_service_exception(self):
        """TC-COV-CORE-031: ServiceException creation."""
        exc = ServiceException("SERVICE_FAIL", "Service failed")
        assert exc.code == "SERVICE_FAIL"
        assert exc.layer == "SERVICE"

    def test_install_exception_handlers(self):
        """TC-COV-CORE-032: Install exception handlers on FastAPI app."""
        app = FastAPI()
        install_exception_handlers(app)
        # Verify handlers are installed by checking exception_handlers
        assert len(app.exception_handlers) > 0
