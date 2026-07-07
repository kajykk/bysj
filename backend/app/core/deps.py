import logging
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt import PyJWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.contracts import (
    USER_ROLE_ADMIN,
    USER_ROLE_COUNSELOR,
    USER_ROLE_USER,
    USER_STATUS_ACTIVE,
)
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User

logger = logging.getLogger(__name__)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

# MAINT-P1-003: 角色与状态字面量统一引用 contracts.py 契约常量 (Single Source of Truth)
ROLE_HIERARCHY: dict[str, set[str]] = {
    USER_ROLE_ADMIN: {USER_ROLE_ADMIN, USER_ROLE_COUNSELOR, USER_ROLE_USER},
    USER_ROLE_COUNSELOR: {USER_ROLE_COUNSELOR},
    USER_ROLE_USER: {USER_ROLE_USER},
}

PERMISSION_MATRIX: dict[str, set[str]] = {
    USER_ROLE_USER: {
        "user.warning.read",
        "user.warning.track",
        "user.assessment.read",
        "user.export.risk",
        "user.predict.use",
        "user.dashboard.view",
        "user.content.read",
        "user.intervention.read",
        "user.settings.manage",
    },
    USER_ROLE_COUNSELOR: {
        "counselor.warning.handle",
        "counselor.warning.ignore",
        "counselor.warning.batch",
        "counselor.user.consultation.view",
        "counselor.predict.use",
        "counselor.dashboard.view",
        "counselor.settings.manage",
        "review.view",
        "review.handle",
    },
    USER_ROLE_ADMIN: {
        "admin.operation_log.view",
        "admin.operation_log.filter",
        "admin.operation_log.audit",
        "admin.predict.audit",
        "admin.dashboard.view",
        "admin.settings.manage",
        "admin.template.manage",
        # ISS-095 修复：补齐与前端 permissions.ts 对齐的告警/静默权限
        "admin.alerts.view",
        "admin.silences.manage",
        "review.view",
        "review.handle",
        "crisis_event.view",
        "crisis_event.handle",
        "crisis_event.export",
    },
}


async def get_current_user(
    request: Request,
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="未提供认证Token"
        )
    try:
        payload = decode_token(token)
        # v1.27: 缓存到 request.state，供 _role_for_request 等复用，避免重复 decode
        request.state.token_payload = payload
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的Token类型"
            )
        sub = payload.get("sub")
        if sub is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token缺少主体信息"
            )
        user_id = int(sub)
    except HTTPException:
        raise
    except (PyJWTError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="无效或已过期的Token"
        ) from exc

    # SEC-P1-001: 检查 jti 是否在 blocklist 中 (登出撤销)
    from app.core.token_blocklist import is_token_revoked

    jti = payload.get("jti")
    if jti and await is_token_revoked(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token已被撤销"
        )

    user = await db.get(User, user_id)
    if not user or user.status != USER_STATUS_ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已被禁用"
        )
    if not user.role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户角色缺失"
        )

    # SEC-P1-001: 校验 JWT role 与 DB role 一致 (防止降权后继续使用旧 token)
    token_role = payload.get("role")
    if token_role and token_role != user.role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token角色与当前用户角色不匹配",
        )

    return user


def _role_for_request(request: Request) -> str | None:
    """提取请求中 JWT 的角色声明。

    v1.27 优化:
    - 优先从 `request.state.token_payload` 读取（get_current_user 已解析）
    - 避免对同一请求重复 decode_token（性能 + 避免潜在 timing 差异）
    """
    cached = getattr(request.state, "token_payload", None)
    if cached is not None:
        role = cached.get("role")
        return role if isinstance(role, str) else None

    header = request.headers.get("authorization")
    if not header or not header.lower().startswith("bearer "):
        return None
    token = header.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        payload = decode_token(token)
    except Exception as exc:
        # P1-E 修复：认证 token 解码失败必须记录日志，便于排查 token 伪造、JWT 密钥错误等问题
        logger.warning("decode_token failed: %s", exc)
        return None
    role = payload.get("role")
    return role if isinstance(role, str) else None


