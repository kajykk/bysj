"""v1.37-grafana-dashboards: Grafana Service Account 鉴权测试 (T-GRAF-009).

覆盖测试组:
- TC-AUTH-001: Grafana Service Account 鉴权 (3/3)
  - test_auth_with_sa_token
  - test_auth_with_admin_jwt
  - test_auth_with_user_jwt_403

鉴权路径:
1. Service Account Token (Bearer GRAFANA_SERVICE_TOKEN) → 200 + 虚拟 admin User
2. Admin User JWT → 200 (经 get_current_user 验证)
3. User JWT (非 admin) → 403 (权限拒绝)
"""
from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-ci-only")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.deps import require_sa_or_admin
from app.models.user import User


# ============ Fixtures ============


@pytest.fixture
def sa_token_env(monkeypatch):
    """设置 GRAFANA_SERVICE_TOKEN 环境变量."""
    monkeypatch.setenv("GRAFANA_SERVICE_TOKEN", "test-sa-secret-xyz789")
    # Reload settings to pick up env var
    import importlib
    import app.core.config as cfg_mod
    importlib.reload(cfg_mod)
    return "test-sa-secret-xyz789"


@pytest.fixture
def client(as_role):
    """提供干净的 TestClient, 不预设 admin override."""
    with TestClient(app) as c:
        yield c


# ============ Test 1: SA token 鉴权成功 ============


def test_auth_with_sa_token(client: TestClient, sa_token_env: str) -> None:
    """T-GRAF-009: Bearer GRAFANA_SERVICE_TOKEN → 200.

    SA token 路径: 字符串等价比较, 匹配则返回虚拟 admin User (id=0).
    """
    # 确保不覆盖 require_sa_or_admin (让真实逻辑跑)
    app.dependency_overrides.pop(require_sa_or_admin, None)

    resp = client.get(
        "/api/v1/alerts/observability/grafana/health",
        headers={"Authorization": f"Bearer {sa_token_env}"},
    )
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "v1.37"


# ============ Test 2: Admin User JWT 鉴权成功 ============


def test_auth_with_admin_jwt(client: TestClient, as_role, sa_token_env: str) -> None:
    """T-GRAF-009: Admin User JWT → 200.

    非 SA token 路径: 走 get_current_user (被 conftest override), as_role("admin") 使其返回 admin.
    require_sa_or_admin 校验 role == "admin" → 通过.
    """
    # 不发送 SA token, 让其走 JWT 路径
    # 设置 role 为 admin
    as_role("admin", 3)

    resp = client.get(
        "/api/v1/alerts/observability/grafana/health",
        headers={"Authorization": "Bearer some-jwt-token-here"},
    )
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["status"] == "ok"


# ============ Test 3: User JWT (非 admin) → 403 ============


def test_auth_with_user_jwt_403(client: TestClient, as_role, sa_token_env: str) -> None:
    """T-GRAF-009: User JWT (role != 'admin') → 403.

    非 SA token + 非 admin 用户, require_sa_or_admin 应返回 403.
    """
    as_role("user", 1)  # 普通用户

    resp = client.get(
        "/api/v1/alerts/observability/grafana/health",
        headers={"Authorization": "Bearer user-jwt-token"},
    )
    assert resp.status_code == 403, f"expected 403, got {resp.status_code}: {resp.text}"


# ============ Test count verification ============


def test_test_count() -> None:
    """Meta-test: 验证本文件测试数量 == 3 (不含本 meta-test)."""
    test_funcs = [
        name for name, dir in [(n, globals()) for n in globals()]
        if name.startswith("test_") and callable(dir[name]) and name != "test_test_count"
    ]
    assert len(test_funcs) == 3, f"expected 3 tests, got {len(test_funcs)}: {test_funcs}"
