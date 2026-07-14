"""Tests for middlewares."""

from __future__ import annotations

from fastapi import FastAPI, Request
from starlette.testclient import TestClient

from app.core.middlewares import request_id_middleware, security_headers_middleware

app = FastAPI()


@app.get("/test")
def test_endpoint():
    return {"ok": True}


# Install middlewares manually for testing
@app.middleware("http")
async def _req_id_middleware(request: Request, call_next):
    return await request_id_middleware(request, call_next)


@app.middleware("http")
async def _sec_headers_middleware(request: Request, call_next):
    return await security_headers_middleware(request, call_next)


client = TestClient(app)


class TestMiddlewares:
    """Test middleware functions."""

    def test_request_id_header_set(self):
        """TC-COV-MID-001: Request ID header is set."""
        response = client.get("/test")
        assert response.status_code == 200
        assert "x-request-id" in response.headers
        assert len(response.headers["x-request-id"]) == 36

    def test_request_id_header_preserved(self):
        """TC-COV-MID-002: Existing request ID is preserved."""
        existing_id = "test-request-id-123"
        response = client.get("/test", headers={"x-request-id": existing_id})
        assert response.headers["x-request-id"] == existing_id

    def test_security_headers(self):
        """TC-COV-MID-003: Security headers are set."""
        response = client.get("/test")
        # SEC-P2-010: X-Frame-Options 由 nginx 统一设置, 后端不再设置 (避免双重 header)
        assert "X-Frame-Options" not in response.headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        # SEC-P2-009: CSP 由 nginx 统一设置, 后端不再设置 (避免双重 header 冲突)
        assert "Content-Security-Policy" not in response.headers
        assert "Content-Security-Policy-Report-Only" not in response.headers

    def test_csp_not_set_by_backend(self):
        """TC-COV-MID-004: CSP 不由后端设置 (SEC-P2-009, 由 nginx 统一设置)."""
        response = client.get("/test")
        # SEC-P2-009: 后端不再生成 CSP, nginx 在 frontend/nginx.conf:81 统一设置
        assert "Content-Security-Policy" not in response.headers
        assert "Content-Security-Policy-Report-Only" not in response.headers
