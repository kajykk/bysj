"""STAB-P2-003 专项测试: 部署后健康检查门禁.

验证健康检查脚本能正确检测服务状态, 失败时触发回滚 (非零退出码).
"""

from __future__ import annotations

import importlib.util
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
_WORKFLOWS_DIR = Path(__file__).resolve().parent.parent.parent / ".github" / "workflows"

# 动态导入 scripts/check_post_deploy_health.py
_spec = importlib.util.spec_from_file_location(
    "check_post_deploy_health",
    _SCRIPTS_DIR / "check_post_deploy_health.py",
)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


# ─────────────────────────── 脚本文件结构测试 ───────────────────────────


class TestScriptStructure:
    """验证健康检查脚本文件结构."""

    def test_script_exists(self):
        """脚本文件存在."""
        assert (_SCRIPTS_DIR / "check_post_deploy_health.py").exists()

    def test_script_has_stab_p2_003_comment(self):
        """脚本包含 STAB-P2-003 注释."""
        content = (_SCRIPTS_DIR / "check_post_deploy_health.py").read_text(
            encoding="utf-8"
        )
        assert "STAB-P2-003" in content

    def test_script_has_main_function(self):
        """脚本有 main 函数和 run_health_checks 函数."""
        assert hasattr(_mod, "main")
        assert hasattr(_mod, "run_health_checks")
        assert hasattr(_mod, "check_endpoint")

    def test_script_has_env_vars(self):
        """脚本支持环境变量配置."""
        content = (_SCRIPTS_DIR / "check_post_deploy_health.py").read_text(
            encoding="utf-8"
        )
        for var in [
            "HEALTH_CHECK_URL",
            "HEALTH_CHECK_TIMEOUT",
            "HEALTH_CHECK_RETRIES",
            "HEALTH_CHECK_INTERVAL",
            "HEALTH_CHECK_PATHS",
            "HEALTH_CHECK_SKIP",
        ]:
            assert var in content, f"脚本必须支持 {var} 环境变量"

    def test_script_has_exit_codes(self):
        """脚本定义了退出码 (0=pass, 1=fail, 2=config error)."""
        content = (_SCRIPTS_DIR / "check_post_deploy_health.py").read_text(
            encoding="utf-8"
        )
        assert "return 0" in content  # 成功
        assert "return 1" in content  # 失败
        assert "return 2" in content  # 配置错误

    def test_script_has_retry_logic(self):
        """脚本包含重试逻辑."""
        content = (_SCRIPTS_DIR / "check_post_deploy_health.py").read_text(
            encoding="utf-8"
        )
        assert "retries" in content
        assert "attempt" in content

    def test_script_has_skip_option(self):
        """脚本支持紧急跳过."""
        content = (_SCRIPTS_DIR / "check_post_deploy_health.py").read_text(
            encoding="utf-8"
        )
        assert "HEALTH_CHECK_SKIP" in content
        assert "true" in content.lower()
        assert "1" in content
        assert "yes" in content


# ─────────────────────────── CI Workflow 结构测试 ───────────────────────────


class TestWorkflowStructure:
    """验证 CI workflow 文件结构."""

    def test_workflow_exists(self):
        """CI workflow 文件存在."""
        assert (_WORKFLOWS_DIR / "post-deploy-health-check.yml").exists()

    def test_workflow_has_stab_p2_003_comment(self):
        """workflow 包含 STAB-P2-003 注释."""
        content = (_WORKFLOWS_DIR / "post-deploy-health-check.yml").read_text(
            encoding="utf-8"
        )
        assert "STAB-P2-003" in content

    def test_workflow_has_workflow_dispatch(self):
        """workflow 支持 workflow_dispatch 触发."""
        content = (_WORKFLOWS_DIR / "post-deploy-health-check.yml").read_text(
            encoding="utf-8"
        )
        assert "workflow_dispatch" in content

    def test_workflow_has_health_check_url_input(self):
        """workflow 定义了 health_check_url 输入."""
        content = (_WORKFLOWS_DIR / "post-deploy-health-check.yml").read_text(
            encoding="utf-8"
        )
        assert "health_check_url" in content

    def test_workflow_runs_script(self):
        """workflow 调用 check_post_deploy_health.py 脚本."""
        content = (_WORKFLOWS_DIR / "post-deploy-health-check.yml").read_text(
            encoding="utf-8"
        )
        assert "check_post_deploy_health.py" in content

    def test_workflow_runs_tests(self):
        """workflow 运行 pytest 测试."""
        content = (_WORKFLOWS_DIR / "post-deploy-health-check.yml").read_text(
            encoding="utf-8"
        )
        assert "test_stab_p2_003" in content

    def test_workflow_has_skip_input(self):
        """workflow 定义了 skip 输入 (紧急部署)."""
        content = (_WORKFLOWS_DIR / "post-deploy-health-check.yml").read_text(
            encoding="utf-8"
        )
        assert "skip" in content.lower()

    def test_workflow_uses_python(self):
        """workflow 使用 Python 3.12."""
        content = (_WORKFLOWS_DIR / "post-deploy-health-check.yml").read_text(
            encoding="utf-8"
        )
        assert "python-version" in content
        assert "3.12" in content


