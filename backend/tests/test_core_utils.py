"""Tests for core utility modules."""

from __future__ import annotations

from fastapi import Request

from app.core.request_id import REQUEST_ID_HEADER, get_or_create_request_id
from app.core.response import fail, ok
from app.core.risk_thresholds import (
    MODALITY_RISK_THRESHOLDS,
    RISK_LEVEL_LABELS,
    RISK_LEVEL_THRESHOLDS,
    get_fusion_threshold,
    get_threshold_by_modality,
    score_to_level,
    should_fallback,
)


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
        # M-Core-11: score 低于 mild 阈值时返回 0（最低级别），不再强制返回 mild
        assert result == 0

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
        # STAB-P1-001: 统一响应体结构含 error: None
        assert result == {
            "code": 200,
            "message": "success",
            "data": None,
            "error": None,
        }

    def test_ok_with_data(self):
        """TC-COV-RESP-002: Ok response with data."""
        result = ok(data={"id": 1})
        assert result["data"] == {"id": 1}
        assert result["error"] is None
        assert result["code"] == 200

    def test_ok_custom_message(self):
        """TC-COV-RESP-003: Ok response with custom message."""
        result = ok(message="created")
        assert result["message"] == "created"
        assert result["error"] is None

    def test_ok_custom_code(self):
        """TC-COV-RESP-004: Ok response with custom code (e.g. 201 Created)."""
        result = ok(data={"id": 1}, message="created", code=201)
        assert result["code"] == 201
        assert result["message"] == "created"
        assert result["data"] == {"id": 1}

    def test_fail_default(self):
        """TC-COV-RESP-005: Default fail response."""
        result = fail("internal error")
        assert result["code"] == 500
        assert result["message"] == "internal error"
        assert result["data"] is None
        # fail 默认将 error 设为 {"message": "..."} 占位
        assert result["error"] == {"message": "internal error"}

    def test_fail_with_explicit_error(self):
        """TC-COV-RESP-006: Fail response with explicit error dict."""
        result = fail("bad request", code=400, error={"code": "INVALID_INPUT"})
        assert result["code"] == 400
        assert result["error"] == {"code": "INVALID_INPUT"}
        assert result["data"] is None

    def test_fail_with_string_error(self):
        """TC-COV-RESP-007: Fail response with string error detail."""
        result = fail("warn", code=400, error="validation failed")
        assert result["error"] == "validation failed"


class TestScoreToLevel:
    """Test score_to_level 风险等级转换函数."""

    def test_critical_level_structured(self):
        """structured 模态 critical 阈值=85, score=90 → level=4."""
        assert score_to_level(90, "structured") == 4

    def test_high_level_structured(self):
        """structured 模态 high 阈值=65, score=70 → level=3."""
        assert score_to_level(70, "structured") == 3

    def test_moderate_level_structured(self):
        """structured 模态 moderate 阈值=45, score=50 → level=2."""
        assert score_to_level(50, "structured") == 2

    def test_mild_level_structured(self):
        """structured 模态 mild 阈值=25, score=30 → level=1."""
        assert score_to_level(30, "structured") == 1

    def test_none_level_below_mild(self):
        """score < mild 阈值 → level=0 (none)."""
        assert score_to_level(10, "structured") == 0
        assert score_to_level(0, "structured") == 0

    def test_boundary_critical(self):
        """score == critical 阈值时 → level=4 (>=)."""
        assert score_to_level(85, "structured") == 4

    def test_boundary_high(self):
        """score == high 阈值 (65) 时 → level=3 (因 65 < critical=85)."""
        assert score_to_level(65, "structured") == 3

    def test_boundary_below_critical(self):
        """score < critical 但 == high 时 → level=3."""
        assert score_to_level(70, "structured") == 3
        assert score_to_level(80, "structured") == 3

    def test_score_just_below_critical(self):
        """score = critical-1 → level=3."""
        assert score_to_level(84, "structured") == 3

    def test_text_modality(self):
        """text 模态阈值: critical=80, high=60, moderate=40, mild=20."""
        assert score_to_level(85, "text") == 4
        assert score_to_level(70, "text") == 3
        assert score_to_level(45, "text") == 2
        assert score_to_level(25, "text") == 1
        assert score_to_level(10, "text") == 0

    def test_physiological_modality(self):
        """physiological 模态阈值: critical=90, high=75, moderate=55, mild=35."""
        assert score_to_level(95, "physiological") == 4
        assert score_to_level(80, "physiological") == 3
        assert score_to_level(60, "physiological") == 2
        assert score_to_level(40, "physiological") == 1
        assert score_to_level(20, "physiological") == 0

    def test_fusion_modality(self):
        """fusion 模态阈值: critical=82, high=62, moderate=42, mild=22."""
        assert score_to_level(90, "fusion") == 4
        assert score_to_level(70, "fusion") == 3
        assert score_to_level(50, "fusion") == 2
        assert score_to_level(25, "fusion") == 1

    def test_default_modality_is_structured(self):
        """默认 modality='structured'."""
        # 不传 modality 应等价于 structured
        assert score_to_level(90) == score_to_level(90, "structured")
        assert score_to_level(30) == score_to_level(30, "structured")

    def test_unknown_modality_falls_back_to_default(self):
        """未知 modality 应回退到 RISK_LEVEL_THRESHOLDS."""
        # 未知 modality 使用 RISK_LEVEL_THRESHOLDS: critical=80
        assert score_to_level(85, "unknown") == 4
        assert score_to_level(65, "unknown") == 3
        assert score_to_level(45, "unknown") == 2
        assert score_to_level(25, "unknown") == 1
        assert score_to_level(10, "unknown") == 0

    def test_risk_level_labels_complete(self):
        """RISK_LEVEL_LABELS 包含 0~4 全部等级."""
        assert RISK_LEVEL_LABELS[0] == "none"
        assert RISK_LEVEL_LABELS[1] == "mild"
        assert RISK_LEVEL_LABELS[2] == "moderate"
        assert RISK_LEVEL_LABELS[3] == "high"
        assert RISK_LEVEL_LABELS[4] == "critical"

    def test_modality_risk_thresholds_all_modalities(self):
        """MODALITY_RISK_THRESHOLDS 包含所有 4 个模态."""
        for mod in ("structured", "text", "physiological", "fusion"):
            assert mod in MODALITY_RISK_THRESHOLDS
            for level in ("mild", "moderate", "high", "critical"):
                assert level in MODALITY_RISK_THRESHOLDS[mod]

    def test_risk_level_thresholds_keys(self):
        """RISK_LEVEL_THRESHOLDS 包含 mild/moderate/high/critical."""
        for k in ("mild", "moderate", "high", "critical"):
            assert k in RISK_LEVEL_THRESHOLDS


