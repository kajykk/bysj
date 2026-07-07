"""SEC-P1-001: JWT access token blocklist (撤销机制).

原问题:
    access_token 无撤销机制, 用户登出后 token 仍有效直到 exp 过期 (默认 2h).
    管理员降级用户角色后, 旧 token 仍以原角色访问 (最多 2h 窗口).

修复方案:
    1. Role 对比 (deps.py): JWT payload role 必须与 DB user.role 一致
    2. Token blocklist (本文件): jti 级别撤销, 登出时将 access_token jti 加入 Redis blocklist

设计:
    - 复用 cache_get/cache_set (Redis 断路器 + 内存 LRU 回退)
    - TTL = token 剩余有效期 (自动清理过期条目)
    - key: "token_blocklist:{jti}"
"""

from __future__ import annotations

import logging

from app.core.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

_BLOCKLIST_KEY_PREFIX = "token_blocklist"


def _make_key(jti: str) -> str:
    """构造 blocklist key."""
    return f"{_BLOCKLIST_KEY_PREFIX}:{jti}"


async def is_token_revoked(jti: str) -> bool:
    """检查 jti 是否在 blocklist 中.

    Args:
        jti: JWT ID (access token 的唯一标识)

    Returns:
        True 如果 jti 已被撤销, False 否则 (含 jti 为空/查询失败的情况)
    """
    if not jti:
        return False
    value = await cache_get(_make_key(jti))
    return value is not None


async def revoke_token(jti: str, ttl: int) -> bool:
    """将 jti 加入 blocklist.

    Args:
        jti: JWT ID (access token 的唯一标识)
        ttl: 过期秒数 (应设置为 token 的剩余有效期, 过期后自动清理)

    Returns:
        True 成功, False 失败 (jti 为空或 ttl 非法)
    """
    if not jti or ttl <= 0:
        return False
    success = await cache_set(_make_key(jti), {"revoked": True}, ttl=ttl)
    if success:
        logger.info("token_blocklist: revoked jti=%s ttl=%ds", jti, ttl)
    return success
