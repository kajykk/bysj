"""v1.33: 告警处理工具函数 (从 alerts.py 拆分).

包含:
- _validate_history_time_range: 查询时间范围校验
- _to_naive_utc: datetime 统一为 naive UTC
- _parse_alertmanager_payload: 解析 AlertManager payload
- _persist_alert_log: 持久化告警到 OperationLog
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.alerts._schemas import (
    _ALERT_MAX_MSG_LEN,
    AlertManagerPayload,
)
from app.models.admin import OperationLog
from app.monitoring.notifier import AlertPayload

logger = logging.getLogger(__name__)

# P1-SEC-022 修复：查询时间范围限制，防止超大窗口导致 DoS
_HISTORY_MAX_RANGE_DAYS = 90  # 告警历史查询最大时间跨度


def _validate_history_time_range(
    start_time: datetime | None,
    end_time: datetime | None,
) -> None:
    """P1-SEC-022 修复：校验查询时间范围，防止超大窗口导致 DoS.

    规则:
    1. 若同时提供 start_time 和 end_time，则 start_time <= end_time
    2. 时间跨度不能超过 _HISTORY_MAX_RANGE_DAYS 天
    """
    if start_time is None or end_time is None:
        return
    if start_time > end_time:
        raise HTTPException(
            status_code=400,
            detail="start_time 不能晚于 end_time",
        )
    # 统一为 timezone-aware UTC 进行比较
    s = start_time if start_time.tzinfo else start_time.replace(tzinfo=timezone.utc)
    e = end_time if end_time.tzinfo else end_time.replace(tzinfo=timezone.utc)
    if (e - s) > timedelta(days=_HISTORY_MAX_RANGE_DAYS):
        raise HTTPException(
            status_code=400,
            detail=f"查询时间跨度不能超过 {_HISTORY_MAX_RANGE_DAYS} 天",
        )


def _to_naive_utc(dt: datetime | None) -> datetime | None:
    """M-API-1 修复：将 datetime 统一为 naive UTC，用于与 naive DB 列比较.

    服务器非 UTC 时区时，aware datetime 直接与 naive DB 列比较会导致查询窗口偏移。
    naive datetime 假设为 UTC（项目约定），aware datetime 先转 UTC 再去除 tzinfo。
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_alertmanager_payload(payload: AlertManagerPayload) -> list[AlertPayload]:
    """解析 AlertManager payload 为内部 AlertPayload 列表."""
    out: list[AlertPayload] = []
    for alert in payload.alerts:
        labels = {**payload.commonLabels, **alert.labels}
        annotations = {**payload.commonAnnotations, **alert.annotations}
        severity = labels.get("severity", "P2")
        # normalize: critical -> P0, warning -> P1
        if severity in ("critical",):
            severity = "P0"
        elif severity in ("warning",):
            severity = "P1"
        elif severity in ("info",):
            severity = "P2"
        rule = labels.get("alertname", "UnknownAlert")
        msg = annotations.get("summary") or annotations.get("description") or rule
        # P1-SEC-024 修复：限制 message 长度，防止超长文本导致日志/DB 膨胀
        if len(msg) > _ALERT_MAX_MSG_LEN:
            msg = msg[:_ALERT_MAX_MSG_LEN]
        out.append(
            AlertPayload(
                rule=rule,
                severity=severity,
                status=alert.status or payload.status,
                message=msg,
                labels=labels,
                annotations=annotations,
                fingerprint=alert.fingerprint or payload.groupKey,
                starts_at=alert.startsAt,
                ends_at=alert.endsAt,
                generator_url=alert.generatorURL,
            )
        )
    return out


async def _persist_alert_log(
    db: AsyncSession,
    alert: AlertPayload,
    operator_id: int | None = None,
    operator_role: str = "system",
) -> int:
    """持久化告警到 OperationLog. 返回新行 ID."""
    action_type = "alert_fired" if alert.status == "firing" else "alert_resolved"
    detail = json.dumps(
        {
            "rule": alert.rule,
            "severity": alert.severity,
            "fingerprint": alert.fingerprint,
            "labels": alert.labels,
            "annotations": alert.annotations,
            "message": alert.message,
        },
        ensure_ascii=False,
    )[
        :5000
    ]  # 限制 detail 长度
    row = OperationLog(
        operator_id=operator_id,
        operator_role=operator_role,
        action_type=action_type,
        target_type="alert",
        target_id=None,
        detail=detail,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row.id
