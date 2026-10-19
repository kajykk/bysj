"""REV-2026-10-20 S7 回归：租户"封禁"开关必须真正生效。

改前 ``tenant_admin.suspend`` 只把 ``Tenant.status`` 写成 ``suspended``，
全仓没有任何读取点：``get_current_tenant`` 在 ``app/api`` 下的
``Depends`` 命中 0 次，``login`` / ``refresh`` 只校验 ``user.status``，
WS handshake 也不看租户。管理员暂停一个租户后，该租户用户仍可登录、
旧 access token（2h）与 refresh token（7d）继续有效、全部业务接口照常读写。

本文件走真实依赖函数 + 真实 DB 行 + 真实 JWT，不替换被测层。
唯一被替换的是 Redis blocklist 检查（本机无 Redis，且该层与本缺陷无关）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from starlette.requests import Request

from app.core.pii_crypto import compute_blind_index
from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
)
from app.models.auth import RefreshTokenSession
from app.models.tenant import Tenant
from app.models.user import User

TENANT_ID = 9901
USER_ID = 9901
USERNAME = "s7_student"
PASSWORD = "testpass123"


def _http_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/users/me",
            "query_string": b"",
            "headers": [],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 12345),
        }
    )


@pytest.fixture
async def tenant_user(db_session, monkeypatch):
    """租户 9901（active）+ 用户 9901；返回 (db, tenant, user)。"""
    # Redis 不可用：blocklist 检查与本缺陷无关，替换为"未撤销"
    import app.core.token_blocklist as blocklist

    async def _not_revoked(jti: str) -> bool:
        return False

    monkeypatch.setattr(blocklist, "is_token_revoked", _not_revoked)

    tenant = Tenant(id=TENANT_ID, name="S7 租户", code="s7-tenant", status="active")
    email = "s7@test.com"
    user = User(
        id=USER_ID,
        username=USERNAME,
        email=email,
        email_hash=compute_blind_index(email, "email"),
        password_hash=get_password_hash(PASSWORD),
        role="user",
        status="active",
        tenant_id=TENANT_ID,
    )
    db_session.add_all([tenant, user])
    await db_session.commit()
    return db_session, tenant, user


def _access_token(user: User) -> str:
    return create_access_token(
        {"sub": str(user.id), "role": user.role, "tenant_id": user.tenant_id}
    )


async def test_active_tenant_request_is_allowed(tenant_user):
    from app.core.deps import get_current_user

    db, _, user = tenant_user
    result = await get_current_user(
        request=_http_request(), token=_access_token(user), db=db
    )
    assert result.id == USER_ID


async def test_suspended_tenant_blocks_authenticated_request(tenant_user):
    from app.core.deps import get_current_user

    db, tenant, user = tenant_user
    tenant.status = "suspended"
    await db.commit()

    # 旧 token 仍在有效期内 —— 必须在认证入口就被拒绝
    with pytest.raises(HTTPException) as excinfo:
        await get_current_user(request=_http_request(), token=_access_token(user), db=db)

    assert excinfo.value.status_code == 403
    assert "租户已暂停" in str(excinfo.value.detail)


async def test_suspended_tenant_blocks_login(tenant_user):
    from app.schemas.auth import LoginRequest
    from app.services.auth_service import AuthService

    db, tenant, _ = tenant_user
    service = AuthService(db)

    # 正常态可登录（保证修复没有误伤）
    tokens = await service.login(
        LoginRequest(username=USERNAME, password=PASSWORD), tenant_id=TENANT_ID
    )
    assert tokens["access_token"]

    tenant.status = "suspended"
    await db.commit()

    with pytest.raises(ValueError) as excinfo:
        await service.login(
            LoginRequest(username=USERNAME, password=PASSWORD), tenant_id=TENANT_ID
        )
    assert "租户已暂停" in str(excinfo.value)


async def test_suspended_tenant_blocks_refresh(tenant_user):
    from app.services.auth_service import AuthService

    db, tenant, user = tenant_user
    jti = "s7-refresh-jti"
    token = create_refresh_token(
        {"sub": str(user.id), "role": user.role, "tenant_id": user.tenant_id},
        jti=jti,
    )
    db.add(
        RefreshTokenSession(
            user_id=user.id,
            jti=jti,
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None)
            + timedelta(days=1),
        )
    )
    await db.commit()

    tenant.status = "suspended"
    await db.commit()

    with pytest.raises(ValueError) as excinfo:
        await AuthService(db).refresh(token)
    assert "租户已暂停" in str(excinfo.value)

    # 暂停期间不得留下新的会话行（refresh 在签发前就被拒）
    rows = (
        await db.execute(
            select(RefreshTokenSession).where(RefreshTokenSession.user_id == user.id)
        )
    ).scalars().all()
    assert len(rows) == 1
