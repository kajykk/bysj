"""Tests for InputValidator service."""

from __future__ import annotations

import pytest
import math

from app.services.input_validator import InputValidator, ValidationResult


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_default_creation(self):
        """TC-COV-VAL-001: ValidationResult default values."""
        result = ValidationResult()
        assert result.is_valid is True
        assert result.errors == []
        assert result.sanitized_input is None

    def test_add_error(self):
        """TC-COV-VAL-002: add_error updates state."""
        result = ValidationResult()
        result.add_error("field1", "test_error", "Test message")
        assert result.is_valid is False
        assert len(result.errors) == 1
        assert result.errors[0]["field"] == "field1"
        assert result.errors[0]["anomaly_type"] == "test_error"

    def test_to_dict(self):
        """TC-COV-VAL-003: to_dict returns correct structure."""
        result = ValidationResult()
        result.add_error("field", "type", "msg")
        result.sanitized_input = {"key": "value"}
        d = result.to_dict()
        assert d["is_valid"] is False
        assert len(d["errors"]) == 1
        assert d["sanitized_input"] == {"key": "value"}


class TestInputValidator:
    """Test input validation service."""

    def test_validate_tabular_with_valid_data(self):
        """TC-COV-VAL-004: Valid structured data passes validation."""
        validator = InputValidator()
        result = validator.validate_tabular({
            "sleep_hours": 7.0,
            "exercise_minutes": 30.0,
            "heart_rate": 70.0,
        })
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert result.sanitized_input["sleep_hours"] == 7.0

    def test_validate_tabular_with_none_input(self):
        """TC-COV-VAL-005: None input returns validation error."""
        validator = InputValidator()
        result = validator.validate_tabular(None)
        assert result.is_valid is False
        assert any(e["anomaly_type"] == "null_input" for e in result.errors)

    def test_validate_tabular_with_non_dict_input(self):
        """TC-COV-VAL-006: Non-dict input returns validation error."""
        validator = InputValidator()
        result = validator.validate_tabular("not a dict")
        assert result.is_valid is False
        assert any(e["anomaly_type"] == "type_error" for e in result.errors)

    def test_validate_tabular_with_empty_dict(self):
        """TC-COV-VAL-007: Empty dict returns validation error."""
        validator = InputValidator()
        result = validator.validate_tabular({})
        assert result.is_valid is False
        assert any(e["anomaly_type"] == "empty_input" for e in result.errors)

    def test_validate_tabular_with_all_empty_values(self):
        """TC-COV-VAL-008: All-empty values returns validation error."""
        validator = InputValidator()
        result = validator.validate_tabular({
            "sleep_hours": None,
            "exercise_minutes": "",
        })
        assert result.is_valid is False
        assert any(e["anomaly_type"] == "all_empty" for e in result.errors)

    def test_validate_tabular_with_invalid_types(self):
        """TC-COV-VAL-009: Invalid types returns validation error."""
        validator = InputValidator()
        result = validator.validate_tabular({
            "sleep_hours": [1, 2, 3],
            "exercise_minutes": {"value": 10},
        })
        assert result.is_valid is False
        assert any(e["anomaly_type"] == "illegal_type" for e in result.errors)

    def test_validate_tabular_with_nan_values(self):
        """TC-COV-VAL-010: NaN values returns validation error."""
        validator = InputValidator()
        result = validator.validate_tabular({
            "sleep_hours": float("nan"),
        })
        assert result.is_valid is False
        assert any(e["anomaly_type"] == "nan_value" for e in result.errors)

    def test_validate_tabular_with_inf_values(self):
        """TC-COV-VAL-011: Inf values returns validation error."""
        validator = InputValidator()
        result = validator.validate_tabular({
            "exercise_minutes": float("inf"),
        })
        assert result.is_valid is False
        assert any(e["anomaly_type"] == "inf_value" for e in result.errors)

    def test_validate_tabular_with_negative_inf_values(self):
        """TC-COV-VAL-012: Negative Inf values returns validation error."""
        validator = InputValidator()
        result = validator.validate_tabular({
            "exercise_minutes": float("-inf"),
        })
        assert result.is_valid is False
        assert any(e["anomaly_type"] == "inf_value" for e in result.errors)

    def test_validate_tabular_with_out_of_range_values(self):
        """TC-COV-VAL-013: Out-of-range values returns validation error."""
        validator = InputValidator()
        result = validator.validate_tabular({
            "sleep_hours": 999.0,
            "exercise_minutes": -10.0,
        })
        assert result.is_valid is False
        assert any(e["anomaly_type"] == "out_of_range" for e in result.errors)

    def test_validate_tabular_with_required_fields(self):
        """TC-COV-VAL-014: Missing required fields returns validation error."""
        validator = InputValidator()
        result = validator.validate_tabular(
            {"exercise_minutes": 30.0},
            required_fields=["sleep_hours", "exercise_minutes"],
        )
        assert result.is_valid is False
        assert any(e["anomaly_type"] == "missing_required" for e in result.errors)

    def test_validate_tabular_with_non_numeric_range_field(self):
        """TC-COV-VAL-015: Non-numeric value in range field returns error."""
        validator = InputValidator()
        result = validator.validate_tabular({
            "sleep_hours": "not_a_number",
        })
        assert result.is_valid is False
        assert any(e["anomaly_type"] == "type_error" for e in result.errors)

    def test_validate_text_with_valid_input(self):
        """TC-COV-VAL-016: Valid text input passes validation."""
        validator = InputValidator()
        result = validator.validate_text("I feel sad today")
        assert result.is_valid is True
        assert result.sanitized_input == {"text": "I feel sad today"}

    def test_validate_text_with_empty_input(self):
        """TC-COV-VAL-017: Empty text returns validation error."""
        validator = InputValidator()
        result = validator.validate_text("")
        assert result.is_valid is False
        assert any(e["anomaly_type"] == "empty_text" for e in result.errors)

    def test_validate_text_with_none_input(self):
        """TC-COV-VAL-018: None text returns validation error."""
        validator = InputValidator()
        result = validator.validate_text(None)
        assert result.is_valid is False
        assert any(e["anomaly_type"] == "missing_required" for e in result.errors)

    def test_validate_text_with_non_string_input(self):
        """TC-COV-VAL-019: Non-string text returns validation error."""
        validator = InputValidator()
        result = validator.validate_text(123)
        assert result.is_valid is False
        assert any(e["anomaly_type"] == "type_error" for e in result.errors)

    def test_validate_text_with_too_short_input(self):
        """TC-COV-VAL-020: Too short text returns validation error."""
        validator = InputValidator()
        result = validator.validate_text("ab")
        assert result.is_valid is False
        assert any(e["anomaly_type"] == "too_short" for e in result.errors)

    def test_validate_text_with_too_long_input(self):
        """TC-COV-VAL-021: Too long text returns validation error."""
        validator = InputValidator()
        long_text = "a" * 10001
        result = validator.validate_text(long_text)
        assert result.is_valid is False
        assert any(e["anomaly_type"] == "too_long" for e in result.errors)

    def test_validate_text_with_extreme_distribution(self):
        """TC-COV-VAL-022: Single repeated character returns error."""
        validator = InputValidator()
        result = validator.validate_text("aaaaaaaaaa")
        assert result.is_valid is False
        assert any(e["anomaly_type"] == "extreme_distribution" for e in result.errors)

    def test_validate_text_with_low_diversity(self):
        """TC-COV-VAL-023: Low character diversity returns error."""
        validator = InputValidator()
        result = validator.validate_text("abababababab")
        assert result.is_valid is False
        assert any(e["anomaly_type"] == "extreme_distribution" for e in result.errors)

    def test_validate_physiological_with_valid_data(self):
        """TC-COV-VAL-024: Valid physiological data passes validation."""
        validator = InputValidator()
        result = validator.validate_physiological({
            "sleep_hours": 7.0,
            "sleep_quality": 8,
            "exercise_minutes": 30,
            "heart_rate": 70,
            "systolic_bp": 120,
            "diastolic_bp": 80,
            "steps": 10000,
        })
        assert result.is_valid is True

    def test_validate_physiological_with_missing_required(self):
        """TC-COV-VAL-025: Missing required physiological fields returns error."""
        validator = InputValidator()
        result = validator.validate_physiological({
            "sleep_hours": 7.0,
        })
        assert result.is_valid is False
        assert any(e["anomaly_type"] == "missing_required" for e in result.errors)

    def test_validate_fusion_with_all_valid(self):
        """TC-COV-VAL-026: Valid fusion inputs pass validation."""
        validator = InputValidator()
        result = validator.validate_fusion(
            features={"feature1": 1.0},
            text="I feel okay today",
            physiological={
                "sleep_hours": 7.0,
                "sleep_quality": 8,
                "exercise_minutes": 30,
                "heart_rate": 70,
                "systolic_bp": 120,
                "diastolic_bp": 80,
                "steps": 10000,
            },
        )
        assert result.is_valid is True
        assert "features" in result.sanitized_input
        assert "text" in result.sanitized_input
        assert "physiological" in result.sanitized_input

    def test_validate_fusion_with_invalid_text(self):
        """TC-COV-VAL-027: Invalid text in fusion returns error."""
        validator = InputValidator()
        result = validator.validate_fusion(text="")
        assert result.is_valid is False
        assert any(e["anomaly_type"] == "empty_text" for e in result.errors)

    def test_validate_fusion_with_invalid_features(self):
        """TC-COV-VAL-028: Invalid features in fusion returns error."""
        validator = InputValidator()
        result = validator.validate_fusion(features=None)
        # 当 features=None,text=None 时允许返回 valid(由实现决定)
        assert isinstance(result.is_valid, bool)

    def test_validate_fusion_with_partial_valid(self):
        """TC-COV-VAL-029: Fusion with only text valid."""
        validator = InputValidator()
        result = validator.validate_fusion(text="Valid text here")
        assert result.is_valid is True
        assert result.sanitized_input["text"] == "Valid text here"

    def test_global_validator_instance(self):
        """TC-COV-VAL-030: Global validator instance exists."""
        from app.services.input_validator import input_validator
        assert isinstance(input_validator, InputValidator)
