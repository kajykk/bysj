from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review import CrisisEvent, ReviewTask
from app.schemas.review import (
    CrisisEventCreate,
    CrisisEventFilter,
    ReviewStats,
    ReviewTaskCreate,
    ReviewTaskFilter,
    ReviewTaskListResponse,
    ReviewTaskResponse,
)

logger = logging.getLogger(__name__)


class ReviewService:
    """复核任务服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_review_task(self, data: ReviewTaskCreate) -> ReviewTask:
        """根据预测结果创建复核任务"""
        # 检查是否已存在同一用户的 pending 复核任务
        existing = await self.db.execute(
            select(ReviewTask).where(
                ReviewTask.user_id == data.user_id,
                ReviewTask.status == "pending",
            )
        )
        existing_task = existing.scalar_one_or_none()

        if existing_task:
            # 更新现有任务
            existing_task.risk_level = data.risk_level
            existing_task.risk_score = data.risk_score
            existing_task.review_triggers = json.dumps(data.review_triggers)
            existing_task.crisis_override = data.crisis_override
            existing_task.priority = data.priority.value
            existing_task.updated_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(existing_task)
            return existing_task

        # 创建新任务
        task = ReviewTask(
            user_id=data.user_id,
            risk_report_id=data.risk_report_id,
            risk_level=data.risk_level,
            risk_score=data.risk_score,
            review_triggers=json.dumps(data.review_triggers),
            crisis_override=data.crisis_override,
            status="pending",
            priority=data.priority.value,
        )
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def get_reviews(
        self,
        filter_data: ReviewTaskFilter,
    ) -> ReviewTaskListResponse:
        """查询复核任务列表"""
        query = select(ReviewTask)

        if filter_data.status:
            query = query.where(ReviewTask.status == filter_data.status.value)
        if filter_data.priority:
            query = query.where(ReviewTask.priority == filter_data.priority.value)
        if filter_data.assigned_to:
            query = query.where(ReviewTask.assigned_to == filter_data.assigned_to)
        if filter_data.user_id:
            query = query.where(ReviewTask.user_id == filter_data.user_id)

        # 获取总数
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # 分页
        query = query.order_by(desc(ReviewTask.created_at))
        query = query.offset((filter_data.page - 1) * filter_data.page_size)
        query = query.limit(filter_data.page_size)

        result = await self.db.execute(query)
        tasks = result.scalars().all()

        return ReviewTaskListResponse(
            items=[self.to_response(t) for t in tasks],
            total=total,
            page=filter_data.page,
            page_size=filter_data.page_size,
        )

    async def get_review_by_id(self, review_id: int) -> ReviewTask | None:
        """根据 ID 获取复核任务"""
        result = await self.db.execute(
            select(ReviewTask).where(ReviewTask.id == review_id)
        )
        return result.scalar_one_or_none()

    async def assign_review(self, review_id: int, counselor_id: int) -> ReviewTask:
        """分配复核任务给咨询师"""
        task = await self.get_review_by_id(review_id)
        if not task:
            raise ValueError(f"Review task {review_id} not found")

        if task.status != "pending":
            raise ValueError(f"Cannot assign review with status {task.status}")

        task.assigned_to = counselor_id
        task.status = "in_review"
        task.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def resolve_review(
        self,
        review_id: int,
        counselor_id: int,
        resolution_note: str,
        *,
        is_admin: bool = False,
    ) -> ReviewTask:
        """处理复核任务"""
        task = await self.get_review_by_id(review_id)
        if not task:
            raise ValueError(f"Review task {review_id} not found")

        if task.status not in ["pending", "in_review"]:
            raise ValueError(f"Cannot resolve review with status {task.status}")

        # P1-SEC-007 修复：越权检查 - 仅分配的咨询师或管理员可处理
        if not is_admin and task.assigned_to is not None and task.assigned_to != counselor_id:
            raise ValueError("无权处理此复核任务：任务已分配给其他咨询师")

        task.resolved_by = counselor_id
        task.resolution_note = resolution_note
        task.status = "resolved"
        task.resolved_at = datetime.now(timezone.utc)
        task.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def escalate_review(
        self,
        review_id: int,
        counselor_id: int,
        reason: str,
        *,
        is_admin: bool = False,
    ) -> ReviewTask:
        """升级复核任务"""
        task = await self.get_review_by_id(review_id)
        if not task:
            raise ValueError(f"Review task {review_id} not found")

        if task.status not in ["pending", "in_review"]:
            raise ValueError(f"Cannot escalate review with status {task.status}")

        # P1-SEC-007 修复：越权检查 - 仅分配的咨询师或管理员可升级
        if not is_admin and task.assigned_to is not None and task.assigned_to != counselor_id:
            raise ValueError("无权升级此复核任务：任务已分配给其他咨询师")

        task.resolved_by = counselor_id
        task.resolution_note = reason
        task.status = "escalated"
        task.resolved_at = datetime.now(timezone.utc)
        task.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def get_review_stats(self, days: int = 30) -> ReviewStats:
        """获取复核统计"""
        # 总数
        total_result = await self.db.execute(select(func.count()).select_from(ReviewTask))
        total = total_result.scalar() or 0

        # 各状态数量 - M14 修复：使用一次 GROUP BY 聚合替代循环查询
        status_result = await self.db.execute(
            select(ReviewTask.status, func.count()).group_by(ReviewTask.status)
        )
        status_counts = {status: count for status, count in status_result.all()}

        # 危机数量
        crisis_result = await self.db.execute(
            select(func.count()).where(ReviewTask.crisis_override.is_(True))
        )
        crisis_count = crisis_result.scalar() or 0

        # 高风险数量
        high_risk_result = await self.db.execute(
            select(func.count()).where(ReviewTask.priority == "high_risk_review")
        )
        high_risk_count = high_risk_result.scalar() or 0

        return ReviewStats(
            total=total,
            pending=status_counts.get("pending", 0),
            in_review=status_counts.get("in_review", 0),
            resolved=status_counts.get("resolved", 0),
            escalated=status_counts.get("escalated", 0),
            crisis_count=crisis_count,
            high_risk_count=high_risk_count,
        )

    def to_response(self, task: ReviewTask) -> ReviewTaskResponse:
        """转换为响应模型"""
        return ReviewTaskResponse(
            id=task.id,
            user_id=task.user_id,
            risk_report_id=task.risk_report_id,
            risk_level=task.risk_level,
            risk_score=task.risk_score,
            review_triggers=json.loads(task.review_triggers or "[]"),
            crisis_override=bool(task.crisis_override),
            status=task.status,
            priority=task.priority,
            assigned_to=task.assigned_to,
            resolved_by=task.resolved_by,
            resolution_note=task.resolution_note,
            created_at=task.created_at,
            updated_at=task.updated_at,
            resolved_at=task.resolved_at,
        )


class CrisisEventService:
    """危机事件审计服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_crisis_event(self, data: CrisisEventCreate) -> CrisisEvent:
        """记录危机事件"""
        event = CrisisEvent(
            user_id=data.user_id,
            report_id=data.report_id,
            trigger_source=data.trigger_source,
            crisis_keywords=json.dumps(data.crisis_keywords),
            crisis_score=data.crisis_score,
            input_summary=data.input_summary,
            review_task_id=data.review_task_id,
            status="detected",
        )
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def get_crisis_events(
        self,
        filter_data: CrisisEventFilter,
    ) -> dict:
        """查询危机事件"""
        query = select(CrisisEvent)

        if filter_data.status:
            query = query.where(CrisisEvent.status == filter_data.status)
        if filter_data.start_date:
            query = query.where(CrisisEvent.created_at >= filter_data.start_date)
        if filter_data.end_date:
            query = query.where(CrisisEvent.created_at <= filter_data.end_date)

        # 获取总数
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # 分页
        query = query.order_by(desc(CrisisEvent.created_at))
        query = query.offset((filter_data.page - 1) * filter_data.page_size)
        query = query.limit(filter_data.page_size)

        result = await self.db.execute(query)
        events = result.scalars().all()

        return {
            "items": [self._to_response(e) for e in events],
            "total": total,
            "page": filter_data.page,
            "page_size": filter_data.page_size,
        }

    async def handle_crisis_event(
        self,
        event_id: int,
        handled_by: int,
        action: str,
    ) -> CrisisEvent:
        """处理危机事件"""
        result = await self.db.execute(
            select(CrisisEvent).where(CrisisEvent.id == event_id)
        )
        event = result.scalar_one_or_none()
        if not event:
            raise ValueError(f"Crisis event {event_id} not found")

        event.handled_by = handled_by
        event.handled_action = action
        event.status = "handled"
        event.handled_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    def _to_response(self, event: CrisisEvent) -> dict:
        """转换为响应"""
        return {
            "id": event.id,
            "user_id": event.user_id,
            "report_id": event.report_id,
            "trigger_source": event.trigger_source,
            "crisis_keywords": json.loads(event.crisis_keywords or "[]"),
            "crisis_score": event.crisis_score,
            "input_summary": event.input_summary,
            "review_task_id": event.review_task_id,
            "status": event.status,
            "handled_by": event.handled_by,
            "handled_action": event.handled_action,
            "created_at": event.created_at.isoformat() if event.created_at else None,
            "handled_at": event.handled_at.isoformat() if event.handled_at else None,
        }
