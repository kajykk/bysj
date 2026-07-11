"""Phase 3 模型预测暂停开关（Kill Switch）.

按 Phase 3 计划要求：
- "设置暂停开关，不允许模型输出自动触发惩罚性或医疗决定"
- "发生危机事件、安全事件或重大误判时立即暂停相关能力并复盘"

特性：
- Redis 优先存储状态（支持多实例同步），内存降级
- 暂停时所有预测端点返回 503
- 记录暂停原因、操作人、时间戳
- 审计日志通过 OperationLog 记录

使用方式：
    from app.core.kill_switch import is_model_paused

    if await is_model_paused():
        raise HTTPException(503, "模型预测服务已暂停")
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Redis Key
_REDIS_KEY = "model:kill_switch"
# 本地降级缓存 TTL（秒）：避免每次预测都查 Redis
_LOCAL_CACHE_TTL = 5
# 内存降级状态（Redis 不可用时使用）
_memory_state: dict[str, Any] = {
    "paused": False,
    "reason": None,
    "activated_by": None,
    "activated_at": None,
}
# 本地缓存（减少 Redis 查询频率）
_local_cache: dict[str, Any] | None = None
_local_cache_expire_at: float = 0.0


async def _get_redis() -> Any:
    """获取共享 Redis 客户端，不可用时返回 None."""
    try:
        from app.core.cache import get_redis_client

        return await get_redis_client()
    except Exception as exc:
        logger.debug("Kill switch: Redis unavailable: %s", exc)
        return None


async def is_model_paused() -> bool:
    """检查模型预测是否已暂停.

    使用本地缓存（TTL=5s）减少 Redis 查询频率。
    Redis 不可用时降级到内存状态。

    Returns:
        True 如果模型预测已暂停
    """
    global _local_cache, _local_cache_expire_at

    # 先检查本地缓存
    now = time.monotonic()
    if _local_cache is not None and now < _local_cache_expire_at:
        return bool(_local_cache.get("paused", False))

    # 缓存未命中或过期，查询 Redis
    redis = await _get_redis()
    if redis is not None:
        try:
            data = await redis.get(_REDIS_KEY)
            if data:
                state = json.loads(data)
                _local_cache = state
                _local_cache_expire_at = now + _LOCAL_CACHE_TTL
                return bool(state.get("paused", False))
            else:
                # Redis 中无记录，状态为未暂停
                _local_cache = {"paused": False}
                _local_cache_expire_at = now + _LOCAL_CACHE_TTL
                return False
        except Exception as exc:
            logger.warning("Kill switch: Redis read failed, using memory: %s", exc)

    # Redis 不可用，使用内存降级
    _local_cache = _memory_state.copy()
    _local_cache_expire_at = now + _LOCAL_CACHE_TTL
    return bool(_memory_state.get("paused", False))


async def set_model_paused(
    paused: bool,
    admin_id: int,
    reason: str | None = None,
) -> dict[str, Any]:
    """设置模型预测暂停状态.

    Args:
        paused: True 暂停，False 恢复
        admin_id: 操作管理员 ID
        reason: 暂停/恢复原因

    Returns:
        当前状态字典
    """
    global _local_cache, _local_cache_expire_at

    now_iso = datetime.now(timezone.utc).isoformat()
    state: dict[str, Any] = {
        "paused": paused,
        "reason": reason,
        "activated_by": admin_id if paused else None,
        "activated_at": now_iso if paused else None,
        "updated_at": now_iso,
    }

    # 写入 Redis
    redis = await _get_redis()
    if redis is not None:
        try:
            await redis.set(_REDIS_KEY, json.dumps(state))
            # 立即更新本地缓存
            _local_cache = state.copy()
            _local_cache_expire_at = time.monotonic() + _LOCAL_CACHE_TTL
            logger.warning(
                "Kill switch %s by admin %s: %s",
                "ACTIVATED" if paused else "DEACTIVATED",
                admin_id,
                reason or "no reason given",
            )
            return state
        except Exception as exc:
            logger.warning("Kill switch: Redis write failed, using memory: %s", exc)

    # Redis 不可用，写入内存
    _memory_state.update(state)
    _local_cache = _memory_state.copy()
    _local_cache_expire_at = time.monotonic() + _LOCAL_CACHE_TTL
    logger.warning(
        "Kill switch %s by admin %s (memory mode): %s",
        "ACTIVATED" if paused else "DEACTIVATED",
        admin_id,
        reason or "no reason given",
    )
    return state


async def get_kill_switch_status() -> dict[str, Any]:
    """获取暂停开关的完整状态.

    Returns:
        状态字典：paused, reason, activated_by, activated_at, updated_at
    """
    global _local_cache, _local_cache_expire_at

    # 直接查询 Redis 获取最新状态（状态查询不走缓存）
    redis = await _get_redis()
    if redis is not None:
        try:
            data = await redis.get(_REDIS_KEY)
            if data:
                return json.loads(data)
            return {
                "paused": False,
                "reason": None,
                "activated_by": None,
                "activated_at": None,
                "updated_at": None,
            }
        except Exception as exc:
            logger.warning("Kill switch: Redis status read failed: %s", exc)

    # 内存降级
    return _memory_state.copy()


def invalidate_local_cache() -> None:
    """清除本地缓存（测试用）."""
    global _local_cache, _local_cache_expire_at
    _local_cache = None
    _local_cache_expire_at = 0.0


def reset_memory_state() -> None:
    """重置内存状态（测试用）."""
    global _memory_state, _local_cache, _local_cache_expire_at
    _memory_state = {
        "paused": False,
        "reason": None,
        "activated_by": None,
        "activated_at": None,
    }
    _local_cache = None
    _local_cache_expire_at = 0.0
