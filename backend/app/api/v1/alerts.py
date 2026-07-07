"""v1.33: 告警接收与查询 API.

端点:
- POST /api/v1/alerts/webhook: 接收 AlertManager Webhook
- GET /api/v1/alerts/history: 查询告警历史
- POST /api/v1/alerts/{id}/ack: 确认告警 (停止升级)
"""

from __future__ import annotations

import ipaddress
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.rate_limit import limiter
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


def _validate_url_safety(url: str | None, field_name: str = "url") -> str | None:
    """C-API-3 修复：校验 URL 安全性，防止 SSRF.

    - 必须以 http:// 或 https:// 开头（拒绝 javascript:, data:, file: 等）
    - 不指向内网/元数据地址（169.254.169.254, 127.0.0.1, 10.x, 192.168.x, 172.16-31.x）
    """
    if not url:
        return url
    url = url.strip()
    if not url:
        return url
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"{field_name} 必须以 http:// 或 https:// 开头")
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return url
        # 拒绝 localhost 和云元数据地址
        if hostname in ("localhost", "0.0.0.0", "::1") or hostname.startswith(
            "169.254."
        ):
            raise ValueError(f"{field_name} 不允许指向本机或元数据地址")
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValueError(f"{field_name} 不允许指向内网/保留 IP 地址")
        except ValueError:
            # 非 IP 格式（域名），允许通过
            pass
    except ValueError:
        raise
    except Exception:
        # 解析失败时放行（AlertManager 的 generatorURL 通常是合法 URL）
        pass
    return url


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
        # C-API-3 修复：校验 generatorURL 协议，防止 SSRF
        if self.generatorURL:
            self.generatorURL = _validate_url_safety(self.generatorURL, "generatorURL")
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

    @model_validator(mode="after")
    def _validate_payload_urls(self) -> "AlertManagerPayload":
        """C-API-3 修复：校验 externalURL 协议，防止 SSRF."""
        if self.externalURL:
            self.externalURL = _validate_url_safety(self.externalURL, "externalURL")
        return self


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


# ===== Endpoints =====


