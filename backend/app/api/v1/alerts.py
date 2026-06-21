"""v1.33: 告警接收与查询 API.

端点:
- POST /api/v1/alerts/webhook: 接收 AlertManager Webhook
- GET /api/v1/alerts/history: 查询告警历史
- POST /api/v1/alerts/{id}/ack: 确认告警 (停止升级)
"""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
from app.core.deps import require_role
from app.core.response import ok
from app.models.admin import OperationLog
from app.models.user import User
from app.monitoring.notifier import AlertPayload, CompositeNotifier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])

# P1-SEC-022 修复：查询时间范围限制，防止超大窗口导致 DoS
_HISTORY_MAX_RANGE_DAYS = 90  # 告警历史查询最大时间跨度
# P1-SEC-024 修复：AlertManager payload 大小限制，防止恶意大 payload 耗尽资源
_ALERT_MAX_LABELS = 50
_ALERT_MAX_LABEL_KEY_LEN = 128
_ALERT_MAX_LABEL_VAL_LEN = 2048
_ALERT_MAX_ANNOTATIONS = 50
_ALERT_MAX_ANNOTATION_VAL_LEN = 4096
_ALERT_MAX_URL_LEN = 2048
_ALERT_MAX_LIST_SIZE = 500
_ALERT_MAX_MSG_LEN = 4096


# ===== Request/Response Models =====


class AlertManagerAlert(BaseModel):
    """v1.33: AlertManager 单条告警."""

    status: str = "firing"  # firing/resolved
    labels: dict[str, str] = Field(default_factory=dict, max_length=_ALERT_MAX_LABELS)
    annotations: dict[str, str] = Field(
        default_factory=dict, max_length=_ALERT_MAX_ANNOTATIONS
    )
    startsAt: str | None = Field(default=None, max_length=64)
    endsAt: str | None = Field(default=None, max_length=64)
    generatorURL: str | None = Field(default=None, max_length=_ALERT_MAX_URL_LEN)
    fingerprint: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def _validate_alert_fields(self) -> "AlertManagerAlert":
        """P1-SEC-024 修复：校验 labels/annotations 键值长度."""
        for key, value in self.labels.items():
            if len(key) > _ALERT_MAX_LABEL_KEY_LEN:
                raise ValueError(
                    f"label key 长度不能超过 {_ALERT_MAX_LABEL_KEY_LEN} 字符"
                )
            if len(value) > _ALERT_MAX_LABEL_VAL_LEN:
                raise ValueError(
                    f"label value 长度不能超过 {_ALERT_MAX_LABEL_VAL_LEN} 字符"
                )
        for key, value in self.annotations.items():
            if len(key) > _ALERT_MAX_LABEL_KEY_LEN:
                raise ValueError(
                    f"annotation key 长度不能超过 {_ALERT_MAX_LABEL_KEY_LEN} 字符"
                )
            if len(value) > _ALERT_MAX_ANNOTATION_VAL_LEN:
                raise ValueError(
                    f"annotation value 长度不能超过 {_ALERT_MAX_ANNOTATION_VAL_LEN} 字符"
                )
        return self


class AlertManagerPayload(BaseModel):
    """v1.33: AlertManager webhook payload (v4 格式)."""

    version: str = Field(default="1", max_length=32)
    groupKey: str | None = Field(default=None, max_length=512)
    status: str = Field(default="firing", max_length=32)
    receiver: str | None = Field(default=None, max_length=128)
    groupLabels: dict[str, str] = Field(
        default_factory=dict, max_length=_ALERT_MAX_LABELS
    )
    commonLabels: dict[str, str] = Field(
        default_factory=dict, max_length=_ALERT_MAX_LABELS
    )
    commonAnnotations: dict[str, str] = Field(
        default_factory=dict, max_length=_ALERT_MAX_ANNOTATIONS
    )
    externalURL: str | None = Field(default=None, max_length=_ALERT_MAX_URL_LEN)
    alerts: list[AlertManagerAlert] = Field(
        default_factory=list, max_length=_ALERT_MAX_LIST_SIZE
    )


class AlertHistoryItem(BaseModel):
    """v1.33: 告警历史条目."""

    id: int
    rule: str
    severity: str
    status: str
    message: str
    fingerprint: str | None = None
    operator_id: int | None = None
    operator_role: str | None = None
    created_at: str | None = None


# ===== Helpers =====


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
    )[:5000]  # 限制 detail 长度
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


# ===== Endpoints =====


