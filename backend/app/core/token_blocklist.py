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

SEC-FIX (H1): 原实现 fail-open——Redis 故障时 cache_get 回退进程内缓存,
多 worker 部署下 A 节点撤销的 token 在 B 节点仍被接受, 且登出静默报告成功.
现改为 strict 模式: Redis 已配置但不可用时, 撤销状态检查失败关闭 (视为已撤销,
拒绝请求), 撤销写入失败时返回 False 并记录 ERROR 日志.
"""

from __future__ import annotations

import logging

from app.core.cache import CacheUnavailableError, cache_get, cache_set

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
        True 如果 jti 已被撤销, False 否则 (含 jti 为空的情况).

    Raises:
        CacheUnavailableError: Redis 已配置但不可用时向上抛出,
        由 deps.py 转为 503 (认证服务暂时不可用), 与"token 已被撤销"
        的 401 语义区分, 避免基础设施故障被误报为撤销事件。
        失败关闭语义不变: 请求依然被拒绝, 只是状态码/文案准确。
    """
    if not jti:
        return False
    value = await cache_get(_make_key(jti), strict=True)
    return value is not None


async def revoke_token(jti: str, ttl: int) -> bool:
    """将 jti 加入 blocklist.

    Args:
        jti: JWT ID (access token 的唯一标识)
        ttl: 过期秒数 (应设置为 token 的剩余有效期, 过期后自动清理)

    Returns:
        True 成功, False 失败 (jti 为空/ttl 非法/Redis 不可用).
        SEC-FIX (H1): Redis 已配置但不可用时返回 False 并记录 ERROR,
        不再静默假装撤销成功 (仅单进程开发模式允许内存回退).
    """
    if not jti or ttl <= 0:
        return False
    try:
        success = await cache_set(_make_key(jti), {"revoked": True}, ttl=ttl, strict=True)
    except CacheUnavailableError:
        logger.error(
            "token_blocklist: redis unavailable, revoke failed for jti=%s "
            "(token remains valid on other workers until exp)", jti[:12]
        )
        return False
    if success:
        # L-20 风格: 日志截断 jti, 与 auth_service 的 [:12] 截断策略一致
        logger.info("token_blocklist: revoked jti=%s ttl=%ds", jti[:12], ttl)
    return success
