from __future__ import annotations

import hashlib
import json
import logging

from app.core.cache import get_redis_client

logger = logging.getLogger(__name__)

# ISS-094: 幂等窗口 (秒). 相同 Idempotency-Key 在该窗口内重放首次响应,
# 防止 upsert 类写端点重复提交。
IDEMPOTENCY_TTL_SECONDS = 60

# SEC-FIX-2026-10-05: 占位值必须是「非法 JSON」, 才能与已 settle 的响应区分开。
# 原实现写入 "1", 而 json.loads("1") 合法返回整数 1 且不抛异常, 于是重复提交时
# begin_idempotent_call 返回 (False, 1), 调用方把整数 1 当成首次响应重放
# （admin.py 的模板/阈值/配置三处 upsert 会返回 200 {"data": 1} 而非 409）。
# 这里用带下划线前缀的字符串: 它不是合法 JSON 字面量, json.loads 必抛 ValueError,
# 且语义上自解释 —— 读到这个值即表示「前一次请求仍在处理中」。
_PENDING_PLACEHOLDER = "__PENDING__"


def make_idempotency_key(actor_id: int, client_key: str) -> str:
    """按操作者 + 客户端幂等键生成 Redis 键, 隔离不同管理员的同名幂等键."""
    digest = hashlib.sha256(
        f"{actor_id}:{client_key}".encode("utf-8")
    ).hexdigest()[:32]
    return f"admin:upsert:idem:{digest}"


async def begin_idempotent_call(key: str) -> tuple[bool, dict | None]:
    """开始幂等调用, 返回 (should_proceed, replay_result).

    - 首次执行: SETNX 占位成功 → (True, None)
    - 已完成 (键值是 JSON 对象): (False, result) 供调用方重放首次响应
    - 正在处理 (占位值): (False, None) 表示重复提交
    - Redis 不可用: 降级返回 (True, None), 不做幂等控制 (与 dedup_lock 降级策略一致)

    SEC-FIX-2026-10-05: 重放分支加了 dict 类型守卫。
    仅靠「json.loads 抛异常」来识别占位值是不够的 —— 任何合法 JSON 标量
    （如 "1"/"true"/"null" 之外的数字串）都会解析成功并被当成本次响应返回。
    settle_idempotent_call 的契约是写 dict, 因此只接受 dict, 其余一律视为
    「仍在处理中」。这与返回值类型标注 (dict | None) 也保持一致。
    """
    client = await get_redis_client()
    if client is None:
        return True, None
    try:
        existing = await client.get(key)
        if existing is not None:
            # 占位值: 明确判定为「前一次仍在处理中」, 不做 JSON 解析。
            if existing == _PENDING_PLACEHOLDER:
                return False, None
            try:
                parsed = json.loads(existing)
            except (TypeError, ValueError):
                # 非法 JSON 的历史残留值: 同样按「处理中」处理, 避免把垃圾数据
                # 返给调用方。
                return False, None
            if isinstance(parsed, dict):
                return False, parsed
            # JSON 标量/数组: 不是本模块写入的契约形态, 不重放。
            logger.warning(
                "[idempotency] 键值非 dict 契约形态, 按处理中处理 (key=%s, type=%s)",
                key,
                type(parsed).__name__,
            )
            return False, None
        if not await client.set(
            key, _PENDING_PLACEHOLDER, ex=IDEMPOTENCY_TTL_SECONDS, nx=True
        ):
            return False, None
        return True, None
    except Exception as exc:
        logger.warning("[idempotency] begin failed (key=%s): %s", key, exc)
        return True, None


async def settle_idempotent_call(key: str, result: dict) -> None:
    """请求成功后写入响应数据, 供窗口内重复请求重放.

    写入的是首次执行的真实响应 (dict), 覆盖掉 _PENDING_PLACEHOLDER 占位值。
    参数契约是 dict —— begin_idempotent_call 的重放分支也只接受 dict。
    """
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
