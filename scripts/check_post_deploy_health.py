#!/usr/bin/env python
"""STAB-P2-003: 部署后健康检查门禁脚本.

在部署完成后执行健康检查, 验证服务是否正常启动.
若健康检查失败, 退出非零码触发 CI/CD 回滚.

用法:
    python scripts/check_post_deploy_health.py

环境变量:
    HEALTH_CHECK_URL: 健康检查基础 URL (默认 http://localhost:8000)
    HEALTH_CHECK_TIMEOUT: 单次请求超时秒数 (默认 5)
    HEALTH_CHECK_RETRIES: 重试次数 (默认 6)
    HEALTH_CHECK_INTERVAL: 重试间隔秒数 (默认 5)
    HEALTH_CHECK_PATHS: 检查路径列表, 逗号分隔 (默认 /health,/health/ready)
    HEALTH_CHECK_SKIP: 跳过检查 (设为 true/1/yes 时直接通过, 用于紧急部署)

退出码:
    0: 所有健康检查通过
    1: 健康检查失败 (触发回滚)
    2: 配置错误
"""

from __future__ import annotations

import os
import sys
import time
import urllib.error
import urllib.request
from typing import NamedTuple


class HealthCheckResult(NamedTuple):
    path: str
    status_code: int | None
    success: bool
    error: str | None


def _get_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _get_env_int(name: str, default: int) -> int:
    try:
        return int(_get_env(name, str(default)))
    except ValueError:
        print(f"WARNING: invalid {name}, using default {default}", file=sys.stderr)
        return default


def _parse_paths(raw: str) -> list[str]:
    """解析逗号分隔的路径列表."""
    paths = [p.strip() for p in raw.split(",") if p.strip()]
    if not paths:
        return ["/health", "/health/ready"]
    return paths


def check_endpoint(
    base_url: str, path: str, timeout: int
) -> HealthCheckResult:
    """检查单个健康端点.

    Args:
        base_url: 基础 URL (如 http://localhost:8000)
        path: 路径 (如 /health)
        timeout: 请求超时秒数

    Returns:
        HealthCheckResult: 检查结果
    """
    url = base_url.rstrip("/") + path
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status_code = resp.status
            if 200 <= status_code < 300:
                return HealthCheckResult(
                    path=path, status_code=status_code, success=True, error=None
                )
            return HealthCheckResult(
                path=path,
                status_code=status_code,
                success=False,
                error=f"HTTP {status_code}",
            )
    except urllib.error.HTTPError as exc:
        return HealthCheckResult(
            path=path,
            status_code=exc.code,
            success=False,
            error=f"HTTP {exc.code}: {exc.reason}",
        )
    except urllib.error.URLError as exc:
        return HealthCheckResult(
            path=path,
            status_code=None,
            success=False,
            error=f"URL Error: {exc.reason}",
        )
    except Exception as exc:
        return HealthCheckResult(
            path=path,
            status_code=None,
            success=False,
            error=f"{type(exc).__name__}: {exc}",
        )


def run_health_checks() -> int:
    """执行健康检查, 返回退出码.

    Returns:
        0: 全部通过
        1: 检查失败
        2: 配置错误
    """
    # 紧急跳过
    skip = _get_env("HEALTH_CHECK_SKIP", "").lower()
    if skip in ("true", "1", "yes"):
        print("INFO: HEALTH_CHECK_SKIP=true, skipping health checks")
        return 0

    base_url = _get_env("HEALTH_CHECK_URL", "http://localhost:8000")
    if not base_url.startswith("http"):
        print(f"ERROR: HEALTH_CHECK_URL must start with http:// or https://, got: {base_url}", file=sys.stderr)
        return 2

    timeout = _get_env_int("HEALTH_CHECK_TIMEOUT", 5)
    retries = _get_env_int("HEALTH_CHECK_RETRIES", 6)
    interval = _get_env_int("HEALTH_CHECK_INTERVAL", 5)
    paths = _parse_paths(_get_env("HEALTH_CHECK_PATHS", "/health,/health/ready"))

    print(f"INFO: health check config: base_url={base_url}, paths={paths}, "
          f"timeout={timeout}s, retries={retries}, interval={interval}s")

    all_passed = False
    for attempt in range(1, retries + 1):
        print(f"\n--- Attempt {attempt}/{retries} ---")
        results: list[HealthCheckResult] = []
        all_passed = True

        for path in paths:
            result = check_endpoint(base_url, path, timeout)
            results.append(result)
            status_text = "PASS" if result.success else "FAIL"
            code_text = f" [{result.status_code}]" if result.status_code else ""
            print(f"  {status_text} {path}{code_text} {result.error or ''}")
            if not result.success:
                all_passed = False

        if all_passed:
            print(f"\n✓ All health checks passed on attempt {attempt}/{retries}")
            return 0

        if attempt < retries:
            print(f"  Waiting {interval}s before retry...")
            time.sleep(interval)

    print(f"\n✗ Health checks failed after {retries} attempts", file=sys.stderr)
    return 1


def main() -> int:
    return run_health_checks()


if __name__ == "__main__":
    sys.exit(main())
