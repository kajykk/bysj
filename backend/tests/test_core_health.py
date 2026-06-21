"""Tests for app/core/health module."""

from __future__ import annotations

import pytest

from app.core.health import (
    HealthSnapshot,
    get_health_cache_ttl_seconds,
)


class TestHealthSnapshot:
    """Test HealthSnapshot dataclass."""

    def test_default_creation(self):
        """TC-COV-CORE-044: HealthSnapshot default values."""
        snapshot = HealthSnapshot()
        assert snapshot.database is None
        assert snapshot.redis is None
        assert snapshot.celery_worker is None
        assert snapshot.collected_at == 0.0

    def test_custom_creation(self):
        """TC-COV-CORE-045: HealthSnapshot with custom values."""
        snapshot = HealthSnapshot(database=True, redis=False, celery_worker=True, collected_at=1.0)
        assert snapshot.database is True
        assert snapshot.redis is False
        assert snapshot.celery_worker is True
        assert snapshot.collected_at == 1.0


class TestHealthCache:
    """Test health cache utilities."""

    def test_get_health_cache_ttl(self):
        """TC-COV-CORE-046: get_health_cache_ttl_seconds returns positive value."""
        ttl = get_health_cache_ttl_seconds()
        assert ttl > 0
