"""v1.36: 观测 API 5min 缓存工具.

提供 Redis 缓存读写与 cache key 生成能力.
P1-3: Redis 不可用时回退到进程内 LRU+TTL 内存缓存, 避免缓存击穿.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from typing import Any

import redis.asyncio as aioredis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

logger = logging.getLogger(__name__)

DEFAULT_CACHE_TTL = 300  # 5min


class _MemoryTTLCache:
    """P1-3: 进程内 LRU + TTL 缓存, 作为 Redis 不可用时的回退层.

    特性:
    - LRU 淘汰: 超过 max_size 时淘汰最久未访问的条目 (利用 dict 插入顺序).
    - TTL 过期: get 时惰性检查过期时间, 过期则移除并返回 None.
    - 非线程安全: 仅在 asyncio 单线程事件循环中使用 (cache_get/set 均为 async).

    设计权衡:
    - 内存缓存仅作为 Redis 故障期间的回退, 不作为二级缓存.
      Redis 恢复后, 内存中的过期条目由 TTL 自然清理, 无需主动清除.
    - max_size 默认 1000, 防止无界增长. 观测 API 仅 7 个端点, 1000 足够.
    """

    def __init__(self, max_size: int = 1000) -> None:
        self._store: dict[str, tuple[Any, float]] = {}
        self._max_size = max_size

    def get(self, key: str) -> Any | None:
        """读取缓存. 命中且未过期时返回值, 否则返回 None.

        LRU 语义: 命中时将条目移到 dict 末尾 (最近使用).
        过期判断: expire_at <= now (TTL=0 视为立即过期, 语义清晰).
        """
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expire_at = entry
        # 惰性过期检查: expire_at <= now 表示 TTL 已耗尽
        if expire_at <= time.monotonic():
            self._store.pop(key, None)
            return None
        # LRU: 移到末尾 (删除再插入)
        self._store.pop(key)
        self._store[key] = entry
        return value

    def set(self, key: str, value: Any, ttl: int) -> None:
        """写入缓存. 超过 max_size 时淘汰最旧条目."""
        expire_at = time.monotonic() + ttl
        # key 已存在时先移除以更新顺序
        self._store.pop(key, None)
        self._store[key] = (value, expire_at)
        # LRU 淘汰: 超过容量时弹出最旧的 (dict 第一个 key)
        while len(self._store) > self._max_size:
            oldest_key = next(iter(self._store))
            self._store.pop(oldest_key)

    def clear(self) -> None:
        """清空所有缓存条目 (测试/Redis 恢复时使用)."""
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


# P1-3: 全局内存回退缓存实例
_memory_cache = _MemoryTTLCache(max_size=1000)


def clear_memory_cache() -> None:
    """P1-3: 清空内存回退缓存.

    适用于测试隔离, 或 Redis 恢复后主动清除可能过期的内存条目.
    """
    _memory_cache.clear()


# 模块级共享 Redis 客户端 (懒加载, 复用连接池, 避免每次操作创建新连接)
_redis_client: aioredis.Redis | None = None
# ISS-14 修复：pubsub 订阅专用客户端单例。
# 共享客户端 socket_timeout=2 会使订阅空闲阻塞读 (pubsub.listen()) 超过 2s 时
# 抛 redis.exceptions.TimeoutError, 触发 ws.py _pubsub_loop 崩溃重启循环。
# 订阅是长空闲阻塞读, 必须用独立客户端 + socket_timeout=None, 与共享缓存客户端隔离。
_redis_pubsub_client: aioredis.Redis | None = None
# H-Core-2 修复：使用 asyncio.Lock 替代 threading.Lock，
# 避免 asyncio 上下文中使用同步锁阻塞事件循环
_redis_client_lock = asyncio.Lock()

# H-Core-3 修复：Redis 断路器状态，防止瞬时抖动引发连接重建风暴
_REDIS_FAILURE_THRESHOLD = 3  # 连续失败阈值
_REDIS_COOLDOWN_SECONDS = 30.0  # 冷却窗口(秒)
_redis_failure_count = 0
_redis_last_failure_time = 0.0


async def _get_redis_client() -> aioredis.Redis | None:
    """获取共享 Redis 客户端. 无可用 URL 返回 None.

    使用模块级单例, 首次调用时创建, 后续复用同一连接池.
    H-Core-2 修复：使用 asyncio.Lock 的双重检查模式，避免并发下重复创建客户端。
    """
    global _redis_client
    # 第一次检查（无锁，快速路径）
    if _redis_client is not None:
        return _redis_client
    # 第二次检查（加锁，确保只创建一次）
    async with _redis_client_lock:
        if _redis_client is not None:
            return _redis_client
        url = _get_redis_url()
        if not url:
            return None
        try:
            _redis_client = aioredis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
        except Exception as exc:
            logger.warning("[cache] redis client init failed: %s", exc)
            _redis_client = None
            return None
        return _redis_client


async def get_redis_pubsub_client() -> "aioredis.Redis | None":
    """ISS-14 修复：获取 pubsub 订阅专用 Redis 客户端 (socket_timeout=None)。

    与 get_redis_client 共享同一 Redis URL, 但独立连接池, 且:
      - socket_timeout=None: 订阅是长空闲阻塞读 (pubsub.listen), 绝不应有读超时;
        若沿用共享客户端的 socket_timeout=2, 空闲 >2s 即抛 TimeoutError,
        导致 ws.py _pubsub_loop 每秒崩溃重启 (ISS-14)。
      - socket_connect_timeout=2: 连接阶段仍保持短超时, 启动失败快速退出。
      - socket_keepalive=True + health_check_interval=30: 保活, 静默断线时
        周期性 PING 探测, 失败即抛 ConnectionError 触发 _pubsub_loop 重连。
      - retry_on_timeout=True: 超时自动重试 (与 socket_timeout=None 配合, 兜底)。

    该客户端仅供 ws.py 的 _pubsub_loop 使用, 不用于普通缓存读写。
    """
    global _redis_pubsub_client
    if _redis_pubsub_client is not None:
        return _redis_pubsub_client
    async with _redis_client_lock:
        if _redis_pubsub_client is not None:
            return _redis_pubsub_client
        url = _get_redis_url()
        if not url:
            return None
        try:
            _redis_pubsub_client = aioredis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=None,
                socket_keepalive=True,
                health_check_interval=30,
                retry_on_timeout=True,
            )
        except Exception as exc:
            logger.warning("[cache] redis pubsub client init failed: %s", exc)
            _redis_pubsub_client = None
            return None
        return _redis_pubsub_client


def _reset_redis_client() -> None:
    """重置 Redis 客户端单例，下次调用 _get_redis_client 时重建连接。

    H-Core-2 修复：仅做赋值操作，无需锁保护，保持同步以便在异常处理中直接调用。
    """
    global _redis_client, _redis_pubsub_client
    _redis_client = None
    _redis_pubsub_client = None


async def get_redis_client() -> "aioredis.Redis | None":
    """P1-2: 公共 API - 获取共享 Redis 客户端单例.

    所有需要直接操作 Redis 的模块 (健康检查/告警去重/任务存储等)
    应统一调用此函数, 复用同一连接池, 避免每次创建新连接.

    Returns:
        Redis 客户端实例, 无可用 URL 或初始化失败时返回 None.

    注意:
        - 调用方不应调用 client.aclose(), 否则会破坏单例复用语义.
          连接生命周期由模块统一管理 (应用关闭时由 close_redis_client 释放).
        - 失败时会通过断路器 (_should_skip_redis) 避免连接重建风暴.
    """
    return await _get_redis_client()


async def close_redis_client() -> None:
    """P1-2: 应用关闭时关闭共享 Redis 客户端, 释放连接池资源.

    应在 FastAPI lifespan 的关闭阶段调用. 调用后单例被重置,
    下次 get_redis_client() / get_redis_pubsub_client() 会重建连接
    (主要用于测试或应用重启场景).
    """
    global _redis_client, _redis_pubsub_client
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except Exception as exc:
            logger.warning("[cache] redis client aclose failed: %s", exc)
        _redis_client = None
    if _redis_pubsub_client is not None:
        try:
            await _redis_pubsub_client.aclose()
        except Exception as exc:
            logger.warning("[cache] redis pubsub client aclose failed: %s", exc)
        _redis_pubsub_client = None


def _should_skip_redis() -> bool:
    """H-Core-3 修复：断路器检查。

    连续失败次数超阈值且在冷却窗口内时返回 True，跳过 Redis 操作
    (不重置客户端也不尝试连接)，避免瞬时抖动引发连接重建风暴。
    _redis_client 被外部重置(如测试 fixture)时同步重置失败计数。
    """
    global _redis_failure_count
    if _redis_client is None and _redis_failure_count > 0:
        _redis_failure_count = 0
        return False
    if _redis_failure_count < _REDIS_FAILURE_THRESHOLD:
        return False
    # 冷却窗口已过，重置计数器并允许重试
    if time.monotonic() - _redis_last_failure_time > _REDIS_COOLDOWN_SECONDS:
        _redis_failure_count = 0
        return False
    return True


def _record_redis_failure(exc: Exception) -> None:
    """H-Core-3 修复：记录 Redis 失败，仅对连接类异常计入断路器。"""
    global _redis_failure_count, _redis_last_failure_time
    # 仅真正的连接类异常才计入断路器，应用异常(如序列化)不计入
    if not isinstance(exc, (RedisConnectionError, RedisTimeoutError)):
        return
    _redis_failure_count += 1
    _redis_last_failure_time = time.monotonic()
    logger.warning(
        "[cache] redis 连接异常 (%s), 连续失败 %d 次",
        type(exc).__name__,
        _redis_failure_count,
    )


def _record_redis_success() -> None:
    """H-Core-3 修复：操作成功时重置失败计数。"""
    global _redis_failure_count
    if _redis_failure_count > 0:
        _redis_failure_count = 0


def _get_redis_url() -> str | None:
    """从 settings 或环境变量获取 Redis URL. 无可用 URL 返回 None."""
    try:
        from app.core.config import settings

        url = settings.redis_url
        if url and url.startswith("redis"):
            return url
    except Exception as exc:
        logger.debug("settings.redis_url access failed: %s", exc)
    env_url = os.getenv("REDIS_URL")
    if env_url and env_url.startswith("redis"):
        return env_url
    return None


async def _safe_aclose(client: Any, key: str, op: str) -> None:
    """v1.36: 关闭 Redis client, 异常仅日志不抛错.

    防止 aclose 自身异常覆盖正常的 cache_get/set 返回值.
    """
    try:
        await client.aclose()
    except Exception as exc:
        logger.warning("[cache] %s aclose failed (key=%s): %s", op, key, exc)


async def cache_get(key: str) -> Any | None:
    """v1.36: 读缓存.

    P1-3: Redis 不可用 (断路器开启/无 URL/操作异常) 时回退到内存缓存,
    避免缓存击穿导致后端雪崩. Redis 可用时走 Redis, 不检查内存缓存.

    Args:
        key: cache key

    Returns:
        解析后的 Python 对象, 缓存未命中或失败返回 None
    """
    if not key:
        return None
    # H-Core-3 修复：断路器开启时直接跳过，不重置客户端也不尝试连接
    if _should_skip_redis():
        # P1-3: 断路器开启, 回退到内存缓存
        logger.debug("[cache] circuit open, fallback to memory cache")
        return _memory_cache.get(key)
    client = await _get_redis_client()
    if client is None:
        # P1-3: 无 Redis 配置, 回退到内存缓存
        logger.debug("[cache] no redis_url, fallback to memory cache")
        return _memory_cache.get(key)
    try:
        value = await client.get(key)
    except Exception as exc:
        logger.warning("[cache] get failed (key=%s): %s", key, exc)
        _record_redis_failure(exc)
        # P1-3: Redis 操作失败, 回退到内存缓存
        return _memory_cache.get(key)
    _record_redis_success()
    if value is None:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError) as exc:
        logger.warning("[cache] get parse failed (key=%s): %s", key, exc)
        return None


async def cache_set(key: str, value: Any, ttl: int = DEFAULT_CACHE_TTL) -> bool:
    """v1.36: 写缓存.

    P1-3: Redis 不可用时回退写入内存缓存, 返回 True (避免上游误判写入失败).
    Redis 可用时走 Redis, 不写入内存缓存 (避免双写不一致).

    Args:
        key: cache key
        value: 任意可序列化为 JSON 的对象
        ttl: 过期秒数 (默认 300s = 5min)

    Returns:
        成功 True, 失败 False (仅当 key/value 非法时)
    """
    if not key or value is None:
        return False
    if ttl <= 0:
        ttl = DEFAULT_CACHE_TTL
    # H-Core-3 修复：断路器开启时直接跳过，不重置客户端也不尝试连接
    if _should_skip_redis():
        # P1-3: 断路器开启, 回退写入内存缓存
        logger.debug("[cache] circuit open, fallback set to memory cache")
        _memory_cache.set(key, value, ttl)
        return True
    client = await _get_redis_client()
    if client is None:
        # P1-3: 无 Redis 配置, 回退写入内存缓存
        logger.debug("[cache] no redis_url, fallback set to memory cache")
        _memory_cache.set(key, value, ttl)
        return True
    try:
        await client.set(key, json.dumps(value), ex=ttl)
    except Exception as exc:
        logger.warning("[cache] set failed (key=%s): %s", key, exc)
        _record_redis_failure(exc)
        # P1-3: Redis 写入失败, 回退写入内存缓存 (尽力而为)
        _memory_cache.set(key, value, ttl)
        return True
    _record_redis_success()
    return True


def make_cache_key(endpoint: str, params: dict[str, Any] | None) -> str:
    """v1.36: 生成稳定 cache key.

    同 endpoint + 同 params (sort_keys) → 同 key.
    使用 sha256 前 32 字符避免过长 key.

    Args:
        endpoint: 端点名, e.g. "trend", "response-time"
        params: 参数字典, 传 None 时视为空 dict.
                调用方需保证值可被 json.dumps 序列化;
                不可序列化的类型 (datetime/Decimal/UUID 等) 应提前
                转为字符串或基本类型, 避免 key 冲突 (e.g. datetime
                与 "2026-06-01" 可能产生相同 key).

    Returns:
        形如 "obs:trend:abc123def456..."

    Raises:
        TypeError: 当 params 含不可序列化的值时 (不再静默转 str)
    """
    raw_params = params or {}
    # L-Core-4 修复：过滤 None 值，使 {"a": None} 与 {} 产生相同 key，
    # 避免调用方在 None 与缺失间漂移时缓存分裂。
    # json.dumps 已将 None 序列化为 "null"（一致），但 None 与缺失键仍产生不同 key。
    safe_params = {k: v for k, v in raw_params.items() if v is not None}
    # 显式 raise, 避免 default=str 引发 cache key 冲突
    raw = json.dumps(safe_params, sort_keys=True)
    # M-Core-4 修复：MD5 前 16 字符仅 64 bit，百万级 key 下碰撞概率非零；
    # 改用 sha256 前 32 字符（128 bit）显著降低碰撞概率。
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return f"obs:{endpoint}:{digest}"
