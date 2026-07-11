"""P1-5 埋点与隐私闭环：最小化事件模型 + 同意/撤回/保留期限/审计.

事件模型遵循"最小化"原则：
- 仅采集事件类型、时间戳和分类元数据（如 assessment_type、risk_level）
- 禁止采集问卷正文、敏感健康原文、用户输入文本
- 所有事件带保留期限（默认 90 天），过期自动清理
- 用户可随时同意/撤回，变更写入 OperationLog 审计日志
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.rate_limit import get_real_client_ip
from app.models.admin import OperationLog
from app.models.user import User, UserProfile
from app.core.response import ok

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analytics", tags=["analytics-events"])

# 事件保留期限（天）
_EVENT_RETENTION_DAYS = 90

# 允许的事件类型白名单
_ALLOWED_EVENT_TYPES = frozenset({
    "assessment_enter",
    "assessment_start",
    "assessment_complete",
    "assessment_abandon",
    "warning_handle",
    "help_use",
    "task_fail",
})

# 允许的元数据键白名单（禁止任意键，防止注入敏感字段）
_ALLOWED_METADATA_KEYS = frozenset({
    "assessment_type",   # structured/text/physiological/fusion
    "risk_level",        # 0-4 数值
    "warning_id",        # 整数 ID
    "help_action",       # faq/contact/feedback/onboarding
    "task_type",         # export/training/report
    "error_code",        # 字符串错误码（非错误消息）
    "page",              # 页面路由路径（不含 query）
})

# 元数据值最大长度（防止超长字符串携带敏感内容）
_MAX_METADATA_VALUE_LEN = 200

# 内存事件存储（生产环境可替换为数据库表）
_event_store: list[dict[str, Any]] = []
_event_store_lock = asyncio.Lock()
_MAX_STORE_SIZE = 20000


class AnalyticsEventPayload(BaseModel):
    """单个分析事件负载."""

    event_type: str = Field(..., description="事件类型（必须在白名单内）")
    timestamp: int = Field(..., description="客户端时间戳（毫秒）", ge=0, le=2_000_000_000_000)
    metadata: dict[str, Any] = Field(default_factory=dict, description="非敏感分类元数据")

    @model_validator(mode="after")
    def validate_event_type(self) -> "AnalyticsEventPayload":
        if self.event_type not in _ALLOWED_EVENT_TYPES:
            raise ValueError(f"event_type '{self.event_type}' 不在允许的白名单内")
        return self

    @model_validator(mode="after")
    def sanitize_metadata(self) -> "AnalyticsEventPayload":
        """过滤元数据：仅保留白名单键，限制值长度，拒绝非标量类型."""
        sanitized: dict[str, Any] = {}
        for key, value in self.metadata.items():
            if key not in _ALLOWED_METADATA_KEYS:
                continue
            # 仅允许标量类型（str/int/float/bool），拒绝 list/dict 防止嵌套敏感内容
            if isinstance(value, (str, int, float, bool)):
                if isinstance(value, str) and len(value) > _MAX_METADATA_VALUE_LEN:
                    value = value[:_MAX_METADATA_VALUE_LEN]
                sanitized[key] = value
            # bool 是 int 子类，上面的分支已处理
        self.metadata = sanitized
        return self


class AnalyticsEventBatch(BaseModel):
    """批量事件上报负载."""

    events: list[AnalyticsEventPayload] = Field(..., min_length=1, max_length=50)


class ConsentUpdateRequest(BaseModel):
    """同意状态更新请求."""

    consent: bool = Field(..., description="是否同意采集分析事件")


def _naive_utc_now() -> datetime:
    """返回 naive UTC datetime（兼容 SQLite）."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _check_consent(db: AsyncSession, user_id: int) -> bool:
    """查询用户分析同意状态."""
    result = await db.execute(
        select(UserProfile.analytics_consent).where(UserProfile.user_id == user_id)
    )
    row = result.first()
    return bool(row[0]) if row else False


@router.post("/events", summary="上报分析事件（需用户同意）")
async def submit_events(
    payload: AnalyticsEventBatch,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """接收并存储分析事件.

    要求:
    - 用户必须已通过 ``analytics_consent`` 明确同意
    - 事件类型和元数据键必须在白名单内
    - 禁止包含问卷正文、敏感健康原文等 PII 数据
    """
    consented = await _check_consent(db, current_user.id)
    if not consented:
        raise HTTPException(status_code=403, detail="用户未同意分析事件采集")

    now = _naive_utc_now()
    retention_expires = now + timedelta(days=_EVENT_RETENTION_DAYS)
    client_ip = get_real_client_ip(request)

    records = []
    for evt in payload.events:
        records.append({
            "user_id": current_user.id,
            "event_type": evt.event_type,
            "timestamp": evt.timestamp,
            "metadata": evt.metadata,
            "client_ip": client_ip,
            "received_at": now.isoformat(),
            "retention_expires_at": retention_expires.isoformat(),
        })

    async with _event_store_lock:
        _event_store.extend(records)
        # 超过上限时淘汰最旧记录
        overflow = len(_event_store) - _MAX_STORE_SIZE
        if overflow > 0:
            del _event_store[:overflow]

    logger.info(
        "Analytics events stored: %d events from user_id=%s",
        len(records),
        current_user.id,
    )
    return ok({"stored": len(records), "retention_days": _EVENT_RETENTION_DAYS})


@router.get("/consent", summary="查询分析事件同意状态")
async def get_consent(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """返回当前用户的分析事件同意状态及保留期限说明."""
    consented = await _check_consent(db, current_user.id)
    return ok({
        "consented": consented,
        "retention_days": _EVENT_RETENTION_DAYS,
        "event_types": sorted(_ALLOWED_EVENT_TYPES),
    })


@router.put("/consent", summary="更新分析事件同意状态（同意/撤回）")
async def update_consent(
    body: ConsentUpdateRequest,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """更新用户同意状态，变更写入 OperationLog 审计日志.

    撤回同意后：
    - 不再接收新的事件
    - 已采集的事件按保留期限到期后清理（不立即删除，保证审计可追溯）
    """
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="用户资料不存在")

    old_consent = bool(profile.analytics_consent)
    if old_consent == body.consent:
        return ok({"consented": body.consent, "changed": False})

    profile.analytics_consent = body.consent

    # 写入审计日志
    action = "analytics.consent.grant" if body.consent else "analytics.consent.withdraw"
    db.add(
        OperationLog(
            operator_id=current_user.id,
            operator_role=current_user.role,
            action_type=action,
            target_type="user",
            target_id=current_user.id,
            detail=json.dumps(
                {"old": old_consent, "new": body.consent},
                ensure_ascii=False,
            ),
            ip_address=get_real_client_ip(request),
        )
    )
    await db.commit()

    logger.info(
        "Analytics consent changed: user_id=%s old=%s new=%s",
        current_user.id,
        old_consent,
        body.consent,
    )
    return ok({"consented": body.consent, "changed": True})


@router.get("/events", summary="查询分析事件（管理员审计）")
async def query_events(
    event_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """查询已存储的分析事件（仅管理员）."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可查询分析事件")

    # 清理过期事件
    now = _naive_utc_now()
    async with _event_store_lock:
        _event_store[:] = [
            e for e in _event_store
            if datetime.fromisoformat(e["retention_expires_at"]) > now
        ]
        records = list(_event_store)

    if event_type:
        records = [r for r in records if r["event_type"] == event_type]

    records = records[-limit:]
    return ok({"events": records, "total": len(_event_store)})
