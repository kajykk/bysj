"""v1.35: dedup_lock 模块测试.

v1.36: 增加 T1.3 - dedup_lock 内存计数 + flush 测试.
"""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.monitoring import dedup_lock as dedup_lock_mod
from app.monitoring.dedup_lock import (
    _get_redis_url,
    flush_lock_stats,
    get_last_flush_at,
    get_stats,
    release_lock,
    reset_stats,
    set_last_flush_at,
    try_acquire_lock,
)


@pytest.fixture(autouse=True)
def _clear_stats() -> None:
    """每个测试前重置内存统计, 避免相互干扰."""
    reset_stats()


# ===== try_acquire_lock =====


async def test_acquire_lock_success() -> None:
    """v1.35: 锁未被占用时应获取成功."""
    with patch("app.monitoring.dedup_lock.aioredis") as mock_aioredis:
        mock_client = AsyncMock()
        mock_client.set = AsyncMock(return_value=True)  # SET NX 成功
        mock_client.aclose = AsyncMock()
        mock_aioredis.from_url.return_value = mock_client

        result = await try_acquire_lock("fp-1", redis_url="redis://localhost:6379/0")
        assert result is True
        mock_client.set.assert_awaited_once()
        call_args = mock_client.set.call_args
        assert call_args.kwargs["nx"] is True
        assert call_args.kwargs["ex"] == 300


async def test_acquire_lock_already_held() -> None:
    """v1.35: 锁已被其他实例占用时返回 False."""
    with patch("app.monitoring.dedup_lock.aioredis") as mock_aioredis:
        mock_client = AsyncMock()
        mock_client.set = AsyncMock(return_value=False)  # SET NX 失败
        mock_client.aclose = AsyncMock()
        mock_aioredis.from_url.return_value = mock_client

        result = await try_acquire_lock("fp-held", redis_url="redis://localhost:6379/0")
        assert result is False


async def test_acquire_lock_redis_down() -> None:
    """v1.35: Redis 不可用时返回 True (降级: 允许发送)."""
    with patch("app.monitoring.dedup_lock.aioredis") as mock_aioredis:
        mock_aioredis.from_url.side_effect = Exception("redis down")
        result = await try_acquire_lock("fp-1", redis_url="redis://bad:6379/0")
        # 降级: 返回 True, 允许发送 (由 SQL dedup 二次校验)
        assert result is True


async def test_acquire_lock_no_fingerprint() -> None:
    """v1.35: 无 fingerprint 应直接返回 True."""
    result = await try_acquire_lock("", redis_url="redis://localhost:6379/0")
    assert result is True
    result = await try_acquire_lock(None, redis_url="redis://localhost:6379/0")  # type: ignore
    assert result is True


async def test_acquire_lock_no_redis_url() -> None:
    """v1.35: 无 Redis client (共享 client 为 None) 应降级返回 True."""
    with patch("app.core.cache.get_redis_client", AsyncMock(return_value=None)):
        result = await try_acquire_lock("fp-1")
        assert result is True


async def test_acquire_lock_custom_ttl() -> None:
    """v1.35: 自定义 TTL 应生效."""
    with patch("app.monitoring.dedup_lock.aioredis") as mock_aioredis:
        mock_client = AsyncMock()
        mock_client.set = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()
        mock_aioredis.from_url.return_value = mock_client

        await try_acquire_lock(
            "fp-1", ttl_seconds=60, redis_url="redis://localhost:6379/0"
        )
        call_args = mock_client.set.call_args
        assert call_args.kwargs["ex"] == 60


async def test_acquire_lock_uses_redis_url() -> None:
    """v1.35: 应使用正确的 redis URL."""
    with patch("app.monitoring.dedup_lock.aioredis") as mock_aioredis:
        mock_client = AsyncMock()
        mock_client.set = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()
        mock_aioredis.from_url.return_value = mock_client

        await try_acquire_lock("fp-1", redis_url="redis://custom:1234/5")
        mock_aioredis.from_url.assert_called_once()
        called_url = mock_aioredis.from_url.call_args.args[0]
        assert "custom:1234/5" in called_url


