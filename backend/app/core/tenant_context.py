"""Phase 5 租户上下文中间件与依赖.

按 ADR-001 决策：
- 中间件从请求头 X-Tenant-ID 或子域名解析租户
- 租户上下文存储在 request.state.tenant_id
- 依赖注入 get_current_tenant 提供给路由使用

解析优先级:
1. 请求头 X-Tenant-ID（数字 ID 或租户 code）
2. 子域名（如 xx_univ.dws.example.com → code="xx_univ"）
3. JWT 中的 tenant_id 声明（已登录用户）
4. 默认租户 (DEFAULT_TENANT_ID)

向后兼容：未解析到租户时使用默认租户，保证现有 API 正常工作。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.contracts import (
    DEFAULT_TENANT_ID,
    TENANT_STATUS_ACTIVE,
    TENANT_STATUS_SUSPENDED,
)
from app.core.database import get_db
from app.core.deps import ROLE_HIERARCHY, get_current_user
from app.models.tenant import Tenant
from app.models.user import User

logger = logging.getLogger(__name__)

# 请求头名称
TENANT_HEADER = "X-Tenant-ID"

# request.state 上的属性名
TENANT_STATE_KEY = "tenant_id"
TENANT_OBJ_STATE_KEY = "_tenant_obj"


async def tenant_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """解析请求租户上下文并存储到 request.state.

    解析顺序：
    1. 请求头 X-Tenant-ID（数字 ID 或 code 字符串）
    2. 子域名（第一段作为 code）
    3. JWT 中的 tenant_id 声明
    4. 默认租户

    注意：此中间件只解析 tenant_id 并写入 request.state，
    不做租户存在性校验（避免每个请求都查库）。
    租户校验由 get_current_tenant 依赖在需要时执行。
    """
    tenant_id: int | None = None
    tenant_code: str | None = None

    # 1. 请求头 X-Tenant-ID
    header_value = request.headers.get(TENANT_HEADER)
    if header_value:
        header_value = header_value.strip()
        if header_value.isdigit():
            tenant_id = int(header_value)
        else:
            tenant_code = header_value

    # 2. 子域名解析（仅在未通过请求头解析时）
    if tenant_id is None and tenant_code is None:
        host = request.headers.get("host", "")
        # 形如 xx_univ.dws.example.com → 取第一段
        if "." in host and not host.startswith(("localhost", "127.0.0.1", "0.0.0.0")):
            first_segment = host.split(".", 1)[0]
            # 排除常见非租户子域名
            if first_segment and first_segment not in {"www", "api", "admin", "dws"}:
                tenant_code = first_segment

    # 3. JWT 中的 tenant_id（已在 get_current_user 之前解析，可能未设置）
    if tenant_id is None and tenant_code is None:
        # 注意：此时 JWT 可能尚未解析，回退到默认
        jwt_tenant = getattr(request.state, "tenant_id_from_jwt", None)
        if isinstance(jwt_tenant, int):
            tenant_id = jwt_tenant

    # 4. 默认租户
    if tenant_id is None and tenant_code is None:
        tenant_id = DEFAULT_TENANT_ID

    # 存储到 request.state
    if tenant_id is not None:
        request.state.tenant_id = tenant_id
        request.state.tenant_code = None
    else:
        # 有 code 但未解析为 ID，留给 get_current_tenant 依赖查库
        request.state.tenant_id = None
        request.state.tenant_code = tenant_code

    return await call_next(request)


async def _resolve_tenant(
    db: AsyncSession, tenant_id: int | None, tenant_code: str | None
) -> Tenant:
    """根据 tenant_id 或 tenant_code 查库解析租户，返回 Tenant 对象.

    Raises:
        HTTPException(404): 租户不存在
        HTTPException(403): 租户已暂停
    """
    stmt = select(Tenant)
    if tenant_id is not None:
        stmt = stmt.where(Tenant.id == tenant_id)
    elif tenant_code is not None:
        stmt = stmt.where(Tenant.code == tenant_code)
    else:
        # 兜底：默认租户
        stmt = stmt.where(Tenant.id == DEFAULT_TENANT_ID)

    tenant = (await db.execute(stmt)).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"租户不存在: id={tenant_id}, code={tenant_code}",
        )

    if tenant.status == TENANT_STATUS_SUSPENDED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"租户已暂停: {tenant.code}",
        )

    return tenant


async def get_current_tenant(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Tenant:
    """获取当前请求的租户对象.

    优先从 request.state 缓存的租户对象读取，
    否则根据 tenant_id / tenant_code 查库解析。

    Raises:
        HTTPException(404): 租户不存在
        HTTPException(403): 租户已暂停
    """
    # 优先读缓存
    cached = getattr(request.state, TENANT_OBJ_STATE_KEY, None)
    if cached is not None:
        return cached

    tenant_id = getattr(request.state, TENANT_STATE_KEY, None)
    tenant_code = getattr(request.state, "tenant_code", None)

    tenant = await _resolve_tenant(db, tenant_id, tenant_code)

    # 缓存到 request.state，避免同请求多次查库
    request.state.tenant_id = tenant.id
    request.state.tenant_code = None
    setattr(request.state, TENANT_OBJ_STATE_KEY, tenant)
    return tenant


async def get_current_tenant_id(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> int:
    """获取当前请求的租户 ID（轻量级，不返回完整对象）.

    与 get_current_tenant 区别：此依赖返回 int，用于只需 ID 的场景，
    但仍会校验租户存在性和状态（通过 get_current_tenant 复用）。
    """
    tenant = await get_current_tenant(request=request, db=db)
    return tenant.id


def get_request_tenant_id(request: Request) -> int:
    """从 request.state 直接读取已解析的 tenant_id（不查库）.

    适用于中间件已解析但无需租户存在性校验的场景。
    若未设置，返回 DEFAULT_TENANT_ID。
    """
    tenant_id = getattr(request.state, TENANT_STATE_KEY, None)
    if isinstance(tenant_id, int):
        return tenant_id
    return DEFAULT_TENANT_ID


def enforce_tenant_match(resource_tenant_id: int | None, request_tenant_id: int) -> None:
    """强制校验资源租户与请求租户匹配（防串租）.

    Args:
        resource_tenant_id: 资源记录上的 tenant_id（可能为 None，视为默认租户）
        request_tenant_id: 当前请求的 tenant_id

    Raises:
        HTTPException(403): 租户不匹配
    """
    effective = resource_tenant_id if resource_tenant_id is not None else DEFAULT_TENANT_ID
    if effective != request_tenant_id:
        logger.warning(
            "Cross-tenant access blocked: resource_tenant=%s, request_tenant=%s",
            effective, request_tenant_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="跨租户访问被拒绝",
        )


# =========================================================================
# RBAC + 租户上下文绑定依赖
# =========================================================================


def require_role_tenant_scoped(*roles: str):
    """角色 + 租户双向校验依赖工厂.

    在 ``require_role`` 基础上增加租户上下文一致性校验：
    1. 校验用户角色属于允许列表（复用 ROLE_HIERARCHY）
    2. 校验用户 ``tenant_id`` 与请求租户上下文一致（防串租）

    防御场景：租户 A 的用户伪造 ``X-Tenant-ID: B`` 头，试图在租户 B
    上下文中执行操作。此依赖在入口层即阻断此类租户混淆攻击。

    用法::

        current_user: Annotated[User, Depends(require_role_tenant_scoped("admin"))]

    Raises:
        HTTPException(403): 角色不足或租户不匹配
    """
    allowed = set(roles)

    async def checker(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        # 1. 角色校验
        if current_user.role not in ROLE_HIERARCHY:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="权限不足"
            )
        effective = ROLE_HIERARCHY[current_user.role]
        if not effective.intersection(allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="权限不足"
            )

        # 2. 租户上下文一致性校验（防串租）
        request_tenant_id = get_request_tenant_id(request)
        user_tenant_id = (
            current_user.tenant_id
            if current_user.tenant_id is not None
            else DEFAULT_TENANT_ID
        )
        if user_tenant_id != request_tenant_id:
            logger.warning(
                "Tenant confusion blocked: user_tenant=%s, request_tenant=%s, user_id=%s",
                user_tenant_id,
                request_tenant_id,
                current_user.id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="用户租户与请求租户不匹配",
            )

        return current_user

    return checker
