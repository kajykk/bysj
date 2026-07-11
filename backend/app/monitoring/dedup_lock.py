"""v1.35: 跨实例告警去重 (Redis 分布式锁).

机制:
- SETNX 锁: alert:dedup:<fingerprint> = <ts>
- TTL = 5 分钟 (与 dedup 窗口一致)
- 获取成功 -> 本实例发送, 其他实例应跳过
- 获取失败 -> 其他实例已获取, 本实例跳过
- Redis 不可用 -> 降级到 SQL dedup (v1.34)

v1.36: 增加内存统计 + flush 机制
- 维护 _stats: {acquired, skipped, fallback, errors}
- try_acquire_lock 返回时根据路径增加计数
- flush_lock_stats(db) 写入 OperationLog (action_type=dedup_lock_stats)
- flush 失败不清零 (下次重试)
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import TYPE_CHECKING

import redis.asyncio as aioredis

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 默认 TTL: 5 分钟 (与 v1.34 dedup 窗口一致)
DEFAULT_DEDUP_LOCK_TTL_SECONDS = 300


# v1.36: 内存统计
_stats: dict[str, int] = {
    "acquired": 0,   # 本实例成功获取锁
    "skipped": 0,    # 其他实例持有锁, 本实例跳过
    "fallback": 0,   # Redis 不可用, 降级到 SQL dedup
    "errors": 0,     # 其他异常
}

# v1.36: 上次 flush 时间 (ISO 8601, None = 尚未 flush)
_last_flush_at: str | None = None


def _get_redis_url() -> str | None:
    """v1.35: 从 settings 或环境变量获取 Redis URL."""
    try:
        from app.core.config import settings
        if settings.redis_url and settings.redis_url.startswith("redis"):
            return settings.redis_url
    except Exception:
        pass
    return os.getenv("REDIS_URL")


def get_stats() -> dict[str, int]:
    """v1.36: 获取当前内存统计 (只读快照, 不清零)."""
    return dict(_stats)


def get_last_flush_at() -> str | None:
    """v1.36: 获取上次 flush 时间 (ISO 8601, None = 尚未 flush)."""
    return _last_flush_at


def set_last_flush_at(ts: str | None) -> None:
    """v1.36: 设置上次 flush 时间 (flush_lock_stats 内部使用)."""
    global _last_flush_at
    _last_flush_at = ts


def reset_stats() -> None:
    """v1.36: 测试用, 重置内存统计."""
    for k in _stats:
        _stats[k] = 0
    global _last_flush_at
    _last_flush_at = None


async def try_acquire_lock(
    fingerprint: str,
    ttl_seconds: int = DEFAULT_DEDUP_LOCK_TTL_SECONDS,
    redis_url: str | None = None,
) -> bool:
    """v1.35: 尝试获取 dedup 锁.

    Args:
        fingerprint: 告警 fingerprint
        ttl_seconds: 锁 TTL 秒数 (默认 5 分钟)
        redis_url: Redis URL (None 则从 settings 读取)

    Returns:
        True = 本实例获得锁, 应发送通知
        False = 锁已被其他实例获取, 应跳过
        注: Redis 不可用时返回 True (降级: 不阻止发送)

    v1.36: 同时增加内存统计 (acquired/skipped/fallback/errors).
    P1-2: 复用 app.core.cache 共享 Redis 客户端, 不再每次 from_url+aclose.
    """
    if not fingerprint:
        return True  # 无 fingerprint, 不去重

    # P1-2: redis_url 参数仅用于显式覆盖, 默认走共享客户端的内部 URL 解析.
    # 若调用方显式传入 redis_url (测试场景), 仍按旧路径创建一次性客户端.
    if redis_url is None:
        from app.core.cache import get_redis_client
        try:
            client = await get_redis_client()
            if client is None:
                # 无 Redis 配置或断路器开启 -> 降级路径
                _stats["fallback"] += 1
                logger.debug("[dedup_lock] no redis client, skip lock (fallback)")
                return True
            key = f"alert:dedup:{fingerprint}"
            value = f"{int(time.time())}"
            # SETNX with TTL (使用 SET NX EX)
            acquired = await client.set(key, value, nx=True, ex=ttl_seconds)
            # P1-2: 不再 aclose, 保留单例供下次复用
            if acquired:
                _stats["acquired"] += 1
                logger.debug("[dedup_lock] acquired (fingerprint=%s, ttl=%ds)", fingerprint, ttl_seconds)
            else:
                _stats["skipped"] += 1
                logger.info("[dedup_lock] held by other instance (fingerprint=%s)", fingerprint)
            return bool(acquired)
        except Exception as exc:
            _stats["fallback"] += 1
            logger.warning("[dedup_lock] redis unavailable, falling back to SQL dedup: %s", exc)
            # 降级: 返回 True (允许发送, 后续 SQL dedup 会二次校验)
            return True

    # 显式传入 redis_url (测试场景): 使用一次性客户端, 保持参数语义
    url = redis_url
    try:
        client = aioredis.from_url(url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
        key = f"alert:dedup:{fingerprint}"
        value = f"{int(time.time())}"
        acquired = await client.set(key, value, nx=True, ex=ttl_seconds)
        await client.aclose()
        if acquired:
            _stats["acquired"] += 1
            logger.debug("[dedup_lock] acquired (fingerprint=%s, ttl=%ds)", fingerprint, ttl_seconds)
        else:
            _stats["skipped"] += 1
            logger.info("[dedup_lock] held by other instance (fingerprint=%s)", fingerprint)
        return bool(acquired)
    except Exception as exc:
        _stats["fallback"] += 1
        logger.warning("[dedup_lock] redis unavailable, falling back to SQL dedup: %s", exc)
        return True


async def release_lock(fingerprint: str, redis_url: str | None = None) -> bool:
    """v1.35: 释放 dedup 锁 (用于测试或主动清理).

    通常无需调用: 锁 TTL 5 分钟后自动过期.
    P1-2: 默认复用共享客户端, redis_url 显式传入时使用一次性客户端 (测试场景).
    """
    if not fingerprint:
        return False
    if redis_url is None:
        from app.core.cache import get_redis_client
        try:
            client = await get_redis_client()
            if client is None:
                return False
            key = f"alert:dedup:{fingerprint}"
            deleted = await client.delete(key)
            return bool(deleted)
        except Exception as exc:
            logger.warning("[dedup_lock] release failed: %s", exc)
            return False
    # 测试场景: 使用一次性客户端
    try:
        client = aioredis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
        key = f"alert:dedup:{fingerprint}"
        deleted = await client.delete(key)
        await client.aclose()
        return bool(deleted)
    except Exception as exc:
        logger.warning("[dedup_lock] release failed: %s", exc)
        return False


async def flush_lock_stats(
    db: "AsyncSession",
) -> bool:
    """v1.36: 将内存统计 flush 到 OperationLog.

    流程:
    1. 读取当前 _stats 快照
    2. 写入 OperationLog (action_type=dedup_lock_stats)
    3. detail 包含: acquired/skipped/fallback/errors + instance_id
    4. flush 成功 -> 清零内存计数
    5. flush 失败 -> 不清零, 下次重试

    Returns:
        True = 写入成功 (计数已清零)
        False = 写入失败 (计数保留)
    """
    # 读取快照 (避免在 await 期间被其他调用修改)
    snapshot = dict(_stats)
    # 若全部为 0, 不写空日志 (避免噪音)
    if all(v == 0 for v in snapshot.values()):
        return True

    try:
        from app.core.instance import get_instance_id
        from app.models.admin import OperationLog

        detail_dict = {
            "instance_id": get_instance_id(),
            "acquired": snapshot["acquired"],
            "skipped": snapshot["skipped"],
            "fallback": snapshot["fallback"],
            "errors": snapshot["errors"],
        }
        log = OperationLog(
            operator_id=None,
            operator_role="system",
            action_type="dedup_lock_stats",
            target_type="dedup_lock",
            target_id=None,
            detail=json.dumps(detail_dict, ensure_ascii=False),
        )
        db.add(log)
        await db.flush()

        # flush 成功 -> 清零 (仅清零已写入的计数, 保留 flush 期间新增的)
        for k in snapshot:
            _stats[k] -= snapshot[k]
            if _stats[k] < 0:
                _stats[k] = 0
        # v1.36: 记录 flush 时间
        from datetime import datetime, timezone
        set_last_flush_at(datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
        return True
    except Exception as exc:
        # flush 失败 -> 不清零, 下次重试
        logger.error("[dedup_lock] flush stats failed: %s", exc)
        return False
