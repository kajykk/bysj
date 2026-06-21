"""v1.36: 告警可观测性 API.

端点 (Phase 2):
- T2.2 GET /alerts/observability/trend        - 告警趋势
- T2.3 GET /alerts/observability/response-time - 响应时长
- T2.4 GET /alerts/observability/escalation-rate - 升级率
- T2.5 GET /alerts/observability/channels     - 通道成功率
- T2.6 GET /alerts/observability/silence-hit-rate - 静默命中率
- T2.7 GET /alerts/observability/am-sync      - AM 同步可观测
- T2.8 GET /alerts/observability/lock-stats   - Redis 锁可观测

设计:
- 所有端点 admin 角色
- 5min Redis 缓存 (cache 工具 T0.1)
- 响应体包含 instance_id (instance 工具 T0.2)
- 写日志失败不影响主流程
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, desc, func, select
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
from app.models.admin import OperationLog
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts/observability", tags=["observability"])


# ===== 公共依赖 (Phase 2 端点复用) =====

# 类型别名, 减少 endpoint 签名噪音
DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminDep = Annotated[User, Depends(require_role("admin"))]


# ===== 公共工具函数 =====


def _utcnow_iso() -> str:
    """v1.36: UTC ISO 格式时间戳."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def cached_or_compute(
    endpoint: str,
    params: dict[str, Any] | None,
    compute_fn,
    ttl: int = DEFAULT_CACHE_TTL,
) -> tuple[dict[str, Any], bool]:
    """v1.36: 通用缓存包装 (cache hit/miss 透明).

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
    data = await compute_fn()
    await cache_set(key, data, ttl=ttl)
    return data, False


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


# ===== T2.2 EP-1 告警趋势 =====


_ALERT_ACTIONS = ("alert_fired", "alert_resolved")
_BUCKET_SECONDS = {
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "6h": 21600,
    "1d": 86400,
}


def _bucket_key(ts: datetime, bucket: str) -> str:
    """v1.36: 将 timestamp 向下对齐到 bucket 边界."""
    secs = _BUCKET_SECONDS[bucket]
    epoch = int(ts.timestamp())
    bucket_epoch = epoch - (epoch % secs)
    return datetime.fromtimestamp(bucket_epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")


async def _compute_trend(
    db: AsyncSession,
    start_time: datetime | None,
    end_time: datetime | None,
    bucket: str,
    severity: str | None,
    status: str | None,
    group_by: str,
) -> dict[str, Any]:
    """v1.36 T2.2: 计算告警趋势.

    数据源: OperationLog WHERE action_type IN ('alert_fired', 'alert_resolved')
            AND target_type = 'alert'

    返回:
        buckets: 时间桶序列 (按时间升序)
        total: 总条数
        by_severity / by_status / by_rule: 全量聚合 (依赖 group_by)
    """
    conditions = [
        OperationLog.action_type.in_(_ALERT_ACTIONS),
        OperationLog.target_type == "alert",
    ]
    if start_time:
        conditions.append(OperationLog.created_at >= start_time)
    if end_time:
        conditions.append(OperationLog.created_at <= end_time)

    stmt = (
        select(OperationLog.action_type, OperationLog.created_at, OperationLog.detail)
        .where(and_(*conditions))
        .order_by(desc(OperationLog.created_at))
        .limit(10000)  # 兜底, 防止 OOM
    )
    rows = (await db.execute(stmt)).all()

    buckets: dict[str, dict[str, Any]] = {}
    by_severity: Counter[str] = Counter()
    by_status: Counter[str] = Counter()
    by_rule: Counter[str] = Counter()
    total = 0

    for action_type, created_at, detail_json in rows:
        try:
            detail = json.loads(detail_json) if detail_json else {}
        except Exception:
            detail = {}

        sev = detail.get("severity", "unknown")
        rule = detail.get("rule", "unknown")
        # action_type='alert_fired' -> status='firing'
        # action_type='alert_resolved' -> status='resolved'
        st = "firing" if action_type == "alert_fired" else "resolved"

        # 后置过滤 severity/status
        if severity and sev != severity:
            continue
        if status and st != status:
            continue

        # 桶聚合
        bk = _bucket_key(created_at, bucket)
        slot = buckets.setdefault(
            bk, {"timestamp": bk, "count": 0, "by_severity": {}, "by_status": {}}
        )
        slot["count"] += 1
        slot["by_severity"][sev] = slot["by_severity"].get(sev, 0) + 1
        slot["by_status"][st] = slot["by_status"].get(st, 0) + 1

        # 全量聚合
        by_severity[sev] += 1
        by_status[st] += 1
        by_rule[rule] += 1
        total += 1

    return {
        "buckets": [buckets[k] for k in sorted(buckets.keys())],
        "total": total,
        "by_severity": dict(by_severity),
        "by_status": dict(by_status),
        "by_rule": dict(by_rule.most_common(20)),  # Top-20 规则
        "group_by": group_by,
        "bucket": bucket,
    }


@router.get("/trend", response_model=dict)
async def get_alert_trend(
    db: DbDep,
    _admin: AdminDep,
    start_time: datetime | None = Query(
        None, description="开始时间 (ISO 8601 UTC)"
    ),
    end_time: datetime | None = Query(
        None, description="结束时间 (ISO 8601 UTC)"
    ),
    bucket: Literal["5m", "15m", "1h", "6h", "1d"] = Query(
        "1h", description="时间桶大小"
    ),
    severity: str | None = Query(
        None, description="按严重度过滤 (P0/P1/P2/P3)"
    ),
    status: str | None = Query(
        None, description="按状态过滤 (firing/resolved)"
    ),
    group_by: Literal["severity", "status", "rule", "none"] = Query(
        "severity", description="聚合维度"
    ),
) -> dict[str, Any]:
    """v1.36 T2.2: 告警趋势.

    5min Redis 缓存. 返回时间桶序列 + 全量维度聚合.
    """
    params = {
        "start": start_time.isoformat() if start_time else None,
        "end": end_time.isoformat() if end_time else None,
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
        ttl=DEFAULT_CACHE_TTL,
    )
    return with_instance_meta(
        data=data, cached=cached, extra={"params": params}
    )


# ===== T2.3 EP-2 响应时长 =====


def _percentile(sorted_values: list[float], p: float) -> float:
    """v1.36: 计算 p 分位 (p in [0, 100])."""
    if not sorted_values:
        return 0.0
    if p <= 0:
        return sorted_values[0]
    if p >= 100:
        return sorted_values[-1]
    n = len(sorted_values)
    # 线性插值
    rank = (p / 100) * (n - 1)
    lower = int(rank)
    upper = min(lower + 1, n - 1)
    frac = rank - lower
    return sorted_values[lower] * (1 - frac) + sorted_values[upper] * frac


async def _compute_response_time(
    db: AsyncSession,
    start_time: datetime | None,
    end_time: datetime | None,
    severity: str | None,
) -> dict[str, Any]:
    """v1.36 T2.3: 计算告警响应时长 (fired -> acknowledged).

    实现:
    1. 拉取 alert_fired (fingerprint, created_at, detail)
    2. 拉取 alert_acknowledged (fingerprint, created_at)
    3. self-JOIN: 按 fingerprint 匹配, 计算差值
    4. 统计: count_fired / count_acked / count_pending
       mean / p50 / p95 / p99 (单位: 秒)

    数据源: OperationLog WHERE action_type IN ('alert_fired', 'alert_acknowledged')
    """
    conditions_fired = [
        OperationLog.action_type == "alert_fired",
        OperationLog.target_type == "alert",
    ]
    conditions_acked = [
        OperationLog.action_type == "alert_acknowledged",
        OperationLog.target_type == "alert",
    ]
    if start_time:
        conditions_fired.append(OperationLog.created_at >= start_time)
        conditions_acked.append(OperationLog.created_at >= start_time)
    if end_time:
        conditions_fired.append(OperationLog.created_at <= end_time)
        conditions_acked.append(OperationLog.created_at <= end_time)

    # 拉 fired (限制 10000 兜底)
    fired_stmt = (
        select(OperationLog.created_at, OperationLog.detail)
        .where(and_(*conditions_fired))
        .order_by(desc(OperationLog.created_at))
        .limit(10000)
    )
    fired_rows = (await db.execute(fired_stmt)).all()

    # 拉 acked (限制 10000 兜底)
    acked_stmt = (
        select(OperationLog.created_at, OperationLog.detail)
        .where(and_(*conditions_acked))
        .order_by(desc(OperationLog.created_at))
        .limit(10000)
    )
    acked_rows = (await db.execute(acked_stmt)).all()

    # 解析 detail, 按 fingerprint 索引
    # fired: fingerprint -> (fired_at, severity, rule)
    fired_map: dict[str, tuple[datetime, str, str]] = {}
    for created_at, detail_json in fired_rows:
        try:
            detail = json.loads(detail_json) if detail_json else {}
        except Exception:
            detail = {}
        fp = detail.get("fingerprint")
        if not fp:
            continue
        sev = detail.get("severity", "unknown")
        rule = detail.get("rule", "unknown")
        if severity and sev != severity:
            continue
        fired_map[fp] = (created_at, sev, rule)

    # acked: fingerprint -> ack_at (取最早一次 ack)
    acked_map: dict[str, datetime] = {}
    for created_at, detail_json in acked_rows:
        try:
            detail = json.loads(detail_json) if detail_json else {}
        except Exception:
            detail = {}
        fp = detail.get("fingerprint")
        if not fp:
            continue
        # 同一 fingerprint 可能多次 ack, 取最早
        if fp in acked_map:
            if created_at < acked_map[fp]:
                acked_map[fp] = created_at
        else:
            acked_map[fp] = created_at

    # self-JOIN: 计算响应时长
    response_times: list[float] = []  # 秒
    by_severity: dict[str, list[float]] = {}
    count_acked = 0
    count_pending = 0
    for fp, (fired_at, sev, rule) in fired_map.items():
        ack_at = acked_map.get(fp)
        if ack_at is None:
            count_pending += 1
            continue
        delta = (ack_at - fired_at).total_seconds()
        if delta < 0:
            # 异常: ack 早于 fired (数据异常, 跳过)
            continue
        count_acked += 1
        response_times.append(delta)
        by_severity.setdefault(sev, []).append(delta)

    response_times.sort()
    n = len(response_times)
    mean = sum(response_times) / n if n > 0 else 0.0
    return {
        "total_fired": len(fired_map),
        "total_acked": count_acked,
        "total_pending": count_pending,
        "response_time": {
            "mean": mean,
            "p50": _percentile(response_times, 50),
            "p95": _percentile(response_times, 95),
            "p99": _percentile(response_times, 99),
            "max": response_times[-1] if response_times else 0.0,
            "min": response_times[0] if response_times else 0.0,
        },
        "by_severity": {
            sev: {
                "count": len(times),
                "mean": sum(times) / len(times) if times else 0.0,
                "p95": _percentile(sorted(times), 95),
            }
            for sev, times in sorted(by_severity.items())
        },
        "ack_rate": (
            count_acked / (count_acked + count_pending)
            if (count_acked + count_pending) > 0
            else 0.0
        ),
    }


@router.get("/response-time", response_model=dict)
async def get_response_time(
    db: DbDep,
    _admin: AdminDep,
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    severity: str | None = Query(None, description="按严重度过滤"),
) -> dict[str, Any]:
    """v1.36 T2.3: 告警响应时长.

    5min Redis 缓存. 返回 fired/acked/pending 统计 + mean/p50/p95/p99 分位.
    """
    params = {
        "start": start_time.isoformat() if start_time else None,
        "end": end_time.isoformat() if end_time else None,
        "severity": severity,
    }
    data, cached = await cached_or_compute(
        endpoint="observability.response-time",
        params=params,
        compute_fn=lambda: _compute_response_time(
            db, start_time, end_time, severity
        ),
        ttl=DEFAULT_CACHE_TTL,
    )
    return with_instance_meta(
        data=data, cached=cached, extra={"params": params}
    )


# ===== T2.4 EP-3 升级率 =====


async def _compute_escalation(
    db: AsyncSession,
    start_time: datetime | None,
    end_time: datetime | None,
    severity: str | None,
) -> dict[str, Any]:
    """v1.36 T2.4: 计算告警升级率.

    实现:
    1. 拉取 alert_fired (总数: 分母)
    2. 拉取 alert_escalated (升级次数: 分子)
    3. by_level: L1/L2/L3 各级别升级次数
    4. by_rule: Top-20 规则的升级率
    5. by_severity: 按严重度拆分升级率

    数据源: OperationLog
    """
    conditions_fired = [
        OperationLog.action_type == "alert_fired",
        OperationLog.target_type == "alert",
    ]
    conditions_escalated = [
        OperationLog.action_type == "alert_escalated",
        OperationLog.target_type == "alert",
    ]
    if start_time:
        conditions_fired.append(OperationLog.created_at >= start_time)
        conditions_escalated.append(OperationLog.created_at >= start_time)
    if end_time:
        conditions_fired.append(OperationLog.created_at <= end_time)
        conditions_escalated.append(OperationLog.created_at <= end_time)

    # 拉 fired (限制 10000 兜底)
    fired_stmt = (
        select(OperationLog.detail)
        .where(and_(*conditions_fired))
        .limit(10000)
    )
    fired_details = (await db.execute(fired_stmt)).scalars().all()

    # 拉 escalated (限制 10000 兜底)
    esc_stmt = (
        select(OperationLog.detail)
        .where(and_(*conditions_escalated))
        .limit(10000)
    )
    esc_details = (await db.execute(esc_stmt)).scalars().all()

    # 解析 fired
    rule_fired: Counter[str] = Counter()
    sev_fired: Counter[str] = Counter()
    for detail_json in fired_details:
        try:
            detail = json.loads(detail_json) if detail_json else {}
        except Exception:
            detail = {}
        rule = detail.get("rule", "unknown")
        sev = detail.get("severity", "unknown")
        if severity and sev != severity:
            continue
        rule_fired[rule] += 1
        sev_fired[sev] += 1

    # 解析 escalated
    rule_esc: Counter[str] = Counter()
    sev_esc: Counter[str] = Counter()
    by_level: Counter[str] = Counter()
    for detail_json in esc_details:
        try:
            detail = json.loads(detail_json) if detail_json else {}
        except Exception:
            detail = {}
        rule = detail.get("rule", "unknown")
        sev = detail.get("severity", "unknown")
        if severity and sev != severity:
            continue
        rule_esc[rule] += 1
        sev_esc[sev] += 1
        # from_level/to_level 标识升级到哪个级别
        to_level = detail.get("to_level", detail.get("new_severity", "unknown"))
        by_level[str(to_level)] += 1

    total_fired = sum(rule_fired.values())
    total_escalated = sum(rule_esc.values())

    # 升级率 = escalated / fired
    escalation_rate = (
        total_escalated / total_fired
        if total_fired > 0
        else 0.0
    )

    # 按规则计算升级率 (Top-20)
    rule_stats = []
    for rule in sorted(rule_fired.keys() | rule_esc.keys()):
        f = rule_fired.get(rule, 0)
        e = rule_esc.get(rule, 0)
        rule_stats.append({
            "rule": rule,
            "fired": f,
            "escalated": e,
            "escalation_rate": e / f if f > 0 else 0.0,
        })
    rule_stats.sort(key=lambda x: x["escalated"], reverse=True)
    top_rules = rule_stats[:20]

    # 按严重度拆分
    by_severity: dict[str, dict[str, Any]] = {}
    for sev in sorted(set(sev_fired.keys()) | set(sev_esc.keys())):
        f = sev_fired.get(sev, 0)
        e = sev_esc.get(sev, 0)
        by_severity[sev] = {
            "fired": f,
            "escalated": e,
            "escalation_rate": e / f if f > 0 else 0.0,
        }

    return {
        "total_fired": total_fired,
        "total_escalated": total_escalated,
        "escalation_rate": escalation_rate,
        "by_level": dict(by_level),
        "by_severity": by_severity,
        "by_rule": top_rules,
    }


@router.get("/escalation", response_model=dict)
async def get_escalation(
    db: DbDep,
    _admin: AdminDep,
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    severity: str | None = Query(None, description="按严重度过滤"),
) -> dict[str, Any]:
    """v1.36 T2.4: 告警升级率.

    5min Redis 缓存. 返回总升级率 + by_level + by_severity + by_rule (Top-20).
    """
    params = {
        "start": start_time.isoformat() if start_time else None,
        "end": end_time.isoformat() if end_time else None,
        "severity": severity,
    }
    data, cached = await cached_or_compute(
        endpoint="observability.escalation",
        params=params,
        compute_fn=lambda: _compute_escalation(
            db, start_time, end_time, severity
        ),
        ttl=DEFAULT_CACHE_TTL,
    )
    return with_instance_meta(
        data=data, cached=cached, extra={"params": params}
    )


# ===== T2.5 EP-4 通道成功率 =====


async def _compute_channel_stats(
    db: AsyncSession,
    start_time: datetime | None,
    end_time: datetime | None,
    channel: str | None,
) -> dict[str, Any]:
    """v1.36 T2.5: 计算各通道发送成功率.

    数据源: OperationLog WHERE action_type IN ('alert_channel_sent','alert_channel_failed')
            AND target_type='alert_channel'

    返回:
        channels: {channel_name: {sent, failed, success_rate, avg_duration_ms}}
        total: 全量统计
    """
    conditions = [
        OperationLog.action_type.in_(
            ("alert_channel_sent", "alert_channel_failed")
        ),
        OperationLog.target_type == "alert_channel",
    ]
    if start_time:
        conditions.append(OperationLog.created_at >= start_time)
    if end_time:
        conditions.append(OperationLog.created_at <= end_time)

    stmt = (
        select(OperationLog.action_type, OperationLog.detail)
        .where(and_(*conditions))
        .limit(10000)
    )
    rows = (await db.execute(stmt)).all()

    # channel -> {sent, failed, durations}
    channel_stats: dict[str, dict[str, Any]] = {}
    for action_type, detail_json in rows:
        try:
            detail = json.loads(detail_json) if detail_json else {}
        except Exception:
            detail = {}
        ch = detail.get("channel", "unknown")
        if channel and ch != channel:
            continue
        slot = channel_stats.setdefault(
            ch, {"sent": 0, "failed": 0, "durations": []}
        )
        if action_type == "alert_channel_sent":
            slot["sent"] += 1
        else:
            slot["failed"] += 1
        duration = detail.get("duration_ms")
        if isinstance(duration, (int, float)):
            slot["durations"].append(int(duration))

    # 计算 success_rate 和 avg_duration
    channels_out: dict[str, dict[str, Any]] = {}
    total_sent = 0
    total_failed = 0
    for ch, s in sorted(channel_stats.items()):
        sent = s["sent"]
        failed = s["failed"]
        total = sent + failed
        success_rate = sent / total if total > 0 else 0.0
        avg_duration = (
            sum(s["durations"]) / len(s["durations"])
            if s["durations"]
            else 0
        )
        channels_out[ch] = {
            "sent": sent,
            "failed": failed,
            "total": total,
            "success_rate": success_rate,
            "avg_duration_ms": int(avg_duration),
            "max_duration_ms": max(s["durations"]) if s["durations"] else 0,
        }
        total_sent += sent
        total_failed += failed

    total_all = total_sent + total_failed
    return {
        "channels": channels_out,
        "total_sent": total_sent,
        "total_failed": total_failed,
        "total": total_all,
        "overall_success_rate": (
            total_sent / total_all if total_all > 0 else 0.0
        ),
    }


@router.get("/channel-stats", response_model=dict)
async def get_channel_stats(
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
    """
    params = {
        "start": start_time.isoformat() if start_time else None,
        "end": end_time.isoformat() if end_time else None,
        "channel": channel,
    }
    data, cached = await cached_or_compute(
        endpoint="observability.channel-stats",
        params=params,
        compute_fn=lambda: _compute_channel_stats(
            db, start_time, end_time, channel
        ),
        ttl=DEFAULT_CACHE_TTL,
    )
    return with_instance_meta(
        data=data, cached=cached, extra={"params": params}
    )


