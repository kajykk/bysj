"""Tests for app/core/security module."""

from __future__ import annotations

import pytest

from app.core.security import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)


class TestSecurity:
    """Test security utilities."""

    def test_get_password_hash(self):
        """TC-COV-CORE-033: get_password_hash generates hash."""
        hashed = get_password_hash("password123")
        assert hashed != "password123"
        assert len(hashed) > 0

    def test_verify_password_correct(self):
        """TC-COV-CORE-034: verify_password with correct password."""
        hashed = get_password_hash("password123")
        assert verify_password("password123", hashed) is True

    def test_verify_password_incorrect(self):
        """TC-COV-CORE-035: verify_password with incorrect password."""
        hashed = get_password_hash("password123")
        assert verify_password("wrongpassword", hashed) is False

    def test_verify_password_invalid_hash(self):
        """TC-COV-CORE-036: verify_password with invalid hash returns False."""
        assert verify_password("password", "invalid_hash") is False

    def test_verify_password_long_password(self):
        """TC-COV-CORE-037: get_password_hash rejects passwords exceeding 72 bytes."""
        long_password = "a" * 100
        with pytest.raises(ValueError):
            get_password_hash(long_password)

        # 72-byte password should still hash and verify correctly
        max_password = "a" * 72
        hashed = get_password_hash(max_password)
        assert verify_password(max_password, hashed) is True

    def test_create_access_token(self):
        """TC-COV-CORE-038: create_access_token generates valid token."""
        token = create_access_token({"sub": "1", "role": "user"})
        assert len(token) > 0
        decoded = decode_token(token)
        assert decoded["sub"] == "1"
        assert decoded["role"] == "user"
        assert decoded["type"] == "access"
        assert "jti" in decoded

    def test_create_refresh_token(self):
        """TC-COV-CORE-039: create_refresh_token generates valid token."""
        token = create_refresh_token({"sub": "1", "role": "user"})
        assert len(token) > 0
        decoded = decode_token(token)
        assert decoded["sub"] == "1"
        assert decoded["type"] == "refresh"
        assert "jti" in decoded

    def test_create_refresh_token_with_jti(self):
        """TC-COV-CORE-040: create_refresh_token with custom jti."""
        token = create_refresh_token({"sub": "1"}, jti="custom-jti")
        decoded = decode_token(token)
        assert decoded["jti"] == "custom-jti"

    def test_create_password_reset_token(self):
        """TC-COV-CORE-041: create_password_reset_token generates valid token."""
        token = create_password_reset_token({"sub": "1", "email": "test@test.com"})
        assert len(token) > 0
        decoded = decode_token(token)
        assert decoded["sub"] == "1"
        assert decoded["email"] == "test@test.com"
        assert decoded["type"] == "password_reset"

    def test_decode_token_invalid(self):
        """TC-COV-CORE-042: decode_token with invalid token raises ValueError."""
        with pytest.raises(ValueError, match="Invalid token"):
            decode_token("invalid.token.here")

    def test_create_access_token_with_existing_type(self):
        """TC-COV-CORE-043: create_access_token preserves existing type."""
        token = create_access_token({"sub": "1", "type": "custom"})
        decoded = decode_token(token)
        assert decoded["type"] == "custom"
