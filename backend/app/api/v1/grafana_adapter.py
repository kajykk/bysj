"""v1.37: Grafana JSON Datasource Adapter 路由.

端点 (Phase 1 - 完整 4 端点):
- T-GRAF-002 GET  /grafana/                → 根路径 (Test connection 兼容)
- T-GRAF-002 GET  /grafana/health          → 健康检查
- T-GRAF-003 POST /grafana/metrics         → 可用 metric 列表
- T-GRAF-004 POST /grafana/variable        → 变量 query 数据
- T-GRAF-005 POST /grafana/query           → panel 数据查询 (主, 7 metric)

鉴权: ``require_sa_or_admin`` (支持 SA Token + Admin User)

v1.36 兼容性:
- 不修改 v1.36 现有 8 个 REST 端点
- 复用 v1.36 ``_compute_*`` 函数
- 不修改 v1.36 数据库 schema
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_sa_or_admin
from app.models.user import User

# 类型别名: 减少 endpoint 签名噪音
_SAOrAdminDep = Depends(require_sa_or_admin)

# v1.37: 完整路径 = /api/v1 (api_router 前缀) + /alerts/observability/grafana (本 router 前缀)
router = APIRouter(prefix="/alerts/observability/grafana", tags=["grafana-adapter"])

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


# ===== 端点 1: 根路径 (Test connection 兼容) =====


@router.get("/")
async def grafana_root(
    _user: User = _SAOrAdminDep,
) -> dict:
    """v1.37 T-GRAF-002: Grafana JSON Datasource 根路径.

    ``simpod-json-datasource`` 插件在用户保存数据源时会向数据源 URL
    的根路径发送 GET 请求以验证连通性 (Test connection).

    鉴权: ``require_sa_or_admin`` —— 任何 Grafana 数据源调用都需带
    Authorization 头 (Bearer Service Account Token 或 Admin User JWT).
    """
    return {
        "status": "ok",
        "datasource": "bysj-observability-api",
        "version": "v1.37",
    }


# ===== 端点 2: Health Check =====


@router.get("/health")
async def grafana_health(
    _user: User = _SAOrAdminDep,
) -> dict:
    """v1.37 T-GRAF-002: 健康检查 (供 Grafana 仪表盘 header / alert 探针).

    返回:
        status: "ok"
        version: 后端版本
        timestamp: UTC ISO 时间戳 (用于诊断时钟漂移)
    """
    return {
        "status": "ok",
        "version": "v1.37",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


# ===== 端点 3: Metrics List (7 个 metric 定义) =====


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


@router.post("/metrics")
async def grafana_metrics(
    _user: User = _SAOrAdminDep,
) -> list[dict]:
    """v1.37 T-GRAF-003: 返回可用 metric 列表 (供 panel 配置时选择).

    ``simpod-json-datasource`` 插件要求 POST /metrics 返回标准格式:

        [
          {
            "value": "<metric_id>",
            "label": "<display_name>",
            "payloads": [
              {"name": "<param>", "type": "select", "options": [...]},
              ...
            ]
          },
          ...
        ]

    每个 metric 对应 v1.36 的一个 ``_compute_*`` 函数, 其 ``payloads``
    描述了 panel 维度过滤选项 (bucket/severity/channel 等).

    鉴权: ``require_sa_or_admin``.
    """
    return _METRICS


# ===== 端点 4: Variable Query (4 种 type) =====


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


@router.post("/variable")
async def grafana_variable(
    req: GrafanaVariableRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: User = _SAOrAdminDep,
    start_time: datetime | None = Query(
        None,
        description="开始时间 (ISO 格式). 默认: 7 天前.",
    ),
    end_time: datetime | None = Query(
        None,
        description="结束时间 (ISO 格式). 默认: 现在.",
    ),
) -> list[dict[str, str]]:
    """v1.37 T-GRAF-004: 变量 query 数据 (供 panel 下拉选择).

    支持 4 种 type:
    - **rule** —— top 20 告警规则 (从 ``_compute_trend(group_by='rule')`` 提取)
    - **matcher** —— top 10 静默规则 (从 ``_compute_silence_hit_rate.by_matcher`` 提取)
    - **operation** —— 静态列表 (push_silence / delete_silence / ...)
    - **channel** —— 静态列表 (webhook / slack / dingtalk / email)

    返回格式: ``[{"text": "<label>", "value": "<id>"}, ...]``
    兼容 Grafana variable query (Custom variable) 类型.
    """
    # 默认时间范围: 最近 7 天 (足够覆盖大多数告警 + 静默历史)
    now = datetime.now(timezone.utc)
    if end_time is None:
        end_time = now
    if start_time is None:
        start_time = now - timedelta(days=7)
    # 时区处理: 若 start_time 缺 tz, 视为 UTC
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    # P1-SEC-023 修复：校验时间范围，防止超大窗口导致 DoS
    if start_time > end_time:
        raise HTTPException(
            status_code=400,
            detail="start_time 不能晚于 end_time",
        )
    if (end_time - start_time) > timedelta(days=_GRAFANA_MAX_RANGE_DAYS):
        raise HTTPException(
            status_code=400,
            detail=f"查询时间跨度不能超过 {_GRAFANA_MAX_RANGE_DAYS} 天",
        )

    if req.type == "rule":
        # 复用 v1.36 _compute_trend, group_by="rule" 时 by_rule 是 Top-20 dict
        from app.api.v1.observability import _compute_trend

        result = await _compute_trend(
            db,
            start_time=start_time,
            end_time=end_time,
            bucket="1h",
            severity=None,
            status=None,
            group_by="rule",
        )
        # by_rule: dict[rule_name, count] -> list[{text, value}]
        by_rule = result.get("by_rule") or {}
        return [
            {"text": rule_name, "value": rule_name}
            for rule_name in list(by_rule.keys())[:20]
        ]

    if req.type == "matcher":
        # 复用 v1.36 _compute_silence_hit_rate
        from app.api.v1.observability import _compute_silence_hit_rate

        result = await _compute_silence_hit_rate(db, start_time, end_time)
        by_matcher = result.get("by_matcher") or []
        # by_matcher: list[{silence_name, silenced_count, by_severity}]
        return [
            {"text": m["silence_name"], "value": m["silence_name"]}
            for m in by_matcher[:10]
        ]

    if req.type in _STATIC_VARIABLES:
        return _STATIC_VARIABLES[req.type]

    raise HTTPException(
        status_code=400,
        detail=(
            f"未知 variable type: {req.type!r}. "
            f"支持: rule, matcher, operation, channel"
        ),
    )


# ===== 端点 5: Query (主端点, 7 metric 处理器) =====


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


async def _trend_handler(db: AsyncSession, params: dict) -> dict:
    """v1.37 T-GRAF-005: 告警趋势 → 复用 _compute_trend."""
    from app.api.v1.observability import _compute_trend

    return await _compute_trend(
        db,
        start_time=params.get("start_time"),
        end_time=params.get("end_time"),
        bucket=params.get("bucket", _DEFAULT_BUCKET),
        severity=_normalize_severity(params.get("severity")),
        status=params.get("status") if params.get("status") not in (None, "all", "") else None,
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
        return None


@router.post("/query")
async def grafana_query(
    req: GrafanaQueryRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: User = _SAOrAdminDep,
    start_time: str | None = Query(
        None,
        description="开始时间 (ISO 格式). 默认: 24h 前.",
    ),
    end_time: str | None = Query(
        None,
        description="结束时间 (ISO 格式). 默认: 现在.",
    ),
) -> list[dict]:
    """v1.37 T-GRAF-005: panel 数据查询 (主端点).

    根据 ``req.metric`` 分发到对应的 v1.36 ``_compute_*`` 函数,
    然后通过 T-GRAF-006 ``_format_for_grafana_*`` 适配器包装为
    Grafana dataframe 格式 ``[{"target", "datapoints"}, ...]``.

    时间范围通过 query param 传入 (R2S3 关键调整, 避免 POST body 字符串模板问题).

    Args:
        req: JSON body, 含 ``metric`` 和 ``params`` (severity/bucket/group_by 等)
        start_time: 时间范围起点 (ISO 格式, Grafana 全局变量 ``$__from``)
        end_time: 时间范围终点 (ISO 格式, Grafana 全局变量 ``$__to``)

    Returns:
        Grafana dataframe 格式: ``[{"target": <name>, "datapoints": [[val, ts_ms], ...]}, ...]``

    Raises:
        HTTPException 400: 未知的 metric
        HTTPException 401/403: 鉴权失败 (由 require_sa_or_admin 抛出)
    """
    # 解析时间范围 (query param 优先, 然后 body.params, 最后默认 24h)
    default_start, default_end = _default_time_range()
    qs_start = _parse_iso_datetime(start_time)
    qs_end = _parse_iso_datetime(end_time)
    body_start = req.params.get("start_time")
    body_end = req.params.get("end_time")

    final_start = qs_start or (body_start if isinstance(body_start, datetime) else default_start)
    final_end = qs_end or (body_end if isinstance(body_end, datetime) else default_end)

    # P1-SEC-023 修复：校验时间范围，防止超大窗口导致 DoS
    if final_start > final_end:
        raise HTTPException(
            status_code=400,
            detail="start_time 不能晚于 end_time",
        )
    if (final_end - final_start) > timedelta(days=_GRAFANA_MAX_RANGE_DAYS):
        raise HTTPException(
            status_code=400,
            detail=f"查询时间跨度不能超过 {_GRAFANA_MAX_RANGE_DAYS} 天",
        )

    # 将最终时间范围注入 params (供 handler 透传给 _compute_*)
    enriched_params = dict(req.params)
    enriched_params["start_time"] = final_start
    enriched_params["end_time"] = final_end

    handler = _METRIC_HANDLERS.get(req.metric)
    if handler is None:
        # P1-SEC-023 修复：Literal 已在 schema 层校验，此处为防御性兜底
        raise HTTPException(
            status_code=400,
            detail=(
                f"未知 metric: {req.metric!r}. "
                f"支持: {sorted(_METRIC_HANDLERS.keys())}"
            ),
        )

    data = await handler(db, enriched_params)
    # T-GRAF-006: 应用 Grafana dataframe 格式化适配器.
    formatter = _FORMATTERS.get(req.metric)
    if formatter is None:
        # 无格式化器时返回原始 dict (理论上 _METRIC_HANDLERS 和 _FORMATTERS 同步)
        return data
    return formatter(data)


# ===== T-GRAF-006: Grafana dataframe 格式化适配器 =====


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
        {"target": "total_pending", "datapoints": [[data.get("total_pending", 0), now_ms]]},
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
            series.append({
                "target": f"escalated_to_{level}",
                "datapoints": [[by_level[level], now_ms]],
            })
    # 概览指标
    series.append({
        "target": "escalation_rate",
        "datapoints": [[data.get("escalation_rate", 0), now_ms]],
    })
    series.append({
        "target": "total_escalated",
        "datapoints": [[data.get("total_escalated", 0), now_ms]],
    })
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
        series.append({
            "target": f"{ch_name}_success_rate",
            "datapoints": [[ch_data.get("success_rate", 0), now_ms]],
        })
        # 发送数
        series.append({
            "target": f"{ch_name}_sent",
            "datapoints": [[ch_data.get("sent", 0), now_ms]],
        })
        # 失败数
        series.append({
            "target": f"{ch_name}_failed",
            "datapoints": [[ch_data.get("failed", 0), now_ms]],
        })
        # 平均延迟
        series.append({
            "target": f"{ch_name}_avg_duration_ms",
            "datapoints": [[ch_data.get("avg_duration_ms", 0), now_ms]],
        })
    # 整体成功率
    series.append({
        "target": "overall_success_rate",
        "datapoints": [[data.get("overall_success_rate", 0), now_ms]],
    })
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
    series = [{
        "target": "silence_hit_rate",
        "datapoints": [[data.get("hit_rate", 0), now_ms]],
    }, {
        "target": "total_silenced",
        "datapoints": [[data.get("total_silenced", 0), now_ms]],
    }, {
        "target": "total_processed",
        "datapoints": [[data.get("total_processed", 0), now_ms]],
    }]
    for m in data.get("by_matcher") or []:
        series.append({
            "target": f"matcher_{m['silence_name']}",
            "datapoints": [[m.get("silenced_count", 0), now_ms]],
        })
    return series


def _format_for_grafana_am_sync(data: dict) -> list[dict]:
    """v1.37 T-GRAF-006: am_sync → success_rate gauge + by_operation stat.

    v1.36 ``_compute_am_sync`` 输出:
        success_rate, total_success, total_failed, by_operation[], recent_failures[]

    转换: success_rate gauge + by_operation 每个 op 3 series.
    """
    now_ms = _now_epoch_ms()
    series = [{
        "target": "am_sync_success_rate",
        "datapoints": [[data.get("success_rate", 0), now_ms]],
    }, {
        "target": "am_sync_total",
        "datapoints": [[data.get("total", 0), now_ms]],
    }, {
        "target": "am_sync_avg_duration_ms",
        "datapoints": [[data.get("avg_duration_ms", 0), now_ms]],
    }]
    for op in data.get("by_operation") or []:
        op_name = op.get("operation", "unknown")
        series.append({
            "target": f"am_{op_name}_success",
            "datapoints": [[op.get("success", 0), now_ms]],
        })
        series.append({
            "target": f"am_{op_name}_failed",
            "datapoints": [[op.get("failed", 0), now_ms]],
        })
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
    series = [{
        "target": "lock_acquire_rate",
        "datapoints": [[memory.get("acquire_rate", 0), now_ms]],
    }, {
        "target": "lock_fallback_rate",
        "datapoints": [[memory.get("fallback_rate", 0), now_ms]],
    }, {
        "target": "lock_error_rate",
        "datapoints": [[memory.get("error_rate", 0), now_ms]],
    }, {
        "target": "lock_memory_total",
        "datapoints": [[memory.get("total", 0), now_ms]],
    }, {
        "target": "lock_recent_flush_count",
        "datapoints": [[hist.get("recent_flush_count", 0), now_ms]],
    }]
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
