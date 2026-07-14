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


class TestGetRealClientIp:
    """ISS-02: get_real_client_ip 安全关键（防 XFF 伪造绕过限流）。"""

    def _req(self, client_host, headers=None):
        from starlette.requests import Request

        scope = {
            "type": "http",
            "client": ("1.2.3.4", 1234),  # 占位，get_remote_address 被 mock
            "headers": [
                (k.lower().encode(), v.encode())
                for k, v in (headers or {}).items()
            ],
        }
        return Request(scope)

    def test_direct_connection_uses_client_host(self, monkeypatch):
        from unittest.mock import MagicMock

        from app.core import rate_limit

        monkeypatch.setattr(rate_limit.settings, "trusted_proxies", "")
        monkeypatch.setattr(
            rate_limit, "get_remote_address", lambda r: "203.0.113.9"
        )
        req = self._req("203.0.113.9")
        assert rate_limit.get_real_client_ip(req) == "203.0.113.9"

    def test_trusted_proxy_parses_xff_rightmost_untrusted(self, monkeypatch):
        from unittest.mock import MagicMock

        from app.core import rate_limit

        # XFF 中 10.0.0.1/10.0.0.2 均为受信代理，203.0.113.9 为真实客户端
        monkeypatch.setattr(
            rate_limit.settings, "trusted_proxies", "10.0.0.1,10.0.0.2"
        )
        monkeypatch.setattr(
            rate_limit, "get_remote_address", lambda r: "10.0.0.1"
        )
        req = self._req(
            "10.0.0.1",
            {"x-forwarded-for": "203.0.113.9, 10.0.0.1, 10.0.0.2"},
        )
        # 从右往左跳过 10.0.0.x，取第一个非受信 IP（真实客户端）
        assert rate_limit.get_real_client_ip(req) == "203.0.113.9"

    def test_attacker_spoof_all_trusted_falls_back_leftmost(self, monkeypatch):
        from unittest.mock import MagicMock

        from app.core import rate_limit

        monkeypatch.setattr(
            rate_limit.settings, "trusted_proxies", "10.0.0.1,10.0.0.2"
        )
        monkeypatch.setattr(
            rate_limit, "get_remote_address", lambda r: "10.0.0.1"
        )
        req = self._req(
            "10.0.0.1", {"x-forwarded-for": "10.0.0.5, 10.0.0.1"}
        )
        # 全部是受信代理 IP → 回退最左侧（防伪造）
        assert rate_limit.get_real_client_ip(req) == "10.0.0.5"

    def test_untrusted_direct_connection_ignores_xff(self, monkeypatch):
        from unittest.mock import MagicMock

        from app.core import rate_limit

        monkeypatch.setattr(rate_limit.settings, "trusted_proxies", "")
        monkeypatch.setattr(
            rate_limit, "get_remote_address", lambda r: "198.51.100.7"
        )
        req = self._req("198.51.100.7", {"x-forwarded-for": "1.2.3.4"})
        assert rate_limit.get_real_client_ip(req) == "198.51.100.7"
