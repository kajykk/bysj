"""v1.37 T-GRAF-005: 7 个 metric 处理器.

每个 handler 负责:
1. 从 req.params 提取专属参数 (severity/bucket/group_by/channel/operation)
2. 调用对应的 v1.36 _compute_* 函数
3. 返回原始 dict (T-GRAF-006 会添加 Grafana dataframe 格式化包装)

注: handlers 在 _format_for_grafana_* 适配器可用之前返回原始 dict.
T-GRAF-006 将引入 _format_for_grafana_* 函数并改写 /query 端点.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.grafana_adapter._common import (
    _DEFAULT_BUCKET,
    _DEFAULT_GROUP_BY,
    _normalize_severity,
)


async def _trend_handler(db: AsyncSession, params: dict) -> dict:
    """v1.37 T-GRAF-005: 告警趋势 → 复用 _compute_trend."""
    from app.api.v1.observability import _compute_trend

    return await _compute_trend(
        db,
        start_time=params.get("start_time"),
        end_time=params.get("end_time"),
        bucket=params.get("bucket", _DEFAULT_BUCKET),
        severity=_normalize_severity(params.get("severity")),
        status=(
            params.get("status")
            if params.get("status") not in (None, "all", "")
            else None
        ),
        group_by=params.get("group_by", _DEFAULT_GROUP_BY),
    )


async def _response_time_handler(db: AsyncSession, params: dict) -> dict:
    """v1.37 T-GRAF-005: 响应时长 → 复用 _compute_response_time."""
    from app.api.v1.observability import _compute_response_time

    return await _compute_response_time(
        db,
        start_time=params.get("start_time"),
        end_time=params.get("end_time"),
        severity=_normalize_severity(params.get("severity")),
    )


async def _escalation_handler(db: AsyncSession, params: dict) -> dict:
    """v1.37 T-GRAF-005: 升级率 → 复用 _compute_escalation."""
    from app.api.v1.observability import _compute_escalation

    return await _compute_escalation(
        db,
        start_time=params.get("start_time"),
        end_time=params.get("end_time"),
        severity=_normalize_severity(params.get("severity")),
    )


async def _channel_stats_handler(db: AsyncSession, params: dict) -> dict:
    """v1.37 T-GRAF-005: 通道成功率 → 复用 _compute_channel_stats."""
    from app.api.v1.observability import _compute_channel_stats

    channel = params.get("channel")
    if channel in (None, "all", ""):
        channel = None
    return await _compute_channel_stats(
        db,
        start_time=params.get("start_time"),
        end_time=params.get("end_time"),
        channel=channel,
    )


async def _silence_hit_rate_handler(db: AsyncSession, params: dict) -> dict:
    """v1.37 T-GRAF-005: 静默命中率 → 复用 _compute_silence_hit_rate."""
    from app.api.v1.observability import _compute_silence_hit_rate

    return await _compute_silence_hit_rate(
        db,
        start_time=params.get("start_time"),
        end_time=params.get("end_time"),
    )


async def _am_sync_handler(db: AsyncSession, params: dict) -> dict:
    """v1.37 T-GRAF-005: AM 同步 → 复用 _compute_am_sync."""
    from app.api.v1.observability import _compute_am_sync

    operation = params.get("operation")
    if operation in (None, "all", ""):
        operation = None
    return await _compute_am_sync(
        db,
        start_time=params.get("start_time"),
        end_time=params.get("end_time"),
        operation=operation,
    )


async def _lock_stats_handler(db: AsyncSession, params: dict) -> dict:
    """v1.37 T-GRAF-005: 锁统计 → 复用 _compute_lock_stats (无时间参数)."""
    from app.api.v1.observability import _compute_lock_stats

    return await _compute_lock_stats(db)


# metric -> handler 路由表
_METRIC_HANDLERS: dict[str, Any] = {
    "trend": _trend_handler,
    "response_time": _response_time_handler,
    "escalation": _escalation_handler,
    "channel_stats": _channel_stats_handler,
    "silence_hit_rate": _silence_hit_rate_handler,
    "am_sync": _am_sync_handler,
    "lock_stats": _lock_stats_handler,
}
