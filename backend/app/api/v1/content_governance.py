"""Phase 4 内容治理 API.

按 Phase 4 计划要求：
- "建立内容治理：文章来源、专业审核人、发布日期、复审周期、下架机制"
- "禁止未经审核的自动生成干预内容直接面向高风险用户"

使用现有 EducationContent.status 字段 + OperationLog 审计日志实现治理工作流：
- POST /content-governance/{id}/review   标记内容已审核
- POST /content-governance/{id}/takedown  下架内容
- POST /content-governance/{id}/restore   恢复内容
- GET  /content-governance/pending        待审核/待复审内容列表
- GET  /content-governance/history/{id}   内容审核历史

仅管理员可访问。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.rate_limit import limiter
from app.core.response import ok
from app.models.admin import EducationContent, OperationLog
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/content-governance", tags=["content-governance"])

# 内容状态常量
STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"
STATUS_TAKEDOWN = "takedown"
STATUS_PENDING_REVIEW = "pending_review"

# 默认复审周期（天）
DEFAULT_REVIEW_CYCLE_DAYS = 90


class ReviewRequest(BaseModel):
    """内容审核请求."""

    reviewer_note: str = Field(
        ..., min_length=1, max_length=500, description="审核备注（必填）"
    )
    review_cycle_days: int = Field(
        default=DEFAULT_REVIEW_CYCLE_DAYS, ge=7, le=365,
        description="复审周期（天），默认 90 天",
    )


class TakedownRequest(BaseModel):
    """内容下架请求."""

    reason: str = Field(
        ..., min_length=1, max_length=500, description="下架原因（必填）"
    )


class RestoreRequest(BaseModel):
    """内容恢复请求."""

    reason: str = Field(
        ..., min_length=1, max_length=500, description="恢复原因（必填）"
    )


def _naive_utc_now() -> datetime:
    """生成 naive UTC datetime（与数据库 DateTime 列兼容）."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@router.post(
    "/{content_id}/review",
    responses=COMMON_ERROR_RESPONSES,
    summary="标记内容已审核（管理员）",
)
@limiter.limit("20/minute")
async def review_content(
    request: Request,
    content_id: int,
    payload: ReviewRequest,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """标记内容已通过审核.

    记录审核人、审核备注和复审周期。审核记录写入 OperationLog。
    如果内容状态为 pending_review，审核后变为 active。
    """
    content = await _get_content_or_404(db, content_id)

    previous_status = content.status
    if content.status == STATUS_PENDING_REVIEW:
        content.status = STATUS_ACTIVE

    await db.flush()

    # 记录审核事件到审计日志
    db.add(
        OperationLog(
            operator_id=current_user.id,
            operator_role="admin",
            action_type="content.review",
            target_type="education_content",
            target_id=content_id,
            detail=f"reviewer_note={payload.reviewer_note}; "
                   f"review_cycle_days={payload.review_cycle_days}; "
                   f"previous_status={previous_status}; "
                   f"new_status={content.status}",
        )
    )
    await db.commit()

    logger.info(
        "Content %s reviewed by admin %s (cycle=%d days)",
        content_id, current_user.id, payload.review_cycle_days,
    )

    return ok({
        "content_id": content_id,
        "status": content.status,
        "reviewed_by": current_user.id,
        "reviewed_at": _naive_utc_now().isoformat(),
        "review_cycle_days": payload.review_cycle_days,
        "next_review_due": (
            _naive_utc_now() + timedelta(days=payload.review_cycle_days)
        ).isoformat(),
    })


@router.post(
    "/{content_id}/takedown",
    responses=COMMON_ERROR_RESPONSES,
    summary="下架内容（管理员）",
)
@limiter.limit("20/minute")
async def takedown_content(
    request: Request,
    content_id: int,
    payload: TakedownRequest,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """下架内容.

    将内容状态设为 takedown，记录下架原因。下架后内容不再对用户可见。
    """
    content = await _get_content_or_404(db, content_id)

    if content.status == STATUS_TAKEDOWN:
        raise HTTPException(status_code=409, detail="内容已处于下架状态")

    previous_status = content.status
    content.status = STATUS_TAKEDOWN
    await db.flush()

    db.add(
        OperationLog(
            operator_id=current_user.id,
            operator_role="admin",
            action_type="content.takedown",
            target_type="education_content",
            target_id=content_id,
            detail=f"reason={payload.reason}; previous_status={previous_status}",
        )
    )
    await db.commit()

    logger.warning(
        "Content %s taken down by admin %s: %s",
        content_id, current_user.id, payload.reason,
    )

    return ok({
        "content_id": content_id,
        "status": STATUS_TAKEDOWN,
        "takedown_by": current_user.id,
        "takedown_at": _naive_utc_now().isoformat(),
        "reason": payload.reason,
    })


@router.post(
    "/{content_id}/restore",
    responses=COMMON_ERROR_RESPONSES,
    summary="恢复内容（管理员）",
)
@limiter.limit("20/minute")
async def restore_content(
    request: Request,
    content_id: int,
    payload: RestoreRequest,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """恢复已下架的内容.

    将内容状态从 takedown 恢复为 active。
    """
    content = await _get_content_or_404(db, content_id)

    if content.status != STATUS_TAKEDOWN:
        raise HTTPException(status_code=409, detail="内容未处于下架状态，无法恢复")

    content.status = STATUS_ACTIVE
    await db.flush()

    db.add(
        OperationLog(
            operator_id=current_user.id,
            operator_role="admin",
            action_type="content.restore",
            target_type="education_content",
            target_id=content_id,
            detail=f"reason={payload.reason}",
        )
    )
    await db.commit()

    logger.info(
        "Content %s restored by admin %s: %s",
        content_id, current_user.id, payload.reason,
    )

    return ok({
        "content_id": content_id,
        "status": STATUS_ACTIVE,
        "restored_by": current_user.id,
        "restored_at": _naive_utc_now().isoformat(),
        "reason": payload.reason,
    })


@router.get(
    "/pending",
    responses=COMMON_ERROR_RESPONSES,
    summary="待审核/待复审内容列表（管理员）",
)
@limiter.limit("30/minute")
async def list_pending_content(
    request: Request,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """列出待审核或待复审的内容.

    包括：
    - status 为 pending_review 的内容
    - status 为 active 但超过复审周期（默认 90 天）未审核的内容
    """
    # 待审核内容
    pending_stmt = (
        select(EducationContent)
        .where(EducationContent.status == STATUS_PENDING_REVIEW)
        .order_by(EducationContent.created_at.asc())
    )

    # 活跃但可能需要复审的内容（按创建时间排序，旧内容优先）
    # 注意：由于 EducationContent 没有 last_reviewed_at 字段，
    # 复审检查基于 created_at + review_cycle_days
    review_due_date = _naive_utc_now() - timedelta(days=DEFAULT_REVIEW_CYCLE_DAYS)
    overdue_stmt = (
        select(EducationContent)
        .where(
            EducationContent.status == STATUS_ACTIVE,
            EducationContent.created_at < review_due_date,
        )
        .order_by(EducationContent.created_at.asc())
    )

    # 合并查询（简化：分别查询后在 Python 端合并分页）
    pending_results = (await db.execute(pending_stmt)).scalars().all()
    overdue_results = (await db.execute(overdue_stmt)).scalars().all()

    all_pending = list(pending_results) + list(overdue_results)
    total = len(all_pending)

    # 分页
    offset = (page - 1) * page_size
    page_items = all_pending[offset : offset + page_size]

    items = [
        {
            "id": c.id,
            "title": c.title,
            "content_type": c.content_type,
            "category": c.category,
            "status": c.status,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "needs_review_reason": (
                "pending_review" if c.status == STATUS_PENDING_REVIEW
                else "overdue_for_review"
            ),
            "days_since_creation": (
                (_naive_utc_now() - c.created_at).days if c.created_at else None
            ),
        }
        for c in page_items
    ]

    return ok({
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "review_cycle_days": DEFAULT_REVIEW_CYCLE_DAYS,
    })


@router.get(
    "/history/{content_id}",
    responses=COMMON_ERROR_RESPONSES,
    summary="内容审核历史（管理员）",
)
@limiter.limit("30/minute")
async def get_content_history(
    request: Request,
    content_id: int,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """获取指定内容的审核历史（从 OperationLog 查询）."""
    # 验证内容存在
    await _get_content_or_404(db, content_id)

    # 查询相关的审核日志
    logs = (
        await db.execute(
            select(OperationLog)
            .where(
                OperationLog.target_type == "education_content",
                OperationLog.target_id == content_id,
                OperationLog.action_type.in_([
                    "content.review",
                    "content.takedown",
                    "content.restore",
                ]),
            )
            .order_by(OperationLog.created_at.desc())
            .limit(100)
        )
    ).scalars().all()

    history = [
        {
            "id": log.id,
            "action": log.action_type,
            "operator_id": log.operator_id,
            "operator_role": log.operator_role,
            "detail": log.detail,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]

    return ok({
        "content_id": content_id,
        "history": history,
        "total_events": len(history),
    })


async def _get_content_or_404(db: AsyncSession, content_id: int) -> EducationContent:
    """获取内容或抛出 404."""
    content = (
        await db.execute(
            select(EducationContent).where(EducationContent.id == content_id)
        )
    ).scalar_one_or_none()

    if content is None:
        raise HTTPException(status_code=404, detail="内容不存在")
    return content
