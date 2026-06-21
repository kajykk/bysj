"""Tests for core utility modules."""

from __future__ import annotations

import pytest
from fastapi import Request
from starlette.datastructures import Headers

from app.core.risk_thresholds import (
    get_threshold_by_modality,
    get_fusion_threshold,
    should_fallback,
    RISK_LEVEL_THRESHOLDS,
    MODALITY_RISK_THRESHOLDS,
)
from app.core.response import ok
from app.core.request_id import get_or_create_request_id, REQUEST_ID_HEADER


class TestRiskThresholds:
    """Test risk threshold functions."""

    def test_get_threshold_by_modality_structured(self):
        """TC-COV-RISK-001: Get threshold for structured modality."""
        result = get_threshold_by_modality("structured")
        assert result == MODALITY_RISK_THRESHOLDS["structured"]
        assert result["mild"] == 25

    def test_get_threshold_by_modality_physiological(self):
        """TC-COV-RISK-002: Get threshold for physiological modality."""
        result = get_threshold_by_modality("physiological")
        assert result == MODALITY_RISK_THRESHOLDS["physiological"]
        assert result["mild"] == 35

    def test_get_threshold_by_modality_fusion(self):
        """TC-COV-RISK-003: Get threshold for fusion modality."""
        result = get_threshold_by_modality("fusion")
        assert result["critical"] == 82

    def test_get_threshold_by_modality_default(self):
        """TC-COV-RISK-004: Get default threshold for unknown modality."""
        result = get_threshold_by_modality("unknown")
        assert result == RISK_LEVEL_THRESHOLDS

    def test_get_fusion_threshold_low_confidence(self):
        """TC-COV-RISK-005: Fusion threshold with low confidence."""
        result = get_fusion_threshold(50.0, confidence=0.3)
        assert result == 42  # moderate threshold

    def test_get_fusion_threshold_critical(self):
        """TC-COV-RISK-006: Fusion threshold for critical score."""
        result = get_fusion_threshold(85.0)
        assert result == 82

    def test_get_fusion_threshold_high(self):
        """TC-COV-RISK-007: Fusion threshold for high score."""
        result = get_fusion_threshold(65.0)
        assert result == 62

    def test_get_fusion_threshold_moderate(self):
        """TC-COV-RISK-008: Fusion threshold for moderate score."""
        result = get_fusion_threshold(45.0)
        assert result == 42

    def test_get_fusion_threshold_mild(self):
        """TC-COV-RISK-009: Fusion threshold for mild score."""
        result = get_fusion_threshold(25.0)
        assert result == 22

    def test_get_fusion_threshold_below_mild(self):
        """TC-COV-RISK-010: Fusion threshold below mild."""
        result = get_fusion_threshold(10.0)
        assert result == 22  # returns mild as minimum

    def test_should_fallback_no_availability(self):
        """TC-COV-RISK-011: Should fallback when not available."""
        assert should_fallback(0.9, False) is True

    def test_should_fallback_low_confidence(self):
        """TC-COV-RISK-012: Should fallback with low confidence."""
        assert should_fallback(0.3, True) is True

    def test_should_fallback_high_confidence(self):
        """TC-COV-RISK-013: Should not fallback with high confidence."""
        assert should_fallback(0.8, True) is False

    def test_should_fallback_none_confidence(self):
        """TC-COV-RISK-014: Should not fallback when confidence is None."""
        assert should_fallback(None, True) is False


class TestResponse:
    """Test response utility."""

    def test_ok_default(self):
        """TC-COV-RESP-001: Default ok response."""
        result = ok()
        assert result == {"code": 200, "message": "success", "data": None}

    def test_ok_with_data(self):
        """TC-COV-RESP-002: Ok response with data."""
        result = ok(data={"id": 1})
        assert result["data"] == {"id": 1}

    def test_ok_custom_message(self):
        """TC-COV-RESP-003: Ok response with custom message."""
        result = ok(message="created")
        assert result["message"] == "created"


class TestRequestId:
    """Test request ID utility."""

    def test_get_or_create_request_id_existing(self):
        """TC-COV-REQ-001: Use existing request ID from header."""
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(REQUEST_ID_HEADER.encode(), b"existing-id-123")],
            "query_string": b"",
        }
        request = Request(scope)
        result = get_or_create_request_id(request)
        assert result == "existing-id-123"

    def test_get_or_create_request_id_new(self):
        """TC-COV-REQ-002: Create new request ID when not present."""
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
        }
        request = Request(scope)
        result = get_or_create_request_id(request)
        assert len(result) == 36  # UUID length

    def test_get_or_create_request_id_empty(self):
        """TC-COV-REQ-003: Create new request ID when header is empty."""
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(REQUEST_ID_HEADER.encode(), b"")],
            "query_string": b"",
        }
        request = Request(scope)
        result = get_or_create_request_id(request)
        assert len(result) == 36  # UUID length
