"""v1.33: 告警接收与查询 API.

端点:
- POST /api/v1/alerts/webhook: 接收 AlertManager Webhook
- GET /api/v1/alerts/history: 查询告警历史
- POST /api/v1/alerts/{id}/ack: 确认告警 (停止升级)
- GET /api/v1/alerts/archive: 查询告警归档 (v1.35)

模块拆分 (维护性优化):
- _schemas:  Pydantic 模型 + _validate_url_safety + _ALERT_MAX_* 常量
- _helpers:  _validate_history_time_range / _to_naive_utc / _parse_alertmanager_payload / _persist_alert_log
- __init__:  router + 4 端点 + re-export

patch 路径兼容:
- CompositeNotifier / AlertPayload / OperationLog 在本模块命名空间可见,
  测试 monkeypatch.setattr("app.api.v1.alerts.CompositeNotifier") 生效
  (endpoint 的 __globals__ 即本包命名空间).
- AlertManagerPayload / AlertManagerAlert / _validate_history_time_range 通过
  re-export 保持 ``from app.api.v1.alerts import xxx`` 可用.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

# re-export helpers (back-compat: tests do `from app.api.v1.alerts import _validate_history_time_range`)
from app.api.v1.alerts._helpers import (  # noqa: F401
    _parse_alertmanager_payload,
    _persist_alert_log,
    _to_naive_utc,
    _validate_history_time_range,
)

# re-export schemas (back-compat: tests do `from app.api.v1.alerts import AlertManagerPayload`)
from app.api.v1.alerts._schemas import (  # noqa: F401
    AlertHistoryItem,
    AlertManagerAlert,
    AlertManagerPayload,
    _validate_url_safety,
)
from app.core.database import get_db
from app.core.deps import require_role
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.rate_limit import limiter
from app.core.response import ok
from app.models.admin import OperationLog
from app.models.user import User
from app.monitoring.notifier import (
    AlertPayload,  # noqa: F401  re-export for back-compat
    CompositeNotifier,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])

# P1-SEC-022 修复：查询时间范围限制，防止超大窗口导致 DoS
# (常量定义在 _helpers._HISTORY_MAX_RANGE_DAYS, 此处保留兼容性 re-export 占位)


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
                    )
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
        ),
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
