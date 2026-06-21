"""v1.35: dedup_lock 模块测试.

v1.36: 增加 T1.3 - dedup_lock 内存计数 + flush 测试.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.monitoring import dedup_lock as dedup_lock_mod
from app.monitoring.dedup_lock import (
    flush_lock_stats,
    get_stats,
    release_lock,
    reset_stats,
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
    """v1.35: 无 Redis URL 应直接返回 True."""
    with patch("app.monitoring.dedup_lock._get_redis_url", return_value=None):
        result = await try_acquire_lock("fp-1")
        assert result is True


async def test_acquire_lock_custom_ttl() -> None:
    """v1.35: 自定义 TTL 应生效."""
    with patch("app.monitoring.dedup_lock.aioredis") as mock_aioredis:
        mock_client = AsyncMock()
        mock_client.set = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()
        mock_aioredis.from_url.return_value = mock_client

        await try_acquire_lock("fp-1", ttl_seconds=60, redis_url="redis://localhost:6379/0")
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
    """v1.35: 无 Redis URL 应返回 False."""
    with patch("app.monitoring.dedup_lock._get_redis_url", return_value=None):
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
    """v1.36 T1.3: 无 redis_url 时 fallback 计数 +1."""
    with patch("app.monitoring.dedup_lock._get_redis_url", return_value=None):
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
