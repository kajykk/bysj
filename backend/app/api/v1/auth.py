import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from jwt import PyJWTError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.pii_crypto import mask_pii
from app.core.rate_limit import get_real_client_ip, limiter
from app.core.response import ok
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.admin import OperationLog
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

    M-API-9 修复：dev 环境 secure=False 以便 HTTP 调试，samesite 降级为 lax
    允许跨页跳转携带 Cookie；生产环境强制 secure=True + samesite=strict。
    """
    if not settings.refresh_cookie_enabled:
        return
    is_prod = settings.app_env.lower() == "production"
    # dev: secure=False (HTTP 调试), samesite=lax; prod: secure=True, samesite=strict
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


def _log_auth_operation(
    db: AsyncSession,
    user: User | None,
    action_type: str,
    request: Request,
    detail: dict | None = None,
) -> None:
    """M-API-8 修复：为密码修改/重置/资料更新等敏感操作记录 OperationLog 审计日志."""
    log = OperationLog(
        operator_id=user.id if user else None,
        operator_role=user.role if user else None,
        action_type=action_type,
        target_type="user",
        target_id=user.id if user else None,
        detail=json.dumps(detail or {}, ensure_ascii=False)[:5000],
        ip_address=get_real_client_ip(request),
    )
    db.add(log)


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
async def register(
    request: Request, payload: RegisterRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    service = AuthService(db)
    try:
        data = await service.register(payload)
        # M-API-13 修复：register 响应只返回必要字段（id, username），
        # 不返回 role 等信息，避免泄露用户对象敏感字段
        return ok({"id": data.get("id"), "username": data.get("username")})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/login", responses=COMMON_ERROR_RESPONSES)
@limiter.limit("5/minute")
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = AuthService(db)
    try:
        data = await service.login(payload)
        user_info = data.get("user") or {}
        # P2-B 修复：复用 mask_pii 进行 username 脱敏，避免重复逻辑
        _masked_user = mask_pii(payload.username, keep_first=2)
        logger.info(
            "auth.login.success username=%s role=%s user_id=%s ip=%s",
            _masked_user,
            user_info.get("role"),
            user_info.get("id"),
            get_real_client_ip(request),
        )
        # SEC-002/003 修复：阶段1 双轨模式 - 同时设置 httpOnly Cookie（向后兼容）
        refresh_token = data.get("refresh_token")
        if refresh_token:
            _set_refresh_cookie(response, refresh_token)
        # H-API-12 修复：响应体只返回 access_token 和必要非敏感字段，
        # refresh_token 仅通过 Cookie 设置，不放在 response body，避免双轨重复
        return ok(
            {
                "access_token": data.get("access_token"),
                "token_type": data.get("token_type", "bearer"),
                "user": {
                    "id": user_info.get("id"),
                    "username": user_info.get("username"),
                    "role": user_info.get("role"),
                    "nickname": user_info.get("nickname"),
                },
            }
        )
    except ValueError as exc:
        # P1-SEC-018 修复：对 username 做脱敏处理，避免 PII 泄露到日志
        # P2-B 修复：复用 mask_pii 进行 username 脱敏，避免重复逻辑
        _masked_user = mask_pii(payload.username, keep_first=2)
        # L-20 修复：日志中不记录具体异常信息，避免泄露用户是否存在（用户枚举攻击）
        # 仅记录统一的失败原因，详细异常通过 exc_info=True 记录堆栈到 DEBUG 级别
        logger.warning(
            "auth.login.failed username=%s reason=invalid_credentials ip=%s",
            _masked_user,
            get_real_client_ip(request),
        )
        # L-1 修复：使用 logging.DEBUG 常量替代魔法数字 10
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("auth.login.failed detail: %s", exc, exc_info=True)
        # 统一返回模糊错误信息，避免泄露用户是否存在
        raise HTTPException(status_code=401, detail="用户名或密码错误") from exc


@router.post("/refresh", responses=COMMON_ERROR_RESPONSES)
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
        raise HTTPException(
            status_code=401, detail="无效或已过期的Refresh Token"
        ) from exc

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
    # C-06 修复：使用原子 UPDATE 防止 TOCTOU 竞态导致的 Refresh Token 重放攻击
    # 仅当 revoked_at IS NULL 时才更新，根据 rowcount 判断是否成功
    revoke_result = await db.execute(
        update(RefreshTokenSession)
        .where(
            RefreshTokenSession.jti == jti,
            RefreshTokenSession.revoked_at.is_(None),
        )
        .values(revoked_at=now_naive, replaced_by_jti=new_jti)
    )
    if revoke_result.rowcount == 0:
        # H-03 修复：token 不存在或已被撤销（可能被并发请求抢先使用）。
        # 提供更明确的错误信息，提示用户 token 已被使用，需重新登录。
        # 此为预期行为：原子 UPDATE 保证同一 refresh token 仅能被消费一次，
        # 并发场景下仅一个请求成功，其余请求会落到此分支。
        raise HTTPException(
            status_code=401,
            detail="登录凭证已被使用或失效，请重新登录",
        )

    # 重新查询获取 token_session 用于后续校验
    token_session = (
        await db.execute(
            select(RefreshTokenSession).where(RefreshTokenSession.jti == jti)
        )
    ).scalar_one_or_none()

    expires_at = now_naive + timedelta(days=settings.refresh_token_expire_days)
    db.add(
        RefreshTokenSession(
            user_id=user.id,
            jti=new_jti,
            expires_at=expires_at,
        )
    )

    new_access = create_access_token({"sub": str(user.id), "role": user.role})
    new_refresh = create_refresh_token(
        {"sub": str(user.id), "role": user.role}, jti=new_jti
    )
    await db.commit()

    # SEC-002/003 修复：阶段1 双轨模式 - 同时更新 Cookie
    _set_refresh_cookie(response, new_refresh)

    return ok(
        {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "token_type": "bearer",
        }
    )


@router.put("/change-password", responses=COMMON_ERROR_RESPONSES)
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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # M-API-8 修复：记录审计日志
    _log_auth_operation(db, current_user, "change_password", request)
    await db.commit()
    return ok({"message": "密码修改成功"})


@router.post("/request-reset", responses=COMMON_ERROR_RESPONSES)
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


@router.post("/reset-password", responses=COMMON_ERROR_RESPONSES)
@limiter.limit("3/minute")
async def reset_password(
    request: Request, payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    service = AuthService(db)
    try:
        await service.reset_password(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # M-API-8 修复：记录审计日志（密码重置无登录态，operator_id 为 None）
    _log_auth_operation(db, None, "reset_password", request)
    await db.commit()
    return ok({"message": "密码重置成功"})


@router.post("/logout", responses=COMMON_ERROR_RESPONSES)
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
    # SEC-P1-001: 从 request.state.token_payload 获取 access_token 的 jti 和 exp
    access_payload = getattr(request.state, "token_payload", {}) or {}
    access_jti = access_payload.get("jti")
    access_exp = access_payload.get("exp")
    try:
        result = await service.logout(
            current_user.id,
            refresh_token,
            access_token_jti=access_jti,
            access_token_exp=access_exp,
        )
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


@router.put("/profile", responses=COMMON_ERROR_RESPONSES)
@limiter.limit("5/minute")
async def update_profile(
    payload: UpdateProfileRequest,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = AuthService(db)
    try:
        data = await service.update_profile(current_user.id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # M-API-8 修复：记录审计日志
    _log_auth_operation(db, current_user, "update_profile", request)
    await db.commit()
    return ok(data)
