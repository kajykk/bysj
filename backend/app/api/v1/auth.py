import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from jwt import PyJWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.rate_limit import limiter
from app.core.response import ok
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.auth import RefreshTokenSession
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    RequestPasswordResetRequest,
    ResetPasswordRequest,
    UpdateProfileRequest,
)
from app.schemas.common import ErrorResponse
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


# ── SEC-002/003 修复：Refresh Token httpOnly Cookie 工具函数 ──

def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """设置 refresh_token httpOnly Cookie（阶段1 双轨模式）。

    安全属性：
    - httpOnly=True：防止 JavaScript 读取（防 XSS 窃取）
    - secure=True（生产环境）：仅 HTTPS 传输
    - samesite='strict'：防止 CSRF 攻击
    - path='/api/v1/auth'：限制 Cookie 范围到认证端点
    """
    if not settings.refresh_cookie_enabled:
        return
    is_prod = settings.app_env.lower() == "production"
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        max_age=int(timedelta(days=settings.refresh_token_expire_days).total_seconds()),
        httponly=True,
        secure=is_prod,
        samesite="strict" if is_prod else "lax",
        path=settings.refresh_cookie_path,
    )


def _clear_refresh_cookie(response: Response) -> None:
    """清除 refresh_token Cookie。

    修复：删除 Cookie 时必须传递与设置时一致的安全属性，
    否则浏览器会忽略删除请求（特别是 secure=True 的生产环境）。
    """
    if not settings.refresh_cookie_enabled:
        return
    is_prod = settings.app_env.lower() == "production"
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
        secure=is_prod,
        httponly=True,
        samesite="strict" if is_prod else "lax",
    )


def _get_refresh_token_from_cookie(request: Request) -> str | None:
    """从 Cookie 读取 refresh_token（若存在）。"""
    if not settings.refresh_cookie_enabled:
        return None
    return request.cookies.get(settings.refresh_cookie_name)


