"""Extended tests for app/core/states module."""

from __future__ import annotations

from app.core.states import BindingStatus


class TestBindingStatus:
    """Test BindingStatus enum."""

    def test_binding_status_values(self):
        """TC-COV-050: BindingStatus has correct values."""
        assert BindingStatus.PLACEHOLDER == "placeholder"
        assert BindingStatus.ACTIVE == "active"
        assert BindingStatus.INACTIVE == "inactive"

    def test_normalize_valid(self):
        """TC-COV-051: normalize returns correct status for valid input."""
        assert BindingStatus.normalize("active") == BindingStatus.ACTIVE
        assert BindingStatus.normalize("inactive") == BindingStatus.INACTIVE
        assert BindingStatus.normalize("placeholder") == BindingStatus.PLACEHOLDER

    def test_normalize_invalid(self):
        """TC-COV-052: normalize returns INACTIVE for invalid input."""
        assert BindingStatus.normalize("invalid") == BindingStatus.INACTIVE
        assert BindingStatus.normalize(None) == BindingStatus.INACTIVE

    def test_is_code_usable_placeholder(self):
        """TC-COV-053: is_code_usable returns True for placeholder."""
        assert BindingStatus.is_code_usable("placeholder") is True

    def test_is_code_usable_active(self):
        """TC-COV-054: is_code_usable returns True for active."""
        assert BindingStatus.is_code_usable("active") is True

    def test_is_code_usable_inactive(self):
        """TC-COV-055: is_code_usable returns False for inactive."""
        assert BindingStatus.is_code_usable("inactive") is False

    def test_is_code_usable_invalid(self):
        """TC-COV-056: is_code_usable returns False for invalid."""
        assert BindingStatus.is_code_usable("invalid") is False
        assert BindingStatus.is_code_usable(None) is False
