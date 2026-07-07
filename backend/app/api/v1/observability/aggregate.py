"""v1.36 告警可观测性 API: 聚合类 compute 函数.

包含:
- T2.5 _compute_channel_stats      - 通道成功率
- T2.6 _compute_silence_hit_rate   - 静默命中率
- T2.7 _compute_am_sync            - AM 同步可观测
- T2.8 _compute_lock_stats         - Redis 锁可观测

PERF-P1-001: SQL GROUP BY 下推, json_extract 跨方言聚合.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import Float, and_, cast, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.observability._common import (
    _json_loads,
    _JsonExtract,
    _norm_json_value,
)
from app.models.admin import OperationLog

logger = logging.getLogger(__name__)


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

    PERF-P1-001: SQL GROUP BY 下推 — 从 5000 行 detail 全文拉取改为
    GROUP BY (channel, action_type) + COUNT + AVG + MAX，返回行数从 5000 降至 ~8。
    """
    ch_expr = _JsonExtract(OperationLog.detail, "channel")
    dur_expr = cast(_JsonExtract(OperationLog.detail, "duration_ms"), Float)

    conditions = [
        OperationLog.action_type.in_(("alert_channel_sent", "alert_channel_failed")),
        OperationLog.target_type == "alert_channel",
        OperationLog.created_at >= start_time,
        OperationLog.created_at <= end_time,
    ]
    if channel:
        conditions.append(ch_expr == channel)

    # 一次查询: GROUP BY (channel, action_type) + COUNT + AVG(duration) + MAX(duration)
    # 返回 ~N_channels × 2 行 (例如 4 channels × 2 actions = 8 行)
    stmt = (
        select(
            ch_expr.label("channel"),
            OperationLog.action_type,
            func.count().label("cnt"),
            func.avg(dur_expr).label("avg_dur"),
            func.max(dur_expr).label("max_dur"),
        )
        .where(and_(*conditions))
        .group_by(ch_expr, OperationLog.action_type)
    )
    rows = (await db.execute(stmt)).all()

    # channel -> {sent, failed, avg_dur, max_dur}
    channel_stats: dict[str, dict[str, Any]] = {}
    for ch, action_type, cnt, avg_dur, max_dur in rows:
        ch_norm = _norm_json_value(ch)
        slot = channel_stats.setdefault(
            ch_norm,
            {"sent": 0, "failed": 0, "avg_durs": [], "max_durs": []},
        )
        if action_type == "alert_channel_sent":
            slot["sent"] += cnt
        else:
            slot["failed"] += cnt
        if avg_dur is not None:
            slot["avg_durs"].append((cnt, avg_dur))
        if max_dur is not None:
            slot["max_durs"].append(max_dur)

    # 计算 success_rate 和加权 avg_duration / max_duration
    channels_out: dict[str, dict[str, Any]] = {}
    total_sent = 0
    total_failed = 0
    for ch, s in sorted(channel_stats.items()):
        sent = s["sent"]
        failed = s["failed"]
        total = sent + failed
        success_rate = sent / total if total > 0 else 0.0
        # 加权平均: 按 count 加权合并 sent/failed 的 avg_duration
        total_count = sum(c for c, _ in s["avg_durs"])
        avg_duration = (
            sum(c * d for c, d in s["avg_durs"]) / total_count if total_count > 0 else 0
        )
        max_duration = max(s["max_durs"]) if s["max_durs"] else 0
        channels_out[ch] = {
            "sent": sent,
            "failed": failed,
            "total": total,
            "success_rate": success_rate,
            "avg_duration_ms": int(avg_duration),
            "max_duration_ms": int(max_duration) if max_duration else 0,
        }
        total_sent += sent
        total_failed += failed

    total_all = total_sent + total_failed
    return {
        "channels": channels_out,
        "total_sent": total_sent,
        "total_failed": total_failed,
        "total": total_all,
        "overall_success_rate": (total_sent / total_all if total_all > 0 else 0.0),
    }


# ===== T2.6 EP-5 静默命中率 =====


