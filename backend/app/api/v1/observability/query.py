"""v1.36 告警可观测性 API: 查询类 compute 函数.

包含:
- T2.2 _compute_trend          - 告警趋势
- T2.3 _compute_response_time  - 响应时长
- T2.4 _compute_escalation     - 升级率

PERF-P1-001: SQL GROUP BY 下推, json_extract 跨方言聚合.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.observability._common import (
    DEFAULT_LIMIT,
    _BucketExpr,
    _JsonExtract,
    _norm_json_value,
)
from app.models.admin import OperationLog

logger = logging.getLogger(__name__)


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
    # M-12 修复：统一时区处理，naive datetime 假设为 UTC，避免本地时区导致时间桶对齐错误
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    epoch = int(ts.timestamp())
    bucket_epoch = epoch - (epoch % secs)
    return (
        datetime.fromtimestamp(bucket_epoch, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _ensure_aware(dt: datetime | None) -> datetime | None:
    """H-3 修复：统一 datetime 为 aware UTC，避免 aware/naive 混用导致 TypeError.

    M-API-5 修复：created_at 为 None 时直接返回 None，
    避免 json.loads 失败设为空 dict 后 _ensure_aware(None) 抛 AttributeError。
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


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

    PERF-P1-001: SQL GROUP BY 下推 — 将 Python Counter 聚合 + 5000 行 detail
    全文拉取改为 SQL 侧 json_extract + GROUP BY，返回行数从 5000 降至几十/几百。
    """
    sev_expr = _JsonExtract(OperationLog.detail, "severity")
    rule_expr = _JsonExtract(OperationLog.detail, "rule")
    bucket_secs = _BUCKET_SECONDS[bucket]
    bucket_expr = _BucketExpr(OperationLog.created_at, bucket_secs)

    # 基础条件 (action_type + target_type + 时间范围)
    conditions = [
        OperationLog.action_type.in_(_ALERT_ACTIONS),
        OperationLog.target_type == "alert",
        OperationLog.created_at >= start_time,
        OperationLog.created_at <= end_time,
    ]
    # severity/status 后置过滤下推到 SQL WHERE
    if severity:
        conditions.append(sev_expr == severity)
    if status:
        if status == "firing":
            conditions.append(OperationLog.action_type == "alert_fired")
        else:
            conditions.append(OperationLog.action_type == "alert_resolved")

    # 查询 1: 全量维度聚合 (by_severity / by_status / by_rule / total)
    # GROUP BY (action_type, severity, rule) → 返回 ~10-50 行
    agg_stmt = (
        select(
            OperationLog.action_type,
            sev_expr.label("severity"),
            rule_expr.label("rule"),
            func.count().label("cnt"),
        )
        .where(and_(*conditions))
        .group_by(OperationLog.action_type, sev_expr, rule_expr)
    )
    agg_rows = (await db.execute(agg_stmt)).all()

    by_severity: Counter[str] = Counter()
    by_status: Counter[str] = Counter()
    by_rule: Counter[str] = Counter()
    total = 0
    for action_type, sev, rule, cnt in agg_rows:
        st = "firing" if action_type == "alert_fired" else "resolved"
        sev_norm = _norm_json_value(sev)
        rule_norm = _norm_json_value(rule)
        by_severity[sev_norm] += cnt
        by_status[st] += cnt
        by_rule[rule_norm] += cnt
        total += cnt

    # 查询 2: 时间桶聚合
    # GROUP BY (bucket, action_type, severity) → 返回 ~N_buckets × 2 × 5 行
    bucket_stmt = (
        select(
            bucket_expr.label("bucket"),
            OperationLog.action_type,
            sev_expr.label("severity"),
            func.count().label("cnt"),
        )
        .where(and_(*conditions))
        .group_by(bucket_expr, OperationLog.action_type, sev_expr)
        .order_by(bucket_expr)
    )
    bucket_rows = (await db.execute(bucket_stmt)).all()

    buckets: dict[str, dict[str, Any]] = {}
    for bk, action_type, sev, cnt in bucket_rows:
        # bk 可能为 datetime (PG) 或 string (SQLite datetime() 返回 TEXT)
        if isinstance(bk, str):
            bk = datetime.fromisoformat(bk)
        bk_aware = _ensure_aware(bk)
        bk_str = bk_aware.isoformat().replace("+00:00", "Z")
        st = "firing" if action_type == "alert_fired" else "resolved"
        sev_norm = _norm_json_value(sev)
        slot = buckets.setdefault(
            bk_str,
            {"timestamp": bk_str, "count": 0, "by_severity": {}, "by_status": {}},
        )
        slot["count"] += cnt
        slot["by_severity"][sev_norm] = slot["by_severity"].get(sev_norm, 0) + cnt
        slot["by_status"][st] = slot["by_status"].get(st, 0) + cnt

    # M-API-16 修复: truncated 判断改用 COUNT(*)，避免依赖 LIMIT 截断后的行数
    count_stmt = select(func.count()).select_from(OperationLog).where(and_(*conditions))
    total_in_db = (await db.execute(count_stmt)).scalar() or 0
    truncated = total_in_db > DEFAULT_LIMIT

    return {
        "buckets": [buckets[k] for k in sorted(buckets.keys())],
        "total": total,
        "by_severity": dict(by_severity),
        "by_status": dict(by_status),
        "by_rule": dict(by_rule.most_common(20)),  # Top-20 规则
        "group_by": group_by,
        "bucket": bucket,
        # M-API-16 修复：标记数据是否因 DEFAULT_LIMIT 上限被截断
        "truncated": truncated,
    }


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
    1. 拉取 alert_fired (fingerprint, created_at, severity) via SQL json_extract
    2. 拉取 alert_acknowledged 聚合: GROUP BY fingerprint, MIN(created_at)
    3. Python 字典匹配: 按 fingerprint 计算 fired_at -> ack_at 差值
    4. 统计: count_fired / count_acked / count_pending
       mean / p50 / p95 / p99 (单位: 秒)

    数据源: OperationLog WHERE action_type IN ('alert_fired', 'alert_acknowledged')

    PERF-P1-001: SQL json_extract + GROUP BY 下推 — fired 拉取从 (created_at, detail Text)
    改为 (created_at, fingerprint, severity) 3 小字段；acked 从全量拉取改为
    GROUP BY fingerprint + MIN(created_at)，返回行数从 5000 降至几十/几百。
    """
    fp_expr = _JsonExtract(OperationLog.detail, "fingerprint")
    sev_expr = _JsonExtract(OperationLog.detail, "severity")

    conditions_fired = [
        OperationLog.action_type == "alert_fired",
        OperationLog.target_type == "alert",
        OperationLog.created_at >= start_time,
        OperationLog.created_at <= end_time,
    ]
    conditions_acked = [
        OperationLog.action_type == "alert_acknowledged",
        OperationLog.target_type == "alert",
        OperationLog.created_at >= start_time,
        OperationLog.created_at <= end_time,
    ]
    if severity:
        conditions_fired.append(sev_expr == severity)

    # 查询 1: fired — 仅拉 (created_at, fingerprint, severity) 3 列，避免 detail Text 全文
    fired_stmt = (
        select(
            OperationLog.created_at,
            fp_expr.label("fingerprint"),
            sev_expr.label("severity"),
        )
        .where(and_(*conditions_fired))
        .order_by(desc(OperationLog.created_at))
        .limit(DEFAULT_LIMIT)
    )
    fired_rows = (await db.execute(fired_stmt)).all()

    # 查询 2: acked — GROUP BY fingerprint + MIN(created_at)，返回几十/几百行
    acked_stmt = (
        select(
            fp_expr.label("fingerprint"),
            func.min(OperationLog.created_at).label("ack_at"),
        )
        .where(and_(*conditions_acked))
        .group_by(fp_expr)
    )
    acked_rows = (await db.execute(acked_stmt)).all()
    acked_map: dict[str, datetime] = {fp: ack_at for fp, ack_at in acked_rows if fp}

    # Python 字典匹配 + 计算响应时长
    response_times: list[float] = []  # 秒
    by_severity: dict[str, list[float]] = {}
    count_acked = 0
    count_pending = 0
    seen_fingerprints: set[str] = set()
    for fired_at, fp, sev in fired_rows:
        if not fp:
            continue
        # 同一 fingerprint 可能多次 fired (重复触发)，去重取最新
        if fp in seen_fingerprints:
            continue
        seen_fingerprints.add(fp)
        ack_at = acked_map.get(fp)
        if ack_at is None:
            count_pending += 1
            continue
        # H-3 修复：统一 aware/naive datetime，避免减法抛 TypeError
        delta = (_ensure_aware(ack_at) - _ensure_aware(fired_at)).total_seconds()
        if delta < 0:
            # 异常: ack 早于 fired (数据异常, 跳过)
            continue
        count_acked += 1
        response_times.append(delta)
        sev_norm = _norm_json_value(sev)
        by_severity.setdefault(sev_norm, []).append(delta)

    response_times.sort()
    n = len(response_times)
    mean = sum(response_times) / n if n > 0 else 0.0
    return {
        "total_fired": len(seen_fingerprints),
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


# ===== T2.4 EP-3 升级率 =====


async def _compute_escalation(
    db: AsyncSession,
    start_time: datetime | None,
    end_time: datetime | None,
    severity: str | None,
) -> dict[str, Any]:
    """v1.36 T2.4: 计算告警升级率.

    实现:
    1. 拉取 alert_fired (总数: 分母) — SQL GROUP BY (rule, severity)
    2. 拉取 alert_escalated (升级次数: 分子) — SQL GROUP BY (rule, severity, to_level)
    3. by_level: L1/L2/L3 各级别升级次数
    4. by_rule: Top-20 规则的升级率
    5. by_severity: 按严重度拆分升级率

    数据源: OperationLog

    PERF-P1-001: SQL GROUP BY 下推 — fired/escalated 各从 5000 行 detail 全文
    拉取改为 GROUP BY (rule, severity) / GROUP BY (rule, severity, to_level)，
    返回行数从 10000 降至几十/几百。
    """
    sev_expr = _JsonExtract(OperationLog.detail, "severity")
    rule_expr = _JsonExtract(OperationLog.detail, "rule")
    to_level_expr = _JsonExtract(OperationLog.detail, "to_level")
    new_sev_expr = _JsonExtract(OperationLog.detail, "new_severity")

    conditions_fired = [
        OperationLog.action_type == "alert_fired",
        OperationLog.target_type == "alert",
        OperationLog.created_at >= start_time,
        OperationLog.created_at <= end_time,
    ]
    conditions_escalated = [
        OperationLog.action_type == "alert_escalated",
        OperationLog.target_type == "alert",
        OperationLog.created_at >= start_time,
        OperationLog.created_at <= end_time,
    ]
    if severity:
        conditions_fired.append(sev_expr == severity)
        conditions_escalated.append(sev_expr == severity)

    # 查询 1: fired GROUP BY (rule, severity) → 返回几十行
    fired_stmt = (
        select(
            rule_expr.label("rule"),
            sev_expr.label("severity"),
            func.count().label("cnt"),
        )
        .where(and_(*conditions_fired))
        .group_by(rule_expr, sev_expr)
    )
    fired_rows = (await db.execute(fired_stmt)).all()

    rule_fired: Counter[str] = Counter()
    sev_fired: Counter[str] = Counter()
    for rule, sev, cnt in fired_rows:
        rule_fired[_norm_json_value(rule)] += cnt
        sev_fired[_norm_json_value(sev)] += cnt

    # 查询 2: escalated GROUP BY (rule, severity, to_level, new_severity) → 返回几十行
    esc_stmt = (
        select(
            rule_expr.label("rule"),
            sev_expr.label("severity"),
            to_level_expr.label("to_level"),
            new_sev_expr.label("new_severity"),
            func.count().label("cnt"),
        )
        .where(and_(*conditions_escalated))
        .group_by(rule_expr, sev_expr, to_level_expr, new_sev_expr)
    )
    esc_rows = (await db.execute(esc_stmt)).all()

    rule_esc: Counter[str] = Counter()
    sev_esc: Counter[str] = Counter()
    by_level: Counter[str] = Counter()
    for rule, sev, to_level, new_sev, cnt in esc_rows:
        rule_esc[_norm_json_value(rule)] += cnt
        sev_esc[_norm_json_value(sev)] += cnt
        # from_level/to_level 标识升级到哪个级别 (to_level 优先，回退 new_severity)
        level = to_level if to_level is not None else new_sev
        by_level[_norm_json_value(level)] += cnt

    total_fired = sum(rule_fired.values())
    total_escalated = sum(rule_esc.values())

    # 升级率 = escalated / fired
    escalation_rate = total_escalated / total_fired if total_fired > 0 else 0.0

    # 按规则计算升级率 (Top-20)
    rule_stats = []
    for rule in sorted(rule_fired.keys() | rule_esc.keys()):
        f = rule_fired.get(rule, 0)
        e = rule_esc.get(rule, 0)
        rule_stats.append(
            {
                "rule": rule,
                "fired": f,
                "escalated": e,
                "escalation_rate": e / f if f > 0 else 0.0,
            }
        )
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
