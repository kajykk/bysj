"""Extended tests for app/core/middlewares module."""

from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.middlewares import request_id_middleware, security_headers_middleware
from app.core.request_id import REQUEST_ID_HEADER


class TestRequestIdMiddleware:
    """Test request_id_middleware."""

    def test_request_id_header_set(self):
        """TC-COV-062: request_id_middleware sets X-Request-ID header."""
        app = FastAPI()

        @app.middleware("http")
        async def _middleware(request: Request, call_next):
            return await request_id_middleware(request, call_next)

        @app.get("/test")
        def _test():
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/test")
        assert resp.status_code == 200
        assert REQUEST_ID_HEADER in resp.headers
        assert len(resp.headers[REQUEST_ID_HEADER]) > 0

    def test_request_id_preserved(self):
        """TC-COV-063: request_id_middleware preserves existing request ID."""
        app = FastAPI()

        @app.middleware("http")
        async def _middleware(request: Request, call_next):
            return await request_id_middleware(request, call_next)

        @app.get("/test")
        def _test():
            return {"ok": True}

        client = TestClient(app)
        existing_id = "test-request-id-123"
        resp = client.get("/test", headers={REQUEST_ID_HEADER: existing_id})
        assert resp.headers[REQUEST_ID_HEADER] == existing_id


class TestSecurityHeadersMiddleware:
    """Test security_headers_middleware."""

    def test_security_headers_present(self):
        """TC-COV-064: security_headers_middleware adds all security headers."""
        app = FastAPI()

        @app.middleware("http")
        async def _middleware(request: Request, call_next):
            return await security_headers_middleware(request, call_next)

        @app.get("/test")
        def _test():
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/test")
        assert resp.status_code == 200

        # Check all security headers
        # SEC-P2-010: X-Frame-Options 由 nginx 统一设置, 后端不再设置 (避免双重 header)
        assert "X-Frame-Options" not in resp.headers
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-XSS-Protection"] == "0"
        assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "Permissions-Policy" in resp.headers
        assert resp.headers["X-DNS-Prefetch-Control"] == "off"
        # SEC-P2-009: CSP 由 nginx 统一设置, 后端不再设置 (避免双重 header 冲突)
        assert "Content-Security-Policy" not in resp.headers
        assert "Content-Security-Policy-Report-Only" not in resp.headers

    def test_csp_not_set_by_backend(self):
        """TC-COV-065: CSP 不由后端设置 (SEC-P2-009, 由 nginx 统一设置)."""
        app = FastAPI()

        @app.middleware("http")
        async def _middleware(request: Request, call_next):
            return await security_headers_middleware(request, call_next)

        @app.get("/test")
        def _test():
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/test")
        # SEC-P2-009: 后端不再生成 CSP, nginx 在 frontend/nginx.conf:81 统一设置
        assert "Content-Security-Policy" not in resp.headers
        assert "Content-Security-Policy-Report-Only" not in resp.headers

    def test_hsts_in_production(self):
        """TC-COV-066: HSTS header in production mode."""
        app = FastAPI()

        @app.middleware("http")
        async def _middleware(request: Request, call_next):
            return await security_headers_middleware(request, call_next)

        @app.get("/test")
        def _test():
            return {"ok": True}

        with patch("app.core.middlewares.settings") as mock_settings:
            mock_settings.app_env = "production"
            client = TestClient(app)
            resp = client.get("/test")
            assert "Strict-Transport-Security" in resp.headers
            assert "max-age=31536000" in resp.headers["Strict-Transport-Security"]

    def test_no_hsts_in_development(self):
        """TC-COV-067: No HSTS header in development mode."""
        app = FastAPI()

        @app.middleware("http")
        async def _middleware(request: Request, call_next):
            return await security_headers_middleware(request, call_next)

        @app.get("/test")
        def _test():
            return {"ok": True}

        with patch("app.core.middlewares.settings") as mock_settings:
            mock_settings.app_env = "development"
            client = TestClient(app)
            resp = client.get("/test")
            assert "Strict-Transport-Security" not in resp.headers
