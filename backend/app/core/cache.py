"""v1.36: 观测 API 5min 缓存工具.

提供 Redis 缓存读写与 cache key 生成能力.
Redis 不可用时静默降级, 不影响主流程.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

DEFAULT_CACHE_TTL = 300  # 5min

# 模块级共享 Redis 客户端 (懒加载, 复用连接池, 避免每次操作创建新连接)
_redis_client: aioredis.Redis | None = None


def _get_redis_client() -> aioredis.Redis | None:
    """获取共享 Redis 客户端. 无可用 URL 返回 None.

    使用模块级单例, 首次调用时创建, 后续复用同一连接池.
    """
    global _redis_client
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

    Args:
        key: cache key

    Returns:
        解析后的 Python 对象, 缓存未命中或失败返回 None
    """
    if not key:
        return None
    client = _get_redis_client()
    if client is None:
        logger.debug("[cache] no redis_url, skip get")
        return None
    try:
        value = await client.get(key)
    except Exception as exc:
        logger.warning("[cache] get failed (key=%s): %s", key, exc)
        return None
    if value is None:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError) as exc:
        logger.warning("[cache] get parse failed (key=%s): %s", key, exc)
        return None


async def cache_set(key: str, value: Any, ttl: int = DEFAULT_CACHE_TTL) -> bool:
    """v1.36: 写缓存.

    Args:
        key: cache key
        value: 任意可序列化为 JSON 的对象
        ttl: 过期秒数 (默认 300s = 5min)

    Returns:
        成功 True, 失败 False
    """
    if not key or value is None:
        return False
    if ttl <= 0:
        ttl = DEFAULT_CACHE_TTL
    client = _get_redis_client()
    if client is None:
        logger.debug("[cache] no redis_url, skip set")
        return False
    try:
        await client.set(key, json.dumps(value), ex=ttl)
    except Exception as exc:
        logger.warning("[cache] set failed (key=%s): %s", key, exc)
        return False
    return True


def make_cache_key(endpoint: str, params: dict[str, Any] | None) -> str:
    """v1.36: 生成稳定 cache key.

    同 endpoint + 同 params (sort_keys) → 同 key.
    使用 MD5 前 16 字符避免过长 key.

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
    safe_params = params or {}
    # 显式 raise, 避免 default=str 引发 cache key 冲突
    raw = json.dumps(safe_params, sort_keys=True)
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]
    return f"obs:{endpoint}:{digest}"
