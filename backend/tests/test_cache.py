"""v1.36: cache 工具单元测试."""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_redis_client():
    """每个测试前重置模块级共享 Redis 客户端, 避免测试间状态泄漏."""
    from app.core import cache
    old = cache._redis_client
    cache._redis_client = None
    yield
    cache._redis_client = old


class TestMakeCacheKey:
    def test_make_cache_key_stable_for_same_params(self):
        from app.core.cache import make_cache_key

        key1 = make_cache_key("trend", {"a": 1, "b": 2})
        key2 = make_cache_key("trend", {"b": 2, "a": 1})
        assert key1 == key2
        assert key1.startswith("obs:trend:")

    def test_make_cache_key_differs_for_different_params(self):
        from app.core.cache import make_cache_key

        key1 = make_cache_key("trend", {"a": 1})
        key2 = make_cache_key("trend", {"a": 2})
        assert key1 != key2

    def test_make_cache_key_differs_for_different_endpoints(self):
        from app.core.cache import make_cache_key

        key1 = make_cache_key("trend", {"a": 1})
        key2 = make_cache_key("response-time", {"a": 1})
        assert key1 != key2

    def test_make_cache_key_handles_none_params(self):
        from app.core.cache import make_cache_key

        key1 = make_cache_key("trend", None)
        key2 = make_cache_key("trend", {})
        assert key1 == key2

    def test_make_cache_key_handles_datetime_params(self):
        """datetime 等不可 JSON 序列化的对象, 应显式 raise TypeError."""
        from datetime import datetime

        import pytest

        from app.core.cache import make_cache_key

        params = {"start": datetime(2026, 6, 1, 10, 0, 0)}
        with pytest.raises(TypeError):
            make_cache_key("trend", params)

    def test_make_cache_key_handles_iso_string(self):
        """datetime 转为 ISO 字符串后, 正常使用."""
        from app.core.cache import make_cache_key

        params = {"start": "2026-06-01T10:00:00"}
        key = make_cache_key("trend", params)
        assert key.startswith("obs:trend:")

    def test_make_cache_key_collision_avoided_without_default_str(self):
        """验证两个不同 datetime 和对应字符串, 行为可区分 (无 default=str)."""
        from app.core.cache import make_cache_key

        # 字符串能正常生成 key
        key_str = make_cache_key("trend", {"t": "2026-06-01"})
        # datetime 会 raise, 不生成冲突 key
        import pytest

        with pytest.raises(TypeError):
            make_cache_key("trend", {"t": __import__("datetime").datetime(2026, 6, 1)})
        # 字符串 key 可重现
        key_str2 = make_cache_key("trend", {"t": "2026-06-01"})
        assert key_str == key_str2


class TestCacheGetMiss:
    @pytest.mark.asyncio
    async def test_cache_get_no_redis_url_returns_none(self):
        """无 redis_url 配置时, 静默返回 None."""
        from app.core import cache

        with patch.object(cache, "_get_redis_url", return_value=None):
            result = await cache.cache_get("obs:trend:abc")
            assert result is None

    @pytest.mark.asyncio
    async def test_cache_get_empty_key_returns_none(self):
        from app.core.cache import cache_get

        result = await cache_get("")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_get_redis_returns_none(self):
        """Redis 返回 None (未命中) → 透传 None."""
        from app.core import cache

        with patch.object(cache, "_get_redis_url", return_value="redis://localhost:6379/0"):
            with patch("app.core.cache.aioredis") as mock_aioredis:
                mock_client = MagicMock()
                mock_client.get = AsyncMock(return_value=None)
                mock_client.aclose = AsyncMock()
                mock_aioredis.from_url.return_value = mock_client
                result = await cache.cache_get("obs:trend:abc")
                assert result is None


class TestCacheGetHit:
    @pytest.mark.asyncio
    async def test_cache_get_hit_returns_parsed_value(self):
        """缓存命中 → 解析 JSON 返回."""
        from app.core import cache

        with patch.object(cache, "_get_redis_url", return_value="redis://localhost:6379/0"):
            with patch("app.core.cache.aioredis") as mock_aioredis:
                mock_client = MagicMock()
                mock_client.get = AsyncMock(return_value=json.dumps({"foo": "bar"}))
                mock_client.aclose = AsyncMock()
                mock_aioredis.from_url.return_value = mock_client
                result = await cache.cache_get("obs:trend:abc")
                assert result == {"foo": "bar"}

    @pytest.mark.asyncio
    async def test_cache_get_parse_failed_returns_none(self):
        """JSON 解析失败 → 返回 None (不抛错)."""
        from app.core import cache

        with patch.object(cache, "_get_redis_url", return_value="redis://localhost:6379/0"):
            with patch("app.core.cache.aioredis") as mock_aioredis:
                mock_client = MagicMock()
                mock_client.get = AsyncMock(return_value="not valid json{")
                mock_client.aclose = AsyncMock()
                mock_aioredis.from_url.return_value = mock_client
                result = await cache.cache_get("obs:trend:abc")
                assert result is None


