"""AUDIT-2026-10-06 (P0-1): 租户隔离在认证入口与角色依赖上的落地.

背景（审查报告 ARCH-1 / ARCH-2）：
- ``AuthService.login`` 按 username **全局**查 User，无任何 tenant_id 条件
  → 租户 A 的用户可以在租户 B 上下文登录成功并拿到有效 JWT；
- ``deps.require_role`` / ``deps.require_permission`` 只校验角色/权限，
  **不做租户绑定** → 使用它们的约 40 个路由完全没有租户隔离，
  与 ``require_role_tenant_scoped`` 形成两套标准。

本文件锁定修复后的语义：租户校验是角色依赖的**默认行为**，
且登录从入口就绑定请求租户。
"""

from __future__ import annotations

import pytest

from app.core.contracts import DEFAULT_TENANT_ID
from app.core.security import create_access_token


class TestRequireRoleIsTenantBound:
    """require_role 现在必须做租户一致性校验（原实现完全不做）。"""

    def test_require_role_blocks_cross_tenant_header(
        self, client, auth_headers, as_role
    ):
        """用户 tenant_id=1 + X-Tenant-ID: 2 → 403.

        /user/data/collect 用的是 require_role("user")（旧依赖），
        修复前这个组合是**放行**的 —— 这正是审查报告的 ARCH-2。
        """
        as_role("user", 1, tenant_id=1)
        response = client.post(
            "/api/v1/user/data/collect",
            json={"assessment_type": "structured", "data_payload": {}},
            headers={**auth_headers, "X-Tenant-ID": "2"},
        )
        assert response.status_code == 403

    def test_require_role_allows_matching_tenant(
        self, client, auth_headers, as_role
    ):
        """用户 tenant_id=1 + X-Tenant-ID: 1 → 不因租户被拒.

        注意：断言只排除 403（租户/权限拒绝）。请求体是空的 data_payload，
        业务层会返回 422 校验失败或 500（模型不可用），都属预期 ——
        本用例关心的是"没有因租户不匹配被拦"。
        """
        as_role("user", 1, tenant_id=1)
        response = client.post(
            "/api/v1/user/data/collect",
            json={"assessment_type": "structured", "data_payload": {}},
            headers={**auth_headers, "X-Tenant-ID": "1"},
        )
        assert response.status_code != 403

    def test_reverse_cross_tenant_also_blocked(self, client, auth_headers, as_role):
        """用户 tenant_id=2 + X-Tenant-ID: 1 → 403（反向串租）。"""
        as_role("user", 1, tenant_id=2)
        response = client.post(
            "/api/v1/user/data/collect",
            json={"assessment_type": "structured", "data_payload": {}},
            headers={**auth_headers, "X-Tenant-ID": "1"},
        )
        assert response.status_code == 403


class TestStaleTenantClaimRejected:
    """token 里的 tenant_id 声明必须与用户当前租户一致。

    用单元测试直接打 ``get_current_user``：``as_role`` 夹具会
    ``dependency_overrides[get_current_user]``，走 HTTP 会绕过 JWT 校验路径。
    """

    @pytest.mark.asyncio
    async def test_token_with_stale_tenant_claim_is_rejected(self):
        """用户已被迁到租户 2，手上租户 1 的旧 token 应被拒绝 (401)。

        否则"跨租户迁移/改租户"要等 token 自然过期（最长 2h）才生效。
        """
        from unittest.mock import AsyncMock, patch

        from fastapi import HTTPException, Request

        from app.core.deps import get_current_user
        from app.models.user import User

        user = User(
            id=7,
            username="migrated_user",
            email="m@test.com",
            email_hash="blind-index-placeholder",
            password_hash="x",
            role="user",
            status="active",
            tenant_id=2,
        )
        db = AsyncMock()
        db.get = AsyncMock(return_value=user)

        stale_token = create_access_token(
            {"sub": "7", "role": "user", "tenant_id": DEFAULT_TENANT_ID}
        )
        request = Request({"type": "http", "headers": []})

        # is_token_revoked 在函数内局部导入，patch 目标必须是来源模块
        # app.core.token_blocklist（patch app.core.deps.is_token_revoked 会 AttributeError），
        # 且这里必须 mock：本机 Redis 不可用时它会 fail-closed 抛 CacheUnavailableError(503)。
        with patch(
            "app.core.token_blocklist.is_token_revoked",
            new=AsyncMock(return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(request=request, token=stale_token, db=db)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_token_with_matching_tenant_claim_is_accepted(self):
        """租户声明与用户当前租户一致时应放行（防止上面那条误伤）。"""
        from unittest.mock import AsyncMock, patch

        from fastapi import Request

        from app.core.deps import get_current_user
        from app.models.user import User

        user = User(
            id=7,
            username="normal_user",
            email="n@test.com",
            email_hash="blind-index-placeholder-2",
            password_hash="x",
            role="user",
            status="active",
            tenant_id=1,
        )
        db = AsyncMock()
        db.get = AsyncMock(return_value=user)

        token = create_access_token(
            {"sub": "7", "role": "user", "tenant_id": DEFAULT_TENANT_ID}
        )
        request = Request({"type": "http", "headers": []})

        with patch(
            "app.core.token_blocklist.is_token_revoked",
            new=AsyncMock(return_value=False),
        ):
            result = await get_current_user(request=request, token=token, db=db)

        assert result is user


@pytest.mark.parametrize("tenant_header", ["2", "999"])
def test_login_is_scoped_to_request_tenant(client, tenant_header) -> None:
    """登录必须绑定请求租户：默认租户的用户拿 X-Tenant-ID: 2 登录应失败。

    原实现 login 按 username 全局查，任意租户上下文都能登录成功。
    """
    # 先在默认租户注册一个用户
    username = f"p0_tenant_user_{tenant_header}"
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "Str0ngPass!2026",
        },
    )
    assert reg.status_code == 200, reg.text

    # 用另一个租户的上下文登录 -> 应被拒绝
    # （login 路由把 ValueError 统一映射为 401「用户名或密码错误」，
    #   刻意不区分"用户不存在于本租户"，避免用户枚举）
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "Str0ngPass!2026"},
        headers={"X-Tenant-ID": tenant_header},
    )
    assert resp.status_code == 401

    # 同租户登录 -> 成功
    ok_resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "Str0ngPass!2026"},
        headers={"X-Tenant-ID": str(DEFAULT_TENANT_ID)},
    )
    assert ok_resp.status_code == 200
    assert ok_resp.json()["data"]["access_token"]
