"""Extended tests for app/core/contracts module."""

from __future__ import annotations

from app.core.contracts import (
    ACTION_TYPE_WARNING_HANDLE,
    ACTION_TYPE_WARNING_IGNORE,
    ACTION_TYPE_WARNING_READ,
    ACTION_TYPE_WARNING_READ_ALL,
    RISK_LEVEL_MAP,
    WARNING_ACTION_HANDLE,
    WARNING_ACTION_IGNORE,
    normalize_risk_level,
    resolve_warning_status,
)


class TestRiskLevelMap:
    """Test RISK_LEVEL_MAP constants."""

    def test_risk_level_map_values(self):
        """TC-COV-042: RISK_LEVEL_MAP has correct values."""
        assert RISK_LEVEL_MAP[0] == "none"
        assert RISK_LEVEL_MAP[1] == "low"
        assert RISK_LEVEL_MAP[2] == "medium"
        assert RISK_LEVEL_MAP[3] == "high"
        assert RISK_LEVEL_MAP[4] == "critical"


class TestNormalizeRiskLevel:
    """Test normalize_risk_level function."""

    def test_normalize_none(self):
        """TC-COV-043: normalize_risk_level(None) returns 'none'."""
        assert normalize_risk_level(None) == "none"

    def test_normalize_valid_levels(self):
        """TC-COV-044: normalize_risk_level returns correct level for valid inputs."""
        assert normalize_risk_level(0) == "none"
        assert normalize_risk_level(1) == "low"
        assert normalize_risk_level(2) == "medium"
        assert normalize_risk_level(3) == "high"
        assert normalize_risk_level(4) == "critical"

    def test_normalize_invalid_level(self):
        """TC-COV-045: normalize_risk_level returns 'unknown' for invalid level.

        P1-F7 修复：原逻辑返回 'critical' 会触发虚假紧急告警，
        现改为返回 'unknown' 让调用方显式处理异常情况。
        """
        assert normalize_risk_level(999) == "unknown"
        assert normalize_risk_level(-1) == "unknown"


class TestResolveWarningStatus:
    """Test resolve_warning_status function."""

    def test_unhandled_warning(self):
        """TC-COV-046: resolve_warning_status returns 'pending' when not handled."""
        assert resolve_warning_status(False, None) == "pending"
        assert resolve_warning_status(False, WARNING_ACTION_HANDLE) == "pending"

    def test_handled_warning(self):
        """TC-COV-047: resolve_warning_status returns 'handled' when handled."""
        assert resolve_warning_status(True, WARNING_ACTION_HANDLE) == "handled"
        assert resolve_warning_status(True, None) == "handled"

    def test_ignored_warning(self):
        """TC-COV-048: resolve_warning_status returns 'ignored' for ignore action."""
        assert resolve_warning_status(True, WARNING_ACTION_IGNORE) == "ignored"


class TestActionTypeConstants:
    """Test action type constants."""

    def test_action_type_constants(self):
        """TC-COV-049: Action type constants are correct."""
        assert ACTION_TYPE_WARNING_HANDLE == "warning_handle"
        assert ACTION_TYPE_WARNING_IGNORE == "warning_ignore"
        assert ACTION_TYPE_WARNING_READ == "warning_read"
        assert ACTION_TYPE_WARNING_READ_ALL == "warning_read_all"
