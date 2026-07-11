"""Tests for app/core/config.py.

TC-COV-CONFIG-001 ~ TC-COV-CONFIG-014
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure backend is on path
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class TestSettingsDefaults:
    """Test Settings class initialization with default values."""

    def test_default_app_name(self):
        """TC-COV-CONFIG-001: Default app_name is correct."""
        from app.core.config import Settings

        settings = Settings()
        assert settings.app_name == "Depression Warning System"

    def test_default_app_version(self):
        """TC-COV-CONFIG-002: Default app_version is correct."""
        from app.core.config import Settings

        settings = Settings()
        assert settings.app_version == "3.1.0"

    def test_default_app_env(self):
        """TC-COV-CONFIG-003: Default app_env is development."""
        from app.core.config import Settings

        settings = Settings()
        assert settings.app_env == "development"

    def test_default_database_url(self, monkeypatch):
        """TC-COV-CONFIG-004: Default database_url is SQLite."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        from app.core.config import Settings

        settings = Settings()
        assert settings.database_url.startswith("sqlite")

    def test_default_redis_url(self):
        """TC-COV-CONFIG-005: Default redis_url is correct."""
        from app.core.config import Settings

        settings = Settings()
        assert settings.redis_url == "redis://localhost:6379/0"

    def test_default_jwt_algorithm(self):
        """TC-COV-CONFIG-006: Default jwt_algorithm is HS256."""
        from app.core.config import Settings

        settings = Settings()
        assert settings.jwt_algorithm == "HS256"

    def test_default_token_expiry(self):
        """TC-COV-CONFIG-007: Default token expiry values."""
        from app.core.config import Settings

        settings = Settings()
        assert settings.access_token_expire_minutes == 120
        assert settings.refresh_token_expire_days == 7
        assert settings.password_reset_token_expire_minutes == 30

    def test_default_cors_origins(self):
        """TC-COV-CONFIG-008: Default CORS origins and property."""
        from app.core.config import Settings

        settings = Settings()
        # CORS origins may be overridden by .env file; verify property works
        assert isinstance(settings.cors_origins_list, list)
        assert all(isinstance(o, str) for o in settings.cors_origins_list)

    def test_cors_origins_list_empty_entries(self):
        """TC-COV-CONFIG-009: cors_origins_list filters empty entries."""
        from app.core.config import Settings

        settings = Settings()
        settings.cors_allowed_origins = "http://a.com,, http://b.com ,"
        assert settings.cors_origins_list == ["http://a.com", "http://b.com"]


class TestSettingsEnvOverride:
    """Test environment variable overrides."""

    @patch.dict(os.environ, {"JWT_SECRET_KEY": "my-secret-key"}, clear=False)
    def test_jwt_secret_key_override(self):
        """TC-COV-CONFIG-010: JWT_SECRET_KEY from environment."""
        from app.core.config import Settings

        settings = Settings()
        assert settings.jwt_secret_key == "my-secret-key"

    @patch.dict(
        os.environ,
        {"DATABASE_URL": "postgresql+asyncpg://user:pass@db/db"},
        clear=False,
    )
    def test_database_url_override(self):
        """TC-COV-CONFIG-011: DATABASE_URL from environment."""
        from app.core.config import Settings

        settings = Settings()
        assert settings.database_url == "postgresql+asyncpg://user:pass@db/db"

    @patch.dict(
        os.environ,
        {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql+asyncpg://user:pass@db/prod",
            "PASSWORD_RESET_BASE_URL": "https://example.com/reset-password",
        },
        clear=False,
    )
    def test_app_env_override(self):
        """TC-COV-CONFIG-012: APP_ENV from environment."""
        from app.core.config import Settings

        # Phase 1 安全加固：生产环境必须显式设置非 SQLite 的 DATABASE_URL
        # SEC-P1-002 修复：生产环境必须使用 HTTPS 的 PASSWORD_RESET_BASE_URL
        settings = Settings()
        assert settings.app_env == "production"


class TestSettingsValidation:
    """Test Settings validation logic."""

    def test_production_sqlite_override(self):
        """TC-COV-CONFIG-013: Production env rejects SQLite DATABASE_URL."""
        from app.core.config import Settings

        # Phase 1 安全加固：生产环境直接拒绝 SQLite，不再自动转为 PostgreSQL
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "production",
                "JWT_SECRET_KEY": "a-secure-key-for-testing-only-not-insecure",
                "DATABASE_URL": "sqlite+aiosqlite:///./test.db",
            },
            clear=False,
        ):
            with pytest.raises(
                ValueError, match="DATABASE_URL must be explicitly set in production"
            ):
                Settings()

    def test_production_secure_jwt_required(self):
        """TC-COV-CONFIG-014: Production requires secure JWT key."""
        from app.core.config import Settings

        with patch.dict(
            os.environ,
            {
                "APP_ENV": "production",
                "JWT_SECRET_KEY": "change-this-to-a-random-secret-key",
                "DATABASE_URL": "postgresql+asyncpg://user:pass@db/prod",
            },
            clear=False,
        ):
            with pytest.raises(ValueError) as exc_info:
                Settings()
            assert "JWT_SECRET_KEY is required and must be secure" in str(
                exc_info.value
            )


class TestDependencyDetection:
    """Test runtime dependency detection helpers."""

    def test_check_pytorch_returns_bool(self):
        """TC-COV-CONFIG-015: _check_pytorch returns bool."""
        from app.core.config import _check_pytorch

        result = _check_pytorch()
        assert isinstance(result, bool)

    def test_check_transformers_returns_bool(self):
        """TC-COV-CONFIG-016: _check_transformers returns bool."""
        from app.core.config import _check_transformers

        result = _check_transformers()
        assert isinstance(result, bool)

    def test_get_sklearn_version_returns_string_or_none(self):
        """TC-COV-CONFIG-017: _get_sklearn_version returns str or None."""
        from app.core.config import _get_sklearn_version

        result = _get_sklearn_version()
        assert result is None or isinstance(result, str)


class TestInsecureKeys:
    """Test insecure key detection."""

    def test_insecure_keys_set(self):
        """TC-COV-CONFIG-018: Insecure keys are defined."""
        from app.core.config import _INSECURE_KEYS

        assert "" in _INSECURE_KEYS
        assert "change-this-to-a-random-secret-key" in _INSECURE_KEYS
        assert "depression-warning-system-secret-key-2024" in _INSECURE_KEYS
