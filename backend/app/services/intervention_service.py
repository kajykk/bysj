from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import OperationLog
from app.models.intervention import InterventionPlan, InterventionTask, TaskExecution


class InterventionRecommendation:
    @staticmethod
    def build_from_risk_level(
        risk_level: int, dominant_modality: str | None = None
    ) -> tuple[str, list[str]]:
        if risk_level <= 0:
            return "none", ["保持日常心理健康维护", "推荐心理健康教育内容"]
        if risk_level == 1:
            return "low", [
                "推送轻度风险提醒",
                "推荐放松训练与睡眠管理",
                "建议 7 日内复测",
            ]
        if risk_level == 2:
            actions = ["触发咨询师关注", "推荐在线心理测评", "建议尽快预约辅导"]
            if dominant_modality == "physiological":
                actions.append("建议关注生理指标变化并规律作息")
            return "medium", actions
        if risk_level == 3:
            actions = ["发送高风险预警", "优先转介人工干预", "同步展示风险因素解释"]
            if dominant_modality == "physiological":
                actions.insert(1, "建议进行生理指标专项复查")
            elif dominant_modality == "text":
                actions.insert(1, "建议关注情绪表达并提供心理支持资源")
            return "high", actions
        actions = ["立即触发紧急预警", "建议人工重点随访", "必要时启动危机干预流程"]
        if dominant_modality == "physiological":
            actions.insert(1, "紧急排查生理异常并建议就医检查")
        return "critical", actions


