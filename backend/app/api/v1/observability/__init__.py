"""v1.36: 告警可观测性 API.

端点 (Phase 2):
- T2.1 GET /alerts/observability/health        - 健康检查
- T2.2 GET /alerts/observability/trend           - 告警趋势
- T2.3 GET /alerts/observability/response-time   - 响应时长
- T2.4 GET /alerts/observability/escalation      - 升级率
- T2.5 GET /alerts/observability/channel-stats   - 通道成功率
- T2.6 GET /alerts/observability/silence-hit-rate - 静默命中率
- T2.7 GET /alerts/observability/am-sync         - AM 同步可观测
- T2.8 GET /alerts/observability/lock-stats      - Redis 锁可观测

设计:
- 所有端点 admin 角色
- 5min Redis 缓存 (cache 工具 T0.1)
- 响应体包含 instance_id (instance 工具 T0.2)
- 写日志失败不影响主流程

模块拆分 (PERF-P1-001 后维护性优化):
- _common:    跨方言 SQL 表达式 + 规范化工具 + orjson
- query:      trend / response-time / escalation compute 函数
- aggregate:  channel-stats / silence-hit-rate / am-sync / lock-stats compute 函数
- __init__:   router + 8 端点 + cached_or_compute + with_instance_meta + re-export

patch 路径兼容:
- 所有 _compute_* 在 __init__ re-export, 测试 monkeypatch.setattr(obs_mod, "_compute_*")
  仍生效 (endpoint 的 __globals__ 即本包命名空间).
- cached_or_compute 定义在本模块, 引用的 cache_get / cache_set 同样在本模块命名空间,
  测试 monkeypatch.setattr(obs_mod, "cache_get") 生效.
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import (
    DEFAULT_CACHE_TTL,
    cache_get,
    cache_set,
    make_cache_key,
)
from app.core.database import get_db
from app.core.deps import require_role
from app.core.instance import get_instance_id
from app.core.rate_limit import limiter
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts/observability", tags=["observability"])

# ===== PERF-P1-001 性能调优常量 =====
# 强制时间范围最大跨度 (天)，超过则拒绝以避免全表扫描
MAX_TIME_RANGE_DAYS = 30
# 未传 start_time 时的默认窗口 (小时)
DEFAULT_TIME_RANGE_HOURS = 24
# 缓存 TTL 基准值 (秒)，配合抖动避免缓存雪崩 (PERF-P1-003)
CACHE_TTL_BASE = 300
# 缓存 TTL 抖动幅度 (秒)，实际 TTL = CACHE_TTL_BASE ± CACHE_TTL_JITTER
CACHE_TTL_JITTER = 60


# ===== 公共依赖 (Phase 2 端点复用) =====

# 类型别名, 减少 endpoint 签名噪音
DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminDep = Annotated[User, Depends(require_role("admin"))]


# ===== 公共工具函数 =====


def _utcnow_iso() -> str:
    """v1.36: UTC ISO 格式时间戳."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _cache_key_dt(dt: "datetime | None") -> "str | None":
    """L-API-8 修复：统一 cache key 中的 datetime isoformat 格式.

    不同 tzinfo 的 datetime 会产生不同 isoformat（如 +00:00 / Z / naive），
    导致语义等价的时间命中不同 cache key，降低缓存命中率。
    统一转换为 UTC 并去掉 tzinfo 后再 isoformat，保证相同时刻产生相同 key。
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=None).isoformat()


def _validate_time_range(
    start_time: datetime | None, end_time: datetime | None
) -> tuple[datetime, datetime]:
    """PERF-P1-001: 校验并填充时间范围参数.

    - 未传 start_time 默认为最近 DEFAULT_TIME_RANGE_HOURS 小时
    - 未传 end_time 默认为当前 UTC 时间
    - 最大范围 MAX_TIME_RANGE_DAYS 天，超过则抛 400
    - naive datetime 视为 UTC，避免 aware/naive 混用比较报错

    Returns:
        (start_time, end_time) - 均为 aware UTC datetime
    """
    now = datetime.now(timezone.utc)
    if end_time is None:
        end_time = now
    else:
        # 统一为 aware UTC
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)
        else:
            end_time = end_time.astimezone(timezone.utc)
    if start_time is None:
        start_time = end_time - timedelta(hours=DEFAULT_TIME_RANGE_HOURS)
    else:
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        else:
            start_time = start_time.astimezone(timezone.utc)
    if end_time < start_time:
        raise HTTPException(status_code=400, detail="end_time 必须大于 start_time")
    if end_time - start_time > timedelta(days=MAX_TIME_RANGE_DAYS):
        raise HTTPException(
            status_code=400,
            detail=f"时间范围不能超过 {MAX_TIME_RANGE_DAYS} 天",
        )
    return start_time, end_time


def _jittered_ttl() -> int:
    """PERF-P1-003: 返回带随机抖动的缓存 TTL.

    TTL = CACHE_TTL_BASE ± CACHE_TTL_JITTER，避免大量缓存同时过期引发雪崩.
    """
    return CACHE_TTL_BASE + random.randint(-CACHE_TTL_JITTER, CACHE_TTL_JITTER)


# M-6 修复：single-flight in-flight 表，防止 cache stampede
# 同一 cache key 的并发请求只允许一个执行 compute_fn，其他请求等待结果
_inflight_futures: dict[str, asyncio.Future[tuple[dict[str, Any], bool]]] = {}


async def cached_or_compute(
    endpoint: str,
    params: dict[str, Any] | None,
    compute_fn,
    ttl: int = DEFAULT_CACHE_TTL,
) -> tuple[dict[str, Any], bool]:
    """v1.36: 通用缓存包装 (cache hit/miss 透明).

    M-6 修复：增加 single-flight 防止 cache stampede。
    当 cache miss 时，并发请求只允许第一个执行 compute_fn，其余等待 Future 完成后复用结果。
    6 个 observability 端点共享此模式。

    Args:
        endpoint: 端点名 (用于 cache key)
        params: 参数字典 (用于 cache key)
        compute_fn: async 回调, 用于 cache miss 时计算数据
        ttl: 缓存 TTL 秒数 (默认 5min)

    Returns:
        (data, cached) - 数据 + 是否来自缓存
    """
    key = make_cache_key(endpoint, params)
    cached = await cache_get(key)
    if cached is not None:
        return cached, True

    # M-6 修复：检查是否有 in-flight 请求
    if key in _inflight_futures:
        # 已有请求在执行，等待结果（不重复计算）
        logger.debug("[cached_or_compute] single-flight wait: key=%s", key)
        # M-API-6 修复：leader 抛异常时 waiter 不直接 500，
        # 回退到旧缓存值或空结果，避免所有 waiter 连锁失败
        try:
            return await _inflight_futures[key]
        except Exception as exc:
            logger.warning(
                "[cached_or_compute] leader failed, waiter fallback to stale cache: %s",
                exc,
            )
            stale = await cache_get(key)
            if stale is not None:
                return stale, True
            return {}, False

    # 当前请求成为 leader，创建 Future 让后续请求等待
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[tuple[dict[str, Any], bool]] = loop.create_future()
    _inflight_futures[key] = fut

    try:
        data = await compute_fn()
        await cache_set(key, data, ttl=ttl)
        result = (data, False)
        # 通知所有等待者
        if not fut.done():
            fut.set_result(result)
        return result
    except Exception as exc:
        # 通知所有等待者异常
        if not fut.done():
            fut.set_exception(exc)
        raise
    finally:
        # 清理 in-flight 表（下次请求可重新触发计算）
        _inflight_futures.pop(key, None)


def with_instance_meta(
    data: dict[str, Any],
    cached: bool,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """v1.36: 统一附加 instance_id + cached 元信息.

    Args:
        data: 业务数据
        cached: 是否来自缓存
        extra: 额外顶层字段

    Returns:
        包含 instance_id / cached / timestamp 的响应体
    """
    payload: dict[str, Any] = {
        "data": data,
        "instance_id": get_instance_id(),
        "cached": cached,
        "generated_at": _utcnow_iso(),
    }
    if extra:
        payload.update(extra)
    return payload


# ===== compute 函数 re-export (patch 路径兼容) =====
# 测试通过 monkeypatch.setattr(obs_mod, "_compute_*") 替换, 必须在本模块命名空间可见.
# 端点的 __globals__ 即本模块, lambda 内引用 _compute_* 会从此处查找.
from app.api.v1.observability.aggregate import (  # noqa: E402
    _compute_am_sync,
    _compute_channel_stats,
    _compute_lock_stats,
    _compute_silence_hit_rate,
)
from app.api.v1.observability.query import (  # noqa: E402
    _compute_escalation,
    _compute_response_time,
    _compute_trend,
    _percentile,  # noqa: F401
)

# ===== T2.2 EP-1 告警趋势 =====


@router.get("/trend", response_model=dict)
@limiter.limit("30/minute")
async def get_alert_trend(
    request: Request,
    db: DbDep,
    _admin: AdminDep,
    start_time: datetime | None = Query(None, description="开始时间 (ISO 8601 UTC)"),
    end_time: datetime | None = Query(None, description="结束时间 (ISO 8601 UTC)"),
    bucket: Literal["5m", "15m", "1h", "6h", "1d"] = Query(
        "1h", description="时间桶大小"
    ),
    severity: str | None = Query(None, description="按严重度过滤 (P0/P1/P2/P3)"),
    status: str | None = Query(None, description="按状态过滤 (firing/resolved)"),
    group_by: Literal["severity", "status", "rule", "none"] = Query(
        "severity", description="聚合维度"
    ),
) -> dict[str, Any]:
    """v1.36 T2.2: 告警趋势.

    5min Redis 缓存. 返回时间桶序列 + 全量维度聚合.
    PERF-P1-001: 强制时间范围校验 + TTL 抖动.
    """
    # PERF-P1-001: 强制时间范围 (未传默认最近 24h，最大 30 天)
    start_time, end_time = _validate_time_range(start_time, end_time)
    params = {
        "start": _cache_key_dt(start_time),
        "end": _cache_key_dt(end_time),
        "bucket": bucket,
        "severity": severity,
        "status": status,
        "group_by": group_by,
    }
    data, cached = await cached_or_compute(
        endpoint="observability.trend",
        params=params,
        compute_fn=lambda: _compute_trend(
            db, start_time, end_time, bucket, severity, status, group_by
        ),
        ttl=_jittered_ttl(),  # PERF-P1-003: TTL 抖动避免雪崩
    )
    return with_instance_meta(data=data, cached=cached, extra={"params": params})


# ===== T2.3 EP-2 响应时长 =====


@router.get("/response-time", response_model=dict)
@limiter.limit("30/minute")
async def get_response_time(
    request: Request,
    db: DbDep,
    _admin: AdminDep,
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    severity: str | None = Query(None, description="按严重度过滤"),
) -> dict[str, Any]:
    """v1.36 T2.3: 告警响应时长.

    5min Redis 缓存. 返回 fired/acked/pending 统计 + mean/p50/p95/p99 分位.
    PERF-P1-001: 强制时间范围校验 + TTL 抖动.
    """
    # PERF-P1-001: 强制时间范围 (未传默认最近 24h，最大 30 天)
    start_time, end_time = _validate_time_range(start_time, end_time)
    params = {
        "start": _cache_key_dt(start_time),
        "end": _cache_key_dt(end_time),
        "severity": severity,
    }
    data, cached = await cached_or_compute(
        endpoint="observability.response-time",
        params=params,
        compute_fn=lambda: _compute_response_time(db, start_time, end_time, severity),
        ttl=_jittered_ttl(),  # PERF-P1-003: TTL 抖动避免雪崩
    )
    return with_instance_meta(data=data, cached=cached, extra={"params": params})


# ===== T2.4 EP-3 升级率 =====


@router.get("/escalation", response_model=dict)
@limiter.limit("30/minute")
async def get_escalation(
    request: Request,
    db: DbDep,
    _admin: AdminDep,
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    severity: str | None = Query(None, description="按严重度过滤"),
) -> dict[str, Any]:
    """v1.36 T2.4: 告警升级率.

    5min Redis 缓存. 返回总升级率 + by_level + by_severity + by_rule (Top-20).
    PERF-P1-001: 强制时间范围校验 + TTL 抖动.
    """
    # PERF-P1-001: 强制时间范围 (未传默认最近 24h，最大 30 天)
    start_time, end_time = _validate_time_range(start_time, end_time)
    params = {
        "start": _cache_key_dt(start_time),
        "end": _cache_key_dt(end_time),
        "severity": severity,
    }
    data, cached = await cached_or_compute(
        endpoint="observability.escalation",
        params=params,
        compute_fn=lambda: _compute_escalation(db, start_time, end_time, severity),
        ttl=_jittered_ttl(),  # PERF-P1-003: TTL 抖动避免雪崩
    )
    return with_instance_meta(data=data, cached=cached, extra={"params": params})


# ===== T2.5 EP-4 通道成功率 =====


@router.get("/channel-stats", response_model=dict)
@limiter.limit("30/minute")
async def get_channel_stats(
    request: Request,
    db: DbDep,
    _admin: AdminDep,
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    channel: str | None = Query(
        None, description="按通道过滤 (webhook/slack/dingtalk/email)"
    ),
) -> dict[str, Any]:
    """v1.36 T2.5: 通道发送成功率.

    5min Redis 缓存. 返回各通道 sent/failed/success_rate/avg_duration_ms.
    PERF-P1-001: 强制时间范围校验 + TTL 抖动.
    """
    # PERF-P1-001: 强制时间范围 (未传默认最近 24h，最大 30 天)
    start_time, end_time = _validate_time_range(start_time, end_time)
    params = {
        "start": _cache_key_dt(start_time),
        "end": _cache_key_dt(end_time),
        "channel": channel,
    }
    data, cached = await cached_or_compute(
        endpoint="observability.channel-stats",
        params=params,
        compute_fn=lambda: _compute_channel_stats(db, start_time, end_time, channel),
        ttl=_jittered_ttl(),  # PERF-P1-003: TTL 抖动避免雪崩
    )
    return with_instance_meta(data=data, cached=cached, extra={"params": params})


# ===== T2.6 EP-5 静默命中率 =====


@router.get("/silence-hit-rate", response_model=dict)
@limiter.limit("30/minute")
async def get_silence_hit_rate(
    request: Request,
    db: DbDep,
    _admin: AdminDep,
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
) -> dict[str, Any]:
    """v1.36 T2.6: 静默命中率.

    5min Redis 缓存. 返回 silenced / (fired + silenced) + by_matcher + by_severity.
    PERF-P1-001: 强制时间范围校验 + TTL 抖动.
    """
    # PERF-P1-001: 强制时间范围 (未传默认最近 24h，最大 30 天)
    start_time, end_time = _validate_time_range(start_time, end_time)
    params = {
        "start": _cache_key_dt(start_time),
        "end": _cache_key_dt(end_time),
    }
    data, cached = await cached_or_compute(
        endpoint="observability.silence-hit-rate",
        params=params,
        compute_fn=lambda: _compute_silence_hit_rate(db, start_time, end_time),
        ttl=_jittered_ttl(),  # PERF-P1-003: TTL 抖动避免雪崩
    )
    return with_instance_meta(data=data, cached=cached, extra={"params": params})


# ===== T2.7 EP-6 AM 同步可观测 =====


@router.get("/am-sync", response_model=dict)
@limiter.limit("30/minute")
async def get_am_sync(
    request: Request,
    db: DbDep,
    _admin: AdminDep,
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    operation: str | None = Query(
        None, description="按操作过滤 (push_silence/delete_silence/pull_silences)"
    ),
) -> dict[str, Any]:
    """v1.36 T2.7: AlertManager 同步可观测.

    5min Redis 缓存. 返回 success/failed/total/success_rate + by_operation
    + avg_duration_ms + recent_failures (最近 10 条).
    PERF-P1-001: 强制时间范围校验 + TTL 抖动.
    """
    # PERF-P1-001: 强制时间范围 (未传默认最近 24h，最大 30 天)
    start_time, end_time = _validate_time_range(start_time, end_time)
    params = {
        "start": _cache_key_dt(start_time),
        "end": _cache_key_dt(end_time),
        "operation": operation,
    }
    data, cached = await cached_or_compute(
        endpoint="observability.am-sync",
        params=params,
        compute_fn=lambda: _compute_am_sync(db, start_time, end_time, operation),
        ttl=_jittered_ttl(),  # PERF-P1-003: TTL 抖动避免雪崩
    )
    return with_instance_meta(data=data, cached=cached, extra={"params": params})


# ===== T2.8 EP-7 Redis 锁可观测 =====


@router.get("/lock-stats", response_model=dict)
@limiter.limit("30/minute")
async def get_lock_stats(
    request: Request,
    db: DbDep,
    _admin: AdminDep,
) -> dict[str, Any]:
    """v1.36 T2.8: Redis 锁可观测.

    5min Redis 缓存. 返回内存统计 + 上次 flush 时间 + 最近 10 条 flush 日志.
    PERF-P1-003: TTL 抖动避免雪崩.
    """
    data, cached = await cached_or_compute(
        endpoint="observability.lock-stats",
        params={},
        compute_fn=lambda: _compute_lock_stats(db),
        ttl=_jittered_ttl(),  # PERF-P1-003: TTL 抖动避免雪崩
    )
    return with_instance_meta(data=data, cached=cached, extra={})


# ===== T2.1 健康检查 (用于验证路由注册成功) =====


@router.get("/health", response_model=dict)
@limiter.limit("30/minute")
async def observability_health(
    request: Request,
    _admin: AdminDep,
) -> dict[str, Any]:
    """v1.36 T2.1: 路由骨架健康检查.

    返回:
    - instance_id: 当前实例标识
    - endpoint: "observability"
    - status: "ok"
    - timestamp: ISO 8601 UTC
    """
    return with_instance_meta(
        data={
            "endpoint": "observability",
            "status": "ok",
            "version": "v1.36",
        },
        cached=False,
    )
