"""共享基础设施: 常量、_METRICS 列表、Pydantic 模型、时间工具函数.

向后兼容: 此模块中的符号通过包 __init__ re-export,
仍可由 ``from app.api.v1.grafana_adapter import xxx`` 导入.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

# P1-SEC-023 修复：Grafana adapter 输入限制，防止滥用
_GRAFANA_MAX_RANGE_DAYS = 365  # Grafana 查询最大时间跨度
_GRAFANA_MAX_PARAMS_ENTRIES = 50
_GRAFANA_MAX_PARAM_VAL_LEN = 2048
_GRAFANA_VALID_METRICS = frozenset(
    {
        "trend",
        "response_time",
        "escalation",
        "channel_stats",
        "silence_hit_rate",
        "am_sync",
        "lock_stats",
    }
)
_GRAFANA_VALID_VAR_TYPES = frozenset({"rule", "matcher", "operation", "channel"})


# v1.37 T-GRAF-003: 7 个 metric 的 payload 定义.
# 复用 v1.36 _compute_* 函数的实际参数 (start_time/end_time 由 Grafana 全局变量提供).
_METRICS: list[dict] = [
    {
        "value": "trend",
        "label": "Alert Trend (告警趋势)",
        "payloads": [
            {
                "name": "bucket",
                "label": "Bucket Size",
                "type": "select",
                "options": [
                    {"label": "5min", "value": "5m"},
                    {"label": "15min", "value": "15m"},
                    {"label": "1hour", "value": "1h"},
                    {"label": "6hour", "value": "6h"},
                    {"label": "1day", "value": "1d"},
                ],
                "default": "1h",
            },
            {
                "name": "severity",
                "label": "Severity Filter",
                "type": "select",
                "options": [
                    {"label": "ALL", "value": "all"},
                    {"label": "P0", "value": "P0"},
                    {"label": "P1", "value": "P1"},
                    {"label": "P2", "value": "P2"},
                    {"label": "P3", "value": "P3"},
                ],
                "default": "all",
            },
            {
                "name": "status",
                "label": "Status Filter",
                "type": "select",
                "options": [
                    {"label": "ALL", "value": "all"},
                    {"label": "Firing", "value": "firing"},
                    {"label": "Resolved", "value": "resolved"},
                ],
                "default": "all",
            },
            {
                "name": "group_by",
                "label": "Group By",
                "type": "select",
                "options": [
                    {"label": "Severity", "value": "severity"},
                    {"label": "Status", "value": "status"},
                    {"label": "Rule", "value": "rule"},
                ],
                "default": "severity",
            },
        ],
    },
    {
        "value": "response_time",
        "label": "Response Time (响应时长)",
        "payloads": [
            {
                "name": "severity",
                "label": "Severity Filter",
                "type": "select",
                "options": [
                    {"label": "ALL", "value": "all"},
                    {"label": "P0", "value": "P0"},
                    {"label": "P1", "value": "P1"},
                    {"label": "P2", "value": "P2"},
                ],
                "default": "all",
            },
        ],
    },
    {
        "value": "escalation",
        "label": "Escalation Rate (升级率)",
        "payloads": [
            {
                "name": "severity",
                "label": "Severity Filter",
                "type": "select",
                "options": [
                    {"label": "ALL", "value": "all"},
                    {"label": "P1", "value": "P1"},
                    {"label": "P2", "value": "P2"},
                    {"label": "P3", "value": "P3"},
                ],
                "default": "all",
            },
        ],
    },
    {
        "value": "channel_stats",
        "label": "Channel Stats (通道成功率)",
        "payloads": [
            {
                "name": "channel",
                "label": "Channel Filter",
                "type": "select",
                "options": [
                    {"label": "ALL", "value": "all"},
                    {"label": "webhook", "value": "webhook"},
                    {"label": "slack", "value": "slack"},
                    {"label": "dingtalk", "value": "dingtalk"},
                    {"label": "email", "value": "email"},
                ],
                "default": "all",
            },
        ],
    },
    {
        "value": "silence_hit_rate",
        "label": "Silence Hit Rate (静默命中率)",
        "payloads": [],
    },
    {
        "value": "am_sync",
        "label": "AM Sync (AlertManager 同步)",
        "payloads": [
            {
                "name": "operation",
                "label": "Operation Filter",
                "type": "select",
                "options": [
                    {"label": "ALL", "value": "all"},
                    {"label": "push_silence", "value": "push_silence"},
                    {"label": "delete_silence", "value": "delete_silence"},
                    {"label": "expire_silence", "value": "expire_silence"},
                    {"label": "pull_silences", "value": "pull_silences"},
                ],
                "default": "all",
            },
        ],
    },
    {
        "value": "lock_stats",
        "label": "Redis Lock Stats (锁统计)",
        "payloads": [],
    },
]


# 静态变量表 (不依赖 DB 查询)
_STATIC_VARIABLES: dict[str, list[dict[str, str]]] = {
    "operation": [
        {"text": "ALL", "value": "all"},
        {"text": "push_silence", "value": "push_silence"},
        {"text": "delete_silence", "value": "delete_silence"},
        {"text": "expire_silence", "value": "expire_silence"},
        {"text": "pull_silences", "value": "pull_silences"},
    ],
    "channel": [
        {"text": "ALL", "value": "all"},
        {"text": "webhook", "value": "webhook"},
        {"text": "slack", "value": "slack"},
        {"text": "dingtalk", "value": "dingtalk"},
        {"text": "email", "value": "email"},
    ],
}


class GrafanaVariableRequest(BaseModel):
    """v1.37 T-GRAF-004: JSON Datasource /variable 端点的标准 body.

    simpod-json-datasource 插件在 panel 上配置 variable 时调用此端点.
    """

    # P1-SEC-023 修复：使用 Literal 限制 type 取值，防止任意字符串注入
    type: Literal["rule", "matcher", "operation", "channel"]


class GrafanaQueryRequest(BaseModel):
    """v1.37 T-GRAF-005: JSON Datasource /query 端点的标准 body.

    simpod-json-datasource 插件在 panel 渲染时调用此端点获取数据.
    """

    # P1-SEC-023 修复：使用 Literal 限制 metric 取值，防止任意字符串注入
    metric: Literal[
        "trend",
        "response_time",
        "escalation",
        "channel_stats",
        "silence_hit_rate",
        "am_sync",
        "lock_stats",
    ]
    params: dict[str, Any] = Field(
        default_factory=dict, max_length=_GRAFANA_MAX_PARAMS_ENTRIES
    )


# v1.37 T-GRAF-005: 7 个 metric 处理器.
# 每个 handler 负责:
# 1. 从 req.params 提取专属参数 (severity/bucket/group_by/channel/operation)
# 2. 调用对应的 v1.36 _compute_* 函数
# 3. 返回原始 dict (T-GRAF-006 会添加 Grafana dataframe 格式化包装)

# 注: handlers 在 _format_for_grafana_* 适配器可用之前返回原始 dict.
# T-GRAF-006 将引入 _format_for_grafana_* 函数并改写 /query 端点.
_DEFAULT_SEVERITY = "all"  # "all" = 不过滤, 与 _compute_* 约定一致
_DEFAULT_BUCKET = "1h"
_DEFAULT_GROUP_BY = "severity"


def _normalize_severity(severity: str | None) -> str | None:
    """转换 severity 过滤值: ``"all"`` -> ``None`` (v1.36 _compute_* 用 None 表示不过滤)."""
    if severity is None or severity == "all" or severity == "":
        return None
    return severity


def _default_time_range() -> tuple[datetime, datetime]:
    """默认时间范围: 最近 24 小时."""
    now = datetime.now(timezone.utc)
    return now - timedelta(hours=24), now


def _parse_iso_datetime(value: str | None) -> datetime | None:
    """解析 ISO 格式时间字符串, 容错处理 'Z' 后缀."""
    if not value:
        return None
    try:
        # Grafana 默认传 ISO 格式 (如 2026-06-03T00:00:00Z)
        cleaned = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        # H-4 修复：解析失败返回 None 由调用方走默认值兜底，不再让 None 进入后续比较
        return None


def _ensure_aware(dt: datetime) -> datetime:
    """H-4 修复：统一 datetime 为 aware UTC，避免比较时抛 TypeError."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