# ===== release_lock =====


async def test_release_lock_success() -> None:
    """v1.35: 释放锁应调用 Redis delete."""
    with patch("app.monitoring.dedup_lock.aioredis") as mock_aioredis:
        mock_client = AsyncMock()
        mock_client.delete = AsyncMock(return_value=1)
        mock_client.aclose = AsyncMock()
        mock_aioredis.from_url.return_value = mock_client

        result = await release_lock("fp-1", redis_url="redis://localhost:6379/0")
        assert result is True
        mock_client.delete.assert_awaited_once()


async def test_release_lock_no_fingerprint() -> None:
    """v1.35: 无 fingerprint 应返回 False."""
    result = await release_lock("", redis_url="redis://localhost:6379/0")
    assert result is False


async def test_release_lock_no_redis_url() -> None:
    """v1.35: 无 Redis client (共享 client 为 None) 应返回 False."""
    with patch("app.core.cache.get_redis_client", AsyncMock(return_value=None)):
        result = await release_lock("fp-1")
        assert result is False


async def test_release_lock_redis_down() -> None:
    """v1.35: Redis 不可用时返回 False (异常吞掉)."""
    with patch("app.monitoring.dedup_lock.aioredis") as mock_aioredis:
        mock_aioredis.from_url.side_effect = Exception("redis down")
        result = await release_lock("fp-1", redis_url="redis://bad:6379/0")
        assert result is False


# ===== v1.36: T1.3 dedup_lock 内存统计 + flush (TC-DATA-003) =====


async def test_lock_stats_incremented_on_acquired() -> None:
    """v1.36 T1.3: 成功获取锁时 acquired 计数 +1."""
    with patch("app.monitoring.dedup_lock.aioredis") as mock_aioredis:
        mock_client = AsyncMock()
        mock_client.set = AsyncMock(return_value=True)  # 锁未被占用
        mock_client.aclose = AsyncMock()
        mock_aioredis.from_url.return_value = mock_client

        await try_acquire_lock("fp-success", redis_url="redis://localhost:6379/0")

    stats = get_stats()
    assert stats["acquired"] == 1
    assert stats["skipped"] == 0
    assert stats["fallback"] == 0


async def test_lock_stats_incremented_on_skipped() -> None:
    """v1.36 T1.3: 锁被其他实例持有时 skipped 计数 +1."""
    with patch("app.monitoring.dedup_lock.aioredis") as mock_aioredis:
        mock_client = AsyncMock()
        mock_client.set = AsyncMock(return_value=False)  # 锁已被占用
        mock_client.aclose = AsyncMock()
        mock_aioredis.from_url.return_value = mock_client

        await try_acquire_lock("fp-held", redis_url="redis://localhost:6379/0")

    stats = get_stats()
    assert stats["acquired"] == 0
    assert stats["skipped"] == 1
    assert stats["fallback"] == 0


async def test_lock_stats_incremented_on_fallback() -> None:
    """v1.36 T1.3: Redis 不可用时 fallback 计数 +1."""
    with patch("app.monitoring.dedup_lock.aioredis") as mock_aioredis:
        mock_aioredis.from_url.side_effect = Exception("redis down")

        await try_acquire_lock("fp-fb", redis_url="redis://bad:6379/0")

    stats = get_stats()
    assert stats["acquired"] == 0
    assert stats["skipped"] == 0
    assert stats["fallback"] == 1


async def test_lock_stats_incremented_on_no_redis_url() -> None:
    """v1.36 T1.3: 无 redis client 时 fallback 计数 +1."""
    with patch("app.core.cache.get_redis_client", AsyncMock(return_value=None)):
        await try_acquire_lock("fp-no-url")

    stats = get_stats()
    assert stats["fallback"] == 1


