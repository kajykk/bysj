"""Extended tests for app/core/security module."""

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


class TestPasswordHashing:
    """Test password hashing functions."""

    def test_get_password_hash(self):
        """TC-COV-028: get_password_hash returns hashed password."""
        hashed = get_password_hash("testpassword123")
        assert hashed is not None
        assert len(hashed) > 0
        assert hashed != "testpassword123"

    def test_verify_password_correct(self):
        """TC-COV-029: verify_password returns True for correct password."""
        hashed = get_password_hash("testpassword123")
        assert verify_password("testpassword123", hashed) is True

    def test_verify_password_incorrect(self):
        """TC-COV-030: verify_password returns False for incorrect password."""
        hashed = get_password_hash("testpassword123")
        assert verify_password("wrongpassword", hashed) is False

    def test_password_truncation(self):
        """TC-COV-031: Passwords exceeding 72 bytes are rejected."""
        long_password = "a" * 100
        with pytest.raises(ValueError):
            get_password_hash(long_password)

        # 72-byte password should still hash and verify correctly
        max_password = "a" * 72
        hashed = get_password_hash(max_password)
        assert verify_password(max_password, hashed) is True

    def test_verify_password_invalid_hash(self):
        """TC-COV-032: verify_password returns False for invalid hash."""
        assert verify_password("password", "invalid_hash") is False


class TestTokenCreation:
    """Test JWT token creation."""

    def test_create_access_token(self):
        """TC-COV-033: create_access_token returns valid JWT."""
        token = create_access_token({"sub": "user123", "role": "user"})
        assert token is not None
        assert len(token) > 0

        decoded = decode_token(token)
        assert decoded["sub"] == "user123"
        assert decoded["role"] == "user"
        assert decoded["type"] == "access"
        assert "jti" in decoded
        assert "exp" in decoded

    def test_create_refresh_token(self):
        """TC-COV-034: create_refresh_token returns valid JWT."""
        token = create_refresh_token({"sub": "user123"})
        assert token is not None

        decoded = decode_token(token)
        assert decoded["sub"] == "user123"
        assert decoded["type"] == "refresh"
        assert "jti" in decoded
        assert "exp" in decoded

    def test_create_refresh_token_with_jti(self):
        """TC-COV-035: create_refresh_token accepts custom jti."""
        custom_jti = "custom-jti-123"
        token = create_refresh_token({"sub": "user123"}, jti=custom_jti)
        decoded = decode_token(token)
        assert decoded["jti"] == custom_jti

    def test_create_password_reset_token(self):
        """TC-COV-036: create_password_reset_token returns valid JWT."""
        token = create_password_reset_token({"sub": "user123"})
        assert token is not None

        decoded = decode_token(token)
        assert decoded["sub"] == "user123"
        assert decoded["type"] == "password_reset"
        assert "exp" in decoded

    def test_token_type_default(self):
        """TC-COV-037: Token type defaults correctly."""
        token = create_access_token({"sub": "user123"})
        decoded = decode_token(token)
        assert decoded["type"] == "access"

    def test_token_preserves_existing_type(self):
        """TC-COV-038: Token preserves existing type if provided."""
        token = create_access_token({"sub": "user123", "type": "custom"})
        decoded = decode_token(token)
        assert decoded["type"] == "custom"


class TestDecodeToken:
    """Test token decoding."""

    def test_decode_valid_token(self):
        """TC-COV-039: decode_token returns payload for valid token."""
        original = {"sub": "user123", "role": "admin"}
        token = create_access_token(original)
        decoded = decode_token(token)
        assert decoded["sub"] == "user123"
        assert decoded["role"] == "admin"

    def test_decode_invalid_token(self):
        """TC-COV-040: decode_token raises ValueError for invalid token."""
        with pytest.raises(ValueError, match="Invalid token"):
            decode_token("invalid.token.here")

    def test_decode_expired_token(self):
        """TC-COV-041: decode_token raises ValueError for expired token."""
        from app.core.config import settings as real_settings

        original_expire = real_settings.access_token_expire_minutes
        real_settings.access_token_expire_minutes = -1
        try:
            token = create_access_token({"sub": "user123"})
        finally:
            real_settings.access_token_expire_minutes = original_expire

        with pytest.raises(ValueError, match="Invalid token"):
            decode_token(token)