class InterventionService:
    TERMINAL_STATUSES = {"completed", "missed", "skipped"}
    MUTABLE_STATUSES = {"pending", "postponed"}

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_active(self, user_id: int, *, create_missing: bool = True) -> dict:
        stmt = (
            select(InterventionPlan)
            .where(
                InterventionPlan.user_id == user_id, InterventionPlan.status == "active"
            )
            .order_by(InterventionPlan.created_at.desc())
            .limit(1)
        )
        plan = (await self.db.execute(stmt)).scalar_one_or_none()

        if not plan:
            return {
                "plan": {
                    "id": None,
                    "plan_name": "暂无活跃方案",
                    "risk_level": 0,
                    "start_date": None,
                    "progress": 0,
                },
                "tasks": [],
            }

        task_stmt = (
            select(InterventionTask)
            .where(InterventionTask.plan_id == plan.id)
            .order_by(InterventionTask.sort_order)
        )
        tasks = (await self.db.execute(task_stmt)).scalars().all()

        today = date.today()
        total_tasks = 0
        completed_tasks = 0
        task_items: list[dict] = []

        for task in tasks:
            should_execute = self._should_execute_today(
                task.schedule or "daily", plan.start_date
            )
            if not should_execute:
                continue

            total_tasks += 1
            if create_missing:
                execution = await self._get_or_create_execution(task.id, user_id, today)
            else:
                # 只读模式：仅查询已有执行记录，不创建新记录（用于 GET 端点，保证幂等性）
                execution = await self._get_execution(task.id, user_id, today)
                if execution is None:
                    task_items.append(
                        {
                            "id": task.id,
                            "task_name": task.task_name,
                            "task_type": task.task_type,
                            "description": task.description,
                            "schedule": task.schedule,
                            "duration_minutes": task.duration_minutes,
                            "today_status": "pending",
                            "feedback_score": None,
                            "feedback_note": None,
                            "modality_based_actions": [],
                        }
                    )
                    continue

            status = execution.status
            if status == "completed":
                completed_tasks += 1

            task_items.append(
                {
                    "id": task.id,
                    "task_name": task.task_name,
                    "task_type": task.task_type,
                    "description": task.description,
                    "schedule": task.schedule,
                    "duration_minutes": task.duration_minutes,
                    "today_status": status,
                    "feedback_score": execution.feedback_score,
                    "feedback_note": execution.feedback_note,
                    "modality_based_actions": [],
                }
            )

        progress = round(completed_tasks / total_tasks * 100, 1) if total_tasks else 0
        if create_missing:
            await self.db.commit()

        return {
            "plan": {
                "id": plan.id,
                "plan_name": plan.plan_name,
                "risk_level": plan.risk_level,
                "start_date": str(plan.start_date),
                "progress": progress,
                "dominant_modality": None,
            },
            "tasks": task_items,
        }

    async def get_history(self, user_id: int, page: int, page_size: int) -> dict:
        offset = (page - 1) * page_size
        stmt = (
            select(InterventionPlan)
            .where(InterventionPlan.user_id == user_id)
            .order_by(InterventionPlan.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).scalars().all()

        count_stmt = (
            select(func.count())
            .select_from(InterventionPlan)
            .where(InterventionPlan.user_id == user_id)
        )
        total = (await self.db.execute(count_stmt)).scalar_one()

        # 批量查询优化（修复N+1问题）
        plan_ids = [p.id for p in rows]
        execution_map: dict[int, list] = {}
        task_count_map: dict[int, int] = {}

        if plan_ids:
            tasks_stmt = select(InterventionTask).where(
                InterventionTask.plan_id.in_(plan_ids)
            )
            tasks = (await self.db.execute(tasks_stmt)).scalars().all()
            task_ids = [t.id for t in tasks]
            task_map = {t.id: t.plan_id for t in tasks}  # task_id -> plan_id
            task_count_map = {plan_id: 0 for plan_id in plan_ids}
            for task in tasks:
                task_count_map[task.plan_id] = task_count_map.get(task.plan_id, 0) + 1

            if task_ids:
                exec_stmt = select(TaskExecution).where(
                    TaskExecution.task_id.in_(task_ids),
                    TaskExecution.user_id == user_id,
                )
                executions = (await self.db.execute(exec_stmt)).scalars().all()

                for exe in executions:
                    plan_id = task_map.get(exe.task_id)
                    if plan_id:
                        execution_map.setdefault(plan_id, []).append(exe)

        items = []
        for row in rows:
            executions = execution_map.get(row.id, [])
            total_tasks_in_plan = task_count_map.get(row.id, len(executions))
            completed = len([x for x in executions if x.status == "completed"])
            rate = (
                round((completed / total_tasks_in_plan * 100), 1)
                if total_tasks_in_plan
                else 0
            )
            items.append(
                {
                    "plan_id": row.id,
                    "plan_name": row.plan_name,
                    "status": row.status,
                    "start_date": str(row.start_date),
                    "end_date": str(row.end_date) if row.end_date else None,
                    "completion_rate": rate,
                    "risk_change": None,
                    "dominant_modality": None,
                }
            )

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def complete_task(
        self, user_id: int, task_id: int, scheduled_date: date | None
    ) -> tuple[bool, str | None]:
        task, execution = await self._load_task_execution_readonly(
            task_id, user_id, scheduled_date
        )
        if task is None:
            return False, None
        # H-Svc-15 修复：执行记录不存在说明任务今日未排期，不应自动创建后变更状态
        if execution is None:
            return False, "task_not_scheduled_today"

        valid, reason = self._ensure_transition(execution.status, "completed")
        if not valid:
            return False, reason

        execution.status = "completed"
        execution.completed_at = datetime.now(UTC).replace(tzinfo=None)
        self.db.add(
            OperationLog(
                operator_id=user_id,
                operator_role="user",
                action_type="complete_intervention_task",
                target_type="task_execution",
                target_id=execution.id,
                detail=f"task_id={task_id}, scheduled_date={scheduled_date}",
            )
        )
        await self.db.commit()
        return True, None

    async def feedback_task(
        self,
        user_id: int,
        task_id: int,
        scheduled_date: date | None,
        feedback_score: int | None,
        feedback_note: str | None,
    ) -> tuple[bool, str | None]:
        task, execution = await self._load_task_execution(
            task_id, user_id, scheduled_date
        )
        if task is None or execution is None:
            return False, None

        if feedback_score is not None:
            execution.feedback_score = feedback_score
        if feedback_note is not None:
            execution.feedback_note = feedback_note

        status_changed = False
        if execution.status in self.MUTABLE_STATUSES:
            valid, reason = self._ensure_transition(execution.status, "completed")
            if not valid:
                return False, reason
            execution.status = "completed"
            execution.completed_at = datetime.now(UTC).replace(tzinfo=None)
            status_changed = True

        self.db.add(
            OperationLog(
                operator_id=user_id,
                operator_role="user",
                action_type="feedback_intervention_task",
                target_type="task_execution",
                target_id=execution.id,
                detail=f"task_id={task_id}, scheduled_date={scheduled_date}, status_changed={status_changed}",
            )
        )
        await self.db.commit()
        return True, None

    async def mark_task_missed(
        self,
        user_id: int,
        task_id: int,
        scheduled_date: date | None,
        note: str | None,
    ) -> tuple[bool, str | None]:
        task, execution = await self._load_task_execution_readonly(
            task_id, user_id, scheduled_date
        )
        if task is None:
            return False, None
        # H-Svc-15 修复：执行记录不存在说明任务今日未排期，不应自动创建后变更状态
        if execution is None:
            return False, "task_not_scheduled_today"

        valid, reason = self._ensure_transition(execution.status, "missed")
        if not valid:
            return False, reason

        execution.status = "missed"
        if note:
            execution.feedback_note = note
        await self.db.commit()
        return True, None

    async def skip_task(
        self,
        user_id: int,
        task_id: int,
        scheduled_date: date | None,
        note: str | None,
    ) -> tuple[bool, str | None]:
        task, execution = await self._load_task_execution_readonly(
            task_id, user_id, scheduled_date
        )
        if task is None:
            return False, None
        # H-Svc-15 修复：执行记录不存在说明任务今日未排期，不应自动创建后变更状态
        if execution is None:
            return False, "task_not_scheduled_today"

        valid, reason = self._ensure_transition(execution.status, "skipped")
        if not valid:
            return False, reason

        execution.status = "skipped"
        if note:
            execution.feedback_note = note
        await self.db.commit()
        return True, None

    async def postpone_task(
        self,
        user_id: int,
        task_id: int,
        scheduled_date: date | None,
        postpone_to: date,
        note: str | None,
    ) -> tuple[bool, str | None]:
        if postpone_to < date.today():
            return False, "延期日期不能早于今天"

        task, origin_exec = await self._load_task_execution(
            task_id, user_id, scheduled_date
        )
        if task is None or origin_exec is None:
            return False, None

        if origin_exec.status in {"completed", "missed", "skipped"}:
            return False, f"当前状态为{origin_exec.status}，不允许变更为postponed"

        valid, reason = self._ensure_transition(origin_exec.status, "postponed")
        if not valid:
            return False, reason

        origin_exec.status = "postponed"
        if note:
            origin_exec.feedback_note = note

        new_exec = await self._get_or_create_execution(task_id, user_id, postpone_to)
        if new_exec.status in {"missed", "skipped", "postponed"}:
            new_exec.status = "pending"
        await self.db.commit()
        return True, None

    async def _load_task_execution(
        self,
        task_id: int,
        user_id: int,
        scheduled_date: date | None,
    ) -> tuple[InterventionTask | None, TaskExecution | None]:
        task = await self.db.get(InterventionTask, task_id)
        if task is None:
            return None, None

        plan = await self.db.get(InterventionPlan, task.plan_id)
        if plan is None or plan.user_id != user_id:
            return None, None

        when = scheduled_date or date.today()
        execution = await self._get_or_create_execution(task_id, user_id, when)
        return task, execution

    async def _load_task_execution_readonly(
        self,
        task_id: int,
        user_id: int,
        scheduled_date: date | None,
    ) -> tuple[InterventionTask | None, TaskExecution | None]:
        """H-Svc-15 修复：只读加载任务执行记录，不自动创建。

        用于状态变更操作（complete/mark_missed/skip），避免自动创建 pending execution 后
        立刻转为 completed/missed/skipped，绕过 schedule 检查。
        执行记录不存在时返回 (task, None)，由调用方返回 task_not_scheduled_today 错误。
        """
        task = await self.db.get(InterventionTask, task_id)
        if task is None:
            return None, None

        plan = await self.db.get(InterventionPlan, task.plan_id)
        if plan is None or plan.user_id != user_id:
            return None, None

        when = scheduled_date or date.today()
        execution = await self._get_execution(task_id, user_id, when)
        return task, execution

    async def _get_execution(
        self, task_id: int, user_id: int, scheduled_date: date
    ) -> TaskExecution | None:
        """只读查询执行记录，不创建新记录（用于 GET 端点保证幂等性）。"""
        stmt = select(TaskExecution).where(
            TaskExecution.task_id == task_id,
            TaskExecution.user_id == user_id,
            TaskExecution.scheduled_date == scheduled_date,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _get_or_create_execution(
        self, task_id: int, user_id: int, scheduled_date: date
    ) -> TaskExecution:
        stmt = select(TaskExecution).where(
            TaskExecution.task_id == task_id,
            TaskExecution.user_id == user_id,
            TaskExecution.scheduled_date == scheduled_date,
        )
        execution = (await self.db.execute(stmt)).scalar_one_or_none()
        if execution is not None:
            return execution

        execution = TaskExecution(
            task_id=task_id,
            user_id=user_id,
            scheduled_date=scheduled_date,
            status="pending",
        )
        self.db.add(execution)
        try:
            # M-10 修复：使用 begin_nested savepoint 隔离 flush 操作
            # 失败时只回滚 savepoint，不影响外层事务中已做的其他修改
            async with self.db.begin_nested():
                await self.db.flush()
            return execution
        except IntegrityError:
            # savepoint 已自动回滚，无需手动 rollback
            stmt_retry = select(TaskExecution).where(
                TaskExecution.task_id == task_id,
                TaskExecution.user_id == user_id,
                TaskExecution.scheduled_date == scheduled_date,
            )
            retried = (await self.db.execute(stmt_retry)).scalar_one_or_none()
            if retried is None:
                raise
            return retried

    @classmethod
    def _ensure_transition(
        cls, current_status: str, target_status: str
    ) -> tuple[bool, str | None]:
        if current_status == target_status:
            return False, f"当前状态已是{target_status}，无需重复提交"

        if current_status in cls.TERMINAL_STATUSES:
            return False, f"当前状态为{current_status}，不允许变更为{target_status}"

        allowed_map = {
            "pending": {"completed", "missed", "skipped", "postponed"},
            "postponed": {"pending", "completed", "missed", "skipped"},
        }
        allowed = allowed_map.get(current_status, set())
        if target_status not in allowed:
            return False, f"不支持从{current_status}变更为{target_status}"
        return True, None

    @staticmethod
    def _should_execute_today(schedule: str, start_date: date | None) -> bool:
        today = date.today()
        # H-Svc-14 修复：start_date 可能为 None，直接比较会抛 TypeError 导致整个 get_active 接口 500
        if start_date is None or today < start_date:
            return False
        normalized = (schedule or "daily").strip().lower()
        if normalized == "daily":
            return True
        if normalized == "weekly":
            return (today - start_date).days % 7 == 0
        if normalized in {"one_time", "once", "single"}:
            return today == start_date
        if normalized in {"workday", "weekday"}:
            return today.weekday() < 5
        return True