async def _compute_silence_hit_rate(
    db: AsyncSession,
    start_time: datetime | None,
    end_time: datetime | None,
) -> dict[str, Any]:
    """v1.36 T2.6: 计算静默命中率.

    实现:
    1. 拉取 alert_fired (总数: 分母) — SQL COUNT(*)
    2. 拉取 alert_silenced (静默命中数: 分子) — SQL GROUP BY (silence_name, severity)
    3. hit_rate = silenced / (fired + silenced)
       注意: 实际生产中, alert_silenced 是 fired 的子集
       (即: 触发后被静默, 不再发通知)
    4. by_matcher: 按 silence_name 拆分命中率
    5. by_severity: 按严重度拆分命中率

    数据源: OperationLog

    PERF-P1-001: SQL GROUP BY 下推 — fired 从 5000 行 detail 改为 COUNT(*) 单行；
    silenced 从 5000 行 detail 改为 GROUP BY (silence_name, severity)，返回几十行。
    """
    matcher_expr = _JsonExtract(OperationLog.detail, "silence_name")
    sev_expr = _JsonExtract(OperationLog.detail, "severity")

    conditions_fired = [
        OperationLog.action_type == "alert_fired",
        OperationLog.target_type == "alert",
        OperationLog.created_at >= start_time,
        OperationLog.created_at <= end_time,
    ]
    conditions_silenced = [
        OperationLog.action_type == "alert_silenced",
        OperationLog.target_type == "alert",
        OperationLog.created_at >= start_time,
        OperationLog.created_at <= end_time,
    ]

    # 查询 1: total_fired COUNT(*) → 1 行
    fired_count_stmt = (
        select(func.count()).select_from(OperationLog).where(and_(*conditions_fired))
    )
    total_fired = (await db.execute(fired_count_stmt)).scalar() or 0

    # 查询 2: silenced GROUP BY (silence_name, severity) → 几十行
    sil_stmt = (
        select(
            matcher_expr.label("silence_name"),
            sev_expr.label("severity"),
            func.count().label("cnt"),
        )
        .where(and_(*conditions_silenced))
        .group_by(matcher_expr, sev_expr)
    )
    sil_rows = (await db.execute(sil_stmt)).all()

    matcher_counts: Counter[str] = Counter()
    matcher_severity: dict[str, Counter[str]] = {}
    sev_silenced: Counter[str] = Counter()
    total_silenced = 0
    for matcher, sev, cnt in sil_rows:
        matcher_norm = _norm_json_value(matcher)
        sev_norm = _norm_json_value(sev)
        matcher_counts[matcher_norm] += cnt
        matcher_severity.setdefault(matcher_norm, Counter())[sev_norm] += cnt
        sev_silenced[sev_norm] += cnt
        total_silenced += cnt

    # 总命中率: silenced / (fired + silenced)
    total_processed = total_fired + total_silenced
    hit_rate = total_silenced / total_processed if total_processed > 0 else 0.0

    by_matcher = []
    for matcher, count in matcher_counts.most_common(20):
        by_matcher.append(
            {
                "silence_name": matcher,
                "silenced_count": count,
                "by_severity": dict(matcher_severity[matcher]),
            }
        )

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
       — SQL GROUP BY (operation, action_type) + COUNT + AVG(duration)
    2. success_count / failed_count + total + success_rate
    3. by_operation: 按 push_silence / delete_silence / pull_silences 拆分
    4. recent_failures: 最近 10 条失败 (含 error 详情) — LIMIT 10
    5. avg_duration_ms: 平均同步耗时 (加权合并)

    数据源: OperationLog

    PERF-P1-001: SQL GROUP BY 下推 — success/failed 各从 5000 行 detail 全文
    拉取改为 GROUP BY (operation, action_type) + COUNT + AVG，返回行数从 10000 降至 ~6；
    recent_failures 从 5000 行改为 LIMIT 10。
    """
    op_expr = _JsonExtract(OperationLog.detail, "operation")
    dur_expr = cast(_JsonExtract(OperationLog.detail, "duration_ms"), Float)

    conditions = [
        OperationLog.action_type.in_(("am_sync_success", "am_sync_failed")),
        OperationLog.target_type == "alert_silence",
        OperationLog.created_at >= start_time,
        OperationLog.created_at <= end_time,
    ]
    if operation:
        conditions.append(op_expr == operation)

    # 查询 1: success + failed 合并 GROUP BY (operation, action_type) + COUNT + AVG
    # 返回 ~N_operations × 2 行 (例如 3 ops × 2 = 6 行)
    agg_stmt = (
        select(
            op_expr.label("operation"),
            OperationLog.action_type,
            func.count().label("cnt"),
            func.avg(dur_expr).label("avg_dur"),
        )
        .where(and_(*conditions))
        .group_by(op_expr, OperationLog.action_type)
    )
    agg_rows = (await db.execute(agg_stmt)).all()

    op_success: Counter[str] = Counter()
    op_failed: Counter[str] = Counter()
    op_durations: dict[str, list[tuple[int, float]]] = {}  # op -> [(count, avg_dur)]
    for op, action_type, cnt, avg_dur in agg_rows:
        op_norm = _norm_json_value(op)
        if action_type == "am_sync_success":
            op_success[op_norm] += cnt
        else:
            op_failed[op_norm] += cnt
        if avg_dur is not None:
            op_durations.setdefault(op_norm, []).append((cnt, avg_dur))

    total_success = sum(op_success.values())
    total_failed = sum(op_failed.values())
    total = total_success + total_failed
    success_rate = total_success / total if total > 0 else 0.0

    # 合并 by_operation (加权 avg_duration)
    all_ops = set(op_success.keys()) | set(op_failed.keys())
    by_operation = []
    global_dur_sum = 0.0
    global_dur_count = 0
    for op in sorted(all_ops):
        s = op_success.get(op, 0)
        f = op_failed.get(op, 0)
        d = op_durations.get(op, [])
        op_total_count = sum(c for c, _ in d)
        op_avg_dur = (
            sum(c * avg for c, avg in d) / op_total_count if op_total_count > 0 else 0.0
        )
        global_dur_sum += sum(c * avg for c, avg in d)
        global_dur_count += op_total_count
        by_operation.append(
            {
                "operation": op,
                "success": s,
                "failed": f,
                "total": s + f,
                "avg_duration_ms": int(op_avg_dur) if op_avg_dur else 0,
            }
        )

    avg_duration = int(global_dur_sum / global_dur_count) if global_dur_count > 0 else 0

    # 查询 2: recent_failures LIMIT 10 (保留原逻辑，拉失败详情)
    fail_conditions = [
        OperationLog.action_type == "am_sync_failed",
        OperationLog.target_type == "alert_silence",
        OperationLog.created_at >= start_time,
        OperationLog.created_at <= end_time,
    ]
    if operation:
        fail_conditions.append(op_expr == operation)

    fail_stmt = (
        select(OperationLog.detail, OperationLog.created_at)
        .where(and_(*fail_conditions))
        .order_by(desc(OperationLog.created_at))
        .limit(10)
    )
    fail_rows = (await db.execute(fail_stmt)).all()

    recent_failures: list[dict[str, Any]] = []
    for detail_json, created_at in fail_rows:
        try:
            detail = _json_loads(detail_json) if detail_json else {}
        except Exception:
            # M-L 修复：记录 detail_json 解析失败，避免静默吞掉数据损坏问题
            logger.debug(
                "observability: detail_json parse failed, using empty dict",
                exc_info=True,
            )
            detail = {}
        op = detail.get("operation", "unknown")
        dur = detail.get("duration_ms")
        recent_failures.append(
            {
                "operation": op,
                "error": detail.get("error", "unknown"),
                "duration_ms": int(dur) if isinstance(dur, (int, float)) else 0,
                "am_silence_id": detail.get("am_silence_id"),
                "created_at": created_at.isoformat() if created_at else None,
            }
        )

    return {
        "total_success": total_success,
        "total_failed": total_failed,
        "total": total,
        "success_rate": success_rate,
        "avg_duration_ms": avg_duration,
        "by_operation": by_operation,
        "recent_failures": recent_failures,
    }


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
            detail = _json_loads(detail_json) if detail_json else {}
        except Exception:
            # M-L 修复：记录 detail_json 解析失败，避免静默吞掉数据损坏问题
            logger.debug(
                "observability: detail_json parse failed, using empty dict",
                exc_info=True,
            )
            detail = {}
        recent_flushes.append(
            {
                "acquired": detail.get("acquired", 0),
                "skipped": detail.get("skipped", 0),
                "fallback": detail.get("fallback", 0),
                "errors": detail.get("errors", 0),
                "instance_id": detail.get("instance_id"),
                "created_at": created_at.isoformat() if created_at else None,
            }
        )
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
            total_flushed_fallback / flushed_total if flushed_total > 0 else 0.0
        ),
        "error_rate": (
            total_flushed_errors / flushed_total if flushed_total > 0 else 0.0
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
