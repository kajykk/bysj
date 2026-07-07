"""SEC-P1-001 测试: JWT role 实时校验 + access token blocklist (撤销机制).

测试覆盖:
1. token_blocklist.py - is_token_revoked / revoke_token
2. deps.py get_current_user - role 对比 + blocklist 检查
3. auth_service.py logout - access_token 撤销
4. 源码静态扫描 - 确认关键设计点已实现
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.token_blocklist import (
    _make_key,
    is_token_revoked,
    revoke_token,
)


class TestMakeKey:
    """测试 blocklist key 构造."""

    def test_make_key_format(self):
        """TC-SEC001-001: key 格式为 token_blocklist:{jti}."""
        key = _make_key("abc123")
        assert key == "token_blocklist:abc123"

    def test_make_key_with_empty_jti(self):
        """TC-SEC001-002: 空 jti 返回 token_blocklist:."""
        assert _make_key("") == "token_blocklist:"


class TestIsTokenRevoked:
    """测试 is_token_revoked."""

    @pytest.mark.asyncio
    async def test_returns_false_for_empty_jti(self):
        """TC-SEC001-003: 空 jti 返回 False."""
        assert await is_token_revoked("") is False

    @pytest.mark.asyncio
    async def test_returns_false_for_none_jti(self):
        """TC-SEC001-004: None jti 返回 False."""
        assert await is_token_revoked(None) is False  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_returns_false_when_not_in_blocklist(self):
        """TC-SEC001-005: jti 不在 blocklist 中返回 False."""
        with patch(
            "app.core.token_blocklist.cache_get", new=AsyncMock(return_value=None)
        ):
            result = await is_token_revoked("nonexistent_jti")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_when_in_blocklist(self):
        """TC-SEC001-006: jti 在 blocklist 中返回 True."""
        with patch(
            "app.core.token_blocklist.cache_get",
            new=AsyncMock(return_value={"revoked": True}),
        ):
            result = await is_token_revoked("revoked_jti")
        assert result is True

    @pytest.mark.asyncio
    async def test_calls_cache_get_with_correct_key(self):
        """TC-SEC001-007: 调用 cache_get 时使用正确的 key."""
        mock_cache_get = AsyncMock(return_value=None)
        with patch("app.core.token_blocklist.cache_get", new=mock_cache_get):
            await is_token_revoked("test_jti")
        mock_cache_get.assert_called_once_with("token_blocklist:test_jti")


class TestRevokeToken:
    """测试 revoke_token."""

    @pytest.mark.asyncio
    async def test_returns_false_for_empty_jti(self):
        """TC-SEC001-008: 空 jti 返回 False."""
        assert await revoke_token("", ttl=3600) is False

    @pytest.mark.asyncio
    async def test_returns_false_for_non_positive_ttl(self):
        """TC-SEC001-009: ttl <= 0 返回 False."""
        assert await revoke_token("jti123", ttl=0) is False
        assert await revoke_token("jti123", ttl=-1) is False

    @pytest.mark.asyncio
    async def test_returns_true_on_success(self):
        """TC-SEC001-010: 成功撤销返回 True."""
        mock_cache_set = AsyncMock(return_value=True)
        with patch("app.core.token_blocklist.cache_set", new=mock_cache_set):
            result = await revoke_token("jti123", ttl=3600)
        assert result is True
        mock_cache_set.assert_called_once_with(
            "token_blocklist:jti123",
            {"revoked": True},
            ttl=3600,
        )

    @pytest.mark.asyncio
    async def test_returns_false_on_cache_set_failure(self):
        """TC-SEC001-011: cache_set 失败返回 False."""
        with patch(
            "app.core.token_blocklist.cache_set", new=AsyncMock(return_value=False)
        ):
            result = await revoke_token("jti123", ttl=3600)
        assert result is False


class TestGetCurrentUserRoleCheck:
    """测试 deps.py get_current_user 的 role 对比逻辑."""

    @pytest.mark.asyncio
    async def test_rejects_when_role_mismatch(self):
        """TC-SEC001-012: JWT role 与 DB role 不一致时拒绝."""
        from app.core.deps import get_current_user

        # JWT payload: role=admin
        payload = {
            "sub": "1",
            "role": "admin",
            "type": "access",
            "jti": "test_jti_001",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }

        # Mock User: role=user (与 JWT 不一致)
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.status = "active"
        mock_user.role = "user"

        mock_request = MagicMock()
        mock_db = MagicMock()
        mock_db.get = AsyncMock(return_value=mock_user)

        with (
            patch("app.core.deps.decode_token", return_value=payload),
            patch(
                "app.core.token_blocklist.is_token_revoked",
                new=AsyncMock(return_value=False),
            ),
        ):
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(
                    request=mock_request, token="fake_token", db=mock_db
                )
            assert exc_info.value.status_code == 401
            assert "角色不匹配" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_accepts_when_role_matches(self):
        """TC-SEC001-013: JWT role 与 DB role 一致时通过."""
        from app.core.deps import get_current_user

        payload = {
            "sub": "1",
            "role": "admin",
            "type": "access",
            "jti": "test_jti_002",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }

        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.status = "active"
        mock_user.role = "admin"

        mock_request = MagicMock()
        mock_db = MagicMock()
        mock_db.get = AsyncMock(return_value=mock_user)

        with (
            patch("app.core.deps.decode_token", return_value=payload),
            patch(
                "app.core.token_blocklist.is_token_revoked",
                new=AsyncMock(return_value=False),
            ),
        ):
            user = await get_current_user(
                request=mock_request, token="fake_token", db=mock_db
            )
        assert user is mock_user

    @pytest.mark.asyncio
    async def test_accepts_when_token_has_no_role(self):
        """TC-SEC001-014: JWT 无 role 声明时通过 (向后兼容旧 token)."""
        from app.core.deps import get_current_user

        payload = {
            "sub": "1",
            "type": "access",
            "jti": "test_jti_003",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }

        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.status = "active"
        mock_user.role = "user"

        mock_request = MagicMock()
        mock_db = MagicMock()
        mock_db.get = AsyncMock(return_value=mock_user)

        with (
            patch("app.core.deps.decode_token", return_value=payload),
            patch(
                "app.core.token_blocklist.is_token_revoked",
                new=AsyncMock(return_value=False),
            ),
        ):
            user = await get_current_user(
                request=mock_request, token="fake_token", db=mock_db
            )
        assert user is mock_user


class TestGetCurrentUserBlocklistCheck:
    """测试 deps.py get_current_user 的 blocklist 检查逻辑."""

    @pytest.mark.asyncio
    async def test_rejects_revoked_token(self):
        """TC-SEC001-015: jti 在 blocklist 中时拒绝."""
        from app.core.deps import get_current_user

        payload = {
            "sub": "1",
            "role": "user",
            "type": "access",
            "jti": "revoked_jti_001",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }

        mock_request = MagicMock()
        mock_db = MagicMock()

        with (
            patch("app.core.deps.decode_token", return_value=payload),
            patch(
                "app.core.token_blocklist.is_token_revoked",
                new=AsyncMock(return_value=True),
            ),
        ):
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(
                    request=mock_request, token="fake_token", db=mock_db
                )
            assert exc_info.value.status_code == 401
            assert "已被撤销" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_skips_blocklist_when_no_jti(self):
        """TC-SEC001-016: JWT 无 jti 时跳过 blocklist 检查 (向后兼容)."""
        from app.core.deps import get_current_user

        payload = {
            "sub": "1",
            "role": "user",
            "type": "access",
            # 无 jti
        }

        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.status = "active"
        mock_user.role = "user"

        mock_request = MagicMock()
        mock_db = MagicMock()
        mock_db.get = AsyncMock(return_value=mock_user)

        mock_is_revoked = AsyncMock(return_value=False)

        with (
            patch("app.core.deps.decode_token", return_value=payload),
            patch("app.core.token_blocklist.is_token_revoked", new=mock_is_revoked),
        ):
            user = await get_current_user(
                request=mock_request, token="fake_token", db=mock_db
            )
        assert user is mock_user
        # is_token_revoked 不应被调用 (因为 jti 为空)
        mock_is_revoked.assert_not_called()


class TestAuthServiceLogout:
    """测试 auth_service.py logout 的 access_token 撤销."""

    @pytest.mark.asyncio
    async def test_logout_revokes_access_token(self):
        """TC-SEC001-017: logout 时撤销 access_token (jti 加入 blocklist)."""
        from app.services.auth_service import AuthService

        mock_db = MagicMock()
        mock_db.commit = AsyncMock(return_value=None)
        service = AuthService(mock_db)

        # Mock revoke_token
        mock_revoke = AsyncMock(return_value=True)
        with patch("app.core.token_blocklist.revoke_token", new=mock_revoke):
            # 不传 refresh_token, 走 _revoke_all_user_refresh_tokens 路径
            with patch.object(
                service,
                "_revoke_all_user_refresh_tokens",
                new=AsyncMock(return_value=0),
            ):
                result = await service.logout(
                    user_id=1,
                    refresh_token=None,
                    access_token_jti="test_jti_123",
                    access_token_exp=int(
                        (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()
                    ),
                )

        # 验证 revoke_token 被调用
        mock_revoke.assert_called_once()
        call_args = mock_revoke.call_args
        assert call_args.args[0] == "test_jti_123"
        assert call_args.kwargs["ttl"] > 0
        assert result["revoked_count"] == 0

    @pytest.mark.asyncio
    async def test_logout_skips_access_token_revocation_without_jti(self):
        """TC-SEC001-018: 无 jti 时跳过 access_token 撤销."""
        from app.services.auth_service import AuthService

        mock_db = MagicMock()
        mock_db.commit = AsyncMock(return_value=None)
        service = AuthService(mock_db)

        mock_revoke = AsyncMock(return_value=True)
        with patch("app.core.token_blocklist.revoke_token", new=mock_revoke):
            with patch.object(
                service,
                "_revoke_all_user_refresh_tokens",
                new=AsyncMock(return_value=0),
            ):
                await service.logout(
                    user_id=1,
                    refresh_token=None,
                    access_token_jti=None,
                    access_token_exp=None,
                )

        # revoke_token 不应被调用
        mock_revoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_logout_ttl_is_remaining_seconds(self):
        """TC-SEC001-019: TTL 为 token 剩余有效期 (非负)."""
        from app.services.auth_service import AuthService

        mock_db = MagicMock()
        mock_db.commit = AsyncMock(return_value=None)
        service = AuthService(mock_db)

        # exp 设置为 30s 后
        exp_time = int((datetime.now(timezone.utc) + timedelta(seconds=30)).timestamp())

        mock_revoke = AsyncMock(return_value=True)
        with patch("app.core.token_blocklist.revoke_token", new=mock_revoke):
            with patch.object(
                service,
                "_revoke_all_user_refresh_tokens",
                new=AsyncMock(return_value=0),
            ):
                await service.logout(
                    user_id=1,
                    refresh_token=None,
                    access_token_jti="jti_30s",
                    access_token_exp=exp_time,
                )

        call_args = mock_revoke.call_args
        ttl = call_args.kwargs["ttl"]
        # TTL 应该接近 30s (允许 ±5s 误差)
        assert 25 <= ttl <= 30

    @pytest.mark.asyncio
    async def test_logout_ttl_minimum_1_when_already_expired(self):
        """TC-SEC001-020: token 已过期时 TTL 最小为 1."""
        from app.services.auth_service import AuthService

        mock_db = MagicMock()
        mock_db.commit = AsyncMock(return_value=None)
        service = AuthService(mock_db)

        # exp 设置为 1 小时前 (已过期)
        exp_time = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())

        mock_revoke = AsyncMock(return_value=True)
        with patch("app.core.token_blocklist.revoke_token", new=mock_revoke):
            with patch.object(
                service,
                "_revoke_all_user_refresh_tokens",
                new=AsyncMock(return_value=0),
            ):
                await service.logout(
                    user_id=1,
                    refresh_token=None,
                    access_token_jti="jti_expired",
                    access_token_exp=exp_time,
                )

        call_args = mock_revoke.call_args
        ttl = call_args.kwargs["ttl"]
        assert ttl == 1  # max(1, negative) = 1


class TestSourceStructure:
    """源码静态扫描 - 确认关键设计点已实现."""

    def test_token_blocklist_module_exists(self):
        """TC-SEC001-021: token_blocklist.py 模块存在且可导入."""
        from app.core import token_blocklist

        assert hasattr(token_blocklist, "is_token_revoked")
        assert hasattr(token_blocklist, "revoke_token")

    def test_deps_imports_token_blocklist(self):
        """TC-SEC001-022: deps.py 必须导入并调用 is_token_revoked."""
        from app.core import deps

        source = inspect.getsource(deps.get_current_user)
        assert "is_token_revoked" in source
        assert "token_blocklist" in source

    def test_deps_checks_role_mismatch(self):
        """TC-SEC001-023: deps.py 必须校验 JWT role 与 DB role 一致."""
        from app.core import deps

        source = inspect.getsource(deps.get_current_user)
        assert "role" in source
        assert "不匹配" in source or "mismatch" in source.lower()

    def test_auth_service_logout_revokes_access_token(self):
        """TC-SEC001-024: auth_service.logout 必须撤销 access_token."""
        from app.services import auth_service

        source = inspect.getsource(auth_service.AuthService.logout)
        assert "access_token_jti" in source
        assert "revoke_token" in source

    def test_auth_endpoint_passes_jti_to_logout(self):
        """TC-SEC001-025: auth.py logout 端点必须传递 jti 和 exp 给 service."""
        from app.api.v1 import auth

        source = inspect.getsource(auth.logout)
        assert "access_token_jti" in source
        assert "access_token_exp" in source
        assert "token_payload" in source

    def test_blocklist_uses_cache_get_set(self):
        """TC-SEC001-026: blocklist 必须复用 cache_get/cache_set."""
        from app.core import token_blocklist

        source_is = inspect.getsource(token_blocklist.is_token_revoked)
        source_revoke = inspect.getsource(token_blocklist.revoke_token)
        assert "cache_get" in source_is
        assert "cache_set" in source_revoke
