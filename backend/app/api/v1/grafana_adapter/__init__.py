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

模块拆分:
- _common:     常量 + _METRICS 列表 + Pydantic 模型 + 时间工具函数
- handlers:    7 个 metric 处理器 + _METRIC_HANDLERS 路由表
- formatters:  7 个 Grafana dataframe 格式化适配器 + _FORMATTERS 路由表
- __init__:    router + 5 端点 + re-export (向后兼容)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_sa_or_admin
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.models.user import User

# 类型别名: 减少 endpoint 签名噪音
_SAOrAdminDep = Depends(require_sa_or_admin)

# v1.37: 完整路径 = /api/v1 (api_router 前缀) + /alerts/observability/grafana (本 router 前缀)
router = APIRouter(prefix="/alerts/observability/grafana", tags=["grafana-adapter"])

from app.api.v1.grafana_adapter._common import (  # noqa: E402
    _GRAFANA_MAX_RANGE_DAYS,
    _METRICS,
    _STATIC_VARIABLES,
    GrafanaQueryRequest,
    GrafanaVariableRequest,
    _default_time_range,  # noqa: E402
    _ensure_aware,
    _parse_iso_datetime,
)
from app.api.v1.grafana_adapter.formatters import _FORMATTERS  # noqa: E402
from app.api.v1.grafana_adapter.handlers import _METRIC_HANDLERS  # noqa: E402

# ===== 端点 1: 根路径 (Test connection 兼容) =====


@router.get("/", responses=COMMON_ERROR_RESPONSES)
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


@router.get("/health", responses=COMMON_ERROR_RESPONSES)
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


@router.post("/metrics", responses=COMMON_ERROR_RESPONSES)
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


@router.post("/variable", responses=COMMON_ERROR_RESPONSES)
async def grafana_variable(
    req: GrafanaVariableRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: User = _SAOrAdminDep,
    # M-API-7 修复：与 /query 端点统一使用 str + _parse_iso_datetime 解析，避免类型不一致
    start_time: str | None = Query(
        None,
        description="开始时间 (ISO 格式). 默认: 7 天前.",
    ),
    end_time: str | None = Query(
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
    # M-API-7 修复：统一用 _parse_iso_datetime 解析，与 /query 端点行为一致
    parsed_start = _parse_iso_datetime(start_time)
    parsed_end = _parse_iso_datetime(end_time)
    # 默认时间范围: 最近 7 天 (足够覆盖大多数告警 + 静默历史)
    now = datetime.now(timezone.utc)
    if parsed_end is None:
        parsed_end = now
    if parsed_start is None:
        parsed_start = now - timedelta(days=7)
    start_time_dt = _ensure_aware(parsed_start)
    end_time_dt = _ensure_aware(parsed_end)
    # P1-SEC-023 修复：校验时间范围，防止超大窗口导致 DoS
    if start_time_dt > end_time_dt:
        raise HTTPException(
            status_code=400,
            detail="start_time 不能晚于 end_time",
        )
    if (end_time_dt - start_time_dt) > timedelta(days=_GRAFANA_MAX_RANGE_DAYS):
        raise HTTPException(
            status_code=400,
            detail=f"查询时间跨度不能超过 {_GRAFANA_MAX_RANGE_DAYS} 天",
        )

    if req.type == "rule":
        # 复用 v1.36 _compute_trend, group_by="rule" 时 by_rule 是 Top-20 dict
        from app.api.v1.observability import _compute_trend

        result = await _compute_trend(
            db,
            start_time=start_time_dt,
            end_time=end_time_dt,
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

        result = await _compute_silence_hit_rate(db, start_time_dt, end_time_dt)
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


@router.post("/query", responses=COMMON_ERROR_RESPONSES)
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

    # H-4 修复：统一归一化为 aware UTC，避免 None 或 naive datetime 进入比较
    final_start = qs_start or (
        body_start if isinstance(body_start, datetime) else default_start
    )
    final_end = qs_end or (body_end if isinstance(body_end, datetime) else default_end)
    final_start = _ensure_aware(final_start)
    final_end = _ensure_aware(final_end)

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


__all__ = [
    "router",
    "GrafanaQueryRequest",
    "GrafanaVariableRequest",
]
