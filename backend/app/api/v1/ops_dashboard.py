"""Phase 4 运营看板 API.

提供运营和服务指标聚合端点：
- 预警响应时长（复核任务 created_at → resolved_at）
- 复核任务状态分布
- 危机事件统计
- 用户反馈统计
- 模型暂停开关状态
- 近期审计事件
- 系统健康指标

仅管理员可访问。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.kill_switch import get_kill_switch_status
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.rate_limit import limiter
from app.core.response import ok
from app.models.admin import EducationContent, OperationLog
from app.models.review import CrisisEvent, ReviewTask
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ops-dashboard", tags=["ops-dashboard"])


def _naive_utc_now() -> datetime:
    """生成 naive UTC datetime（与数据库 DateTime 列兼容）."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@router.get(
    "/overview",
    responses=COMMON_ERROR_RESPONSES,
    summary="运营看板总览（管理员）",
)
@limiter.limit("30/minute")
async def ops_dashboard_overview(
    request: Request,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """运营看板总览.

    聚合以下指标：
    - review: 复核任务状态分布 + 平均响应时长
    - crisis: 危机事件统计
    - feedback: 用户反馈统计
    - kill_switch: 模型暂停开关状态
    - audit: 近期审计事件
    - content: 内容治理统计
    """
    now = _naive_utc_now()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    # 1. 复核任务统计
    review_stats = await _get_review_stats(db, last_24h, last_7d, now)

    # 2. 危机事件统计
    crisis_stats = await _get_crisis_stats(db, last_24h, last_7d)

    # 3. 用户反馈统计
    feedback_stats = await _get_feedback_stats(db, last_7d)

    # 4. 模型暂停开关状态
    kill_switch_status = await get_kill_switch_status()

    # 5. 近期审计事件
    audit_events = await _get_recent_audit_events(db, limit=10)

    # 6. 内容治理统计
    content_stats = await _get_content_stats(db)

    return ok({
        "generated_at": now.isoformat(),
        "review": review_stats,
        "crisis": crisis_stats,
        "feedback": feedback_stats,
        "kill_switch": kill_switch_status,
        "audit_events": audit_events,
        "content": content_stats,
    })


@router.get(
    "/review-metrics",
    responses=COMMON_ERROR_RESPONSES,
    summary="复核任务详细指标（管理员）",
)
@limiter.limit("30/minute")
async def ops_review_metrics(
    request: Request,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = 7,
) -> dict[str, Any]:
    """复核任务详细指标.

    Args:
        days: 统计天数（默认 7 天）
    """
    now = _naive_utc_now()
    since = now - timedelta(days=min(max(days, 1), 90))

    stats = await _get_review_stats(db, since, since, now)
    return ok({
        "period_days": min(max(days, 1), 90),
        "since": since.isoformat(),
        **stats,
    })


async def _get_review_stats(
    db: AsyncSession, last_24h: datetime, last_7d: datetime, now: datetime
) -> dict[str, Any]:
    """复核任务统计."""
    # 状态分布
    status_counts_raw = (
        await db.execute(
            select(ReviewTask.status, func.count())
            .group_by(ReviewTask.status)
        )
    ).all()
    status_counts = {row[0]: row[1] for row in status_counts_raw}

    # 最近 7 天复核任务数
    recent_count = (
        await db.execute(
            select(func.count())
            .select_from(ReviewTask)
            .where(ReviewTask.created_at >= last_7d)
        )
    ).scalar_one()

    # 已解决任务的平均响应时长（小时）- 在 Python 端计算，兼容 SQLite/PostgreSQL
    resolved_rows = (
        await db.execute(
            select(ReviewTask.created_at, ReviewTask.resolved_at)
            .where(
                ReviewTask.status == "resolved",
                ReviewTask.resolved_at.is_not(None),
                ReviewTask.created_at >= last_7d,
            )
        )
    ).all()

    avg_response_hours = None
    if resolved_rows:
        total_seconds = 0.0
        for created, resolved in resolved_rows:
            if created and resolved:
                delta = resolved - created
                total_seconds += delta.total_seconds()
        avg_response_hours = round(total_seconds / len(resolved_rows) / 3600, 2)

    # 待处理任务数（pending + in_review）
    pending_count = status_counts.get("pending", 0) + status_counts.get("in_review", 0)

    # 危机优先级任务数
    crisis_pending = (
        await db.execute(
            select(func.count())
            .select_from(ReviewTask)
            .where(
                ReviewTask.priority == "crisis_review",
                ReviewTask.status.in_(["pending", "in_review"]),
            )
        )
    ).scalar_one()

    return {
        "status_distribution": status_counts,
        "total_pending": pending_count,
        "crisis_pending": crisis_pending,
        "recent_7d_count": recent_count,
        "avg_response_hours_7d": avg_response_hours,
        "sla_target_hours": 4,
        "sla_met": avg_response_hours is not None and avg_response_hours <= 4,
    }


async def _get_crisis_stats(
    db: AsyncSession, last_24h: datetime, last_7d: datetime
) -> dict[str, Any]:
    """危机事件统计."""
    # 最近 24 小时危机事件
    count_24h = (
        await db.execute(
            select(func.count())
            .select_from(CrisisEvent)
            .where(CrisisEvent.created_at >= last_24h)
        )
    ).scalar_one()

    # 最近 7 天危机事件
    count_7d = (
        await db.execute(
            select(func.count())
            .select_from(CrisisEvent)
            .where(CrisisEvent.created_at >= last_7d)
        )
    ).scalar_one()

    # 按状态分布
    status_raw = (
        await db.execute(
            select(CrisisEvent.status, func.count())
            .where(CrisisEvent.created_at >= last_7d)
            .group_by(CrisisEvent.status)
        )
    ).all()
    status_distribution = {row[0]: row[1] for row in status_raw}

    return {
        "count_24h": count_24h,
        "count_7d": count_7d,
        "status_distribution_7d": status_distribution,
    }


async def _get_feedback_stats(
    db: AsyncSession, last_7d: datetime
) -> dict[str, Any]:
    """用户反馈统计."""
    from app.models.admin import ModelFeedback

    # 最近 7 天反馈数
    total = (
        await db.execute(
            select(func.count())
            .select_from(ModelFeedback)
            .where(ModelFeedback.created_at >= last_7d)
        )
    ).scalar_one()

    # 同意率（咨询师是否同意模型评估结果）
    agreed_count = (
        await db.execute(
            select(func.count())
            .select_from(ModelFeedback)
            .where(
                ModelFeedback.created_at >= last_7d,
                ModelFeedback.agreed.is_(True),
            )
        )
    ).scalar_one()

    agreement_rate = round(agreed_count / total, 4) if total > 0 else None

    return {
        "count_7d": total,
        "agreement_rate_7d": agreement_rate,
    }


async def _get_recent_audit_events(
    db: AsyncSession, limit: int = 10
) -> list[dict[str, Any]]:
    """获取近期审计事件."""
    rows = (
        await db.execute(
            select(OperationLog)
            .order_by(OperationLog.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    return [
        {
            "id": r.id,
            "operator_id": r.operator_id,
            "operator_role": r.operator_role,
            "action_type": r.action_type,
            "target_type": r.target_type,
            "detail": r.detail[:200] if r.detail else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


async def _get_content_stats(db: AsyncSession) -> dict[str, Any]:
    """内容治理统计."""
    # 按状态分布
    status_raw = (
        await db.execute(
            select(EducationContent.status, func.count())
            .group_by(EducationContent.status)
        )
    ).all()
    status_distribution = {row[0]: row[1] for row in status_raw}

    total = sum(status_distribution.values())

    # 按类型分布
    type_raw = (
        await db.execute(
            select(EducationContent.content_type, func.count())
            .group_by(EducationContent.content_type)
        )
    ).all()
    type_distribution = {row[0]: row[1] for row in type_raw}

    return {
        "total": total,
        "status_distribution": status_distribution,
        "type_distribution": type_distribution,
    }