# ===== T2.6 EP-5 静默命中率 =====


async def _compute_silence_hit_rate(
    db: AsyncSession,
    start_time: datetime | None,
    end_time: datetime | None,
) -> dict[str, Any]:
    """v1.36 T2.6: 计算静默命中率.

    实现:
    1. 拉取 alert_fired (总数: 分母)
    2. 拉取 alert_silenced (静默命中数: 分子)
    3. hit_rate = silenced / (fired + silenced)
       注意: 实际生产中, alert_silenced 是 fired 的子集
       (即: 触发后被静默, 不再发通知)
    4. by_matcher: 按 silence_name 拆分命中率
    5. by_severity: 按严重度拆分命中率

    数据源: OperationLog
    """
    conditions_fired = [
        OperationLog.action_type == "alert_fired",
        OperationLog.target_type == "alert",
    ]
    conditions_silenced = [
        OperationLog.action_type == "alert_silenced",
        OperationLog.target_type == "alert",
    ]
    if start_time:
        conditions_fired.append(OperationLog.created_at >= start_time)
        conditions_silenced.append(OperationLog.created_at >= start_time)
    if end_time:
        conditions_fired.append(OperationLog.created_at <= end_time)
        conditions_silenced.append(OperationLog.created_at <= end_time)

    # 拉 fired
    fired_stmt = (
        select(OperationLog.detail)
        .where(and_(*conditions_fired))
        .limit(10000)
    )
    fired_details = (await db.execute(fired_stmt)).scalars().all()

    # 拉 silenced
    sil_stmt = (
        select(OperationLog.detail)
        .where(and_(*conditions_silenced))
        .limit(10000)
    )
    sil_details = (await db.execute(sil_stmt)).scalars().all()

    total_fired = len(fired_details)
    total_silenced = len(sil_details)

    # 总命中率: silenced / (fired + silenced)
    total_processed = total_fired + total_silenced
    hit_rate = (
        total_silenced / total_processed
        if total_processed > 0
        else 0.0
    )

    # 按 silence_name (matcher) 拆分
    matcher_counts: Counter[str] = Counter()
    matcher_severity: dict[str, Counter[str]] = {}
    for detail_json in sil_details:
        try:
            detail = json.loads(detail_json) if detail_json else {}
        except Exception:
            detail = {}
        matcher = detail.get("silence_name", "unknown")
        sev = detail.get("severity", "unknown")
        matcher_counts[matcher] += 1
        matcher_severity.setdefault(matcher, Counter())[sev] += 1

    by_matcher = []
    for matcher, count in matcher_counts.most_common(20):
        by_matcher.append({
            "silence_name": matcher,
            "silenced_count": count,
            "by_severity": dict(matcher_severity[matcher]),
        })

    # 按严重度拆分 (silenced 中的分布)
    sev_silenced: Counter[str] = Counter()
    for detail_json in sil_details:
        try:
            detail = json.loads(detail_json) if detail_json else {}
        except Exception:
            detail = {}
        sev_silenced[detail.get("severity", "unknown")] += 1

    by_severity = {
        sev: {
            "silenced": count,
            "ratio": count / total_silenced if total_silenced > 0 else 0.0,
        }
        for sev, count in sev_silenced.most_common()
    }

    return {
        "total_fired": total_fired,
        "total_silenced": total_silenced,
        "total_processed": total_processed,
        "hit_rate": hit_rate,
        "by_matcher": by_matcher,
        "by_severity": by_severity,
    }


