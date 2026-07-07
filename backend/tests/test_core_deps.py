"""Tests for app/core/deps.py.

TC-COV-DEPS-001 ~ TC-COV-DEPS-014
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException, Request

from app.core.deps import (
    PERMISSION_MATRIX,
    ROLE_HIERARCHY,
    _role_for_request,
    require_permission,
    require_role,
)
from app.models.user import User


def _mock_user(role: str, user_id: int = 1) -> User:
    return User(
        id=user_id,
        username=f"{role}_tester",
        email=f"{role}@test.com",
        role=role,
        status="active",
        password_hash="x",
    )


def _mock_request_with_token(token: str | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
    }
    if token:
        scope["headers"] = [(b"authorization", f"Bearer {token}".encode())]
    return Request(scope)


class TestRoleHierarchy:
    """Test ROLE_HIERARCHY constants."""

    def test_admin_inherits_all(self):
        """TC-COV-DEPS-001: admin role includes all roles."""
        assert ROLE_HIERARCHY["admin"] == {"admin", "counselor", "user"}

    def test_counselor_inherits_self(self):
        """TC-COV-DEPS-002: counselor role includes only counselor."""
        assert ROLE_HIERARCHY["counselor"] == {"counselor"}

    def test_user_inherits_self(self):
        """TC-COV-DEPS-003: user role includes only user."""
        assert ROLE_HIERARCHY["user"] == {"user"}


class TestPermissionMatrix:
    """Test PERMISSION_MATRIX constants."""

    def test_user_permissions(self):
        """TC-COV-DEPS-004: user role has expected permissions."""
        assert "user.assessment.read" in PERMISSION_MATRIX["user"]
        assert "user.dashboard.view" in PERMISSION_MATRIX["user"]

    def test_counselor_permissions(self):
        """TC-COV-DEPS-005: counselor role has expected permissions."""
        assert "counselor.warning.handle" in PERMISSION_MATRIX["counselor"]
        assert "counselor.user.consultation.view" in PERMISSION_MATRIX["counselor"]

    def test_admin_permissions(self):
        """TC-COV-DEPS-006: admin role has expected permissions."""
        assert "admin.operation_log.view" in PERMISSION_MATRIX["admin"]
        assert "admin.template.manage" in PERMISSION_MATRIX["admin"]


class TestRequireRole:
    """Test require_role dependency."""

    @pytest.mark.asyncio
    async def test_admin_access_user_resource(self):
        """TC-COV-DEPS-007: admin can access user-only resource."""
        checker = require_role("user")
        user = _mock_user("admin")
        request = _mock_request_with_token()
        result = await checker(request, user)
        assert result == user

    @pytest.mark.asyncio
    async def test_user_access_user_resource(self):
        """TC-COV-DEPS-008: user can access user resource."""
        checker = require_role("user")
        user = _mock_user("user")
        request = _mock_request_with_token()
        result = await checker(request, user)
        assert result == user

    @pytest.mark.asyncio
    async def test_user_access_admin_resource_forbidden(self):
        """TC-COV-DEPS-009: user cannot access admin resource."""
        checker = require_role("admin")
        user = _mock_user("user")
        request = _mock_request_with_token()
        with pytest.raises(HTTPException) as exc_info:
            await checker(request, user)
        assert exc_info.value.status_code == 403
        assert "权限不足" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_counselor_access_counselor_resource(self):
        """TC-COV-DEPS-010: counselor can access counselor resource."""
        checker = require_role("counselor")
        user = _mock_user("counselor")
        request = _mock_request_with_token()
        result = await checker(request, user)
        assert result == user

    @pytest.mark.asyncio
    async def test_multiple_roles_allowed(self):
        """TC-COV-DEPS-011: user matches one of multiple allowed roles."""
        checker = require_role("admin", "counselor")
        user = _mock_user("counselor")
        request = _mock_request_with_token()
        result = await checker(request, user)
        assert result == user

    @pytest.mark.asyncio
    async def test_token_role_mismatch_raises_403(self):
        """TC-COV-DEPS-012: token role same as user role but not allowed raises 403."""
        from app.core.security import create_access_token

        token = create_access_token({"sub": "1", "role": "user"})
        checker = require_role("admin")
        user = _mock_user("user")
        request = _mock_request_with_token(token)
        with pytest.raises(HTTPException) as exc_info:
            await checker(request, user)
        assert exc_info.value.status_code == 403


class TestRequirePermission:
    """Test require_permission dependency."""

    @pytest.mark.asyncio
    async def test_user_has_permission(self):
        """TC-COV-DEPS-013: user with permission can access."""
        checker = require_permission("user.assessment.read")
        user = _mock_user("user")
        result = await checker(user)
        assert result == user

    @pytest.mark.asyncio
    async def test_user_lacks_permission(self):
        """TC-COV-DEPS-014: user without permission is forbidden."""
        checker = require_permission("admin.operation_log.view")
        user = _mock_user("user")
        with pytest.raises(HTTPException) as exc_info:
            await checker(user)
        assert exc_info.value.status_code == 403
        assert "权限不足" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_admin_has_permission(self):
        """TC-COV-DEPS-015: admin with permission can access."""
        checker = require_permission("admin.operation_log.view")
        user = _mock_user("admin")
        result = await checker(user)
        assert result == user


class TestRoleForRequest:
    """Test _role_for_request helper."""

    def test_no_authorization_header(self):
        """TC-COV-DEPS-016: no authorization header returns None."""
        scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
        request = Request(scope)
        assert _role_for_request(request) is None

    def test_invalid_header_format(self):
        """TC-COV-DEPS-017: invalid header format returns None."""
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"authorization", b"Basic dXNlcjpwYXNz")],
        }
        request = Request(scope)
        assert _role_for_request(request) is None

    def test_valid_token_returns_role(self):
        """TC-COV-DEPS-018: valid token returns role from payload."""
        from app.core.security import create_access_token

        token = create_access_token({"sub": "1", "role": "admin"})
        request = _mock_request_with_token(token)
        assert _role_for_request(request) == "admin"
