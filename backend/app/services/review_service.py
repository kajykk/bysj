from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import event_bus
from app.models.admin import OperationLog
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

# M-Svc-8 修复：危机事件处理 action 白名单，防止任意字符串写入 handled_action 字段
_ALLOWED_CRISIS_ACTIONS: frozenset[str] = frozenset(
    {"escalate", "notify_counselor", "emergency_contact", "resolved"}
)

# ISS-072 修复：危机事件状态机
# detected → reviewed → escalated → resolved
# - reviewed → reviewed：允许追加处理动作（如再通知其他咨询师）
# - escalated → reviewed：允许降级回处理态（误升级修正）
# - resolved 为终态，不可再转换
_CRISIS_STATE_TRANSITIONS: dict[str, frozenset[str]] = {
    "detected": frozenset({"reviewed", "escalated", "resolved"}),
    "reviewed": frozenset({"reviewed", "escalated", "resolved"}),
    "escalated": frozenset({"reviewed", "resolved"}),
    "resolved": frozenset(),  # 终态
}


class ReviewService:
    """复核任务服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_review_task(self, data: ReviewTaskCreate) -> ReviewTask:
        """根据预测结果创建复核任务"""
        # H-12 修复：使用 PostgreSQL Advisory Lock 防止并发竞态
        # 对 user_id 加事务级锁，确保同一用户的复核任务创建串行化
        # namespace=1000 表示 review_task 创建锁，避免与其他 advisory lock 冲突
        # SQLite 不支持 advisory lock，开发环境跳过（单线程无并发竞态）
        bind = self.db.bind
        if bind is not None and bind.dialect.name == "postgresql":
            await self.db.execute(
                text("SELECT pg_advisory_xact_lock(1000, :user_id)"),
                {"user_id": data.user_id},
            )

        # 检查是否已存在同一用户的 pending 复核任务
        # 使用 first() 而非 scalar_one_or_none()，避免多条 pending 记录时抛 MultipleResultsFound
        existing = await self.db.execute(
            select(ReviewTask)
            .where(
                ReviewTask.user_id == data.user_id,
                ReviewTask.status == "pending",
            )
            .limit(1)
        )
        existing_task = existing.scalars().first()

        if existing_task:
            # 更新现有任务
            existing_task.risk_level = data.risk_level
            existing_task.risk_score = data.risk_score
            existing_task.review_triggers = json.dumps(data.review_triggers)
            existing_task.crisis_override = data.crisis_override
            existing_task.priority = data.priority.value
            # ISS-041 修复：统一 naive UTC，避免 aware/naive datetime 混用
            existing_task.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
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

        # R-C: 发布 review.submitted 事件到 EventBus, 实时更新 Prometheus 指标.
        # 仅在新建 ReviewTask 成功后发布; 更新已有任务 (existing_task 路径) 不发布.
        # 事件发布非阻塞 (put_nowait), 不影响业务主流程.
        try:
            await event_bus.publish(
                "review.submitted",
                {
                    "review_id": task.id,
                    "user_id": task.user_id,
                    "risk_level": task.risk_level,
                    "risk_score": task.risk_score,
                    "priority": task.priority,
                    "crisis_override": bool(task.crisis_override),
                    # ISS-041 修复：统一 naive UTC
                    "created_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                },
            )
        except Exception:
            # EventBus 发布失败不应影响业务主流程
            logger.warning("Failed to publish review.submitted event", exc_info=True)

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
        # ISS-061 修复：使用 with_for_update() 行级锁，防止并发分配同一复核任务
        result = await self.db.execute(
            select(ReviewTask).where(ReviewTask.id == review_id).with_for_update()
        )
        task = result.scalar_one_or_none()
        if not task:
            raise ValueError(f"Review task {review_id} not found")

        if task.status != "pending":
            raise ValueError(f"Cannot assign review with status {task.status}")

        task.assigned_to = counselor_id
        task.status = "in_review"
        # ISS-041 修复：统一 naive UTC
        task.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
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
        if (
            not is_admin
            and task.assigned_to is not None
            and task.assigned_to != counselor_id
        ):
            raise ValueError("无权处理此复核任务：任务已分配给其他咨询师")

        task.resolved_by = counselor_id
        task.resolution_note = resolution_note
        task.status = "resolved"
        # ISS-041 修复：统一 naive UTC
        task.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)
        task.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
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
        if (
            not is_admin
            and task.assigned_to is not None
            and task.assigned_to != counselor_id
        ):
            raise ValueError("无权升级此复核任务：任务已分配给其他咨询师")

        # M-Svc-6 修复：escalate 不应复用 resolved_by/resolved_at 字段（语义不一致：
        # 升级并非解决）。ReviewTask 模型无 escalated_by 字段，改为在 OperationLog.detail
        # 中记录升级操作者，保留审计链清晰。
        previous_status = task.status
        task.resolution_note = reason
        task.status = "escalated"
        # ISS-041 修复：统一 naive UTC
        task.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        # 记录升级审计日志，detail 中明确 escalate_by（避免与 resolved_by 混淆）
        self.db.add(
            OperationLog(
                operator_id=counselor_id,
                operator_role="admin" if is_admin else "counselor",
                action_type="review.escalated",
                target_type="review_task",
                target_id=review_id,
                detail=json.dumps(
                    {
                        "escalated_by": counselor_id,
                        "reason": reason,
                        "previous_status": previous_status,
                    },
                    ensure_ascii=False,
                ),
            )
        )
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def get_review_stats(self, days: int = 30) -> ReviewStats:
        """获取复核统计"""
        # 总数
        total_result = await self.db.execute(
            select(func.count()).select_from(ReviewTask)
        )
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
        # M-Svc-7 修复：验证 crisis_keywords 长度，避免过大 payload 导致
        # JSON 字段溢出或序列化性能问题（每个 keyword ≤100 字符，总数 ≤50）
        keywords = list(data.crisis_keywords or [])
        if len(keywords) > 50:
            raise ValueError("crisis_keywords 数量不能超过 50 个")
        for kw in keywords:
            if len(str(kw)) > 100:
                raise ValueError(
                    f"单个 crisis_keyword 长度不能超过 100 字符: {str(kw)[:20]}..."
                )

        event = CrisisEvent(
            user_id=data.user_id,
            report_id=data.report_id,
            trigger_source=data.trigger_source,
            crisis_keywords=json.dumps(keywords),
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
        note: str | None = None,
    ) -> CrisisEvent:
        """处理危机事件 (status: detected/reviewed/escalated → reviewed)

        ISS-072 修复：
        - 状态从 "handled" 改为 "reviewed"（与前端筛选器一致）
        - 新增状态机校验（detected|reviewed|escalated → reviewed）
        - 新增审计日志写入 OperationLog
        """
        # M-Svc-8 修复：白名单校验 action，防止任意字符串写入 handled_action 字段
        if action not in _ALLOWED_CRISIS_ACTIONS:
            raise ValueError(
                f"无效的 action: {action}，允许值: {', '.join(sorted(_ALLOWED_CRISIS_ACTIONS))}"
            )

        result = await self.db.execute(
            select(CrisisEvent).where(CrisisEvent.id == event_id)
        )
        event = result.scalar_one_or_none()
        if not event:
            raise ValueError(f"Crisis event {event_id} not found")

        # ISS-072 状态机校验
        self._validate_crisis_transition(event.status, "reviewed")

        # ISS-005 修复: 状态变更与审计日志写入同一 savepoint, 统一 commit
        event.handled_by = handled_by
        event.handled_action = action
        event.status = "reviewed"
        # ISS-041 修复：统一 naive UTC
        event.handled_at = datetime.now(timezone.utc).replace(tzinfo=None)
        async with self.db.begin_nested():
            await self.db.flush()
            await self._write_crisis_audit_log(
                operator_id=handled_by,
                action_type="crisis_event_handle",
                event_id=event_id,
                detail={"action": action, "note": note, "new_status": "reviewed"},
            )
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def escalate_crisis_event(
        self,
        event_id: int,
        handled_by: int,
        reason: str,
    ) -> CrisisEvent:
        """升级危机事件 (status: detected|reviewed → escalated)

        ISS-072 修复：新增端点，将事件升级到 escalated 状态（通知更高层级介入）。
        """
        result = await self.db.execute(
            select(CrisisEvent).where(CrisisEvent.id == event_id)
        )
        event = result.scalar_one_or_none()
        if not event:
            raise ValueError(f"Crisis event {event_id} not found")

        self._validate_crisis_transition(event.status, "escalated")

        # ISS-005 修复: 状态变更与审计日志写入同一 savepoint, 统一 commit
        event.handled_by = handled_by
        event.handled_action = "escalate"
        event.status = "escalated"
        # ISS-041 修复：统一 naive UTC
        event.handled_at = datetime.now(timezone.utc).replace(tzinfo=None)
        async with self.db.begin_nested():
            await self.db.flush()
            await self._write_crisis_audit_log(
                operator_id=handled_by,
                action_type="crisis_event_escalate",
                event_id=event_id,
                detail={"reason": reason, "new_status": "escalated"},
            )
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def close_crisis_event(
        self,
        event_id: int,
        handled_by: int,
        note: str | None = None,
    ) -> CrisisEvent:
        """关闭危机事件 (status: detected|reviewed|escalated → resolved)

        ISS-072 修复：新增端点，将事件关闭到 resolved 终态。
        """
        result = await self.db.execute(
            select(CrisisEvent).where(CrisisEvent.id == event_id)
        )
        event = result.scalar_one_or_none()
        if not event:
            raise ValueError(f"Crisis event {event_id} not found")

        self._validate_crisis_transition(event.status, "resolved")

        # ISS-005 修复: 状态变更与审计日志写入同一 savepoint, 统一 commit
        event.handled_by = handled_by
        event.handled_action = "resolved"
        event.status = "resolved"
        # ISS-041 修复：统一 naive UTC
        event.handled_at = datetime.now(timezone.utc).replace(tzinfo=None)
        async with self.db.begin_nested():
            await self.db.flush()
            await self._write_crisis_audit_log(
                operator_id=handled_by,
                action_type="crisis_event_close",
                event_id=event_id,
                detail={"note": note, "new_status": "resolved"},
            )
        await self.db.commit()
        await self.db.refresh(event)
        return event

    def _validate_crisis_transition(self, current: str, target: str) -> None:
        """ISS-072 修复：危机事件状态机校验，禁止非法状态跳变."""
        allowed = _CRISIS_STATE_TRANSITIONS.get(current, frozenset())
        if target not in allowed:
            raise ValueError(
                f"非法状态转换: {current} → {target}，当前状态 {current} 仅允许转换到 "
                f"{sorted(allowed) or '（终态，不可转换）'}"
            )

    async def _write_crisis_audit_log(
        self,
        operator_id: int,
        action_type: str,
        event_id: int,
        detail: dict,
    ) -> None:
        """ISS-072 修复：危机事件状态流转审计日志.

        权限/安全/数据一致性场景，写入 OperationLog 供第二人复核。
        ISS-005 修复：仅 flush 不 commit, 由调用方在 savepoint 内统一 commit.
        """
        op_log = OperationLog(
            operator_id=operator_id,
            operator_role="admin",
            action_type=action_type,
            target_type="crisis_event",
            target_id=event_id,
            # L-API-3 修复：截断 detail 至 5000 字符，避免超 DB 字段限制
            detail=json.dumps(detail, ensure_ascii=False),
        )
        self.db.add(op_log)
        await self.db.flush()

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
