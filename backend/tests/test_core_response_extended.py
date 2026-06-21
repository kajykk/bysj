"""Extended tests for app/core/response module."""

from __future__ import annotations

import pytest

from app.core.response import ok


class TestOkResponse:
    """Test ok response helper."""

    def test_ok_default(self):
        """TC-COV-057: ok() returns default success response."""
        result = ok()
        assert result == {"code": 200, "message": "success", "data": None}

    def test_ok_with_data(self):
        """TC-COV-058: ok() includes data when provided."""
        result = ok(data={"id": 1})
        assert result["data"] == {"id": 1}
        assert result["code"] == 200

    def test_ok_with_message(self):
        """TC-COV-059: ok() includes custom message."""
        result = ok(message="Created")
        assert result["message"] == "Created"

    def test_ok_with_code(self):
        """TC-COV-060: ok() includes custom code."""
        result = ok(code=201)
        assert result["code"] == 201

    def test_ok_full_custom(self):
        """TC-COV-061: ok() supports full customization."""
        result = ok(data={"id": 1}, message="Created", code=201)
        assert result == {"code": 201, "message": "Created", "data": {"id": 1}}