@router.post("/webhook", responses=COMMON_ERROR_RESPONSES)
@limiter.limit("10/minute")
async def alertmanager_webhook(
    request: Request,
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
    if not expected_secret:
        if settings.app_env.lower() == "production":
            # 生产环境且未配置密钥：拒绝访问
            logger.error(
                "[alerts/webhook] ALERTMANAGER_WEBHOOK_SECRET not configured in production"
            )
            raise HTTPException(
                status_code=503,
                detail="Webhook disabled: ALERTMANAGER_WEBHOOK_SECRET not configured",
            )
        # C-API-1 修复：非生产环境使用默认 dev secret，不再完全开放。
        # 原实现开发环境完全无鉴权，任何外部请求都能注入伪造告警，
        # 通过 CompositeNotifier 触发真实通知通道（webhook/slack/email），造成告警风暴。
        expected_secret = "dev-only-webhook-secret"
    # 所有环境统一鉴权校验
    if not authorization or not authorization.startswith("Bearer "):
        logger.warning("[alerts/webhook] missing or malformed Authorization header")
        raise HTTPException(
            status_code=401, detail="Unauthorized: missing bearer token"
        )
    provided = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(provided, expected_secret):
        logger.warning("[alerts/webhook] invalid webhook secret")
        raise HTTPException(status_code=403, detail="Forbidden: invalid webhook secret")

    from app.monitoring.dedup import should_send
    from app.monitoring.silence import is_silenced

    alerts = _parse_alertmanager_payload(payload)
    if not alerts:
        logger.info("[alerts/webhook] received empty payload")
        return {"status": "ok", "processed": 0}

    notifier = CompositeNotifier()
    processed = 0
    # H-API-11 修复：区分持久化失败与通知失败，避免异常被静默吞掉导致状态不一致
    failed = 0
    notify_failed = 0
    for alert in alerts:
        # v1.34: 静默检查
        silenced, silence_rule = await is_silenced(alert, db)
        if silenced:
            logger.info(
                "[alerts/webhook] silenced (fingerprint=%s, silence_id=%s)",
                alert.fingerprint,
                silence_rule.id if silence_rule else None,
            )
            # 持久化但 action_type 标记为 alert_silenced
            try:
                # H-2 修复：使用 savepoint 隔离每条告警的持久化，flush 失败时仅回滚该 savepoint，
                # 避免会话进入 PendingRollbackError 状态导致后续所有操作持续失败。
                async with db.begin_nested():
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
                # H-API-11 修复：持久化失败计入 failed，避免被静默吞掉
                failed += 1
            processed += 1
            continue

        # v1.34: 去重检查 (持久化前, 避免看到自己)
        try:
            send = await should_send(alert, db)
        except Exception as exc:
            logger.error(
                "[alerts/webhook] dedup check failed (defaulting to send): %s", exc
            )
            send = True

        # 持久化 (审计完整)
        try:
            # H-2 修复：使用 savepoint 隔离每条告警的持久化，_persist_alert_log 内部的
            # db.flush() 失败时仅回滚该 savepoint，不影响后续告警的处理。
            async with db.begin_nested():
                alert_id = await _persist_alert_log(db, alert)
            logger.info(
                "[alerts/webhook] persisted rule=%s severity=%s status=%s id=%s",
                alert.rule,
                alert.severity,
                alert.status,
                alert_id,
            )
        except Exception as exc:
            logger.error("[alerts/webhook] persist failed: %s", exc)
            # H-API-11 修复：持久化失败计入 failed 并跳过通知，避免审计记录丢失仍触发通知
            failed += 1
            continue

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
            # H-API-11 修复：通知失败计入 notify_failed，告警状态可能仍为 firing，便于后续重试
            notify_failed += 1
        processed += 1
    # H-2 修复：末尾 commit 包裹 try/except，失败时记录日志但仍返回 200，
    # 满足 AlertManager webhook "always 200" 契约，避免 AlertManager 重试导致重复告警。
    try:
        await db.commit()
    except Exception as exc:
        logger.error("[alerts/webhook] final commit failed: %s", exc)
    return {
        "status": "ok",
        "processed": processed,
        "failed": failed,
        "notify_failed": notify_failed,
    }


@router.get("/history", response_model=dict, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("60/minute")
async def list_alert_history(
    request: Request,
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
    # M-API-1 修复：统一为 naive UTC 用于与 naive DB 列比较，避免服务器非 UTC 时查询窗口偏移
    start_time = _to_naive_utc(start_time)
    end_time = _to_naive_utc(end_time)
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
    # ISS-042 修复：原 contains 子串匹配存在误匹配风险（如 "P1" 误匹配 "P10"）。
    # 当前通过尾随引号 `"severity": "P1"` 实现精确值匹配（JSON 序列化后必然以 `"` 结尾），
    # 并在 Python 端二次校验 detail["severity"] == severity 严格相等，确保不会误匹配。
    # 同时匹配有无空格两种 JSON 序列化格式，避免格式差异导致漏匹配。
    # TODO(H-API-3): 为 OperationLog 增加独立 severity 字段或使用 PostgreSQL JSONB ->> 操作符
    if severity:
        conditions.append(
            or_(
                OperationLog.detail.contains(f'"severity": "{severity}"'),
                OperationLog.detail.contains(f'"severity":"{severity}"'),
            )
        )

    stmt = select(OperationLog).where(and_(*conditions))
    count_stmt = select(func.count()).select_from(OperationLog).where(and_(*conditions))

    # TODO(M-API-4): 当前硬编码 order_by(desc(created_at))，后续需支持自定义排序参数
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
        # ISS-042 修复：Python 端二次校验 severity 严格相等，作为 SQL contains 的安全兜底。
        # SQL 层 `"severity": "P1"` 模式因尾随引号实际等价精确匹配（JSON 序列化必然以 `"` 结尾），
        # 此处仅防御性兜底，正常情况下不会过滤掉任何行，不影响 total 统计。
        if severity and detail.get("severity") != severity:
            continue
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


@router.post("/{alert_id}/ack", response_model=dict, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("30/minute")
async def acknowledge_alert(
    request: Request,
    alert_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> dict:
    """v1.33: 确认告警 (停止自动升级)."""
    # H-API-4 修复：使用 with_for_update 锁定 alert 行，序列化并发确认操作，消除 TOCTOU 竞态
    # SQLite 下 with_for_update 为 no-op，PostgreSQL 下会对该行加排他锁
    row = (
        await db.execute(
            select(OperationLog).where(OperationLog.id == alert_id).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="alert not found")
    if row.action_type != "alert_fired":
        raise HTTPException(
            status_code=400, detail="only firing alerts can be acknowledged"
        )

    # H-04 修复：检查是否已存在确认记录，防止重复确认
    # 持锁后再次检查，此时能看到前一个事务已提交的 ack 记录
    existing_ack = (
        await db.execute(
            select(OperationLog).where(
                OperationLog.target_id == alert_id,
                OperationLog.action_type == "alert_acknowledged",
            )
        )
    ).scalar_one_or_none()
    if existing_ack:
        return ok({"message": "Alert already acknowledged", "alert_id": alert_id})

    # H-06 修复：审计日志不可变 - 不修改原始 alert_fired 行的 detail
    # 改为只插入新的 alert_acknowledged 行，通过 target_id 关联原始告警
    # 查询历史时通过 JOIN 或子查询获取 ack 状态
    ack_log = OperationLog(
        operator_id=current_user.id,
        operator_role="admin",
        action_type="alert_acknowledged",
        target_type="alert",
        target_id=alert_id,
        detail=json.dumps(
            {
                "acknowledged": True,
                "acknowledged_by": current_user.id,
                "acknowledged_at": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            },
            ensure_ascii=False,
        )[:5000],
    )
    db.add(ack_log)
    await db.commit()
    return ok({"alert_id": alert_id, "acknowledged": True})


# ===== v1.35: 归档查询 =====


@router.get("/archive", response_model=dict, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("60/minute")
async def list_alert_archive(
    request: Request,
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
    # M-API-1 修复：统一为 naive UTC 用于与 naive DB 列比较，避免服务器非 UTC 时查询窗口偏移
    start_time = _to_naive_utc(start_time)
    end_time = _to_naive_utc(end_time)
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
    # TODO(M-API-4): 当前硬编码 order_by(desc(created_at))，后续需支持自定义排序参数
    stmt = (
        stmt.order_by(desc(AlertArchive.original_created_at))
        .offset(offset)
        .limit(page_size)
    )

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
                    "original_created_at": (
                        r.original_created_at.isoformat()
                        if r.original_created_at
                        else None
                    ),
                    "archived_at": r.archived_at.isoformat() if r.archived_at else None,
                }
                for r in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )
