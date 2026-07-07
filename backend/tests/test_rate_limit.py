"""Tests for rate limit module."""

from __future__ import annotations

from fastapi import FastAPI, Request
from slowapi.errors import RateLimitExceeded

from app.core.rate_limit import install_rate_limiter, rate_limit_exceeded_handler


class TestRateLimit:
    """Test rate limit functions."""

    def test_rate_limit_exceeded_handler(self):
        """TC-COV-RL-001: Rate limit exceeded handler."""
        from unittest.mock import Mock

        request = Mock(spec=Request)
        # RateLimitExceeded requires a limit object with error_message
        mock_limit = Mock()
        mock_limit.error_message = "Rate limit exceeded"
        exc = RateLimitExceeded(mock_limit)
        response = rate_limit_exceeded_handler(request, exc)
        assert response.status_code == 429
        import json

        data = json.loads(response.body)
        assert data["code"] == 429
        assert "请求过于频繁" in data["message"]

    def test_install_rate_limiter(self):
        """TC-COV-RL-002: Install rate limiter on app."""
        app = FastAPI()
        install_rate_limiter(app)
        assert hasattr(app.state, "limiter")