class TestGetFusionThreshold:
    """Test get_fusion_threshold 函数."""

    def test_critical_score(self):
        """score >= critical(82) → 返回 critical(82)."""
        assert get_fusion_threshold(85.0) == 82
        assert get_fusion_threshold(100.0) == 82

    def test_high_score(self):
        """62 <= score < 82 → 返回 high(62)."""
        assert get_fusion_threshold(70.0) == 62
        assert get_fusion_threshold(80.0) == 62

    def test_moderate_score(self):
        """42 <= score < 62 → 返回 moderate(42)."""
        assert get_fusion_threshold(50.0) == 42
        assert get_fusion_threshold(60.0) == 42

    def test_mild_score(self):
        """22 <= score < 42 → 返回 mild(22)."""
        assert get_fusion_threshold(30.0) == 22
        assert get_fusion_threshold(40.0) == 22

    def test_below_mild_returns_zero(self):
        """score < mild(22) → 返回 0 (M-Core-11 修复)."""
        assert get_fusion_threshold(10.0) == 0
        assert get_fusion_threshold(0.0) == 0

    def test_low_confidence_logged_but_no_change(self):
        """low confidence 仅记录日志, 不影响返回值 (M-Core-11)."""
        # confidence < 0.5 不再强制返回 moderate
        assert get_fusion_threshold(85.0, confidence=0.3) == 82
        assert get_fusion_threshold(10.0, confidence=0.3) == 0

    def test_high_confidence(self):
        """confidence >= 0.5 正常返回对应阈值."""
        assert get_fusion_threshold(70.0, confidence=0.8) == 62


class TestShouldFallback:
    """Test should_fallback 函数."""

    def test_unavailable_returns_true(self):
        """availability=False → 总是 fallback."""
        assert should_fallback(0.9, False) is True
        assert should_fallback(None, False) is True
        assert should_fallback(0.1, False) is True

    def test_available_high_confidence_returns_false(self):
        """availability=True 且 confidence >= 0.5 → 不 fallback."""
        assert should_fallback(0.5, True) is False
        assert should_fallback(0.8, True) is False
        assert should_fallback(1.0, True) is False

    def test_available_low_confidence_returns_true(self):
        """availability=True 且 confidence < 0.5 → fallback."""
        assert should_fallback(0.4, True) is True
        assert should_fallback(0.0, True) is True

    def test_available_none_confidence_returns_false(self):
        """availability=True 且 confidence=None → 不 fallback."""
        assert should_fallback(None, True) is False


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