class TestCacheGetFailure:
    @pytest.mark.asyncio
    async def test_cache_get_redis_down_returns_none(self):
        """Redis 不可用 → 返回 None (降级)."""
        from app.core import cache

        with patch.object(cache, "_get_redis_url", return_value="redis://localhost:6379/0"):
            with patch("app.core.cache.aioredis") as mock_aioredis:
                mock_aioredis.from_url.side_effect = Exception("connection refused")
                result = await cache.cache_get("obs:trend:abc")
                assert result is None

    @pytest.mark.asyncio
    async def test_cache_get_aclose_failure_does_not_propagate(self):
        """aclose 抛错时, 不影响 cache_get 正常返回值."""
        from app.core import cache

        with patch.object(cache, "_get_redis_url", return_value="redis://localhost:6379/0"):
            with patch("app.core.cache.aioredis") as mock_aioredis:
                mock_client = MagicMock()
                mock_client.get = AsyncMock(return_value=json.dumps({"foo": "bar"}))
                mock_client.aclose = AsyncMock(side_effect=Exception("aclose error"))
                mock_aioredis.from_url.return_value = mock_client
                result = await cache.cache_get("obs:trend:abc")
                # 应正常返回解析后的值, 不抛出
                assert result == {"foo": "bar"}


class TestCacheSetSuccess:
    @pytest.mark.asyncio
    async def test_cache_set_success(self):
        """成功写入 → 返回 True."""
        from app.core import cache

        with patch.object(cache, "_get_redis_url", return_value="redis://localhost:6379/0"):
            with patch("app.core.cache.aioredis") as mock_aioredis:
                mock_client = MagicMock()
                mock_client.set = AsyncMock()
                mock_client.aclose = AsyncMock()
                mock_aioredis.from_url.return_value = mock_client
                result = await cache.cache_set("obs:trend:abc", {"foo": "bar"}, ttl=300)
                assert result is True
                mock_client.set.assert_called_once()
                # 验证写入内容
                args, kwargs = mock_client.set.call_args
                assert args[0] == "obs:trend:abc"
                assert json.loads(args[1]) == {"foo": "bar"}
                assert kwargs.get("ex") == 300


class TestCacheSetFailure:
    @pytest.mark.asyncio
    async def test_cache_set_no_redis_url_returns_false(self):
        from app.core import cache

        with patch.object(cache, "_get_redis_url", return_value=None):
            result = await cache.cache_set("obs:trend:abc", {"foo": "bar"})
            assert result is False

    @pytest.mark.asyncio
    async def test_cache_set_empty_key_returns_false(self):
        from app.core.cache import cache_set

        result = await cache_set("", {"foo": "bar"})
        assert result is False

    @pytest.mark.asyncio
    async def test_cache_set_none_value_returns_false(self):
        from app.core.cache import cache_set

        result = await cache_set("obs:trend:abc", None)
        assert result is False

    @pytest.mark.asyncio
    async def test_cache_set_redis_down_returns_false(self):
        """Redis 不可用 → 返回 False (不抛错)."""
        from app.core import cache

        with patch.object(cache, "_get_redis_url", return_value="redis://localhost:6379/0"):
            with patch("app.core.cache.aioredis") as mock_aioredis:
                mock_aioredis.from_url.side_effect = Exception("connection refused")
                result = await cache.cache_set("obs:trend:abc", {"foo": "bar"})
                assert result is False

    @pytest.mark.asyncio
    async def test_cache_set_ttl_zero_uses_default(self):
        """ttl <= 0 时使用默认 300s."""
        from app.core import cache

        with patch.object(cache, "_get_redis_url", return_value="redis://localhost:6379/0"):
            with patch("app.core.cache.aioredis") as mock_aioredis:
                mock_client = MagicMock()
                mock_client.set = AsyncMock()
                mock_client.aclose = AsyncMock()
                mock_aioredis.from_url.return_value = mock_client
                await cache.cache_set("obs:trend:abc", {"foo": "bar"}, ttl=0)
                _, kwargs = mock_client.set.call_args
                assert kwargs.get("ex") == 300


class TestGetRedisUrl:
    def test_get_redis_url_from_settings(self):
        """从 settings.redis_url 读取."""
        # Patch settings BEFORE importing cache
        mock_settings = MagicMock(redis_url="redis://test:6379/0")
        with patch("app.core.config.settings", mock_settings):
            # Force re-import of cache
            import importlib
            from app.core import cache
            importlib.reload(cache)
            try:
                result = cache._get_redis_url()
                assert result == "redis://test:6379/0"
            finally:
                importlib.reload(cache)

    def test_get_redis_url_settings_empty_returns_none(self):
        """settings.redis_url 为空时返回 None."""
        mock_settings = MagicMock(redis_url="")
        with patch("app.core.config.settings", mock_settings):
            import importlib
            from app.core import cache
            importlib.reload(cache)
            try:
                with patch.dict(os.environ, {}, clear=True):
                    # 清理 REDIS_URL 环境变量
                    os.environ.pop("REDIS_URL", None)
                    result = cache._get_redis_url()
                    assert result is None
            finally:
                importlib.reload(cache)

    def test_get_redis_url_fallback_to_env(self):
        """环境变量兜底 (settings 不可用时, 走 REDIS_URL 环境变量)."""
        # Patch the import to raise
        def _raise():
            raise ImportError("settings unavailable")

        with patch.dict(os.environ, {"REDIS_URL": "redis://env:6379/0"}):
            with patch.dict(sys.modules, {"app.core.config": MagicMock(settings=_raise)}):
                from app.core import cache
                # _get_redis_url 会从 settings 失败, 然后走 except, 然后走 env
                result = cache._get_redis_url()
                assert result == "redis://env:6379/0"
