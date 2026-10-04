"""Phase 3 模型预测暂停开关（Kill Switch）.

按 Phase 3 计划要求：
- "设置暂停开关，不允许模型输出自动触发惩罚性或医疗决定"
- "发生危机事件、安全事件或重大误判时立即暂停相关能力并复盘"

特性：
- Redis 优先存储状态（支持多实例同步）
- 暂停时所有预测端点返回 503
- 记录暂停原因、操作人、时间戳
- 审计日志通过 OperationLog 记录
- AUDIT-2026-10-01 (P1-7)：Redis 不可用时**不再静默降级为「未暂停」**
    · fail-closed（生产默认 / ``KILL_SWITCH_FAIL_MODE=closed``）：视为已暂停，
      且写入操作抛 ``KillSwitchUnavailableError``（不返回假成功）
    · fail-open（开发/测试 / ``KILL_SWITCH_FAIL_MODE=open``）：沿用进程内内存状态，
      记 critical 日志 + ``kill_switch_degraded_total`` 指标
    · 两种模式都在状态里返回 ``degraded=True`` / ``source``，以区分
      「确认未暂停」与「不知道」

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

# AUDIT-2026-10-01 (P1-7)：降级告警节流（秒）。
# Redis 整体不可用时，每个预测端点每 5s 缓存过期就会走一次降级路径，
# 不做节流的话会瞬间刷出成百上千条同样的 error 日志，反而淹没真正的告警。
_DEGRADED_LOG_INTERVAL = 60.0
_last_degraded_log_at: float = -1.0


class KillSwitchUnavailableError(RuntimeError):
    """无法确认/写入 Kill Switch 权威状态（Redis 不可用）且处于 fail-closed 模式。

    AUDIT-2026-10-01 (P1-7)：原实现在 Redis 写失败时静默降级到进程内内存并返回
    「设置成功」。多实例部署下这意味着：运维在 A 实例按下暂停，B/C 实例照常预测，
    而操作界面显示「已暂停」—— 一个「看起来成功的失败」。
    """

    def __init__(self, op: str, message: str | None = None) -> None:
        self.op = op
        super().__init__(
            message
            or (
                f"Kill Switch 无法执行 {op}：Redis 不可用，且当前处于 fail-closed 模式。"
                "未写入任何状态——返回成功会让多实例部署下的暂停/恢复静默失效。"
            )
        )


def _fail_closed() -> bool:
    """Redis 不可用时是否按「已暂停」处理。

    唯一判定入口是 ``settings.kill_switch_fail_closed``（见 config.py），
    避免本模块各处重复写 app_env 判断而漂移。
    """
    from app.core.config import settings

    return bool(settings.kill_switch_fail_closed)


def _record_degraded(op: str, exc: BaseException | None) -> None:
    """记录降级事件：节流后的 critical 日志 + Prometheus 计数器。"""
    global _last_degraded_log_at

    now = time.monotonic()
    should_log = (
        _last_degraded_log_at < 0 or (now - _last_degraded_log_at) >= _DEGRADED_LOG_INTERVAL
    )
    if should_log:
        _last_degraded_log_at = now
        logger.error(
            "Kill switch 降级：无法%s权威状态（Redis 不可用，fail_closed=%s）%s",
            "读取" if op == "read" else "写入",
            _fail_closed(),
            f" err={exc!r}" if exc is not None else "",
        )
    try:
        from app.core.metrics import kill_switch_degraded_total

        kill_switch_degraded_total.inc(op=op)
    except Exception:  # noqa: BLE001  指标不可用时不得影响主判定路径
        logger.debug("Kill switch: 记录降级指标失败（忽略）")


async def _get_redis() -> Any:
    """获取共享 Redis 客户端，不可用时返回 None."""
    try:
        from app.core.cache import get_redis_client

        return await get_redis_client()
    except Exception as exc:
        logger.debug("Kill switch: Redis unavailable: %s", exc)
        return None


def _degrade(now: float) -> bool:
    """Redis 不可用时的降级判定，并把结果写入本地缓存。

    AUDIT-2026-10-01 (P1-7)：两种模式的区别只在「无法确认时选哪一边」，
    但**都必须如实标记 degraded**，因为「按内存放行」和「权威地未暂停」
    是两件不同的事，前端/运维必须能分辨。
    """
    global _local_cache, _local_cache_expire_at

    if _fail_closed():
        # 无法确认 = 不放行。安全开关的默认值必须是「安全侧」。
        state: dict[str, Any] = {
            **_memory_state,
            "paused": True,
            "degraded": True,
            "source": "unavailable",
            "reason": (
                _memory_state.get("reason")
                or "无法确认暂停状态（Redis 不可用），按 fail-closed 视为已暂停"
            ),
        }
    else:
        state = {**_memory_state, "degraded": True, "source": "memory"}

    _local_cache = state
    _local_cache_expire_at = now + _LOCAL_CACHE_TTL
    return bool(state.get("paused", False))


async def is_model_paused() -> bool:
    """检查模型预测是否已暂停.

    使用本地缓存（TTL=5s）减少 Redis 查询频率。

    AUDIT-2026-10-01 (P1-7) 修复：Redis 不可用时**不再无条件降级为「未暂停」**。
    原实现回退到进程内 ``_memory_state``（默认 ``paused=False``）即放行，这在多实例
    部署下等于「暂停开关静默失效」。现在：
      - fail-closed 模式（生产默认 / ``KILL_SWITCH_FAIL_MODE=closed``）→ 返回 True；
      - fail-open 模式（开发/测试）→ 沿用内存状态，但记 critical 日志 + 降级指标。

    Returns:
        True 如果应阻止预测（已暂停，或无法确认且处于 fail-closed 模式）
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
                state: dict[str, Any] = json.loads(data)
                state["degraded"] = False
                state["source"] = "redis"
            else:
                # Redis 中无记录 —— 这是「权威地未暂停」，不是降级，必须标记为非 degraded
                state = {"paused": False, "degraded": False, "source": "redis"}
            _local_cache = state
            _local_cache_expire_at = now + _LOCAL_CACHE_TTL
            return bool(state.get("paused", False))
        except Exception as exc:
            _record_degraded("read", exc)
            return _degrade(now)

    # Redis 客户端本身不可用
    _record_degraded("read", None)
    return _degrade(now)


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
        "degraded": False,
        "source": "redis",
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
            _record_degraded("write", exc)
            if _fail_closed():
                # 无法确认 = 不允许声称成功。返回成功会让多实例下的暂停静默失效。
                raise KillSwitchUnavailableError("write") from exc
            return _write_memory(state, admin_id, paused, reason)

    # Redis 客户端本身不可用
    _record_degraded("write", None)
    if _fail_closed():
        raise KillSwitchUnavailableError("write")
    return _write_memory(state, admin_id, paused, reason)