def require_role(*roles: str):
    allowed = set(roles)

    async def checker(
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        # 未知角色直接拒绝，防止注入异常角色名绕过权限
        if current_user.role not in ROLE_HIERARCHY:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="权限不足"
            )
        effective = ROLE_HIERARCHY[current_user.role]
        if effective.intersection(allowed):
            return current_user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")

    return checker


def require_permission(permission: str):
    async def checker(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        granted = PERMISSION_MATRIX.get(current_user.role, set())
        if permission not in granted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="权限不足"
            )
        return current_user

    return checker


# ── v1.37 Grafana Service Account 鉴权 ──


async def _resolve_current_user(
    request: Request,
    token: str | None,
    db: AsyncSession,
) -> User:
    """通过依赖覆盖机制解析当前用户.

    优先检查 ``app.dependency_overrides[get_current_user]`` (测试用),
    否则调用真实 ``get_current_user`` (生产用).

    v1.37 修复: ``require_sa_or_admin`` 直接调用 ``get_current_user`` 会绕过
    FastAPI 的依赖覆盖系统, 导致测试无法 mock. 这里手动检查覆盖.

    治理循环依赖: 原实现 ``from app.main import app`` 会形成
    ``api.v1.* -> core.deps -> main -> api.v1.*`` 启动期循环依赖 (已用 lazy import
    缓解为运行期循环). 改用 ``request.app`` 拿当前 FastAPI 实例 —— FastAPI 在
    路由分发时自动注入 ``request.app``, 语义等价且彻底消除对 app.main 的导入依赖.
    """
    override = request.app.dependency_overrides.get(get_current_user)
    if override is not None:
        # 优先: 走覆盖函数 (测试用)
        result = override(request=request, token=token, db=db)
        if hasattr(result, "__await__"):
            return await result
        return result

    # 兜底: 真实 JWT 解码 (生产用)
    return await get_current_user(request=request, token=token, db=db)


async def require_sa_or_admin(
    request: Request,
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """支持 Grafana Service Account Token 或 Admin User 的双路径鉴权.

    v1.37: Grafana JSON Datasource 调用后端 /grafana/* 端点时使用.

    优先级:
    1. **Service Account Token** —— Bearer 与 ``settings.grafana_service_token``
       匹配时, 返回虚拟 admin ``User`` (id=0, role='admin', status='active').
       不查库, 不解码 JWT, 仅做字符串等价比较.
    2. **Admin User JWT** —— 否则回退到 ``_resolve_current_user`` 解码 JWT,
       验证用户存在且 ``role == 'admin'``.

    当 ``settings.grafana_service_token`` 为空 (``None`` 或 ``""``) 时,
    SA 鉴权路径自动禁用, 仅允许 Admin User JWT 鉴权 (向后兼容 v1.36).

    失败:
    - 无 token 或 token 无效 → 401
    - Token 是合法 JWT 但用户非 admin → 403
    """
    from app.core.config import settings

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证Token",
        )

    # 路径 1: Service Account Token (Grafana 调用)
    sa_token = settings.grafana_service_token
    if sa_token and secrets.compare_digest(token, sa_token):
        # 虚拟 admin 用户 (不写库, 仅作为鉴权通过的标识)
        # M-01 修复: 填充所有必要字段，避免下游代码访问未设置字段时得到 None。
        # created_at/updated_at 使用当前时间，last_login_at 同理，确保类型为 datetime。
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        sa_user = User(
            id=0,
            username="grafana-service-account",
            email="grafana-sa@bysj.local",
            email_hash="grafana-sa-blind-index-placeholder",
            phone=None,
            password_hash="!grafana-sa-token!",
            role=USER_ROLE_ADMIN,
            status=USER_STATUS_ACTIVE,
            avatar_url=None,
            last_login_at=now,
            created_at=now,
            updated_at=now,
        )
        # 缓存 token payload 到 request.state, 供下游 _role_for_request 复用
        request.state.token_payload = {
            "role": USER_ROLE_ADMIN,
            "sub": "0",
            "type": "service_account",
        }
        return sa_user

    # 路径 2: Admin User JWT (人类管理员登录)
    user = await _resolve_current_user(request=request, token=token, db=db)
    if user.role != USER_ROLE_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Grafana 端点需要管理员权限",
        )
    return user