@router.get("/silence-hit-rate", response_model=dict)
async def get_silence_hit_rate(
    db: DbDep,
    _admin: AdminDep,
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
) -> dict[str, Any]:
    """v1.36 T2.6: 静默命中率.

    5min Redis 缓存. 返回 silenced / (fired + silenced) + by_matcher + by_severity.
    """
    params = {
        "start": start_time.isoformat() if start_time else None,
        "end": end_time.isoformat() if end_time else None,
    }
    data, cached = await cached_or_compute(
        endpoint="observability.silence-hit-rate",
        params=params,
        compute_fn=lambda: _compute_silence_hit_rate(db, start_time, end_time),
        ttl=DEFAULT_CACHE_TTL,
    )
    return with_instance_meta(
        data=data, cached=cached, extra={"params": params}
    )


# ===== T2.7 EP-6 AM 同步可观测 =====


async def _compute_am_sync(
    db: AsyncSession,
    start_time: datetime | None,
    end_time: datetime | None,
    operation: str | None,
) -> dict[str, Any]:
    """v1.36 T2.7: 计算 AlertManager 同步可观测.

    实现:
    1. 拉取 am_sync_success / am_sync_failed (target_type='alert_silence')
    2. success_count / failed_count + total + success_rate
    3. by_operation: 按 push_silence / delete_silence / pull_silences 拆分
    4. recent_failures: 最近 N 条失败 (含 error 详情)
    5. avg_duration_ms: 平均同步耗时

    数据源: OperationLog
    """
    conditions_success = [
        OperationLog.action_type == "am_sync_success",
        OperationLog.target_type == "alert_silence",
    ]
    conditions_failed = [
        OperationLog.action_type == "am_sync_failed",
        OperationLog.target_type == "alert_silence",
    ]
    if start_time:
        conditions_success.append(OperationLog.created_at >= start_time)
        conditions_failed.append(OperationLog.created_at >= start_time)
    if end_time:
        conditions_success.append(OperationLog.created_at <= end_time)
        conditions_failed.append(OperationLog.created_at <= end_time)

    # 拉 success (含 detail + created_at, 供最近失败使用)
    succ_stmt = (
        select(OperationLog.detail, OperationLog.created_at)
        .where(and_(*conditions_success))
        .limit(10000)
    )
    succ_rows = (await db.execute(succ_stmt)).all()

    # 拉 failed
    fail_stmt = (
        select(OperationLog.detail, OperationLog.created_at)
        .where(and_(*conditions_failed))
        .order_by(desc(OperationLog.created_at))
        .limit(10000)
    )
    fail_rows = (await db.execute(fail_stmt)).all()

    # 解析 by_operation / duration
    op_success: Counter[str] = Counter()
    op_failed: Counter[str] = Counter()
    durations: list[int] = []
    by_op_durations: dict[str, list[int]] = {}

    for detail_json, _ in succ_rows:
        try:
            detail = json.loads(detail_json) if detail_json else {}
        except Exception:
            detail = {}
        op = detail.get("operation", "unknown")
        if operation and op != operation:
            continue
        op_success[op] += 1
        dur = detail.get("duration_ms")
        if isinstance(dur, (int, float)):
            durations.append(int(dur))
            by_op_durations.setdefault(op, []).append(int(dur))

    recent_failures: list[dict[str, Any]] = []
    for detail_json, created_at in fail_rows:
        try:
            detail = json.loads(detail_json) if detail_json else {}
        except Exception:
            detail = {}
        op = detail.get("operation", "unknown")
        if operation and op != operation:
            continue
        op_failed[op] += 1
        dur = detail.get("duration_ms")
        if isinstance(dur, (int, float)):
            durations.append(int(dur))
            by_op_durations.setdefault(op, []).append(int(dur))
        recent_failures.append({
            "operation": op,
            "error": detail.get("error", "unknown"),
            "duration_ms": int(dur) if isinstance(dur, (int, float)) else 0,
            "am_silence_id": detail.get("am_silence_id"),
            "created_at": created_at.isoformat() if created_at else None,
        })

    # 仅保留最近 10 条失败
    recent_failures = recent_failures[:10]

    total_success = sum(op_success.values())
    total_failed = sum(op_failed.values())
    total = total_success + total_failed
    success_rate = total_success / total if total > 0 else 0.0

    # 合并 by_operation
    all_ops = set(op_success.keys()) | set(op_failed.keys())
    by_operation = []
    for op in sorted(all_ops):
        s = op_success.get(op, 0)
        f = op_failed.get(op, 0)
        d = by_op_durations.get(op, [])
        by_operation.append({
            "operation": op,
            "success": s,
            "failed": f,
            "total": s + f,
            "avg_duration_ms": int(sum(d) / len(d)) if d else 0,
        })

    avg_duration = int(sum(durations) / len(durations)) if durations else 0

    return {
        "total_success": total_success,
        "total_failed": total_failed,
        "total": total,
        "success_rate": success_rate,
        "avg_duration_ms": avg_duration,
        "by_operation": by_operation,
        "recent_failures": recent_failures,
    }


