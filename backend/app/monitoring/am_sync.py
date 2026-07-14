"""v1.35: AlertManager 双向同步.

机制:
- push_silence: 内部创建静默时, 推送到 AlertManager
- pull_silences: 定时从 AlertManager 拉取静默列表
- handle_am_webhook: 接收 AM 的 silence 变更事件

降级:
- AM 不可用 -> 记录失败, 本地静默仍生效
- 同步失败 -> 记录到 OperationLog, 异步重试

v1.36: 所有同步操作支持传入 db (AsyncSession), 成功/失败写入
OperationLog (action_type=am_sync_success/am_sync_failed) 用于可观测.
写日志失败不影响同步主流程返回值.

RES-P1-008/010 修复: async 函数内的同步 requests 调用改用 asyncio.to_thread
卸载到线程池 + 模块级 requests.Session 复用 TCP 连接.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

import requests

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 2  # 2 秒超时

# RES-P1-010 修复: 模块级 requests.Session 复用 TCP 连接, 避免每次请求新建连接 (1-3s 开销)
# requests.Session 内部维护连接池 (urllib3.HTTPConnectionPool), 同一 host 的后续请求复用 TCP 连接
_HTTP_SESSION = requests.Session()


def _get_am_url() -> str | None:
    """v1.35: 从环境变量获取 AlertManager URL."""
    return os.getenv("ALERTMANAGER_URL")


def _get_am_auth() -> tuple[str, str] | None:
    """v1.35: 从环境变量获取 AlertManager 认证."""
    user = os.getenv("ALERTMANAGER_USER")
    pwd = os.getenv("ALERTMANAGER_PASSWORD")
    if user and pwd:
        return (user, pwd)
    return None


async def _write_sync_log(
    db: AsyncSession | None,
    operation: str,
    success: bool,
    am_silence_id: str | None = None,
    error_msg: str | None = None,
    duration_ms: int = 0,
    extra: dict[str, Any] | None = None,
) -> None:
    """v1.36: 写入 am_sync OperationLog. 失败不影响主流程.

    Args:
        db: 可选. 传入时写入 OperationLog.
        operation: 操作名 (push_silence / delete_silence / pull_silences).
        success: 是否成功.
        am_silence_id: AM 返回的 silenceID (push/delete).
        error_msg: 失败原因.
        duration_ms: 同步耗时 (毫秒).
        extra: 额外的 detail 字段.
    """
    if db is None:
        return
    try:
        from app.models.admin import OperationLog

        action_type = "am_sync_success" if success else "am_sync_failed"
        detail_dict: dict[str, Any] = {
            "operation": operation,
            "duration_ms": duration_ms,
        }
        if am_silence_id:
            detail_dict["am_silence_id"] = am_silence_id
        if error_msg:
            detail_dict["error"] = error_msg
        if extra:
            detail_dict.update(extra)
        log = OperationLog(
            operator_id=None,
            operator_role="system",
            action_type=action_type,
            target_type="alert_silence",
            target_id=None,
            detail=json.dumps(detail_dict, ensure_ascii=False),
        )
        db.add(log)
        await db.flush()
    except Exception as exc:
        # 写日志失败不影响主流程
        logger.error(
            "[am_sync] 写 OperationLog 失败 (operation=%s, error=%s)",
            operation,
            exc,
        )


async def push_silence(
    silence: dict[str, Any],
    db: AsyncSession | None = None,
) -> dict[str, Any] | None:
    """v1.35: 推送静默规则到 AlertManager.

    v1.36: 成功/失败可写入 OperationLog (am_sync_success/am_sync_failed).

    Args:
        silence: AM 格式的静默规则, e.g.
            {
                "matchers": [{"name": "alertname", "value": "X", "isRegex": false}],
                "startsAt": "2026-06-03T00:00:00Z",
                "endsAt": "2026-06-04T00:00:00Z",
                "createdBy": "admin",
                "comment": "...",
            }
        db: v1.36 可选. 传入 AsyncSession 时, 同步结果写入 OperationLog.

    Returns:
        AM 返回的 silence 对象 (含 silenceID), 失败返回 None
    """
    url = _get_am_url()
    if not url:
        logger.debug("[am_sync] ALERTMANAGER_URL not set, skip push")
        # 未配置不写日志 (视为"未尝试")
        return None

    start = time.monotonic()
    error_msg: str | None = None
    am_silence_id: str | None = None
    result: dict[str, Any] | None = None
    try:
        # RES-P1-008 修复: 同步 requests 调用卸载到线程池, 避免阻塞事件循环
        # RES-P1-010 修复: 使用模块级 _HTTP_SESSION 复用 TCP 连接
        resp = await asyncio.to_thread(
            _HTTP_SESSION.post,
            f"{url.rstrip('/')}/api/v2/silences",
            json=silence,
            timeout=DEFAULT_TIMEOUT,
            auth=_get_am_auth(),
            headers={"Content-Type": "application/json"},
        )
        if 200 <= resp.status_code < 300:
            data = resp.json()
            am_silence_id = data.get("silenceID", "")
            logger.info("[am_sync] pushed silence to AM (id=%s)", am_silence_id)
            result = data
        else:
            error_msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
            logger.warning("[am_sync] push failed (%s)", error_msg)
    except Exception as exc:
        error_msg = str(exc)
        logger.warning("[am_sync] push exception: %s", exc)
    duration_ms = int((time.monotonic() - start) * 1000)
    await _write_sync_log(
        db=db,
        operation="push_silence",
        success=result is not None,
        am_silence_id=am_silence_id,
        error_msg=error_msg,
        duration_ms=duration_ms,
    )
    return result


async def delete_silence(
    am_silence_id: str,
    db: AsyncSession | None = None,
) -> bool:
    """v1.35: 从 AlertManager 删除静默.

    v1.36: 成功/失败可写入 OperationLog.

    Args:
        am_silence_id: AM 返回的 silenceID
        db: v1.36 可选. 传入 AsyncSession 时, 同步结果写入 OperationLog.

    Returns:
        True = 删除成功
    """
    url = _get_am_url()
    if not url or not am_silence_id:
        return False
    start = time.monotonic()
    error_msg: str | None = None
    success = False
    try:
        # RES-P1-008/010 修复: asyncio.to_thread + _HTTP_SESSION
        resp = await asyncio.to_thread(
            _HTTP_SESSION.delete,
            f"{url.rstrip('/')}/api/v2/silences/{am_silence_id}",
            timeout=DEFAULT_TIMEOUT,
            auth=_get_am_auth(),
        )
        if 200 <= resp.status_code < 300:
            logger.info("[am_sync] deleted silence from AM (id=%s)", am_silence_id)
            success = True
        else:
            error_msg = f"HTTP {resp.status_code}"
            logger.warning("[am_sync] delete failed (%s)", error_msg)
    except Exception as exc:
        error_msg = str(exc)
        logger.warning("[am_sync] delete exception: %s", exc)
    duration_ms = int((time.monotonic() - start) * 1000)
    await _write_sync_log(
        db=db,
        operation="delete_silence",
        success=success,
        am_silence_id=am_silence_id,
        error_msg=error_msg,
        duration_ms=duration_ms,
    )
    return success


async def pull_silences(
    db: AsyncSession | None = None,
) -> list[dict[str, Any]] | None:
    """v1.35: 从 AlertManager 拉取所有静默.

    v1.36: 成功/失败可写入 OperationLog.

    Args:
        db: v1.36 可选. 传入 AsyncSession 时, 同步结果写入 OperationLog.

    Returns:
        AM 返回的 silences 列表, 失败返回 None
    """
    url = _get_am_url()
    if not url:
        return None
    start = time.monotonic()
    error_msg: str | None = None
    result: list[dict[str, Any]] | None = None
    try:
        # RES-P1-008/010 修复: asyncio.to_thread + _HTTP_SESSION
        resp = await asyncio.to_thread(
            _HTTP_SESSION.get,
            f"{url.rstrip('/')}/api/v2/silences",
            timeout=DEFAULT_TIMEOUT,
            auth=_get_am_auth(),
            params={"silenced": "true"},  # 仅活跃
        )
        if 200 <= resp.status_code < 300:
            result = resp.json() or []
            logger.info("[am_sync] pulled %d silences from AM", len(result))
        else:
            error_msg = f"HTTP {resp.status_code}"
            logger.warning("[am_sync] pull failed (%s)", error_msg)
    except Exception as exc:
        error_msg = str(exc)
        logger.warning("[am_sync] pull exception: %s", exc)
    duration_ms = int((time.monotonic() - start) * 1000)
    await _write_sync_log(
        db=db,
        operation="pull_silences",
        success=result is not None,
        error_msg=error_msg,
        duration_ms=duration_ms,
        extra={"count": len(result)} if result is not None else None,
    )
    return result


def local_to_am_format(
    silence_id: int,
    name: str,
    matcher: dict,
    starts_at: datetime,
    ends_at: datetime,
    comment: str | None,
) -> dict:
    """v1.35: 本地 AlertSilence 转 AM silence 格式.

    Args:
        silence_id: 本地静默 ID
        name: 静默名称
        matcher: 本地 matcher dict
        starts_at: 开始时间
        ends_at: 结束时间
        comment: 说明

    Returns:
        AM 格式 dict
    """
    return {
        "matchers": [
            {"name": k, "value": v, "isRegex": False}
            for k, v in matcher.items()
        ],
        "startsAt": starts_at.isoformat() if starts_at else None,
        "endsAt": ends_at.isoformat() if ends_at else None,
        "createdBy": f"dws-backend:{silence_id}",
        "comment": comment or name,
    }
