from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from functools import lru_cache
from time import monotonic

import redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.celery_app import celery_app

# P1-E 修复：添加 logger 记录健康检查失败原因，便于运维定位问题
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class HealthSnapshot:
    database: bool | None = None
    redis: bool | None = None
    celery_worker: bool | None = None
    collected_at: float = 0.0


async def check_database(engine: AsyncEngine) -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        # P1-E 修复：记录数据库健康检查失败原因
        logger.warning("Database health check failed", exc_info=True)
        return False


async def check_redis(redis_url: str) -> bool:
    try:
        client = redis.asyncio.from_url(redis_url)
        pong = await client.ping()
        await client.aclose()
        return bool(pong)
    except Exception:
        # P1-E 修复：记录 Redis 健康检查失败原因
        logger.warning("Redis health check failed", exc_info=True)
        return False


async def check_celery_worker(redis_url: str, timeout_seconds: float = 1.5) -> bool:
    try:
        inspect = celery_app.control.inspect(timeout=timeout_seconds)
        stats = await asyncio.to_thread(inspect.stats)
        return bool(stats)
    except Exception:
        # P1-E 修复：记录 Celery worker 健康检查失败原因
        logger.warning("Celery worker health check failed", exc_info=True)
        return False


@lru_cache(maxsize=1)
def get_health_cache_ttl_seconds() -> float:
    return 5.0


_snapshot: HealthSnapshot = HealthSnapshot()


async def get_health_snapshot(engine: AsyncEngine, redis_url: str) -> HealthSnapshot:
    global _snapshot

    now = monotonic()
    if _snapshot.collected_at and now - _snapshot.collected_at < get_health_cache_ttl_seconds():
        return _snapshot

    database, redis_ok = await asyncio.gather(check_database(engine), check_redis(redis_url))
    celery_ok = await check_celery_worker(redis_url)
    snapshot = HealthSnapshot(
        database=database,
        redis=redis_ok,
        celery_worker=celery_ok,
        collected_at=now,
    )
    _snapshot = snapshot
    return snapshot


async def lightweight_health_snapshot() -> HealthSnapshot:
    return HealthSnapshot(database=True, redis=None, celery_worker=None, collected_at=monotonic())
