"""Tests for SEC-P2-010: X-Frame-Options 前后端冲突解决.

验证 X-Frame-Options 仅由 nginx 层设置 (SAMEORIGIN),
后端不再设置 X-Frame-Options, 避免 proxy_pass 响应出现双重 header.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from starlette.testclient import TestClient

from app.core.middlewares import security_headers_middleware

# Project root (backend/tests/ -> backend/ -> project root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_NGINX_CONF = _PROJECT_ROOT / "frontend" / "nginx.conf"
_MIDDLEWARES_PY = _PROJECT_ROOT / "backend" / "app" / "core" / "middlewares.py"


class TestBackendNoFrameOptions:
    """验证后端不再设置 X-Frame-Options header."""

    def test_backend_does_not_set_x_frame_options(self) -> None:
        """后端 security_headers_middleware 不应设置 X-Frame-Options."""
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
        # SEC-P2-010: X-Frame-Options 应由 nginx 统一设置, 后端不设置
        assert "X-Frame-Options" not in resp.headers, (
            "Backend should NOT set X-Frame-Options (SEC-P2-010: nginx-only)"
        )

    def test_backend_still_sets_other_security_headers(self) -> None:
        """后端仍应设置其他安全头 (X-Content-Type-Options 等)."""
        app = FastAPI()

        @app.middleware("http")
        async def _middleware(request: Request, call_next):
            return await security_headers_middleware(request, call_next)

        @app.get("/test")
        def _test():
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/test")
        # 其他安全头仍应由后端设置
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "Permissions-Policy" in resp.headers


class TestNginxFrameOptionsConfig:
    """验证 nginx 配置正确设置 X-Frame-Options."""

    def test_nginx_conf_exists(self) -> None:
        """nginx.conf 应存在."""
        assert _NGINX_CONF.exists(), f"nginx.conf should exist: {_NGINX_CONF}"

    def test_nginx_sets_x_frame_options(self) -> None:
        """nginx 应设置 X-Frame-Options header."""
        content = _NGINX_CONF.read_text(encoding="utf-8")
        assert "X-Frame-Options" in content, (
            "nginx.conf should set X-Frame-Options (SEC-P2-010: nginx-only)"
        )

    def test_nginx_sets_sameorigin(self) -> None:
        """nginx 应设置 X-Frame-Options 为 SAMEORIGIN (允许同源 iframe)."""
        content = _NGINX_CONF.read_text(encoding="utf-8")
        assert 'X-Frame-Options "SAMEORIGIN"' in content, (
            'nginx.conf should set X-Frame-Options "SAMEORIGIN" '
            "(allow same-origin iframe for PDF preview etc.)"
        )

    def test_nginx_uses_always_directive(self) -> None:
        """nginx add_header 应使用 always 确保所有响应都带 X-Frame-Options."""
        content = _NGINX_CONF.read_text(encoding="utf-8")
        assert 'X-Frame-Options "SAMEORIGIN" always' in content, (
            'nginx should use "always" to ensure X-Frame-Options on all responses (incl. 4xx/5xx)'
        )


class TestMiddlewaresSourceAnnotation:
    """验证 middlewares.py 源码有 SEC-P2-010 注释."""

    def test_middlewares_py_exists(self) -> None:
        """middlewares.py 应存在."""
        assert _MIDDLEWARES_PY.exists(), (
            f"middlewares.py should exist: {_MIDDLEWARES_PY}"
        )

    def test_middlewares_py_has_sec_p2_010_comment(self) -> None:
        """middlewares.py 应有 SEC-P2-010 注释说明 X-Frame-Options 移除原因."""
        content = _MIDDLEWARES_PY.read_text(encoding="utf-8")
        assert "SEC-P2-010" in content, (
            "middlewares.py should reference SEC-P2-010 in comment"
        )

    def test_middlewares_py_no_x_frame_options_assignment(self) -> None:
        """middlewares.py 不应有 X-Frame-Options 赋值 (注释除外)."""
        content = _MIDDLEWARES_PY.read_text(encoding="utf-8")
        lines = content.split("\n")
        # 过滤注释行和空行
        active_lines = [
            line for line in lines
            if line.strip()
            and not line.strip().startswith("#")
            and not line.strip().startswith('"')
            and not line.strip().startswith("'")
        ]
        # 检查没有 active 代码行设置 X-Frame-Options
        xfo_lines = [line for line in active_lines if "X-Frame-Options" in line]
        assert len(xfo_lines) == 0, (
            f"middlewares.py should NOT have active X-Frame-Options assignment, "
            f"found: {xfo_lines}"
        )
