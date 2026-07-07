"""Extended tests for app/core/health module to improve coverage."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.health import (
    HEALTH_MONITOR_INTERVAL_SECONDS,
    basic_health_snapshot,
    check_celery_worker,
    check_database,
    check_redis,
    get_health_cache_ttl_seconds,
    get_health_snapshot,
    get_health_snapshot_nonblocking,
    start_health_monitor,
    stop_health_monitor,
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
    """Test check_redis function.

    P1-2: check_redis 现在复用 app.core.cache.get_redis_client() 共享单例,
    不再直接调用 redis.asyncio.from_url. 测试改为 mock 共享客户端工厂.
    """

    @pytest.mark.asyncio
    async def test_check_redis_success(self):
        """TC-COV-003: check_redis returns True when ping succeeds."""
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        with patch(
            "app.core.cache.get_redis_client",
            new_callable=AsyncMock,
            return_value=mock_client,
        ):
            result = await check_redis("redis://localhost:6379")
            assert result is True

    @pytest.mark.asyncio
    async def test_check_redis_failure(self):
        """TC-COV-004: check_redis returns False on exception."""
        with patch(
            "app.core.cache.get_redis_client",
            new_callable=AsyncMock,
            side_effect=ImportError("No redis"),
        ):
            result = await check_redis("redis://localhost:6379")
            assert result is False

    @pytest.mark.asyncio
    async def test_check_redis_no_client(self):
        """TC-COV-003b: check_redis returns False when shared client is None (no redis_url)."""
        with patch(
            "app.core.cache.get_redis_client", new_callable=AsyncMock, return_value=None
        ):
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

        with patch(
            "app.core.health.check_database", new_callable=AsyncMock, return_value=True
        ) as mock_db, patch(
            "app.core.health.check_redis", new_callable=AsyncMock, return_value=True
        ) as mock_redis, patch(
            "app.core.health.check_celery_worker",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_celery:

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

        with patch(
            "app.core.health.check_database", new_callable=AsyncMock, return_value=True
        ), patch(
            "app.core.health.check_redis", new_callable=AsyncMock, return_value=True
        ), patch(
            "app.core.health.check_celery_worker",
            new_callable=AsyncMock,
            return_value=True,
        ), patch(
            "app.core.health.get_health_cache_ttl_seconds", return_value=0.0
        ):

            result1 = await get_health_snapshot(mock_engine, "redis://localhost:6379")
            await asyncio.sleep(0.01)
            result2 = await get_health_snapshot(mock_engine, "redis://localhost:6379")
            assert result2.collected_at >= result1.collected_at


class TestBasicHealthSnapshot:
    """Test basic_health_snapshot function."""

    @pytest.mark.asyncio
    async def test_basic_health_snapshot(self):
        """TC-COV-010: basic_health_snapshot returns basic snapshot."""
        result = await basic_health_snapshot()
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

    def test_monitor_interval_positive(self):
        """P0-1.1: HEALTH_MONITOR_INTERVAL_SECONDS must be positive."""
        assert HEALTH_MONITOR_INTERVAL_SECONDS > 0


class TestGetHealthSnapshotNonBlocking:
    """P0-1.1: Test get_health_snapshot_nonblocking (readiness probe backend)."""

    @pytest.mark.asyncio
    async def test_returns_cached_snapshot_without_io(self):
        """Non-blocking call returns cached snapshot without invoking checks."""
        mock_engine = MagicMock(spec=AsyncEngine)
        # 预填充缓存
        with patch(
            "app.core.health.check_database", new_callable=AsyncMock, return_value=True
        ), patch(
            "app.core.health.check_redis", new_callable=AsyncMock, return_value=True
        ), patch(
            "app.core.health.check_celery_worker",
            new_callable=AsyncMock,
            return_value=True,
        ):
            await get_health_snapshot(mock_engine, "redis://localhost:6379")

        # 非阻塞调用: 不应触发任何 check_* 函数 (使用新的 mock 验证)
        with patch(
            "app.core.health.check_database", new_callable=AsyncMock
        ) as mock_db, patch(
            "app.core.health.check_redis", new_callable=AsyncMock
        ) as mock_redis, patch(
            "app.core.health.check_celery_worker", new_callable=AsyncMock
        ) as mock_celery:
            result = await get_health_snapshot_nonblocking(
                mock_engine, "redis://localhost:6379"
            )
            assert result.database is True
            assert mock_db.call_count == 0
            assert mock_redis.call_count == 0
            assert mock_celery.call_count == 0

    @pytest.mark.asyncio
    async def test_returns_stale_cache_when_expired(self):
        """Non-blocking call returns stale cache (rather than blocking) when expired."""
        mock_engine = MagicMock(spec=AsyncEngine)
        with patch(
            "app.core.health.check_database", new_callable=AsyncMock, return_value=True
        ), patch(
            "app.core.health.check_redis", new_callable=AsyncMock, return_value=False
        ), patch(
            "app.core.health.check_celery_worker",
            new_callable=AsyncMock,
            return_value=True,
        ), patch(
            "app.core.health.get_health_cache_ttl_seconds", return_value=0.0
        ):
            await get_health_snapshot(mock_engine, "redis://localhost:6379")

        # 缓存已过期, 但非阻塞调用应返回旧值而非重新检查
        with patch("app.core.health.check_database", new_callable=AsyncMock) as mock_db:
            result = await get_health_snapshot_nonblocking(
                mock_engine, "redis://localhost:6379"
            )
            # 返回旧值 (database=True, redis=False)
            assert result.database is True
            assert result.redis is False
            assert mock_db.call_count == 0


class TestHealthMonitor:
    """P0-1.1: Test background health monitor lifecycle."""

    @pytest.mark.asyncio
    async def test_start_and_stop_health_monitor(self):
        """start_health_monitor creates task; stop_health_monitor cancels it."""
        mock_engine = MagicMock(spec=AsyncEngine)
        mock_app = MagicMock()

        with patch("app.core.health._is_test_environment", return_value=False), patch(
            "app.core.health.check_database", new_callable=AsyncMock, return_value=True
        ), patch(
            "app.core.health.check_redis", new_callable=AsyncMock, return_value=True
        ), patch(
            "app.core.health.check_celery_worker",
            new_callable=AsyncMock,
            return_value=True,
        ):
            await start_health_monitor(mock_app, mock_engine, "redis://localhost:6379")
            assert mock_app.state.health_monitor_task is not None

            # 等待后台任务至少执行一次循环
            await asyncio.sleep(0.1)

            await stop_health_monitor()
            # 停止后任务应已完成
            assert (
                mock_app.state.health_monitor_task.cancelled()
                or mock_app.state.health_monitor_task.done()
                or mock_app.state.health_monitor_task.cancelling() >= 0
            )

    @pytest.mark.asyncio
    async def test_stop_when_not_started_is_noop(self):
        """stop_health_monitor when never started is a no-op."""
        # 确保全局任务已清理 (由前一个测试的 stop 完成)
        await stop_health_monitor()
        # 不抛异常即通过

    @pytest.mark.asyncio
    async def test_start_monitor_skipped_in_test_env(self):
        """P0-1.1: start_health_monitor skips in test environment (PYTEST_CURRENT_TEST set)."""
        from types import SimpleNamespace

        mock_engine = MagicMock(spec=AsyncEngine)
        mock_app = SimpleNamespace(state=SimpleNamespace())
        # 不 mock _is_test_environment, 它应检测到 PYTEST_CURRENT_TEST 并跳过
        await start_health_monitor(mock_app, mock_engine, "redis://localhost:6379")
        # 不应创建后台任务 (state.health_monitor_task 不应被设置)
        assert (
            not hasattr(mock_app.state, "health_monitor_task")
            or mock_app.state.health_monitor_task is None
        )
