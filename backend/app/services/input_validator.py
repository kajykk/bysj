from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of input validation."""

    is_valid: bool = True
    errors: list[dict[str, Any]] = field(default_factory=list)
    sanitized_input: dict[str, Any] | None = None

    def add_error(
        self, field: str, anomaly_type: str, message: str, details: dict | None = None
    ) -> None:
        self.is_valid = False
        self.errors.append(
            {
                "field": field,
                "anomaly_type": anomaly_type,
                "message": message,
                "details": details or {},
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "sanitized_input": self.sanitized_input,
        }


class InputValidator:
    """Validates model inputs for anomalies.

    Detects:
    - NaN / Inf values in numeric fields
    - Missing required fields
    - Empty or too-short text
    - Extreme distribution outliers
    """

    # Default valid ranges for physiological features
    PHYSIOLOGICAL_RANGES: dict[str, tuple[float, float]] = {
        "sleep_hours": (0, 24),
        "sleep_quality": (1, 10),
        "exercise_minutes": (0, 1440),
        "heart_rate": (30, 220),
        "systolic_bp": (70, 250),
        "diastolic_bp": (40, 150),
        "steps": (0, 50000),
    }

    # Text constraints
    MIN_TEXT_LENGTH = 3
    MAX_TEXT_LENGTH = 10000

    def __init__(self) -> None:
        pass

    def validate_tabular(
        self, features: dict[str, Any] | None, required_fields: list[str] | None = None
    ) -> ValidationResult:
        """Validate tabular/structured input features.

        Handles:
        - Empty/null input
        - Missing required fields
        - NaN/Inf values
        - Out-of-range values
        - All-empty columns
        - Illegal types
        """
        result = ValidationResult()
        result.sanitized_input = {}

        # Handle null/empty input
        if features is None:
            result.add_error("features", "null_input", "Input features cannot be None")
            return result

        if not isinstance(features, dict):
            result.add_error(
                "features",
                "type_error",
                f"Expected dict, got {type(features).__name__}",
            )
            return result

        if len(features) == 0:
            result.add_error(
                "features", "empty_input", "Input features cannot be empty"
            )
            return result

        # Check for all-empty values (all keys have None/empty values)
        non_empty_values = [v for v in features.values() if v is not None and v != ""]
        if len(non_empty_values) == 0:
            result.add_error(
                "features", "all_empty", "All feature values are empty or null"
            )

        # Check required fields
        if required_fields:
            for field_name in required_fields:
                if field_name not in features or features[field_name] is None:
                    result.add_error(
                        field_name,
                        "missing_required",
                        f"Missing required field: {field_name}",
                    )

        # Validate each feature
        # L-11 修复：原实现对每个 key 调用 any(e["field"] == key for e in result.errors)
        # 进行 O(n²) 嵌套查找。改为先构建错误字段集合，将 sanitize 检查降为 O(1)。
        error_fields: set[str] = set()
        for key, value in features.items():
            # Skip None values (already handled by required_fields check)
            if value is None:
                continue

            # M-Svc-14 修复：list/dict/set 不直接拒绝，转换为可验证形式后继续验证。
            # 原实现直接拒绝集合类型，导致多值特征（如 list/dict）无法通过校验。
            # - list/set → tuple（不可变，更适合作为特征值）
            # - dict → tuple(values())（提取值后验证）
            if isinstance(value, list):
                value = tuple(value)
            elif isinstance(value, set):
                value = tuple(value)
            elif isinstance(value, dict):
                value = tuple(value.values())

            # Check for NaN / Inf in numeric fields
            if isinstance(value, float):
                if math.isnan(value):
                    result.add_error(
                        key, "nan_value", f"NaN value detected in field: {key}"
                    )
                    error_fields.add(key)
                    continue
                if math.isinf(value):
                    result.add_error(
                        key, "inf_value", f"Inf value detected in field: {key}"
                    )
                    error_fields.add(key)
                    continue

            # Check range for known physiological fields
            if key in self.PHYSIOLOGICAL_RANGES and value is not None:
                min_val, max_val = self.PHYSIOLOGICAL_RANGES[key]
                try:
                    numeric_value = float(value)
                    if numeric_value < min_val or numeric_value > max_val:
                        result.add_error(
                            key,
                            "out_of_range",
                            f"Value {numeric_value} out of range [{min_val}, {max_val}] for {key}",
                            {"min": min_val, "max": max_val, "value": numeric_value},
                        )
                        error_fields.add(key)
                except (ValueError, TypeError):
                    result.add_error(
                        key, "type_error", f"Non-numeric value for field: {key}"
                    )
                    error_fields.add(key)

            # Sanitize: keep valid values (集合查找 O(1)，避免 O(n²) 嵌套遍历)
            if key not in error_fields:
                result.sanitized_input[key] = value

        # Record anomalies if any
        if not result.is_valid:
            for error in result.errors:
                from app.services.observability_service import observability_collector

                observability_collector.record_input_anomaly(
                    anomaly_type=error["anomaly_type"],
                    details={
                        "field": error["field"],
                        "message": error["message"],
                        **error.get("details", {}),
                    },
                )

        return result

    def validate_text(self, text: str | None) -> ValidationResult:
        """Validate text input."""
        result = ValidationResult()

        if text is None:
            result.add_error("text", "missing_required", "Text input is required")
            return result

        if not isinstance(text, str):
            result.add_error(
                "text", "type_error", f"Expected string, got {type(text).__name__}"
            )
            return result

        stripped = text.strip()

        if len(stripped) == 0:
            result.add_error("text", "empty_text", "Text is empty after trimming")
        elif len(stripped) < self.MIN_TEXT_LENGTH:
            result.add_error(
                "text",
                "too_short",
                f"Text too short: {len(stripped)} chars (min {self.MIN_TEXT_LENGTH})",
                {"length": len(stripped), "min_length": self.MIN_TEXT_LENGTH},
            )
        elif len(stripped) > self.MAX_TEXT_LENGTH:
            result.add_error(
                "text",
                "too_long",
                f"Text too long: {len(stripped)} chars (max {self.MAX_TEXT_LENGTH})",
                {"length": len(stripped), "max_length": self.MAX_TEXT_LENGTH},
            )

        # Check for extreme character distribution (e.g., all same character)
        if len(stripped) > 0:
            unique_chars = len(set(stripped.lower()))
            if unique_chars == 1:
                result.add_error(
                    "text",
                    "extreme_distribution",
                    "Text consists of a single repeated character",
                    {"unique_chars": unique_chars},
                )
            elif unique_chars < 3 and len(stripped) > 10:
                result.add_error(
                    "text",
                    "extreme_distribution",
                    "Text has extremely low character diversity",
                    {"unique_chars": unique_chars, "length": len(stripped)},
                )

        if result.is_valid:
            result.sanitized_input = {"text": stripped}

        # Record anomalies if any
        if not result.is_valid:
            from app.services.observability_service import observability_collector

            for error in result.errors:
                observability_collector.record_input_anomaly(
                    anomaly_type=error["anomaly_type"],
                    details={
                        "field": error["field"],
                        "message": error["message"],
                        **error.get("details", {}),
                    },
                )

        return result

    def validate_physiological(self, data: dict[str, Any]) -> ValidationResult:
        """Validate physiological data input."""
        required = [
            "sleep_hours",
            "sleep_quality",
            "exercise_minutes",
            "heart_rate",
            "systolic_bp",
            "diastolic_bp",
            "steps",
        ]
        return self.validate_tabular(data, required_fields=required)

    def validate_fusion(
        self,
        features: dict[str, Any] | None = None,
        text: str | None = None,
        physiological: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """Validate fusion model inputs."""
        result = ValidationResult()
        result.sanitized_input = {}

        if features:
            tabular_result = self.validate_tabular(features)
            if not tabular_result.is_valid:
                result.errors.extend(tabular_result.errors)
                result.is_valid = False
            else:
                result.sanitized_input["features"] = tabular_result.sanitized_input

        if text is not None:
            text_result = self.validate_text(text)
            if not text_result.is_valid:
                result.errors.extend(text_result.errors)
                result.is_valid = False
            else:
                result.sanitized_input["text"] = (
                    text_result.sanitized_input.get("text")
                    if text_result.sanitized_input
                    else None
                )

        if physiological:
            physio_result = self.validate_physiological(physiological)
            if not physio_result.is_valid:
                result.errors.extend(physio_result.errors)
                result.is_valid = False
            else:
                result.sanitized_input["physiological"] = physio_result.sanitized_input

        # Record anomalies if any
        if not result.is_valid:
            from app.services.observability_service import observability_collector

            for error in result.errors:
                observability_collector.record_input_anomaly(
                    anomaly_type=error["anomaly_type"],
                    details={
                        "field": error["field"],
                        "message": error["message"],
                        **error.get("details", {}),
                    },
                )

        return result


# Global validator instance
input_validator = InputValidator()
