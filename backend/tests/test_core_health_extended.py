"""Extended tests for app/core/health module to improve coverage."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.health import (
    HealthSnapshot,
    check_database,
    check_redis,
    check_celery_worker,
    get_health_snapshot,
    lightweight_health_snapshot,
    get_health_cache_ttl_seconds,
)


class TestCheckDatabase:
    """Test check_database function."""

    @pytest.mark.asyncio
    async def test_check_database_success(self):
        """TC-COV-001: check_database returns True on success."""
        mock_engine = MagicMock(spec=AsyncEngine)
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await check_database(mock_engine)
        assert result is True

    @pytest.mark.asyncio
    async def test_check_database_failure(self):
        """TC-COV-002: check_database returns False on exception."""
        mock_engine = MagicMock(spec=AsyncEngine)
        mock_engine.connect.side_effect = Exception("DB error")

        result = await check_database(mock_engine)
        assert result is False


class TestCheckRedis:
    """Test check_redis function."""

    @pytest.mark.asyncio
    async def test_check_redis_success(self):
        """TC-COV-003: check_redis returns True when ping succeeds."""
        with patch("app.core.health.redis.asyncio") as mock_redis:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.aclose = AsyncMock()
            mock_redis.from_url.return_value = mock_client

            result = await check_redis("redis://localhost:6379")
            assert result is True

    @pytest.mark.asyncio
    async def test_check_redis_failure(self):
        """TC-COV-004: check_redis returns False on exception."""
        with patch("app.core.health.redis.asyncio") as mock_redis:
            mock_redis.from_url.side_effect = ImportError("No redis")

            result = await check_redis("redis://localhost:6379")
            assert result is False


class TestCheckCeleryWorker:
    """Test check_celery_worker function."""

    @pytest.mark.asyncio
    async def test_check_celery_worker_success(self):
        """TC-COV-005: check_celery_worker returns True when workers exist."""
        with patch("app.core.health.celery_app") as mock_celery:
            mock_inspect = MagicMock()
            mock_inspect.stats.return_value = {"worker1": {"stats": "data"}}
            mock_celery.control.inspect.return_value = mock_inspect

            result = await check_celery_worker("redis://localhost:6379")
            assert result is True

    @pytest.mark.asyncio
    async def test_check_celery_worker_no_workers(self):
        """TC-COV-006: check_celery_worker returns False when no workers."""
        with patch("app.core.health.celery_app") as mock_celery:
            mock_inspect = MagicMock()
            mock_inspect.stats.return_value = None
            mock_celery.control.inspect.return_value = mock_inspect

            result = await check_celery_worker("redis://localhost:6379")
            assert result is False

    @pytest.mark.asyncio
    async def test_check_celery_worker_exception(self):
        """TC-COV-007: check_celery_worker returns False on exception."""
        with patch("app.core.health.celery_app") as mock_celery:
            mock_celery.control.inspect.side_effect = Exception("Celery error")

            result = await check_celery_worker("redis://localhost:6379")
            assert result is False


class TestGetHealthSnapshot:
    """Test get_health_snapshot function."""

    @pytest.mark.asyncio
    async def test_get_health_snapshot_caches_result(self):
        """TC-COV-008: get_health_snapshot caches result within TTL."""
        mock_engine = MagicMock(spec=AsyncEngine)

        with patch("app.core.health.check_database", new_callable=AsyncMock, return_value=True) as mock_db, \
             patch("app.core.health.check_redis", new_callable=AsyncMock, return_value=True) as mock_redis, \
             patch("app.core.health.check_celery_worker", new_callable=AsyncMock, return_value=True) as mock_celery:

            # First call
            result1 = await get_health_snapshot(mock_engine, "redis://localhost:6379")
            assert result1.database is True
            assert result1.redis is True
            assert result1.celery_worker is True
            assert result1.collected_at > 0

            # Second call should use cache
            result2 = await get_health_snapshot(mock_engine, "redis://localhost:6379")
            assert result2.collected_at == result1.collected_at

            # Database and redis should only be called once due to caching
            assert mock_db.call_count == 1
            assert mock_redis.call_count == 1
            assert mock_celery.call_count == 1

    @pytest.mark.asyncio
    async def test_get_health_snapshot_refresh_after_ttl(self):
        """TC-COV-009: get_health_snapshot refreshes after TTL expires."""
        mock_engine = MagicMock(spec=AsyncEngine)

        with patch("app.core.health.check_database", new_callable=AsyncMock, return_value=True), \
             patch("app.core.health.check_redis", new_callable=AsyncMock, return_value=True), \
             patch("app.core.health.check_celery_worker", new_callable=AsyncMock, return_value=True), \
             patch("app.core.health.get_health_cache_ttl_seconds", return_value=0.0):

            result1 = await get_health_snapshot(mock_engine, "redis://localhost:6379")
            await asyncio.sleep(0.01)
            result2 = await get_health_snapshot(mock_engine, "redis://localhost:6379")
            assert result2.collected_at >= result1.collected_at


class TestLightweightHealthSnapshot:
    """Test lightweight_health_snapshot function."""

    @pytest.mark.asyncio
    async def test_lightweight_health_snapshot(self):
        """TC-COV-010: lightweight_health_snapshot returns basic snapshot."""
        result = await lightweight_health_snapshot()
        assert result.database is True
        assert result.redis is None
        assert result.celery_worker is None
        assert result.collected_at > 0


class TestHealthCacheTTL:
    """Test health cache TTL."""

    def test_cache_ttl_default(self):
        """TC-COV-011: get_health_cache_ttl_seconds returns 5.0."""
        ttl = get_health_cache_ttl_seconds()
        assert ttl == 5.0
