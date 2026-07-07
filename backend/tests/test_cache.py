"""v1.36: cache 工具单元测试."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_redis_client():
    """每个测试前重置模块级共享 Redis 客户端 + 内存回退缓存, 避免测试间状态泄漏."""
    from app.core import cache

    old = cache._redis_client
    cache._redis_client = None
    # P1-3: 重置内存回退缓存, 避免上一个测试写入的条目影响下一个测试
    cache.clear_memory_cache()
    yield
    cache._redis_client = old
    cache.clear_memory_cache()


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
        """P1-3: 无 redis_url 且内存缓存为空 → 返回 None (回退到内存但未命中)."""
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

        with patch.object(
            cache, "_get_redis_url", return_value="redis://localhost:6379/0"
        ):
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

        with patch.object(
            cache, "_get_redis_url", return_value="redis://localhost:6379/0"
        ):
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

        with patch.object(
            cache, "_get_redis_url", return_value="redis://localhost:6379/0"
        ):
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

        with patch.object(
            cache, "_get_redis_url", return_value="redis://localhost:6379/0"
        ):
            with patch("app.core.cache.aioredis") as mock_aioredis:
                mock_aioredis.from_url.side_effect = Exception("connection refused")
                result = await cache.cache_get("obs:trend:abc")
                assert result is None

    @pytest.mark.asyncio
    async def test_cache_get_aclose_failure_does_not_propagate(self):
        """aclose 抛错时, 不影响 cache_get 正常返回值."""
        from app.core import cache

        with patch.object(
            cache, "_get_redis_url", return_value="redis://localhost:6379/0"
        ):
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

        with patch.object(
            cache, "_get_redis_url", return_value="redis://localhost:6379/0"
        ):
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
    async def test_cache_set_no_redis_url_falls_back_to_memory(self):
        """P1-3: 无 redis_url 时回退写入内存缓存, 返回 True."""
        from app.core import cache

        with patch.object(cache, "_get_redis_url", return_value=None):
            result = await cache.cache_set("obs:trend:abc", {"foo": "bar"})
            # P1-3: 回退到内存缓存, 写入成功返回 True
            assert result is True
            # 验证内存缓存中确实写入了
            cached = cache._memory_cache.get("obs:trend:abc")
            assert cached == {"foo": "bar"}

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
    async def test_cache_set_redis_down_falls_back_to_memory(self):
        """P1-3: Redis 不可用时回退写入内存缓存, 返回 True (不抛错)."""
        from app.core import cache

        with patch.object(
            cache, "_get_redis_url", return_value="redis://localhost:6379/0"
        ):
            with patch("app.core.cache.aioredis") as mock_aioredis:
                mock_aioredis.from_url.side_effect = Exception("connection refused")
                result = await cache.cache_set("obs:trend:abc", {"foo": "bar"})
                # P1-3: 回退到内存缓存, 写入成功返回 True
                assert result is True
                cached = cache._memory_cache.get("obs:trend:abc")
                assert cached == {"foo": "bar"}

    @pytest.mark.asyncio
    async def test_cache_set_ttl_zero_uses_default(self):
        """ttl <= 0 时使用默认 300s."""
        from app.core import cache

        with patch.object(
            cache, "_get_redis_url", return_value="redis://localhost:6379/0"
        ):
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
            with patch.dict(
                sys.modules, {"app.core.config": MagicMock(settings=_raise)}
            ):
                from app.core import cache

                # _get_redis_url 会从 settings 失败, 然后走 except, 然后走 env
                result = cache._get_redis_url()
                assert result == "redis://env:6379/0"


class TestPublicRedisClientAPI:
    """P1-2: 测试公共 get_redis_client / close_redis_client 包装函数."""

    @pytest.mark.asyncio
    async def test_get_redis_client_returns_none_when_no_url(self):
        """无 redis_url 时 get_redis_client 返回 None."""
        from app.core import cache

        with patch.object(cache, "_get_redis_url", return_value=None):
            client = await cache.get_redis_client()
            assert client is None

    @pytest.mark.asyncio
    async def test_get_redis_client_returns_shared_singleton(self):
        """get_redis_client 返回共享单例 (与 _get_redis_client 同一实例)."""
        from app.core import cache

        mock_client = MagicMock()
        with patch.object(
            cache, "_get_redis_url", return_value="redis://localhost:6379/0"
        ):
            with patch("app.core.cache.aioredis") as mock_aioredis:
                mock_aioredis.from_url.return_value = mock_client
                client1 = await cache.get_redis_client()
                client2 = await cache.get_redis_client()
                # 两次调用应返回同一单例 (from_url 仅调用一次)
                assert client1 is mock_client
                assert client2 is mock_client
                assert mock_aioredis.from_url.call_count == 1

    @pytest.mark.asyncio
    async def test_close_redis_client_resets_singleton(self):
        """close_redis_client 关闭并重置单例, 下次获取会重建."""
        from app.core import cache

        mock_client = AsyncMock()
        mock_client.aclose = AsyncMock()
        cache._redis_client = mock_client
        await cache.close_redis_client()
        # aclose 被调用
        mock_client.aclose.assert_awaited_once()
        # 单例被重置
        assert cache._redis_client is None

    @pytest.mark.asyncio
    async def test_close_redis_client_noop_when_none(self):
        """单例为 None 时 close_redis_client 不抛错."""
        from app.core import cache

        cache._redis_client = None
        # 不应抛出异常
        await cache.close_redis_client()
        assert cache._redis_client is None

    @pytest.mark.asyncio
    async def test_close_redis_client_swallows_aclose_errors(self):
        """aclose 抛错时 close_redis_client 不传播异常."""
        from app.core import cache

        mock_client = AsyncMock()
        mock_client.aclose = AsyncMock(side_effect=RuntimeError("aclose failed"))
        cache._redis_client = mock_client
        # 不应抛出
        await cache.close_redis_client()
        # 单例仍被重置
        assert cache._redis_client is None


class TestMemoryCacheFallback:
    """P1-3: 测试 Redis 不可用时回退到内存缓存的端到端行为."""

    @pytest.mark.asyncio
    async def test_roundtrip_through_memory_when_redis_down(self):
        """Redis 故障期间: 写入内存 → 读取内存命中 (端到端回退)."""
        from app.core import cache

        # 模拟 Redis 完全不可用 (from_url 抛错)
        with patch.object(
            cache, "_get_redis_url", return_value="redis://localhost:6379/0"
        ):
            with patch("app.core.cache.aioredis") as mock_aioredis:
                mock_aioredis.from_url.side_effect = Exception("connection refused")
                # 写入: 应回退到内存, 返回 True
                set_result = await cache.cache_set("obs:trend:test", {"v": 42}, ttl=300)
                assert set_result is True
                # 读取: 应回退到内存, 命中返回值
                get_result = await cache.cache_get("obs:trend:test")
                assert get_result == {"v": 42}

    @pytest.mark.asyncio
    async def test_memory_cache_ttl_expiry(self):
        """内存缓存 TTL 过期后返回 None."""
        from app.core import cache

        with patch.object(cache, "_get_redis_url", return_value=None):
            # 写入, TTL=0 会被修正为默认 300s, 用极短 TTL 测试过期
            # 直接操作内存缓存测试过期逻辑
            cache._memory_cache.set("expiring_key", "data", ttl=0)
            # ttl=0 时 expire_at = now, 立即过期
            result = await cache.cache_get("expiring_key")
            assert result is None

    @pytest.mark.asyncio
    async def test_memory_cache_lru_eviction(self):
        """内存缓存超过 max_size 时淘汰最旧条目."""
        from app.core.cache import _MemoryTTLCache

        small_cache = _MemoryTTLCache(max_size=3)
        small_cache.set("k1", "v1", ttl=300)
        small_cache.set("k2", "v2", ttl=300)
        small_cache.set("k3", "v3", ttl=300)
        # 访问 k1 使其变为最近使用
        assert small_cache.get("k1") == "v1"
        # 写入 k4, 应淘汰最旧的 k2 (k1 被访问过, k3 次旧)
        small_cache.set("k4", "v4", ttl=300)
        assert small_cache.get("k2") is None  # k2 被淘汰
        assert small_cache.get("k1") == "v1"  # k1 保留
        assert small_cache.get("k3") == "v3"  # k3 保留
        assert small_cache.get("k4") == "v4"  # k4 保留
        assert len(small_cache) == 3

    @pytest.mark.asyncio
    async def test_memory_cache_lru_update_on_overwrite(self):
        """重复写入同一 key 时更新值和访问顺序."""
        from app.core.cache import _MemoryTTLCache

        small_cache = _MemoryTTLCache(max_size=2)
        small_cache.set("k1", "v1", ttl=300)
        small_cache.set("k2", "v2", ttl=300)
        # 覆盖 k1
        small_cache.set("k1", "v1_updated", ttl=300)
        # 写入 k3, 应淘汰 k2 (k1 刚被更新, 是最近使用)
        small_cache.set("k3", "v3", ttl=300)
        assert small_cache.get("k2") is None
        assert small_cache.get("k1") == "v1_updated"
        assert small_cache.get("k3") == "v3"

    def test_clear_memory_cache_function(self):
        """clear_memory_cache 清空全局内存缓存实例."""
        from app.core import cache

        cache._memory_cache.set("test_key", "test_value", ttl=300)
        assert len(cache._memory_cache) == 1
        cache.clear_memory_cache()
        assert len(cache._memory_cache) == 0
        assert cache._memory_cache.get("test_key") is None
