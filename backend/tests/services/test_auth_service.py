"""Tests for AuthService."""

from __future__ import annotations

import pytest

from app.schemas.auth import (
    ChangePasswordRequest,
    RegisterRequest,
    ResetPasswordRequest,
    UpdateProfileRequest,
)
from app.services.auth_service import AuthService


class TestAuthService:
    """Test authentication service."""

    @pytest.mark.asyncio
    async def test_register_new_user(self, db_session):
        """TC-COV-AUTH-001: Register a new user successfully."""
        service = AuthService(db_session)
        payload = RegisterRequest(
            username="newuser",
            email="newuser@test.com",
            password="securepassword123",
            role="user",
        )
        result = await service.register(payload)

        assert result["username"] == "newuser"
        assert result["role"] == "user"
        assert "id" in result

    @pytest.mark.asyncio
    async def test_register_duplicate_user(self, db_session, seeded_user_id):
        """TC-COV-AUTH-002: Register with existing username raises error."""
        service = AuthService(db_session)
        payload = RegisterRequest(
            username="seed_user",
            email="unique@test.com",
            password="securepassword123",
            role="user",
        )
        with pytest.raises(ValueError, match="用户名或邮箱已存在"):
            await service.register(payload)

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, db_session, seeded_user_id):
        """TC-COV-AUTH-002b: Register with existing email raises error."""
        service = AuthService(db_session)
        payload = RegisterRequest(
            username="uniqueuser",
            email="seed@test.com",
            password="securepassword123",
            role="user",
        )
        with pytest.raises(ValueError, match="用户名或邮箱已存在"):
            await service.register(payload)

    @pytest.mark.asyncio
    async def test_login_success(self, db_session, seeded_user_id):
        """TC-COV-AUTH-003: Login with correct credentials."""
        service = AuthService(db_session)
        from app.schemas.auth import LoginRequest

        payload = LoginRequest(username="seed_user", password="testpass123")
        result = await service.login(payload)
        assert result["access_token"]
        assert result["refresh_token"]
        assert result["user"]["username"] == "seed_user"

    @pytest.mark.asyncio
    async def test_login_invalid_user(self, db_session):
        """TC-COV-AUTH-004: Login with non-existent user raises error."""
        service = AuthService(db_session)
        from app.schemas.auth import LoginRequest

        payload = LoginRequest(username="nonexistent", password="password")
        with pytest.raises(ValueError, match="用户名或密码错误"):
            await service.login(payload)

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, db_session, seeded_user_id):
        """TC-COV-AUTH-004b: Login with wrong password raises error."""
        service = AuthService(db_session)
        from app.schemas.auth import LoginRequest

        payload = LoginRequest(username="seed_user", password="wrongpassword")
        with pytest.raises(ValueError, match="用户名或密码错误"):
            await service.login(payload)

    @pytest.mark.asyncio
    async def test_login_inactive_user(self, db_session, seeded_user_id):
        """TC-COV-AUTH-004c: Login with inactive user raises error."""
        service = AuthService(db_session)
        # Update user status to inactive
        from app.models.user import User

        user = await db_session.get(User, seeded_user_id)
        user.status = "inactive"
        await db_session.commit()

        from app.schemas.auth import LoginRequest

        payload = LoginRequest(username="seed_user", password="testpass123")
        with pytest.raises(ValueError, match="用户已被禁用"):
            await service.login(payload)

    @pytest.mark.asyncio
    async def test_change_password_user_not_found(self, db_session):
        """TC-COV-AUTH-005: Change password for non-existent user raises error."""
        service = AuthService(db_session)
        payload = ChangePasswordRequest(
            old_password="oldpassword", new_password="newpassword123"
        )
        with pytest.raises(ValueError, match="用户不存在"):
            await service.change_password(9999, payload)

    @pytest.mark.asyncio
    async def test_change_password_wrong_old_password(self, db_session, seeded_user_id):
        """TC-COV-AUTH-005b: Change password with wrong old password raises error."""
        service = AuthService(db_session)
        payload = ChangePasswordRequest(
            old_password="wrongpassword", new_password="newpassword123"
        )
        with pytest.raises(ValueError, match="当前密码错误"):
            await service.change_password(1, payload)

    @pytest.mark.asyncio
    async def test_change_password_success(self, db_session, seeded_user_id):
        """TC-COV-AUTH-005c: Change password successfully."""
        service = AuthService(db_session)
        payload = ChangePasswordRequest(
            old_password="testpass123", new_password="newpassword123"
        )
        # Should not raise
        await service.change_password(1, payload)

        # Verify new password works
        from app.schemas.auth import LoginRequest

        login_payload = LoginRequest(username="seed_user", password="newpassword123")
        result = await service.login(login_payload)
        assert result["access_token"]

    @pytest.mark.asyncio
    async def test_request_password_reset_nonexistent_email(self, db_session):
        """TC-COV-AUTH-006: Password reset for non-existent email returns silently."""
        service = AuthService(db_session)
        # Should not raise
        await service.request_password_reset("nonexistent@test.com")

    @pytest.mark.asyncio
    async def test_reset_password_invalid_token(self, db_session):
        """TC-COV-AUTH-007: Reset password with invalid token raises error."""
        service = AuthService(db_session)
        payload = ResetPasswordRequest(
            reset_token="invalid.token.here.invalid.token.here.invalid.token",
            new_password="newpassword123",
            email="test@test.com",
        )
        with pytest.raises(ValueError, match="无效或已过期的重置令牌"):
            await service.reset_password(payload)

    @pytest.mark.asyncio
    async def test_reset_password_wrong_token_type(self, db_session, seeded_user_id):
        """TC-COV-AUTH-007b: Reset password with access token raises error."""
        service = AuthService(db_session)
        from app.core.security import create_access_token

        access_token = create_access_token({"sub": "1", "email": "seed@test.com"})
        payload = ResetPasswordRequest(
            reset_token=access_token,
            new_password="newpassword123",
            email="seed@test.com",
        )
        with pytest.raises(ValueError, match="无效或已过期的重置令牌"):
            await service.reset_password(payload)

    @pytest.mark.asyncio
    async def test_reset_password_email_mismatch(self, db_session, seeded_user_id):
        """TC-COV-AUTH-007c: Reset password with mismatched email raises error."""
        service = AuthService(db_session)
        from app.core.security import create_password_reset_token

        reset_token = create_password_reset_token(
            {"sub": "1", "email": "seed@test.com"}
        )
        payload = ResetPasswordRequest(
            reset_token=reset_token,
            new_password="newpassword123",
            email="wrong@test.com",
        )
        with pytest.raises(ValueError, match="用户信息不匹配"):
            await service.reset_password(payload)

    @pytest.mark.asyncio
    async def test_reset_password_success(self, db_session, seeded_user_id):
        """TC-COV-AUTH-007d: Reset password successfully."""
        service = AuthService(db_session)
        from app.core.security import create_password_reset_token

        reset_token = create_password_reset_token(
            {"sub": "1", "email": "seed@test.com"}
        )
        payload = ResetPasswordRequest(
            reset_token=reset_token, new_password="newpass123", email="seed@test.com"
        )
        # Should not raise
        await service.reset_password(payload)

        # Verify new password works
        from app.schemas.auth import LoginRequest

        login_payload = LoginRequest(username="seed_user", password="newpass123")
        result = await service.login(login_payload)
        assert result["access_token"]

    @pytest.mark.asyncio
    async def test_logout_without_token(self, db_session, seeded_user_id):
        """TC-COV-AUTH-008: Logout without token revokes all sessions."""
        service = AuthService(db_session)
        result = await service.logout(1)
        assert "revoked_count" in result

    @pytest.mark.asyncio
    async def test_logout_with_invalid_token(self, db_session, seeded_user_id):
        """TC-COV-AUTH-008b: Logout with invalid token raises error."""
        service = AuthService(db_session)
        with pytest.raises(ValueError, match="无效或已过期的Refresh Token"):
            await service.logout(1, refresh_token="invalid.token.here")

    @pytest.mark.asyncio
    async def test_logout_with_access_token(self, db_session, seeded_user_id):
        """TC-COV-AUTH-008c: Logout with access token raises error."""
        service = AuthService(db_session)
        from app.core.security import create_access_token

        access_token = create_access_token({"sub": "1"})
        with pytest.raises(ValueError, match="无效或已过期的Refresh Token"):
            await service.logout(1, refresh_token=access_token)

    @pytest.mark.asyncio
    async def test_update_profile_user_not_found(self, db_session):
        """TC-COV-AUTH-009: Update profile for non-existent user raises error."""
        service = AuthService(db_session)
        payload = UpdateProfileRequest(nickname="newnick")
        with pytest.raises(ValueError, match="用户不存在"):
            await service.update_profile(9999, payload)

    @pytest.mark.asyncio
    async def test_update_profile_success(self, db_session, seeded_user_id):
        """TC-COV-AUTH-010: Update profile successfully."""
        service = AuthService(db_session)
        payload = UpdateProfileRequest(nickname="newnickname")
        result = await service.update_profile(1, payload)
        assert result["nickname"] == "newnickname"

    @pytest.mark.asyncio
    async def test_update_profile_email_exists(self, db_session, seeded_user_id):
        """TC-COV-AUTH-010b: Update profile with existing email raises error."""
        service = AuthService(db_session)
        payload = UpdateProfileRequest(email="c@test.com")  # counselor's email
        with pytest.raises(ValueError, match="邮箱已存在"):
            await service.update_profile(1, payload)

    @pytest.mark.asyncio
    async def test_update_profile_create_new_profile(self, db_session, seeded_user_id):
        """TC-COV-AUTH-010c: Update profile creates new profile if none exists."""
        service = AuthService(db_session)
        # Delete existing profile first
        from sqlalchemy import select

        from app.models.user import UserProfile

        stmt = select(UserProfile).where(UserProfile.user_id == 1)
        profile = (await db_session.execute(stmt)).scalar_one_or_none()
        if profile:
            await db_session.delete(profile)
            await db_session.commit()

        payload = UpdateProfileRequest(nickname="brandnew")
        result = await service.update_profile(1, payload)
        assert result["nickname"] == "brandnew"