@router.post(
    "/register",
    responses={
        400: {
            "description": "用户名或邮箱已存在",
            "model": ErrorResponse,
        }
    },
)
@limiter.limit("5/minute")
async def register(request: Request, payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> dict:
    service = AuthService(db)
    try:
        data = await service.register(payload)
        return ok(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, response: Response, payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> dict:
    service = AuthService(db)
    try:
        data = await service.login(payload)
        user_info = data.get("user") or {}
        # 修复：成功日志也应对 username 脱敏，与失败日志策略一致，避免 PII 泄露到日志系统
        _masked_user = payload.username[:2] + "***" if len(payload.username) > 2 else "***"
        logger.info(
            "auth.login.success username=%s role=%s user_id=%s ip=%s",
            _masked_user,
            user_info.get("role"),
            user_info.get("id"),
            request.client.host if request.client else "-",
        )
        # SEC-002/003 修复：阶段1 双轨模式 - 同时设置 httpOnly Cookie（向后兼容）
        refresh_token = data.get("refresh_token")
        if refresh_token:
            _set_refresh_cookie(response, refresh_token)
        return ok(data)
    except ValueError as exc:
        # P1-SEC-018 修复：对 username 做脱敏处理，避免 PII 泄露到日志
        _masked_user = payload.username[:2] + "***" if len(payload.username) > 2 else "***"
        logger.warning(
            "auth.login.failed username=%s reason=%s ip=%s",
            _masked_user,
            str(exc),
            request.client.host if request.client else "-",
        )
        # 统一返回模糊错误信息，避免泄露用户是否存在
        raise HTTPException(status_code=401, detail="用户名或密码错误") from exc


@router.post("/refresh")
@limiter.limit("30/minute")
async def refresh_token(
    request: Request,
    response: Response,
    payload: RefreshTokenRequest | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # SEC-002/003 修复：阶段1 双轨模式 - 优先从 Cookie 读取，回退到 body
    refresh_token_value: str | None = None
    if payload and payload.refresh_token:
        refresh_token_value = payload.refresh_token
    else:
        refresh_token_value = _get_refresh_token_from_cookie(request)

    if not refresh_token_value:
        raise HTTPException(status_code=401, detail="未提供Refresh Token")

    try:
        token_data = decode_token(refresh_token_value)
        sub = token_data.get("sub")
        user_id = int(sub) if sub is not None else None
    except (PyJWTError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="无效或已过期的Refresh Token") from exc

    if token_data.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="无效的Refresh Token类型")
    jti = token_data.get("jti")
    if user_id is None or not jti:
        raise HTTPException(status_code=401, detail="Refresh Token缺少必要信息")

    user = await db.get(User, user_id)
    if not user or user.status != "active":
        raise HTTPException(status_code=401, detail="用户不存在或已被禁用")

    stmt = select(RefreshTokenSession).where(RefreshTokenSession.jti == jti)
    token_session = (await db.execute(stmt)).scalar_one_or_none()
    if token_session is None or token_session.user_id != user.id:
        raise HTTPException(status_code=401, detail="Refresh Token未登记或已失效")
    if token_session.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Refresh Token已被撤销")
    now_utc = datetime.now(timezone.utc)
    now_naive = _to_utc_naive(now_utc)
    expires_at_naive = _to_utc_naive(token_session.expires_at)
    if expires_at_naive <= now_naive:
        raise HTTPException(status_code=401, detail="Refresh Token已过期")

    new_jti = uuid4().hex
    token_session.revoked_at = now_naive
    token_session.replaced_by_jti = new_jti

    # 先 flush 确保旧 token 状态已写入
    await db.flush()

    expires_at = now_naive + timedelta(days=settings.refresh_token_expire_days)
    db.add(
        RefreshTokenSession(
            user_id=user.id,
            jti=new_jti,
            expires_at=expires_at,
        )
    )

    new_access = create_access_token({"sub": str(user.id), "role": user.role})
    new_refresh = create_refresh_token({"sub": str(user.id), "role": user.role}, jti=new_jti)
    await db.commit()

    # SEC-002/003 修复：阶段1 双轨模式 - 同时更新 Cookie
    _set_refresh_cookie(response, new_refresh)

    return ok({"access_token": new_access, "refresh_token": new_refresh, "token_type": "bearer"})


@router.put("/change-password")
@limiter.limit("5/minute")
async def change_password(
    request: Request,
    payload: ChangePasswordRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = AuthService(db)
    try:
        await service.change_password(current_user.id, payload)
        return ok({"message": "密码修改成功"})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/request-reset")
@limiter.limit("3/minute")
async def request_password_reset(
    request: Request,
    payload: RequestPasswordResetRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = AuthService(db)
    try:
        await service.request_password_reset(payload.email)
        return ok({"message": "如果邮箱已注册，重置邮件将尽快发送"})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reset-password")
@limiter.limit("3/minute")
async def reset_password(request: Request, payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)) -> dict:
    service = AuthService(db)
    try:
        await service.reset_password(payload)
        return ok({"message": "密码重置成功"})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/logout")
@limiter.limit("30/minute")
async def logout(
    request: Request,
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
    payload: RefreshTokenRequest | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """用户登出，撤销refresh token。如果提供refresh_token（body 或 cookie），只撤销该token；
    否则撤销该用户所有未过期的refresh token。"""
    service = AuthService(db)
    # SEC-002/003 修复：阶段1 双轨模式 - 优先从 body 读取，回退到 cookie
    refresh_token = payload.refresh_token if payload else None
    if not refresh_token:
        refresh_token = _get_refresh_token_from_cookie(request)
    try:
        result = await service.logout(current_user.id, refresh_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # 清除 refresh_token Cookie
    _clear_refresh_cookie(response)
    logger.info(
        "auth.logout user_id=%s role=%s revoked_count=%s",
        current_user.id,
        current_user.role,
        result.get("revoked_count"),
    )
    return ok({"message": "登出成功", **result})


@router.put("/profile")
async def update_profile(
    payload: UpdateProfileRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = AuthService(db)
    try:
        data = await service.update_profile(current_user.id, payload)
        return ok(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
