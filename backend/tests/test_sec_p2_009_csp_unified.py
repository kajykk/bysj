"""SEC-P2-009: CSP 统一由 nginx 设置, 后端不设置 测试.

验证:
1. backend middlewares.py 不再设置 Content-Security-Policy header
2. backend middlewares.py 不再生成 csp_nonce (因为 nginx CSP 不使用 nonce)
3. nginx.conf 已配置 Content-Security-Policy
4. middlewares.py 中有 SEC-P2-009 注释说明
5. secrets 导入已移除 (csp_nonce 不再需要)
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.middlewares import security_headers_middleware


def _make_test_app() -> FastAPI:
    """创建测试 app, 安装 security_headers_middleware."""
    app = FastAPI()

    @app.middleware("http")
    async def _mw(request: Request, call_next):
        return await security_headers_middleware(request, call_next)

    @app.get("/")
    def _root():
        return {"ok": True}

    return app


class TestBackendNoCSPHeader:
    """后端响应中不应包含 CSP header."""

    def test_no_content_security_policy_header(self):
        """响应中不应有 Content-Security-Policy header."""
        client = TestClient(_make_test_app())
        resp = client.get("/")
        assert "Content-Security-Policy" not in resp.headers

    def test_no_content_security_policy_report_only_header(self):
        """响应中不应有 Content-Security-Policy-Report-Only header."""
        client = TestClient(_make_test_app())
        resp = client.get("/")
        assert "Content-Security-Policy-Report-Only" not in resp.headers

    def test_other_security_headers_present(self):
        """其他安全头仍然存在 (CSP 移除不影响其他头)."""
        client = TestClient(_make_test_app())
        resp = client.get("/")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-XSS-Protection"] == "0"
        assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "Permissions-Policy" in resp.headers
        assert resp.headers["X-DNS-Prefetch-Control"] == "off"


class TestBackendNoCSPNonce:
    """后端不应再生成 csp_nonce."""

    def test_no_csp_nonce_in_request_state(self):
        """request.state 不应设置 csp_nonce."""
        captured_state = {}

        app = FastAPI()

        @app.middleware("http")
        async def _mw(request: Request, call_next):
            response = await security_headers_middleware(request, call_next)
            captured_state["has_csp_nonce"] = hasattr(request.state, "csp_nonce")
            return response

        @app.get("/")
        def _root():
            return {"ok": True}

        client = TestClient(app)
        client.get("/")
        assert captured_state.get("has_csp_nonce") is False

    def test_no_secrets_import_in_middlewares(self):
        """middlewares.py 不应再导入 secrets (csp_nonce 不再需要)."""
        middlewares_path = (
            Path(__file__).resolve().parent.parent
            / "app"
            / "core"
            / "middlewares.py"
        )
        content = middlewares_path.read_text(encoding="utf-8")
        # secrets 模块不应被导入 (csp_nonce 移除后不再需要)
        lines = content.split("\n")
        for line in lines:
            stripped = line.strip()
            # 允许出现在注释中, 但不允许出现在 import 语句中
            if stripped.startswith("import secrets") or stripped.startswith(
                "from secrets"
            ):
                raise AssertionError(
                    f"SEC-P2-009: middlewares.py 仍导入 secrets: {line.strip()}"
                )


class TestNginxCSPConfig:
    """nginx.conf 中应配置 CSP."""

    def _get_nginx_conf_path(self) -> Path:
        return (
            Path(__file__).resolve().parent.parent.parent
            / "frontend"
            / "nginx.conf"
        )

    def test_nginx_conf_exists(self):
        """nginx.conf 文件存在."""
        assert self._get_nginx_conf_path().exists()

    def test_nginx_sets_content_security_policy(self):
        """nginx.conf 设置了 Content-Security-Policy header."""
        content = self._get_nginx_conf_path().read_text(encoding="utf-8")
        assert "Content-Security-Policy" in content

    def test_nginx_csp_uses_unsafe_inline_for_style(self):
        """nginx CSP style-src 允许 unsafe-inline (Element Plus 需要)."""
        content = self._get_nginx_conf_path().read_text(encoding="utf-8")
        # 找到 CSP 行
        csp_lines = [
            line for line in content.split("\n") if "Content-Security-Policy" in line
        ]
        assert csp_lines, "nginx.conf 未找到 Content-Security-Policy 配置"
        csp_value = " ".join(csp_lines)
        assert "style-src" in csp_value
        assert "'unsafe-inline'" in csp_value

    def test_nginx_csp_script_src_no_unsafe_inline(self):
        """nginx CSP script-src 不应允许 unsafe-inline (XSS 防护)."""
        content = self._get_nginx_conf_path().read_text(encoding="utf-8")
        csp_lines = [
            line for line in content.split("\n") if "Content-Security-Policy" in line
        ]
        csp_value = " ".join(csp_lines)
        # 提取 script-src 部分
        if "script-src" in csp_value:
            # 验证 script-src 不包含 'unsafe-inline'
            # 简单方法: 检查 'unsafe-inline' 只出现在 style-src 部分
            # 更严格: script-src 段不应有 unsafe-inline
            parts = csp_value.split("script-src")
            if len(parts) > 1:
                script_src_part = parts[1].split(";")[0]
                assert "'unsafe-inline'" not in script_src_part, (
                    f"SEC-P2-009: nginx CSP script-src 不应包含 'unsafe-inline': "
                    f"{script_src_part.strip()}"
                )

    def test_nginx_uses_always_directive(self):
        """nginx add_header 使用 always 关键字 (确保所有响应都设置)."""
        content = self._get_nginx_conf_path().read_text(encoding="utf-8")
        csp_lines = [
            line for line in content.split("\n") if "Content-Security-Policy" in line
        ]
        assert csp_lines, "未找到 CSP 配置"
        for line in csp_lines:
            assert "always" in line, f"CSP 配置缺少 always 关键字: {line.strip()}"


class TestMiddlewaresSourceAnnotation:
    """middlewares.py 源码应有 SEC-P2-009 注释说明."""

    def _get_middlewares_path(self) -> Path:
        return (
            Path(__file__).resolve().parent.parent
            / "app"
            / "core"
            / "middlewares.py"
        )

    def test_middlewares_file_exists(self):
        """middlewares.py 文件存在."""
        assert self._get_middlewares_path().exists()

    def test_sec_p2_009_annotation_present(self):
        """middlewares.py 中有 SEC-P2-009 注释."""
        content = self._get_middlewares_path().read_text(encoding="utf-8")
        assert "SEC-P2-009" in content

    def test_no_active_csp_assignment(self):
        """middlewares.py 中不应有 active CSP header 赋值 (允许出现在注释中)."""
        content = self._get_middlewares_path().read_text(encoding="utf-8")
        lines = content.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            # 跳过注释行
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'"):
                continue
            # 检查是否有 active CSP 赋值
            if (
                'response.headers["Content-Security-Policy"]' in line
                or "response.headers['Content-Security-Policy']" in line
                or 'response.headers["Content-Security-Policy-Report-Only"]' in line
                or "response.headers['Content-Security-Policy-Report-Only']" in line
            ):
                raise AssertionError(
                    f"SEC-P2-009: middlewares.py 行 {i + 1} 仍有 active CSP 赋值: "
                    f"{line.strip()}"
                )

    def test_no_csp_nonce_generation(self):
        """middlewares.py 中不应有 csp_nonce 生成代码."""
        content = self._get_middlewares_path().read_text(encoding="utf-8")
        lines = content.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            # 跳过注释行
            if stripped.startswith("#") or stripped.startswith('"""'):
                continue
            # 检查是否有 active csp_nonce 生成 (允许在字符串注释中提及)
            if "csp_nonce" in line and "=" in line and "request.state.csp_nonce" in line:
                raise AssertionError(
                    f"SEC-P2-009: middlewares.py 行 {i + 1} 仍有 csp_nonce 生成: "
                    f"{line.strip()}"
                )