def _write_memory(
    state: dict[str, Any], admin_id: int, paused: bool, reason: str | None
) -> dict[str, Any]:
    """写入进程内内存（仅 fail-open 模式可达），并如实标记 degraded。

    现状保留是因为：单实例部署 / 无 Redis 的开发环境下，内存写入确实是有效的；
    此时正确做法不是拒绝，而是让调用方看到 ``source="memory"`` 知道它只对本实例生效。
    """
    global _local_cache, _local_cache_expire_at

    state["degraded"] = True
    state["source"] = "memory"
    _memory_state.update(state)
    _local_cache = _memory_state.copy()
    _local_cache_expire_at = time.monotonic() + _LOCAL_CACHE_TTL
    logger.warning(
        "Kill switch %s by admin %s (memory mode: 仅本实例生效): %s",
        "ACTIVATED" if paused else "DEACTIVATED",
        admin_id,
        reason or "no reason given",
    )
    return state


def _degraded_status() -> dict[str, Any]:
    """Redis 不可用时的状态表示（供 get_kill_switch_status 使用）。"""
    if _fail_closed():
        return {
            **_memory_state,
            "paused": True,
            "degraded": True,
            "source": "unavailable",
            "reason": (
                _memory_state.get("reason")
                or "无法确认暂停状态（Redis 不可用），按 fail-closed 视为已暂停"
            ),
        }
    return {**_memory_state, "degraded": True, "source": "memory"}


async def get_kill_switch_status() -> dict[str, Any]:
    """获取暂停开关的完整状态.

    AUDIT-2026-10-01 (P1-7) 新增两个字段，用于区分「确认未暂停」与「不知道」：
      - ``degraded``: True 表示当前状态**不是**权威状态（Redis 不可用）
      - ``source``: "redis"（权威） | "memory"（仅本进程） | "unavailable"（无法确认）

    没有这两个字段时，Redis 挂掉会让运维看到一个「未暂停」，而实际是「不知道」——
    这正是安全开关最危险的呈现方式。

    Returns:
        状态字典：paused, reason, activated_by, activated_at, updated_at, degraded, source
    """
    # 直接查询 Redis 获取最新状态（状态查询不走缓存）
    redis = await _get_redis()
    if redis is not None:
        try:
            data = await redis.get(_REDIS_KEY)
            if data:
                state: dict[str, Any] = json.loads(data)
                state["degraded"] = False
                state["source"] = "redis"
                return state
            return {
                "paused": False,
                "reason": None,
                "activated_by": None,
                "activated_at": None,
                "updated_at": None,
                "degraded": False,
                "source": "redis",
            }
        except Exception as exc:
            _record_degraded("read", exc)
            return _degraded_status()

    # Redis 客户端本身不可用
    _record_degraded("read", None)
    return _degraded_status()


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