@router.post("/webhook")
async def alertmanager_webhook(
    payload: AlertManagerPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: str | None = Header(default=None),
) -> dict:
    """v1.34: 接收 AlertManager Webhook (含去重 + 静默).

    CRIT-006 修复：添加共享密钥鉴权，防止未授权的告警注入。
    生产环境必须配置 ALERTMANAGER_WEBHOOK_SECRET，AlertManager 需在
    Authorization header 中发送 "Bearer <secret>"。

    行为:
    1. 验证 webhook 密钥
    2. 解析每条 alert
    3. 检查静默规则 -> 静默期内只持久化不通知
    4. 检查去重 (5min) -> 重复 fingerprint 不通知
    5. 持久化到 OperationLog
    6. 触发 CompositeNotifier
    7. 返回 200 (避免 AlertManager 重试)
    """
    # CRIT-006 修复：Webhook 密钥鉴权
    from app.core.config import settings

    expected_secret = settings.alertmanager_webhook_secret
    if expected_secret:
        # 生产环境：必须提供正确的 Bearer token
        if not authorization or not authorization.startswith("Bearer "):
            logger.warning("[alerts/webhook] missing or malformed Authorization header")
            raise HTTPException(status_code=401, detail="Unauthorized: missing bearer token")
        provided = authorization.removeprefix("Bearer ").strip()
        if not secrets.compare_digest(provided, expected_secret):
            logger.warning("[alerts/webhook] invalid webhook secret")
            raise HTTPException(status_code=403, detail="Forbidden: invalid webhook secret")
    elif settings.app_env.lower() == "production":
        # 生产环境且未配置密钥：拒绝访问
        logger.error("[alerts/webhook] ALERTMANAGER_WEBHOOK_SECRET not configured in production")
        raise HTTPException(
            status_code=503,
            detail="Webhook disabled: ALERTMANAGER_WEBHOOK_SECRET not configured",
        )
    # 开发环境且未配置密钥：允许访问（便于本地测试）

    from app.monitoring.dedup import should_send
    from app.monitoring.silence import is_silenced

    alerts = _parse_alertmanager_payload(payload)
    if not alerts:
        logger.info("[alerts/webhook] received empty payload")
        return {"status": "ok", "processed": 0}

    notifier = CompositeNotifier()
    processed = 0
    for alert in alerts:
        # v1.34: 静默检查
        silenced, silence_rule = await is_silenced(alert, db)
        if silenced:
            logger.info(
                "[alerts/webhook] silenced (fingerprint=%s, silence_id=%s)",
                alert.fingerprint, silence_rule.id if silence_rule else None,
            )
            # 持久化但 action_type 标记为 alert_silenced
            try:
                detail = json.dumps(
                    {
                        "rule": alert.rule,
                        "severity": alert.severity,
                        "fingerprint": alert.fingerprint,
                        "labels": alert.labels,
                        "annotations": alert.annotations,
                        "message": alert.message,
                        "silenced_by": silence_rule.id if silence_rule else None,
                        "silence_name": silence_rule.name if silence_rule else None,
                    },
                    ensure_ascii=False,
                )[:5000]
                sil_log = OperationLog(
                    operator_id=None,
                    operator_role="system",
                    action_type="alert_silenced",
                    target_type="alert",
                    target_id=None,
                    detail=detail,
                )
                db.add(sil_log)
            except Exception as exc:
                logger.error("[alerts/webhook] persist silenced failed: %s", exc)
            processed += 1
            continue

        # v1.34: 去重检查 (持久化前, 避免看到自己)
        try:
            send = await should_send(alert, db)
        except Exception as exc:
            logger.error("[alerts/webhook] dedup check failed (defaulting to send): %s", exc)
            send = True

        # 持久化 (审计完整)
        try:
            alert_id = await _persist_alert_log(db, alert)
            logger.info(
                "[alerts/webhook] persisted rule=%s severity=%s status=%s id=%s",
                alert.rule, alert.severity, alert.status, alert_id,
            )
        except Exception as exc:
            logger.error("[alerts/webhook] persist failed: %s", exc)

        if not send:
            logger.info(
                "[alerts/webhook] dedup skip (fingerprint=%s)",
                alert.fingerprint,
            )
            processed += 1
            continue

        # 通知
        try:
            await notifier.send(alert, db=db)
        except Exception as exc:
            logger.error("[alerts/webhook] notify failed: %s", exc)
        processed += 1
    await db.commit()
    return {"status": "ok", "processed": processed}