async def test_flush_lock_stats_writes_to_db() -> None:
    """v1.36 T1.3: flush_lock_stats 写入 OperationLog (dedup_lock_stats)."""
    # 模拟已累加的计数
    dedup_lock_mod._stats["acquired"] = 5
    dedup_lock_mod._stats["skipped"] = 3
    dedup_lock_mod._stats["fallback"] = 1
    dedup_lock_mod._stats["errors"] = 0

    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    success = await flush_lock_stats(db)
    assert success is True
    assert db.add.called
    log_obj = db.add.call_args.args[0]
    assert log_obj.action_type == "dedup_lock_stats"
    assert log_obj.target_type == "dedup_lock"
    assert log_obj.operator_role == "system"
    assert log_obj.operator_id is None


async def test_flush_lock_stats_includes_detail() -> None:
    """v1.36 T1.3: detail 包含 acquired/skipped/fallback/errors/instance_id."""
    dedup_lock_mod._stats["acquired"] = 7
    dedup_lock_mod._stats["skipped"] = 2
    dedup_lock_mod._stats["fallback"] = 1
    dedup_lock_mod._stats["errors"] = 0

    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    await flush_lock_stats(db)
    log_obj = db.add.call_args.args[0]
    detail = json.loads(log_obj.detail)
    assert detail["acquired"] == 7
    assert detail["skipped"] == 2
    assert detail["fallback"] == 1
    assert detail["errors"] == 0
    assert "instance_id" in detail
    assert "-" in detail["instance_id"]  # hostname-pid 格式


async def test_flush_lock_stats_clears_memory() -> None:
    """v1.36 T1.3: flush 成功后清零内存计数."""
    dedup_lock_mod._stats["acquired"] = 10
    dedup_lock_mod._stats["skipped"] = 5

    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    success = await flush_lock_stats(db)
    assert success is True
    stats = get_stats()
    # flush 成功后计数应清零
    assert stats["acquired"] == 0
    assert stats["skipped"] == 0


async def test_flush_lock_stats_empty_skips_write() -> None:
    """v1.36 T1.3: 所有计数为 0 时不写空日志."""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    success = await flush_lock_stats(db)
    assert success is True
    # 不应调用 db.add (避免噪音)
    assert not db.add.called


async def test_flush_lock_stats_failure_keeps_memory() -> None:
    """v1.36 T1.3: flush 失败时保留内存计数, 下次重试."""
    dedup_lock_mod._stats["acquired"] = 8
    dedup_lock_mod._stats["skipped"] = 4

    db = MagicMock()
    db.add = MagicMock(side_effect=Exception("db unavailable"))
    db.flush = AsyncMock()
    success = await flush_lock_stats(db)
    assert success is False
    stats = get_stats()
    # 失败时计数应保留
    assert stats["acquired"] == 8
    assert stats["skipped"] == 4


# ===== 新增: 覆盖 _get_redis_url (L49-55) =====


def test_get_redis_url_from_settings() -> None:
    """settings.redis_url 有效且以 redis 开头时应返回该值."""
    with patch("app.core.config.settings") as mock_settings:
        mock_settings.redis_url = "redis://localhost:6379/0"
        assert _get_redis_url() == "redis://localhost:6379/0"


def test_get_redis_url_invalid_protocol() -> None:
    """settings.redis_url 不以 redis 开头时应回退到环境变量."""
    with patch.dict(os.environ, {"REDIS_URL": "redis://env:6379/0"}, clear=False):
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.redis_url = "memory://invalid"
            assert _get_redis_url() == "redis://env:6379/0"


def test_get_redis_url_empty_settings() -> None:
    """settings.redis_url 为空时应回退到环境变量."""
    with patch.dict(os.environ, {"REDIS_URL": "redis://env:6379/0"}, clear=False):
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.redis_url = ""
            assert _get_redis_url() == "redis://env:6379/0"


def test_get_redis_url_settings_exception() -> None:
    """settings 访问异常时应回退到环境变量 (except 分支)."""
    with patch.dict(os.environ, {"REDIS_URL": "redis://env:6379/0"}, clear=False):
        # 模拟 settings 属性访问抛异常
        class _ExplodingSettings:
            @property
            def redis_url(self):
                raise RuntimeError("config init failed")

        with patch("app.core.config.settings", _ExplodingSettings()):
            result = _get_redis_url()
            assert result == "redis://env:6379/0"


def test_get_redis_url_no_env_var() -> None:
    """settings 无效且无环境变量时应返回 None."""
    with patch.dict(os.environ, {}, clear=True):
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.redis_url = ""
            assert _get_redis_url() is None


# ===== 新增: 覆盖 get_last_flush_at / set_last_flush_at (L65) =====


def test_get_last_flush_at_initial() -> None:
    """初始状态下 get_last_flush_at 应返回 None."""
    reset_stats()
    assert get_last_flush_at() is None


def test_set_and_get_last_flush_at() -> None:
    """set_last_flush_at 设置后 get_last_flush_at 应返回该值."""
    set_last_flush_at("2024-01-01T00:00:00Z")
    assert get_last_flush_at() == "2024-01-01T00:00:00Z"
    # 清理
    set_last_flush_at(None)
    assert get_last_flush_at() is None


# ===== 新增: 覆盖 try_acquire_lock 共享 client 路径 (L113-127) =====


async def test_acquire_lock_shared_client_success() -> None:
    """redis_url=None 时使用共享 client, 成功获取锁."""
    mock_client = AsyncMock()
    mock_client.set = AsyncMock(return_value=True)
    with patch("app.core.cache.get_redis_client", AsyncMock(return_value=mock_client)):
        result = await try_acquire_lock("fp-shared")
    assert result is True
    mock_client.set.assert_awaited_once()
    stats = get_stats()
    assert stats["acquired"] == 1


async def test_acquire_lock_shared_client_held() -> None:
    """redis_url=None 时锁已被其他实例持有."""
    mock_client = AsyncMock()
    mock_client.set = AsyncMock(return_value=False)
    with patch("app.core.cache.get_redis_client", AsyncMock(return_value=mock_client)):
        result = await try_acquire_lock("fp-held-shared")
    assert result is False
    stats = get_stats()
    assert stats["skipped"] == 1


async def test_acquire_lock_shared_client_none() -> None:
    """redis_url=None 时共享 client 为 None (无 Redis 配置), 应回退降级."""
    with patch("app.core.cache.get_redis_client", AsyncMock(return_value=None)):
        result = await try_acquire_lock("fp-no-client")
    assert result is True
    stats = get_stats()
    assert stats["fallback"] == 1


async def test_acquire_lock_shared_client_exception() -> None:
    """redis_url=None 时共享 client 抛异常, 应降级返回 True."""
    with patch(
        "app.core.cache.get_redis_client",
        AsyncMock(side_effect=Exception("redis down")),
    ):
        result = await try_acquire_lock("fp-exception")
    assert result is True
    stats = get_stats()
    assert stats["fallback"] == 1


async def test_acquire_lock_shared_client_custom_ttl() -> None:
    """redis_url=None 时自定义 TTL 应传给共享 client."""
    mock_client = AsyncMock()
    mock_client.set = AsyncMock(return_value=True)
    with patch("app.core.cache.get_redis_client", AsyncMock(return_value=mock_client)):
        await try_acquire_lock("fp-ttl", ttl_seconds=60)
    call_args = mock_client.set.call_args
    assert call_args.kwargs["ex"] == 60
    assert call_args.kwargs["nx"] is True


# ===== 新增: 覆盖 release_lock 共享 client 路径 (L168, L171) =====


async def test_release_lock_shared_client_success() -> None:
    """redis_url=None 时通过共享 client 释放锁."""
    mock_client = AsyncMock()
    mock_client.delete = AsyncMock(return_value=1)
    with patch("app.core.cache.get_redis_client", AsyncMock(return_value=mock_client)):
        result = await release_lock("fp-release")
    assert result is True
    mock_client.delete.assert_awaited_once()


