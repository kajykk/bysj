"""T-GRAF-006: Grafana dataframe 格式化适配器.

7 个 metric 各对应一个 formatter, 将 v1.36 _compute_* 的原始 dict
转换为 Grafana JSON Datasource 要求的 dataframe 格式:
``[{"target": <name>, "datapoints": [[val, ts_ms], ...]}, ...]``
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _iso_to_epoch_ms(iso_str: str) -> int:
    """将 ISO 时间字符串转为 epoch 毫秒 (Grafana dataframe 要求)."""
    try:
        cleaned = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError):
        return 0


def _now_epoch_ms() -> int:
    """当前时间的 epoch 毫秒."""
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _format_for_grafana_trend(data: dict) -> list[dict]:
    """v1.37 T-GRAF-006: trend → timeseries 多序列.

    v1.36 ``_compute_trend`` 输出:
        buckets: [{"timestamp": "<ISO>", "count": N, "by_severity": {...}, "by_status": {...}}, ...]
        by_severity: 全量 P0/P1/P2 计数
        by_status: 全量 firing/resolved 计数

    转换:
        按 group_by 维度拆成多个 series, 每个 series 一个 target.
        默认 group_by="severity", 所以 P0/P1/P2/P3 各一个 series.
    """
    buckets = data.get("buckets") or []
    group_by = data.get("group_by", "severity")
    series: dict[str, list] = {}

    for bk in buckets:
        ts_ms = _iso_to_epoch_ms(bk.get("timestamp", ""))
        breakdown = bk.get(f"by_{group_by}") or {}
        for key, val in breakdown.items():
            target = f"alert_{key}" if group_by == "severity" else str(key)
            series.setdefault(target, []).append([val, ts_ms])

    # 如果没有 bucket 数据, 至少输出一个空 series (避免 Grafana 报错)
    if not series:
        series["alert_total"] = []
    # 按时间升序排序
    for tgt in series:
        series[tgt].sort(key=lambda dp: dp[1])
    return [{"target": tgt, "datapoints": dps} for tgt, dps in series.items()]


def _format_for_grafana_response_time(data: dict) -> list[dict]:
    """v1.37 T-GRAF-006: response_time → stat 多指标.

    v1.36 ``_compute_response_time`` 输出:
        response_time: {mean, p50, p95, p99, min, max}
        ack_rate, total_fired, total_acked, total_pending

    转换: 每个指标一个 series, 单点 (now).
    """
    rt = data.get("response_time") or {}
    now_ms = _now_epoch_ms()
    return [
        {"target": "response_time_mean", "datapoints": [[rt.get("mean", 0), now_ms]]},
        {"target": "response_time_p50", "datapoints": [[rt.get("p50", 0), now_ms]]},
        {"target": "response_time_p95", "datapoints": [[rt.get("p95", 0), now_ms]]},
        {"target": "response_time_p99", "datapoints": [[rt.get("p99", 0), now_ms]]},
        {"target": "ack_rate", "datapoints": [[data.get("ack_rate", 0), now_ms]]},
        {"target": "total_fired", "datapoints": [[data.get("total_fired", 0), now_ms]]},
        {
            "target": "total_pending",
            "datapoints": [[data.get("total_pending", 0), now_ms]],
        },
    ]


def _format_for_grafana_escalation(data: dict) -> list[dict]:
    """v1.37 T-GRAF-006: escalation → by_level 饼图 + 概览指标.

    v1.36 ``_compute_escalation`` 输出:
        by_level: {P0: N, P1: M, ...}
        escalation_rate, total_fired, total_escalated

    转换: by_level 拆成 P0/P1/P2 series (饼图), 加概览指标.
    """
    by_level = data.get("by_level") or {}
    now_ms = _now_epoch_ms()
    series = []
    # by_level: 每级别一个 series (Grafana 饼图/条形图可消费)
    for level in ("P0", "P1", "P2", "P3"):
        if level in by_level:
            series.append(
                {
                    "target": f"escalated_to_{level}",
                    "datapoints": [[by_level[level], now_ms]],
                }
            )
    # 概览指标
    series.append(
        {
            "target": "escalation_rate",
            "datapoints": [[data.get("escalation_rate", 0), now_ms]],
        }
    )
    series.append(
        {
            "target": "total_escalated",
            "datapoints": [[data.get("total_escalated", 0), now_ms]],
        }
    )
    if not series:
        series = [{"target": "escalation_empty", "datapoints": []}]
    return series


def _format_for_grafana_channel_stats(data: dict) -> list[dict]:
    """v1.37 T-GRAF-006: channel_stats → per-channel stat + bargauge.

    v1.36 ``_compute_channel_stats`` 输出:
        channels: {webhook: {sent, failed, total, success_rate, avg_duration_ms, max_duration_ms}, ...}
        overall_success_rate, total_sent, total_failed

    转换: 每个通道 3 个 series (success_rate / sent / failed).
    """
    channels = data.get("channels") or {}
    now_ms = _now_epoch_ms()
    series = []
    for ch_name, ch_data in channels.items():
        # 成功率 (bargauge 友好)
        series.append(
            {
                "target": f"{ch_name}_success_rate",
                "datapoints": [[ch_data.get("success_rate", 0), now_ms]],
            }
        )
        # 发送数
        series.append(
            {
                "target": f"{ch_name}_sent",
                "datapoints": [[ch_data.get("sent", 0), now_ms]],
            }
        )
        # 失败数
        series.append(
            {
                "target": f"{ch_name}_failed",
                "datapoints": [[ch_data.get("failed", 0), now_ms]],
            }
        )
        # 平均延迟
        series.append(
            {
                "target": f"{ch_name}_avg_duration_ms",
                "datapoints": [[ch_data.get("avg_duration_ms", 0), now_ms]],
            }
        )
    # 整体成功率
    series.append(
        {
            "target": "overall_success_rate",
            "datapoints": [[data.get("overall_success_rate", 0), now_ms]],
        }
    )
    if not series:
        series = [{"target": "channels_empty", "datapoints": []}]
    return series


def _format_for_grafana_silence_hit_rate(data: dict) -> list[dict]:
    """v1.37 T-GRAF-006: silence_hit_rate → hit_rate + by_matcher bargauge.

    v1.36 ``_compute_silence_hit_rate`` 输出:
        hit_rate, by_matcher: [{silence_name, silenced_count, by_severity}, ...]

    转换: hit_rate 单点, by_matcher 每个 matcher 一个 series.
    """
    now_ms = _now_epoch_ms()
    series = [
        {
            "target": "silence_hit_rate",
            "datapoints": [[data.get("hit_rate", 0), now_ms]],
        },
        {
            "target": "total_silenced",
            "datapoints": [[data.get("total_silenced", 0), now_ms]],
        },
        {
            "target": "total_processed",
            "datapoints": [[data.get("total_processed", 0), now_ms]],
        },
    ]
    for m in data.get("by_matcher") or []:
        series.append(
            {
                "target": f"matcher_{m['silence_name']}",
                "datapoints": [[m.get("silenced_count", 0), now_ms]],
            }
        )
    return series


def _format_for_grafana_am_sync(data: dict) -> list[dict]:
    """v1.37 T-GRAF-006: am_sync → success_rate gauge + by_operation stat.

    v1.36 ``_compute_am_sync`` 输出:
        success_rate, total_success, total_failed, by_operation[], recent_failures[]

    转换: success_rate gauge + by_operation 每个 op 3 series.
    """
    now_ms = _now_epoch_ms()
    series = [
        {
            "target": "am_sync_success_rate",
            "datapoints": [[data.get("success_rate", 0), now_ms]],
        },
        {
            "target": "am_sync_total",
            "datapoints": [[data.get("total", 0), now_ms]],
        },
        {
            "target": "am_sync_avg_duration_ms",
            "datapoints": [[data.get("avg_duration_ms", 0), now_ms]],
        },
    ]
    for op in data.get("by_operation") or []:
        op_name = op.get("operation", "unknown")
        series.append(
            {
                "target": f"am_{op_name}_success",
                "datapoints": [[op.get("success", 0), now_ms]],
            }
        )
        series.append(
            {
                "target": f"am_{op_name}_failed",
                "datapoints": [[op.get("failed", 0), now_ms]],
            }
        )
    return series


def _format_for_grafana_lock_stats(data: dict) -> list[dict]:
    """v1.37 T-GRAF-006: lock_stats → memory gauge + recent_flushes 详情.

    v1.36 ``_compute_lock_stats`` 输出:
        memory: {acquired, skipped, fallback, errors, total, acquire_rate, fallback_rate, error_rate}
        historical_recent: {recent_flush_count, total_acquired, ...}
        recent_flushes: [...]
    """
    now_ms = _now_epoch_ms()
    memory = data.get("memory") or {}
    hist = data.get("historical_recent") or {}
    series = [
        {
            "target": "lock_acquire_rate",
            "datapoints": [[memory.get("acquire_rate", 0), now_ms]],
        },
        {
            "target": "lock_fallback_rate",
            "datapoints": [[memory.get("fallback_rate", 0), now_ms]],
        },
        {
            "target": "lock_error_rate",
            "datapoints": [[memory.get("error_rate", 0), now_ms]],
        },
        {
            "target": "lock_memory_total",
            "datapoints": [[memory.get("total", 0), now_ms]],
        },
        {
            "target": "lock_recent_flush_count",
            "datapoints": [[hist.get("recent_flush_count", 0), now_ms]],
        },
    ]
    return series


# metric -> formatter 路由表
_FORMATTERS: dict[str, Any] = {
    "trend": _format_for_grafana_trend,
    "response_time": _format_for_grafana_response_time,
    "escalation": _format_for_grafana_escalation,
    "channel_stats": _format_for_grafana_channel_stats,
    "silence_hit_rate": _format_for_grafana_silence_hit_rate,
    "am_sync": _format_for_grafana_am_sync,
    "lock_stats": _format_for_grafana_lock_stats,
}
