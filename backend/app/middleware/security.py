"""Security middleware for enhanced HTTP security headers."""

# DEPRECATED: 此中间件未被使用，功能已迁移到 app.core.middlewares
# 保留用于参考，不应在新代码中导入

from __future__ import annotations

import secrets
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware for adding security headers to all responses."""

    def __init__(
        self,
        app,
        csp_report_only: bool = True,
        hsts_max_age: int = 31536000,
        hsts_include_subdomains: bool = True,
    ):
        super().__init__(app)
        self.csp_report_only = csp_report_only
        self.hsts_max_age = hsts_max_age
        self.hsts_include_subdomains = hsts_include_subdomains

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Generate random nonce for CSP
        nonce = secrets.token_urlsafe(16)

        # Strict-Transport-Security (HSTS)
        hsts_value = f"max-age={self.hsts_max_age}"
        if self.hsts_include_subdomains:
            hsts_value += "; includeSubDomains"
        response.headers["Strict-Transport-Security"] = hsts_value

        # Content-Security-Policy
        csp_header = (
            "Content-Security-Policy-Report-Only"
            if self.csp_report_only
            else "Content-Security-Policy"
        )
        response.headers[csp_header] = self._build_csp(nonce)

        # Inject nonce into HTML responses
        self._inject_nonce_to_html(response, nonce)

        # X-Content-Type-Options
        response.headers["X-Content-Type-Options"] = "nosniff"

        # X-Frame-Options
        response.headers["X-Frame-Options"] = "DENY"

        # Referrer-Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions-Policy
        response.headers["Permissions-Policy"] = (
            "geolocation=(), " "microphone=(), " "camera=(), " "payment=(), " "usb=()"
        )

        # X-DNS-Prefetch-Control
        response.headers["X-DNS-Prefetch-Control"] = "off"

        return response

    def _build_csp(self, nonce: str) -> str:
        """Build Content Security Policy string."""
        directives = [
            "default-src 'self'",
            f"script-src 'self' 'nonce-{nonce}'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob:",
            "connect-src 'self' https://sentry.io",
            "font-src 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "upgrade-insecure-requests",
            "report-uri /api/csp-report",
        ]
        return "; ".join(directives)

    def _inject_nonce_to_html(self, response: Response, nonce: str) -> None:
        """Inject CSP nonce meta tag into HTML responses."""
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("text/html"):
            return

        try:
            body = getattr(response, "body", None)
            if body and b"<head>" in body:
                nonce_meta = f'<meta name="csp-nonce" content="{nonce}">'.encode()
                response.body = body.replace(b"<head>", b"<head>" + nonce_meta)
        except (AttributeError, TypeError):
            pass
