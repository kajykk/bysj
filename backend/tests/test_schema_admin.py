"""Tests for admin schema validators."""

from __future__ import annotations

import pytest

from app.schemas.admin import (
    ConfigUpsertRequest,
    ModelRegistryRequest,
    ModelUpdateRequest,
    TemplateTaskItem,
    TemplateUpsertRequest,
    ThresholdUpsertRequest,
)


class TestTemplateTaskItem:
    """Test TemplateTaskItem schema."""

    def test_valid(self):
        """TC-COV-SCHEMA-ADMIN-001: Valid task item."""
        item = TemplateTaskItem(task_name="t1", task_type="checkin")
        assert item.task_name == "t1"
        assert item.task_type == "checkin"

    def test_invalid_task_type(self):
        """TC-COV-SCHEMA-ADMIN-002: Invalid task type."""
        with pytest.raises(ValueError, match="task_type must be one of"):
            TemplateTaskItem(task_name="t1", task_type="invalid_type")


class TestTemplateUpsertRequest:
    """Test TemplateUpsertRequest schema."""

    def test_duplicate_levels(self):
        """TC-COV-SCHEMA-ADMIN-003: Duplicate levels raise error."""
        task = TemplateTaskItem(task_name="t1", task_type="checkin")
        with pytest.raises(ValueError, match="duplicate"):
            TemplateUpsertRequest(
                template_name="test",
                applicable_levels=[1, 1],
                task_list=[task],
            )


class TestThresholdUpsertRequest:
    """Test ThresholdUpsertRequest schema."""

    def test_min_gt_max(self):
        """TC-COV-SCHEMA-ADMIN-004: min > max raises error."""
        with pytest.raises(ValueError, match="less than"):
            ThresholdUpsertRequest(
                level=1,
                level_name="low",
                min_score=50,
                max_score=30,
                color="red",
                action_required="act",
            )

    def test_min_equals_max(self):
        """TC-COV-SCHEMA-ADMIN-005: min == max raises error."""
        with pytest.raises(ValueError, match="not be equal"):
            ThresholdUpsertRequest(
                level=1,
                level_name="low",
                min_score=50,
                max_score=50,
                color="red",
                action_required="act",
            )


class TestConfigUpsertRequest:
    """Test ConfigUpsertRequest schema."""

    def test_valid(self):
        """TC-COV-SCHEMA-ADMIN-006: Valid config."""
        req = ConfigUpsertRequest(
            config_key="key1",
            config_value={"a": 1, "b": "hello"},
        )
        assert req.config_value == {"a": 1, "b": "hello"}

    def test_empty_dict(self):
        """TC-COV-SCHEMA-ADMIN-007: Empty dict raises error."""
        with pytest.raises(ValueError, match="must not be empty"):
            ConfigUpsertRequest(config_key="k", config_value={})

    def test_nested_too_deep(self):
        """TC-COV-SCHEMA-ADMIN-008: Nested too deep raises error."""
        deep = {"a": {"b": {"c": {"d": {"e": 1}}}}}
        with pytest.raises(ValueError, match="too deep"):
            ConfigUpsertRequest(config_key="k", config_value=deep)

    def test_non_string_key(self):
        """TC-COV-SCHEMA-ADMIN-009: Non-string key raises error."""
        with pytest.raises(ValueError, match="keys must be"):
            ConfigUpsertRequest(config_key="k", config_value={1: "val"})

    def test_empty_string_key(self):
        """TC-COV-SCHEMA-ADMIN-010: Empty string key raises error."""
        with pytest.raises(ValueError, match="keys must be"):
            ConfigUpsertRequest(config_key="k", config_value={"": "val"})

    def test_list_too_long(self):
        """TC-COV-SCHEMA-ADMIN-011: List too long raises error."""
        long_list = list(range(101))
        with pytest.raises(ValueError, match="too long"):
            ConfigUpsertRequest(config_key="k", config_value={"items": long_list})

    def test_null_value_ok(self):
        """TC-COV-SCHEMA-ADMIN-012: None value is accepted."""
        req = ConfigUpsertRequest(config_key="k", config_value={"key": None})
        assert req.config_value == {"key": None}

    def test_unsupported_type(self):
        """TC-COV-SCHEMA-ADMIN-013: Unsupported type raises error."""
        from datetime import datetime

        with pytest.raises(ValueError, match="unsupported type"):
            ConfigUpsertRequest(config_key="k", config_value={"t": datetime.now()})

    def test_string_too_long(self):
        """TC-COV-SCHEMA-ADMIN-014: String too long raises error."""
        long_str = "x" * 5001
        with pytest.raises(ValueError, match="too long"):
            ConfigUpsertRequest(config_key="k", config_value={"s": long_str})


class TestModelRegistryRequest:
    """Test ModelRegistryRequest schema."""

    def test_valid(self):
        """TC-COV-SCHEMA-ADMIN-015: Valid model registry."""
        req = ModelRegistryRequest(model_id="m1", model_name="test", model_type="dl")
        assert req.model_id == "m1"

    def test_invalid_status(self):
        """TC-COV-SCHEMA-ADMIN-016: Invalid status."""
        with pytest.raises(ValueError):
            ModelRegistryRequest(model_id="m1", model_name="test", status="invalid")

    def test_accuracy_range(self):
        """TC-COV-SCHEMA-ADMIN-017: Accuracy > 1 raises error."""
        with pytest.raises(ValueError):
            ModelRegistryRequest(model_id="m1", model_name="test", accuracy=1.5)


class TestModelUpdateRequest:
    """Test ModelUpdateRequest schema."""

    def test_valid(self):
        """TC-COV-SCHEMA-ADMIN-018: Valid update."""
        req = ModelUpdateRequest(status="active")
        assert req.status == "active"

    def test_invalid_status(self):
        """TC-COV-SCHEMA-ADMIN-019: Invalid status."""
        with pytest.raises(ValueError):
            ModelUpdateRequest(status="invalid")