async def test_release_lock_shared_client_not_found() -> None:
    """redis_url=None 时锁不存在, delete 返回 0."""
    mock_client = AsyncMock()
    mock_client.delete = AsyncMock(return_value=0)
    with patch("app.core.cache.get_redis_client", AsyncMock(return_value=mock_client)):
        result = await release_lock("fp-not-found")
    assert result is False


async def test_release_lock_shared_client_none() -> None:
    """redis_url=None 时共享 client 为 None, 应返回 False."""
    with patch("app.core.cache.get_redis_client", AsyncMock(return_value=None)):
        result = await release_lock("fp-no-client")
    assert result is False


async def test_release_lock_shared_client_exception() -> None:
    """redis_url=None 时共享 client 抛异常, 应返回 False."""
    with patch(
        "app.core.cache.get_redis_client",
        AsyncMock(side_effect=Exception("redis down")),
    ):
        result = await release_lock("fp-exception")
    assert result is False


# ===== 新增: 覆盖 flush_lock_stats 负数 clamp (L235) =====


async def test_flush_lock_stats_clamps_negative() -> None:
    """flush 期间 stats 被并发减少时应 clamp 到 0 (不出现负数)."""
    dedup_lock_mod._stats["acquired"] = 5

    async def _reduce_stats():
        # 模拟并发修改: flush 期间 stats 被重置
        dedup_lock_mod._stats["acquired"] = 2

    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock(side_effect=_reduce_stats)

    success = await flush_lock_stats(db)
    assert success is True
    # snapshot=5, 当前=2, 2-5=-3 -> clamp to 0
    assert get_stats()["acquired"] == 0


# ===== 新增: 锁竞争场景验证 =====


async def test_lock_competition_first_wins() -> None:
    """锁竞争: 第一个实例获取成功, 第二个失败."""
    mock_client = AsyncMock()
    mock_client.set = AsyncMock(side_effect=[True, False])  # 第一次成功, 第二次失败
    with patch("app.monitoring.dedup_lock.aioredis") as mock_aioredis:
        mock_aioredis.from_url.return_value = mock_client

        r1 = await try_acquire_lock("fp-comp", redis_url="redis://localhost:6379/0")
        r2 = await try_acquire_lock("fp-comp", redis_url="redis://localhost:6379/0")

    assert r1 is True
    assert r2 is False
    stats = get_stats()
    assert stats["acquired"] == 1
    assert stats["skipped"] == 1


# ===== 新增: TOCTOU 修复点验证 (with_for_update 锁相关) =====


async def test_acquire_lock_uses_setnx_semantics() -> None:
    """TOCTOU 修复: SETNX 原子操作避免竞态条件 (验证 nx=True)."""
    mock_client = AsyncMock()
    mock_client.set = AsyncMock(return_value=True)
    mock_client.aclose = AsyncMock()
    with patch("app.monitoring.dedup_lock.aioredis") as mock_aioredis:
        mock_aioredis.from_url.return_value = mock_client
        await try_acquire_lock("fp-toctou", redis_url="redis://localhost:6379/0")

    # 验证 SETNX 语义: nx=True 保证原子性
    call_args = mock_client.set.call_args
    assert call_args.kwargs["nx"] is True
    assert call_args.kwargs["ex"] == 300  # TTL 默认 5 分钟


# ===== 新增: Redis 失败回退路径 (共享 client) =====


async def test_acquire_lock_fallback_does_not_block() -> None:
    """Redis 不可用时降级返回 True, 不阻止发送 (由 SQL dedup 二次校验)."""
    # 共享 client 路径降级
    with patch(
        "app.core.cache.get_redis_client",
        AsyncMock(side_effect=ConnectionError("refused")),
    ):
        result = await try_acquire_lock("fp-fallback")
    assert result is True
    assert get_stats()["fallback"] == 1