# ─────────────────────────── 健康检查逻辑测试 ───────────────────────────


class TestCheckEndpoint:
    """验证 check_endpoint 函数逻辑."""

    def test_check_endpoint_success(self):
        """成功响应返回 success=True."""
        # 使用 mock HTTP server
        import urllib.request

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), _Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = _mod.check_endpoint(
                f"http://127.0.0.1:{port}", "/health", timeout=2
            )
            assert result.success is True
            assert result.status_code == 200
            assert result.error is None
        finally:
            server.shutdown()

    def test_check_endpoint_500_failure(self):
        """500 响应返回 success=False."""
        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(500)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), _Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = _mod.check_endpoint(
                f"http://127.0.0.1:{port}", "/health", timeout=2
            )
            assert result.success is False
            assert result.status_code == 500
        finally:
            server.shutdown()

    def test_check_endpoint_connection_refused(self):
        """连接被拒返回 success=False, status_code=None."""
        result = _mod.check_endpoint(
            "http://127.0.0.1:1", "/health", timeout=1
        )
        assert result.success is False
        assert result.status_code is None
        assert result.error is not None


# ─────────────────────────── 环境变量与退出码测试 ───────────────────────────


class TestRunHealthChecks:
    """验证 run_health_checks 函数的退出码逻辑."""

    def test_skip_returns_zero(self, monkeypatch):
        """HEALTH_CHECK_SKIP=true 时返回 0."""
        monkeypatch.setenv("HEALTH_CHECK_SKIP", "true")
        assert _mod.run_health_checks() == 0

    def test_skip_returns_zero_for_yes(self, monkeypatch):
        """HEALTH_CHECK_SKIP=yes 时返回 0."""
        monkeypatch.setenv("HEALTH_CHECK_SKIP", "yes")
        assert _mod.run_health_checks() == 0

    def test_skip_returns_zero_for_1(self, monkeypatch):
        """HEALTH_CHECK_SKIP=1 时返回 0."""
        monkeypatch.setenv("HEALTH_CHECK_SKIP", "1")
        assert _mod.run_health_checks() == 0

    def test_invalid_url_returns_2(self, monkeypatch):
        """无效 URL 返回 2 (配置错误)."""
        monkeypatch.delenv("HEALTH_CHECK_SKIP", raising=False)
        monkeypatch.setenv("HEALTH_CHECK_URL", "ftp://invalid")
        assert _mod.run_health_checks() == 2

    def test_missing_url_prefix_returns_2(self, monkeypatch):
        """URL 不以 http 开头返回 2."""
        monkeypatch.delenv("HEALTH_CHECK_SKIP", raising=False)
        monkeypatch.setenv("HEALTH_CHECK_URL", "localhost:8000")
        assert _mod.run_health_checks() == 2

    def test_all_pass_returns_zero(self, monkeypatch):
        """所有端点健康返回 0."""
        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), _Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            monkeypatch.delenv("HEALTH_CHECK_SKIP", raising=False)
            monkeypatch.setenv("HEALTH_CHECK_URL", f"http://127.0.0.1:{port}")
            monkeypatch.setenv("HEALTH_CHECK_RETRIES", "1")
            monkeypatch.setenv("HEALTH_CHECK_INTERVAL", "0")
            monkeypatch.setenv("HEALTH_CHECK_TIMEOUT", "2")
            monkeypatch.setenv("HEALTH_CHECK_PATHS", "/health")
            assert _mod.run_health_checks() == 0
        finally:
            server.shutdown()

    def test_all_fail_returns_one(self, monkeypatch):
        """所有端点不健康返回 1."""
        monkeypatch.delenv("HEALTH_CHECK_SKIP", raising=False)
        monkeypatch.setenv("HEALTH_CHECK_URL", "http://127.0.0.1:1")
        monkeypatch.setenv("HEALTH_CHECK_RETRIES", "2")
        monkeypatch.setenv("HEALTH_CHECK_INTERVAL", "0")
        monkeypatch.setenv("HEALTH_CHECK_TIMEOUT", "1")
        monkeypatch.setenv("HEALTH_CHECK_PATHS", "/health")
        assert _mod.run_health_checks() == 1


# ─────────────────────────── 辅助函数测试 ───────────────────────────


class TestParsePaths:
    """验证 _parse_paths 函数."""

    def test_default_paths(self):
        """空字符串返回默认路径."""
        paths = _mod._parse_paths("")
        assert paths == ["/health", "/health/ready"]

    def test_single_path(self):
        """单个路径."""
        paths = _mod._parse_paths("/health")
        assert paths == ["/health"]

    def test_multiple_paths(self):
        """多个逗号分隔路径."""
        paths = _mod._parse_paths("/health,/health/ready,/metrics")
        assert paths == ["/health", "/health/ready", "/metrics"]

    def test_paths_with_whitespace(self):
        """带空格的路径被正确 trim."""
        paths = _mod._parse_paths(" /health , /health/ready ")
        assert paths == ["/health", "/health/ready"]

    def test_empty_paths_filtered(self):
        """空路径被过滤."""
        paths = _mod._parse_paths("/health,,/health/ready,")
        assert paths == ["/health", "/health/ready"]
