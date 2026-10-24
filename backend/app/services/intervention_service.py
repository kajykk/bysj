from __future__ import annotations

import logging
import math
from datetime import UTC, date, datetime

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.contracts import USER_ROLE_USER
from app.core.degradation import record_silent_degradation
from app.models.intervention import InterventionPlan, InterventionTask, TaskExecution

logger = logging.getLogger(__name__)

# M11 修复（ROUND_19）：完成率口径的唯一事实来源。
#
# 原口径：分子 = 该计划下**所有日期**的已完成 TaskExecution 条数，
# 分母 = InterventionTask 条数。TaskExecution 唯一键是
# ``(task_id, user_id, scheduled_date)`` —— 一个 daily 任务连续打卡 3 天即 3 条
# 执行记录，完成率算出 300%。咨询师据"依从性"判断会得到相反结论。
#
# 新口径（分子分母同源，均按**任务**计数）：
#   完成率 = 至少完成过一次的任务数 / 该计划任务总数 × 100
# 结构性保证 ∈ [0, 100]：分子是分母集合的子集计数。
# 仍保留钳制 + 记账作为纵深防御（见 _completion_rate_percent）。
COMPLETION_RATE_LOCATION = "services.intervention_service.completion_rate"


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

    @staticmethod
    def _completion_rate_percent(completed_tasks: int, total_tasks: int) -> float:
        """完成率（百分比）= 至少完成过一次的任务数 / 任务总数 × 100。

        M11 修复（ROUND_19）：口径见模块顶部 ``COMPLETION_RATE_LOCATION`` 注释。
        分子分母同源（都按 InterventionTask 计数）⇒ 数学上必然 ∈ [0, 100]；
        这里仍做钳制 + ``record_silent_degradation`` 记账，属于纵深防御：
        真被触发说明上游计数逻辑被改坏，仪表盘会看到计数而不是静默的 300%。
        """
        if total_tasks <= 0:
            return 0.0
        rate = completed_tasks / total_tasks * 100
        if rate < 0 or rate > 100:
            record_silent_degradation(COMPLETION_RATE_LOCATION)
            logger.warning(
                "intervention.completion_rate.out_of_range completed=%s total=%s rate=%s",
                completed_tasks,
                total_tasks,
                rate,
            )
            rate = min(max(rate, 0.0), 100.0)
        return round(rate, 1)

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_active(self, user_id: int, *, create_missing: bool = True) -> dict:
        stmt = (
            select(InterventionPlan)
            .where(
                InterventionPlan.user_id == user_id, InterventionPlan.status == "active"
            )
            .order_by(InterventionPlan.created_at.desc(), InterventionPlan.id.desc())
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
            .order_by(InterventionTask.sort_order, InterventionTask.id)
        )
        tasks = (await self.db.execute(task_stmt)).scalars().all()

        today = date.today()
        total_tasks = 0
        completed_tasks = 0
        task_items: list[dict] = []

        # AUDIT-2026-10-05: 消除 N+1。
        # 原实现对每个 task 调一次 _get_or_create_execution(内含一次 SELECT,
        # 缺失时再 INSERT) —— T 个任务 = 2T 次串行往返。该方法是用户端高频入口,
        # 60ms 几乎全是 DB 往返时间。
        # 改为: 循环前一次性批量查出今日已有执行记录, 循环内只做内存查找,
        # 缺失时才创建 (创建路径仍走 _get_or_create_execution 以保留
        # savepoint 隔离与并发唯一约束兜底)。
        today_executions: dict[int, TaskExecution] = {}
        if tasks:
            exec_stmt = select(TaskExecution).where(
                TaskExecution.user_id == user_id,
                TaskExecution.task_id.in_([t.id for t in tasks]),
                TaskExecution.scheduled_date == today,
            )
            today_executions = {
                e.task_id: e for e in (await self.db.execute(exec_stmt)).scalars().all()
            }

        for task in tasks:
            should_execute = self._should_execute_today(
                task.schedule or "daily", plan.start_date
            )
            if not should_execute:
                continue

            total_tasks += 1
            cached = today_executions.get(task.id)
            if cached is not None:
                execution = cached
            elif create_missing:
                execution = await self._get_or_create_execution(
                    task.id, user_id, today
                )
                today_executions[task.id] = execution
            else:
                # 只读模式：今日无执行记录则不创建, 直接按 pending 呈现
                # （用于 GET 端点，保证幂等性）
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
        # 钳制 offset 防溢出: 超大 page × page_size 会超出 SQLite int64 (LIMIT/OFFSET 上限)
        offset = min((page - 1) * page_size, 2**63 - 1)
        stmt = (
            select(InterventionPlan)
            .where(InterventionPlan.user_id == user_id)
            .order_by(InterventionPlan.created_at.desc(), InterventionPlan.id.desc())
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
            # M11 修复（ROUND_19）：分子改为"至少完成过一次的任务数"。
            # 原实现数的是执行记录条数（completed executions），一个 daily 任务
            # 连续打卡 3 天即 3 条记录 ⇒ 完成率 300%。新口径与 get_stats 的
            # ``count(distinct task_id)`` 逐字同源，两条路径给同一个数。
            completed_task_ids = {
                x.task_id for x in executions if x.status == "completed"
            }
            completed = len(completed_task_ids)
            rate = self._completion_rate_percent(completed, total_tasks_in_plan)
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

    async def get_stats(self, user_id: int) -> dict:
        """干预计划统计（P1-15 / F-03 修复）。

        原前端 ``page_size:200`` 拉全量计划到浏览器 filter：数据超 200 条时
        分子（active/completed/cancelled 与完成率）只覆盖前 200 条而分母不截断，
        统计结果错误；且每页打开都传输 200 条完整计划记录。改为 SQL 层聚合。

        口径与 ``get_history`` 逐条计算严格一致：
        - 完成率 = 该计划下**至少完成过一次的任务数** / InterventionTask 总数 × 100，
          无任务的计划记 0（``get_history`` 的 ``total_tasks_in_plan`` 为 0 分支）；
          M11 修复前分子是"执行记录条数"，daily 任务连续打卡 3 天即算出 300%。
        - 均值为**全部计划**的算术平均（含 0 值计划），四舍五入口径与前端
          ``Math.round`` 对齐（half-up，非 Python 银行家舍入）。
        """
        # 每计划任务总数（子查询）
        task_counts = (
            select(
                InterventionTask.plan_id.label("plan_id"),
                func.count().label("task_count"),
            )
            .group_by(InterventionTask.plan_id)
            .subquery()
        )
        # 每计划已完成**任务数**（子查询）：distinct task_id，与 get_history 的
        # `len({x.task_id for x in executions if x.status == "completed"})` 同源；
        # execution 同样按 user_id 限定，与 get_history 的过滤一致
        exec_counts = (
            select(
                InterventionTask.plan_id.label("plan_id"),
                func.count(func.distinct(TaskExecution.task_id)).label("exec_count"),
            )
            .select_from(
                TaskExecution.__table__.join(
                    InterventionTask.__table__,
                    TaskExecution.task_id == InterventionTask.id,
                )
            )
            .where(
                TaskExecution.status == "completed",
                TaskExecution.user_id == user_id,
            )
            .group_by(InterventionTask.plan_id)
            .subquery()
        )
        # NULLIF 防除零：SQLite 整除零返回 NULL、PostgreSQL 直接报错，
        # 统一转为 NULL 后 COALESCE 为 0（无任务计划记 0 分）
        plan_rate = func.coalesce(
            exec_counts.c.exec_count * 100.0
            / func.nullif(task_counts.c.task_count, 0),
            0.0,
        )
        stmt = (
            select(
                func.count()
                .filter(InterventionPlan.status == "active")
                .label("active"),
                func.count()
                .filter(InterventionPlan.status == "completed")
                .label("completed"),
                func.count()
                .filter(InterventionPlan.status == "cancelled")
                .label("cancelled"),
                func.coalesce(func.avg(plan_rate), 0.0).label("avg_completion"),
            )
            .select_from(
                InterventionPlan.__table__
                .outerjoin(task_counts, task_counts.c.plan_id == InterventionPlan.id)
                .outerjoin(exec_counts, exec_counts.c.plan_id == InterventionPlan.id)
            )
            .where(InterventionPlan.user_id == user_id)
        )
        row = (await self.db.execute(stmt)).one()
        avg_completion = float(row.avg_completion or 0.0)
        return {
            "active": int(row.active or 0),
            "completed": int(row.completed or 0),
            "cancelled": int(row.cancelled or 0),
            # half-up 舍入，对齐前端 Math.round
            "avg_completion": int(math.floor(avg_completion + 0.5)),
        }

    async def complete_task(
        self,
        user_id: int,
        task_id: int,
        scheduled_date: date | None,
        *,
        # P2-33 第六批：审计上下文由调用方穿入（API 端点传 request + 操作者租户；
        # 任务/旧测试不传则记 None/平台默认）。
        request: Request | None = None,
        tenant_id: int | None = None,
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
        # P2-33 第六批：改走 record_audit（SSOT）。detail 原为裸字符串
        # （`task_id=1, scheduled_date=...`），现统一为 JSON 对象，便于按字段检索。
        await record_audit(
            self.db,
            actor_id=user_id,
            actor_role=USER_ROLE_USER,
            action="complete_intervention_task",
            target_type="task_execution",
            target_id=execution.id,
            detail={"task_id": task_id, "scheduled_date": str(scheduled_date)},
            request=request,
            tenant_id=tenant_id,
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
        *,
        # P2-33 第六批：审计上下文（同上）
        request: Request | None = None,
        tenant_id: int | None = None,
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

        # P2-33 第六批：改走 record_audit（SSOT），detail 统一为 JSON 对象。
        await record_audit(
            self.db,
            actor_id=user_id,
            actor_role=USER_ROLE_USER,
            action="feedback_intervention_task",
            target_type="task_execution",
            target_id=execution.id,
            detail={
                "task_id": task_id,
                "scheduled_date": str(scheduled_date),
                "status_changed": status_changed,
                "feedback_score": feedback_score,
            },
            request=request,
            tenant_id=tenant_id,
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
        # SEC-FIX (P2): 状态冲突类错误统一加机器可读前缀 task_status_conflict:,
        # 前端据此精确映射文案, 不再依赖中文 detail 正则 (后端文案改动即失效)
        if current_status == target_status:
            return False, f"task_status_conflict: 当前状态已是{target_status}，无需重复提交"

        if current_status in cls.TERMINAL_STATUSES:
            return False, f"task_status_conflict: 当前状态为{current_status}，不允许变更为{target_status}"

        allowed_map = {
            "pending": {"completed", "missed", "skipped", "postponed"},
            "postponed": {"pending", "completed", "missed", "skipped"},
        }
        allowed = allowed_map.get(current_status, set())
        if target_status not in allowed:
            return False, f"task_status_conflict: 不支持从{current_status}变更为{target_status}"
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