@router.get("/am-sync", response_model=dict)
async def get_am_sync(
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
    """
    params = {
        "start": start_time.isoformat() if start_time else None,
        "end": end_time.isoformat() if end_time else None,
        "operation": operation,
    }
    data, cached = await cached_or_compute(
        endpoint="observability.am-sync",
        params=params,
        compute_fn=lambda: _compute_am_sync(db, start_time, end_time, operation),
        ttl=DEFAULT_CACHE_TTL,
    )
    return with_instance_meta(
        data=data, cached=cached, extra={"params": params}
    )


# ===== T2.8 EP-7 Redis 锁可观测 =====


async def _compute_lock_stats(
    db: AsyncSession,
) -> dict[str, Any]:
    """v1.36 T2.8: 计算 Redis 锁可观测.

    实现:
    1. 读内存统计: dedup_lock.get_stats() -> {acquired, skipped, fallback, errors}
    2. 读上次 flush 时间: dedup_lock.get_last_flush_at()
    3. 拉取最近 N 条 OperationLog (action_type='dedup_lock_stats',
       target_type='dedup_lock') 用于历史趋势
    4. 计算: total / acquire_rate / fallback_rate / error_rate

    数据源:
    - 内存: dedup_lock._stats (本进程)
    - 持久化: OperationLog (跨实例/历史)
    """
    # 1. 内存统计 (本进程)
    try:
        from app.monitoring.dedup_lock import get_last_flush_at, get_stats
        mem_stats = get_stats()
        last_flush_at = get_last_flush_at()
    except Exception as exc:
        logger.warning("[observability] 读 dedup_lock 内存统计失败: %s", exc)
        mem_stats = {"acquired": 0, "skipped": 0, "fallback": 0, "errors": 0}
        last_flush_at = None

    # 2. 计算比例
    acquired = mem_stats.get("acquired", 0)
    skipped = mem_stats.get("skipped", 0)
    fallback = mem_stats.get("fallback", 0)
    errors = mem_stats.get("errors", 0)
    total = acquired + skipped + fallback + errors
    acquire_rate = acquired / total if total > 0 else 0.0
    fallback_rate = fallback / total if total > 0 else 0.0
    error_rate = errors / total if total > 0 else 0.0

    # 3. 拉取最近 10 条 flush 日志
    flush_stmt = (
        select(OperationLog.detail, OperationLog.created_at)
        .where(
            and_(
                OperationLog.action_type == "dedup_lock_stats",
                OperationLog.target_type == "dedup_lock",
            )
        )
        .order_by(desc(OperationLog.created_at))
        .limit(10)
    )
    flush_rows = (await db.execute(flush_stmt)).all()

    recent_flushes: list[dict[str, Any]] = []
    total_flushed_acquired = 0
    total_flushed_skipped = 0
    total_flushed_fallback = 0
    total_flushed_errors = 0
    for detail_json, created_at in flush_rows:
        try:
            detail = json.loads(detail_json) if detail_json else {}
        except Exception:
            detail = {}
        recent_flushes.append({
            "acquired": detail.get("acquired", 0),
            "skipped": detail.get("skipped", 0),
            "fallback": detail.get("fallback", 0),
            "errors": detail.get("errors", 0),
            "instance_id": detail.get("instance_id"),
            "created_at": created_at.isoformat() if created_at else None,
        })
        total_flushed_acquired += detail.get("acquired", 0)
        total_flushed_skipped += detail.get("skipped", 0)
        total_flushed_fallback += detail.get("fallback", 0)
        total_flushed_errors += detail.get("errors", 0)

    # 4. 累计历史 (最近 10 次 flush)
    flushed_total = (
        total_flushed_acquired
        + total_flushed_skipped
        + total_flushed_fallback
        + total_flushed_errors
    )
    historical = {
        "recent_flush_count": len(recent_flushes),
        "total_acquired": total_flushed_acquired,
        "total_skipped": total_flushed_skipped,
        "total_fallback": total_flushed_fallback,
        "total_errors": total_flushed_errors,
        "total": flushed_total,
        "fallback_rate": (
            total_flushed_fallback / flushed_total
            if flushed_total > 0
            else 0.0
        ),
        "error_rate": (
            total_flushed_errors / flushed_total
            if flushed_total > 0
            else 0.0
        ),
    }

    return {
        "memory": {
            "acquired": acquired,
            "skipped": skipped,
            "fallback": fallback,
            "errors": errors,
            "total": total,
            "acquire_rate": acquire_rate,
            "fallback_rate": fallback_rate,
            "error_rate": error_rate,
        },
        "last_flush_at": last_flush_at,
        "recent_flushes": recent_flushes,
        "historical_recent": historical,
    }


@router.get("/lock-stats", response_model=dict)
async def get_lock_stats(
    db: DbDep,
    _admin: AdminDep,
) -> dict[str, Any]:
    """v1.36 T2.8: Redis 锁可观测.

    5min Redis 缓存. 返回内存统计 + 上次 flush 时间 + 最近 10 条 flush 日志.
    """
    data, cached = await cached_or_compute(
        endpoint="observability.lock-stats",
        params={},
        compute_fn=lambda: _compute_lock_stats(db),
        ttl=DEFAULT_CACHE_TTL,
    )
    return with_instance_meta(
        data=data, cached=cached, extra={}
    )


# ===== T2.1 健康检查 (用于验证路由注册成功) =====


@router.get("/health", response_model=dict)
async def observability_health(
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
