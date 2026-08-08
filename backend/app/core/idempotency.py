from __future__ import annotations

import hashlib
import json
import logging

from app.core.cache import get_redis_client

logger = logging.getLogger(__name__)

# ISS-094: 幂等窗口 (秒). 相同 Idempotency-Key 在该窗口内重放首次响应,
# 防止 upsert 类写端点重复提交。
IDEMPOTENCY_TTL_SECONDS = 60


def make_idempotency_key(actor_id: int, client_key: str) -> str:
    """按操作者 + 客户端幂等键生成 Redis 键, 隔离不同管理员的同名幂等键."""
    digest = hashlib.sha256(
        f"{actor_id}:{client_key}".encode("utf-8")
    ).hexdigest()[:32]
    return f"admin:upsert:idem:{digest}"


async def begin_idempotent_call(key: str) -> tuple[bool, dict | None]:
    """开始幂等调用, 返回 (should_proceed, replay_result).

    - 首次执行: SETNX 占位成功 → (True, None)
    - 已完成 (键值可解析为 JSON): (False, result) 供调用方重放首次响应
    - 正在处理 (占位值非 JSON): (False, None) 表示重复提交
    - Redis 不可用: 降级返回 (True, None), 不做幂等控制 (与 dedup_lock 降级策略一致)
    """
    client = await get_redis_client()
    if client is None:
        return True, None
    try:
        existing = await client.get(key)
        if existing is not None:
            try:
                return False, json.loads(existing)
            except (TypeError, ValueError):
                return False, None
        if not await client.set(key, "1", ex=IDEMPOTENCY_TTL_SECONDS, nx=True):
            return False, None
        return True, None
    except Exception as exc:
        logger.warning("[idempotency] begin failed (key=%s): %s", key, exc)
        return True, None


async def settle_idempotent_call(key: str, result: dict) -> None:
    """请求成功后写入响应数据, 供窗口内重复请求重放."""
    client = await get_redis_client()
    if client is None:
        return
    try:
        await client.set(
            key, json.dumps(result, ensure_ascii=False), ex=IDEMPOTENCY_TTL_SECONDS
        )
    except Exception as exc:
        logger.warning("[idempotency] settle failed (key=%s): %s", key, exc)


async def dismiss_idempotent_call(key: str) -> None:
    """请求失败后释放幂等键, 允许客户端修正后重试."""
    client = await get_redis_client()
    if client is None:
        return
    try:
        await client.delete(key)
    except Exception as exc:
        logger.warning("[idempotency] dismiss failed (key=%s): %s", key, exc)