@router.get("/history", response_model=dict)
async def list_alert_history(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_role("admin"))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    severity: str | None = Query(default=None, pattern="^(P0|P1|P2)$"),
    status: str | None = Query(default=None, pattern="^(firing|resolved)$"),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
) -> dict:
    """v1.33: 查询告警历史 (admin).

    从 OperationLog 表过滤 action_type = 'alert_fired' / 'alert_resolved'。
    """
    # P1-SEC-022 修复：校验时间范围
    _validate_history_time_range(start_time, end_time)
    offset = (page - 1) * page_size

    # 基础条件: alert 相关
    conditions = [
        OperationLog.action_type.in_(["alert_fired", "alert_resolved"]),
    ]
    if start_time:
        conditions.append(OperationLog.created_at >= start_time)
    if end_time:
        conditions.append(OperationLog.created_at <= end_time)

    # M5 修复：status 过滤下推到 SQL (基于 action_type 推断 status)
    if status == "firing":
        conditions.append(OperationLog.action_type == "alert_fired")
    elif status == "resolved":
        conditions.append(OperationLog.action_type == "alert_resolved")

    # M5 修复：severity 过滤下推到 SQL (detail 是 JSON 字符串，使用 contains 匹配)
    # severity 值为 P0/P1/P2，labels 中 severity 值为 critical/warning/info，不会冲突
    if severity:
        conditions.append(OperationLog.detail.contains(f'"severity": "{severity}"'))

    stmt = select(OperationLog).where(and_(*conditions))
    count_stmt = select(func.count()).select_from(OperationLog).where(and_(*conditions))

    stmt = stmt.order_by(desc(OperationLog.created_at)).offset(offset).limit(page_size)
    rows = (await db.execute(stmt)).scalars().all()
    total = (await db.execute(count_stmt)).scalar_one()

    items: list[dict[str, Any]] = []
    for r in rows:
        detail: dict = {}
        try:
            if r.detail:
                detail = json.loads(r.detail)
        except Exception as exc:
            # P1-E 修复：告警 detail JSON 解析失败必须记录日志，便于发现告警数据损坏
            logger.warning("Failed to parse alert detail JSON (id=%s): %s", r.id, exc)
            detail = {}
        item = {
            "id": r.id,
            "rule": detail.get("rule", ""),
            "severity": detail.get("severity", ""),
            "status": "firing" if r.action_type == "alert_fired" else "resolved",
            "message": detail.get("message", ""),
            "fingerprint": detail.get("fingerprint"),
            "operator_id": r.operator_id,
            "operator_role": r.operator_role,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        items.append(item)

    return ok(
        {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("/{alert_id}/ack", response_model=dict)
async def acknowledge_alert(
    alert_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> dict:
    """v1.33: 确认告警 (停止自动升级)."""
    row = (await db.execute(select(OperationLog).where(OperationLog.id == alert_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="alert not found")
    if row.action_type != "alert_fired":
        raise HTTPException(status_code=400, detail="only firing alerts can be acknowledged")

    # 在 detail 中追加 ack 标记
    detail: dict = {}
    try:
        detail = json.loads(row.detail or "{}")
    except Exception as exc:
        # P1-E 修复：告警 detail JSON 解析失败必须记录日志，便于发现告警数据损坏
        logger.warning("Failed to parse alert detail JSON (id=%s): %s", row.id, exc)
        detail = {}

    detail["acknowledged"] = True
    detail["acknowledged_by"] = current_user.id
    detail["acknowledged_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    row.detail = json.dumps(detail, ensure_ascii=False)[:5000]
    # 记录新行 (ack 操作)
    ack_log = OperationLog(
        operator_id=current_user.id,
        operator_role="admin",
        action_type="alert_acknowledged",
        target_type="alert",
        target_id=alert_id,
        detail=json.dumps({"acknowledged_by": current_user.id}, ensure_ascii=False),
    )
    db.add(ack_log)
    await db.commit()
    return ok({"alert_id": alert_id, "acknowledged": True})


# ===== v1.35: 归档查询 =====


@router.get("/archive", response_model=dict)
async def list_alert_archive(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_role("admin"))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    rule: str | None = Query(default=None, max_length=200),
    severity: str | None = Query(default=None, pattern="^(P0|P1|P2)$"),
    status: str | None = Query(default=None, pattern="^(firing|resolved)$"),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
) -> dict:
    """v1.35: 查询告警归档 (admin).

    AlertArchive 是 90 天前告警的只读表.
    适用于审计、复盘、合规审查.
    """
    from app.models.admin import AlertArchive

    # P1-SEC-022 修复：校验时间范围
    _validate_history_time_range(start_time, end_time)
    offset = (page - 1) * page_size
    conditions = []
    if rule:
        conditions.append(AlertArchive.rule == rule)
    if severity:
        conditions.append(AlertArchive.severity == severity)
    if status:
        conditions.append(AlertArchive.status == status)
    if start_time:
        conditions.append(AlertArchive.original_created_at >= start_time)
    if end_time:
        conditions.append(AlertArchive.original_created_at <= end_time)

    stmt = select(AlertArchive)
    count_stmt = select(func.count()).select_from(AlertArchive)
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))
    stmt = stmt.order_by(desc(AlertArchive.original_created_at)).offset(offset).limit(page_size)

    rows = (await db.execute(stmt)).scalars().all()
    total = (await db.execute(count_stmt)).scalar_one()

    return ok(
        {
            "items": [
                {
                    "id": r.id,
                    "original_id": r.original_id,
                    "rule": r.rule,
                    "severity": r.severity,
                    "status": r.status,
                    "message": r.message,
                    "labels": r.labels or {},
                    "annotations": r.annotations or {},
                    "fingerprint": r.fingerprint,
                    "original_created_at": r.original_created_at.isoformat() if r.original_created_at else None,
                    "archived_at": r.archived_at.isoformat() if r.archived_at else None,
                }
                for r in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )
