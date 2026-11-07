"""ROUND_35 / M-20 + M-21：后端 RBAC 的**真实对象**端到端验证。

审查报告第七节把「M-21 后端是否真的拦截越权」「M-20 篡改角色能否进入
咨询师工作台」列为未验证项。原因是仓库既有用例普遍依赖 conftest 的
autouse fixture ``override_user_dependency``，它把 ``get_current_user``
换成读 ``CURRENT_USER`` 字典构造的 User —— 那是**测试替身**：只能证明
调用契约，不能证明真实鉴权链（decode_token → jti blocklist → DB 用户 →
JWT/DB 角色一致性 → 角色层级 → 租户一致性）会拦截越权。

本文件显式 pop 该 override，走真实链路：真实注册写库 → 真实登录签发
JWT → 真实 ``get_current_user`` + ``require_role``。数据库是 conftest 提供的
真实 SQLite 会话（非 mock）；只用 ``memory_blocklist`` 改变缓存后端选型，
避免本机 6379 无 Redis 时 fail-closed 的 503 掩盖 403 判据。

「混合输入才可区分」：每个拒绝用例都配一个**正向对照**——同一 token 访问
user 级端点必须 200。否则「全 403」可能只是 token 无效被当成 401，断言
就失去了区分力。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.deps import get_current_user
from app.main import app
from app.models.user import User

_COUNSELOR_ONLY = "/api/v1/counselor/warnings"
_PLATFORM_ADMIN_ONLY = "/api/v1/tenants"
_USER_ALLOWED = "/api/v1/auth/profile"


@pytest.fixture
def clean_db(db_session):
    """conftest 的真实 SQLite AsyncSession（test_auth_flow.py 里的同名 fixture 是局部的）。"""
    return db_session


@pytest.fixture
def real_auth_chain():
    """临时移除 get_current_user 的测试替身，恢复真实鉴权链。

    pop 后 autouse fixture 的 teardown 会再 pop 一次（无害）；这里仍用
    try/finally 显式还原，保证同一进程内后续用例看到的状态与 fixture 约定一致。
    """
    sentinel = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides.pop(get_current_user, None)
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        if sentinel is not None:
            app.dependency_overrides[get_current_user] = sentinel


def _register_and_login(client: TestClient, *, username: str, requested_role: str) -> str:
    """真实注册 + 真实登录，返回 access_token。"""
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@test.com",
            "password": "StrongPass123",
            "role": requested_role,
        },
    )
    assert reg.status_code == 200, f"注册失败: {reg.status_code} {reg.text}"
    login = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "StrongPass123"},
    )
    assert login.status_code == 200, f"登录失败: {login.status_code} {login.text}"
    token = login.json()["data"]["access_token"]
    assert isinstance(token, str) and token, "登录未返回 access_token"
    return token


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestRealRbacRejectsRoleEscalation:
    @pytest.mark.asyncio
    async def test_registration_ignores_requested_counselor_role(
        self, client: TestClient, clean_db, real_auth_chain, memory_blocklist
    ):
        """篡改注册 payload 的 role 不能提权：DB 里落库角色仍是 user。"""
        token = _register_and_login(
            client, username="r35_role_tamper", requested_role="counselor"
        )
        # 真实 DB 读回（不是替身造的 User 对象）
        row = (
            await clean_db.execute(
                select(User).where(User.username == "r35_role_tamper")
            )
        ).scalar_one()
        assert row.role == "user", f"注册角色未被强制收敛: {row.role}"

        # 正向对照：同一 token 在 user 级端点必须能用，排除「token 无效」解释
        allowed = client.get(_USER_ALLOWED, headers=_bearer(token))
        assert allowed.status_code == 200, (
            f"正向对照失败，token 可能无效: {allowed.status_code} {allowed.text}"
        )

        # 真实鉴权链必须按角色拒绝，而不是靠前端 v-if 收敛
        denied = client.get(_COUNSELOR_ONLY, headers=_bearer(token))
        assert denied.status_code == 403, (
            f"真实 user token 竟可访问咨询师端点: {denied.status_code} {denied.text}"
        )

    def test_platform_admin_endpoint_also_rejects_real_user_token(
        self, client: TestClient, clean_db, real_auth_chain, memory_blocklist
    ):
        """M-20 的另一半：平台级端点同样不能靠普通 token 进入。"""
        token = _register_and_login(
            client, username="r35_platform_tamper", requested_role="admin"
        )
        allowed = client.get(_USER_ALLOWED, headers=_bearer(token))
        assert allowed.status_code == 200

        denied = client.get(_PLATFORM_ADMIN_ONLY, headers=_bearer(token))
        assert denied.status_code == 403

    def test_tampered_test_double_does_not_change_backend_decision(
        self, client: TestClient, clean_db, real_auth_chain, memory_blocklist,
        as_role,
    ):
        """把 CURRENT_USER 篡改成 counselor 也无效：真实后端不读测试替身。

        这条专门证伪「既有用例里 as_role('counselor') 能过 = 后端已放行」的
        误读——只要 get_current_user 被 override，那个结论就只是替身行为。
        """
        token = _register_and_login(
            client, username="r35_double_tamper", requested_role="user"
        )
        as_role("counselor", 999, tenant_id=1)  # 模拟前端 store / 测试替身被篡改
        denied = client.get(_COUNSELOR_ONLY, headers=_bearer(token))
        assert denied.status_code == 403

        allowed = client.get(_USER_ALLOWED, headers=_bearer(token))
        assert allowed.status_code == 200
