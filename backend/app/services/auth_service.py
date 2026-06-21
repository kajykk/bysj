from datetime import datetime, timedelta, timezone
import logging
from uuid import uuid4

from jwt import PyJWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
)
from app.core.pii_crypto import compute_blind_index
from app.models.auth import RefreshTokenSession
from app.models.user import User, UserProfile
from app.schemas.auth import ChangePasswordRequest, LoginRequest, RegisterRequest, ResetPasswordRequest, UpdateProfileRequest
from app.core.config import settings
from app.services.email_service import EmailService

# P1-E 修复：添加 logger 记录密码验证异常，防止服务端异常被静默吞掉
logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.email_service = EmailService()

    async def register(self, payload: RegisterRequest) -> dict:
        # PII 加密：使用 email_hash 盲索引进行唯一性检查（密文不可直接比较）
        email_hash = compute_blind_index(payload.email, "email")
        stmt = select(User).where((User.username == payload.username) | (User.email_hash == email_hash))
        exists_user = (await self.db.execute(stmt)).scalar_one_or_none()
        if exists_user:
            raise ValueError("用户名或邮箱已存在")

        user = User(
            username=payload.username,
            email=payload.email,
            email_hash=email_hash,
            password_hash=get_password_hash(payload.password),
            role="user",  # SEC-001 修复：强制注册用户为 user 角色，咨询师账号需管理员创建
            status="active",
        )
        self.db.add(user)
        await self.db.flush()

        profile = UserProfile(user_id=user.id, nickname=payload.username)
        self.db.add(profile)
        await self.db.commit()

        return {"id": user.id, "username": user.username, "role": user.role}

    async def login(self, payload: LoginRequest) -> dict:
        stmt = select(User).where(User.username == payload.username)
        user = (await self.db.execute(stmt)).scalar_one_or_none()
        if not user or not verify_password(payload.password, user.password_hash):
            raise ValueError("用户名或密码错误")
        if user.status != "active":
            raise ValueError("用户已被禁用")

        access_token = create_access_token({"sub": str(user.id), "role": user.role})
        refresh_jti = uuid4().hex
        refresh_token = create_refresh_token({"sub": str(user.id), "role": user.role}, jti=refresh_jti)

        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
        self.db.add(
            RefreshTokenSession(
                user_id=user.id,
                jti=refresh_jti,
                expires_at=expires_at,
            )
        )
        await self.db.commit()

        profile_stmt = select(UserProfile).where(UserProfile.user_id == user.id)
        profile = (await self.db.execute(profile_stmt)).scalar_one_or_none()

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "nickname": profile.nickname if profile and profile.nickname else user.username,
            },
        }

    async def change_password(self, user_id: int, payload: ChangePasswordRequest) -> None:
        user = await self.db.get(User, user_id)
        if user is None:
            raise ValueError("用户不存在")
        try:
            password_valid = verify_password(payload.old_password, user.password_hash)
        except Exception:
            # P1-E 修复：记录密码验证异常，防止服务端异常（如 bcrypt 库问题）被静默视为密码错误
            logger.warning("Password verification failed for user %s", user_id, exc_info=True)
            password_valid = False
        if not password_valid:
            raise ValueError("当前密码错误")
        user.password_hash = get_password_hash(payload.new_password)
        # P1-SEC-002 修复：密码修改后撤销所有 refresh token，强制重新登录
        await self._revoke_all_user_refresh_tokens(user_id)
        await self.db.commit()

    async def request_password_reset(self, email: str) -> None:
        # PII 加密：使用 email_hash 盲索引查询（密文不可直接比较）
        email_hash = compute_blind_index(email, "email")
        stmt = select(User).where(User.email_hash == email_hash)
        user = (await self.db.execute(stmt)).scalar_one_or_none()
        if user is None:
            # 为了防止邮箱枚举，即使邮箱不存在也返回成功
            return

        # 生成密码重置令牌（仅用于邮件发送，不通过 API 返回）
        reset_token = create_password_reset_token({"sub": str(user.id), "email": email})
        # 重置令牌仅通过电子邮件发送，绝不通过 API 响应返回
        # M11 修复：send_password_reset_email 已改为 async，需要 await
        await self.email_service.send_password_reset_email(email, reset_token)

    async def reset_password(self, payload: ResetPasswordRequest) -> None:
        from app.core.security import decode_token

        try:
            token_data = decode_token(payload.reset_token)
            if token_data.get("type") != "password_reset":
                raise ValueError("无效的重置令牌类型")
            sub = token_data.get("sub")
            if sub is None:
                raise ValueError("重置令牌缺少主体信息")
            user_id = int(sub)
        except (PyJWTError, ValueError, TypeError) as exc:
            raise ValueError("无效或已过期的重置令牌") from exc

        user = await self.db.get(User, user_id)
        if user is None or user.email != payload.email:
            raise ValueError("用户信息不匹配")
        user.password_hash = get_password_hash(payload.new_password)
        # P1-SEC-003 修复：密码重置后撤销所有 refresh token，防止旧 token 继续使用
        await self._revoke_all_user_refresh_tokens(user_id)
        await self.db.commit()

    async def logout(self, user_id: int, refresh_token: str | None = None) -> dict:
        """撤销用户的refresh token会话。如果提供refresh_token，只撤销该token；
        否则撤销该用户所有未过期的refresh token。"""
        from app.core.security import decode_token

        revoked_count = 0

        if refresh_token:
            try:
                token_data = decode_token(refresh_token)
                if token_data.get("type") != "refresh":
                    raise ValueError("无效的Refresh Token类型")
                jti = token_data.get("jti")
                if not jti:
                    raise ValueError("Refresh Token缺少必要信息")

                stmt = select(RefreshTokenSession).where(
                    RefreshTokenSession.jti == jti,
                    RefreshTokenSession.user_id == user_id,
                )
                token_session = (await self.db.execute(stmt)).scalar_one_or_none()
                if token_session is None:
                    raise ValueError("Refresh Token未登记或已失效")
                if token_session.revoked_at is None:
                    token_session.revoked_at = datetime.now(timezone.utc)
                revoked_count = 1
            except (PyJWTError, ValueError, TypeError) as exc:
                raise ValueError("无效或已过期的Refresh Token") from exc
        else:
            revoked_count = await self._revoke_all_user_refresh_tokens(user_id)

        await self.db.commit()
        return {"revoked_count": revoked_count}

    async def _revoke_all_user_refresh_tokens(self, user_id: int) -> int:
        """撤销指定用户所有未过期的 refresh token 会话。

        用于密码变更/重置后强制所有设备重新登录，防止旧 token 继续使用。
        注意：调用方负责 commit。
        """
        stmt = select(RefreshTokenSession).where(
            RefreshTokenSession.user_id == user_id,
            RefreshTokenSession.revoked_at.is_(None),
        )
        sessions = (await self.db.execute(stmt)).scalars().all()
        now = datetime.now(timezone.utc)
        for session in sessions:
            session.revoked_at = now
        return len(sessions)

    async def update_profile(self, user_id: int, payload: UpdateProfileRequest) -> dict:
        user = await self.db.get(User, user_id)
        if user is None:
            raise ValueError("用户不存在")

        # 先完成所有冲突检查（email 唯一性），再创建/修改 session 中的对象，
        # 避免冲突抛异常时 profile 已入 session 造成脏数据
        new_email_hash = None
        if payload.email is not None:
            # PII 加密：使用 email_hash 盲索引检查唯一性
            new_email_hash = compute_blind_index(payload.email, "email")
            stmt = select(User).where(User.email_hash == new_email_hash, User.id != user_id)
            existing = (await self.db.execute(stmt)).scalar_one_or_none()
            if existing is not None:
                raise ValueError("邮箱已存在")

        stmt = select(UserProfile).where(UserProfile.user_id == user_id)
        profile = (await self.db.execute(stmt)).scalar_one_or_none()

        if payload.nickname is not None:
            if profile:
                profile.nickname = payload.nickname
            else:
                profile = UserProfile(user_id=user_id, nickname=payload.nickname)
                self.db.add(profile)

        if payload.email is not None:
            user.email = payload.email
            user.email_hash = new_email_hash

        await self.db.commit()

        return {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "nickname": profile.nickname if profile else payload.nickname,
            "email": user.email,
        }