class TestCSPEnvironmentBehavior:
    """所有环境下后端都不应设置 CSP (统一由 nginx)."""

    def test_production_no_backend_csp(self):
        """生产环境后端不设置 CSP."""
        from unittest.mock import patch

        app = FastAPI()

        @app.middleware("http")
        async def _mw(request, call_next):
            with patch("app.core.middlewares.settings") as mock_settings:
                mock_settings.app_env = "production"
                return await security_headers_middleware(request, call_next)

        @app.get("/")
        def _root():
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/")
        assert "Content-Security-Policy" not in resp.headers
        assert "Content-Security-Policy-Report-Only" not in resp.headers

    def test_development_no_backend_csp(self):
        """开发环境后端不设置 CSP."""
        from unittest.mock import patch

        app = FastAPI()

        @app.middleware("http")
        async def _mw(request, call_next):
            with patch("app.core.middlewares.settings") as mock_settings:
                mock_settings.app_env = "development"
                return await security_headers_middleware(request, call_next)

        @app.get("/")
        def _root():
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/")
        assert "Content-Security-Policy" not in resp.headers
        assert "Content-Security-Policy-Report-Only" not in resp.headers

    def test_staging_no_backend_csp(self):
        """staging 环境后端不设置 CSP."""
        from unittest.mock import patch

        app = FastAPI()

        @app.middleware("http")
        async def _mw(request, call_next):
            with patch("app.core.middlewares.settings") as mock_settings:
                mock_settings.app_env = "staging"
                return await security_headers_middleware(request, call_next)

        @app.get("/")
        def _root():
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/")
        assert "Content-Security-Policy" not in resp.headers
        assert "Content-Security-Policy-Report-Only" not in resp.headers
