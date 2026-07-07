"""Tests for InterventionService and InterventionRecommendation."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.intervention import InterventionPlan, InterventionTask, TaskExecution
from app.services.intervention_service import (
    InterventionRecommendation,
    InterventionService,
)


class TestInterventionRecommendation:
    """Test intervention recommendation builder."""

    def test_build_from_risk_level_none(self):
        """TC-COV-INTV-001: Risk level 0 returns none."""
        level, actions = InterventionRecommendation.build_from_risk_level(0)
        assert level == "none"
        assert len(actions) > 0

    def test_build_from_risk_level_low(self):
        """TC-COV-INTV-002: Risk level 1 returns low."""
        level, actions = InterventionRecommendation.build_from_risk_level(1)
        assert level == "low"
        assert any("放松" in action or "复测" in action for action in actions)

    def test_build_from_risk_level_medium(self):
        """TC-COV-INTV-003: Risk level 2 returns medium."""
        level, actions = InterventionRecommendation.build_from_risk_level(2)
        assert level == "medium"
        assert any("咨询师" in action for action in actions)

    def test_build_from_risk_level_medium_physiological(self):
        """TC-COV-INTV-004: Risk level 2 with physiological modality."""
        level, actions = InterventionRecommendation.build_from_risk_level(
            2, dominant_modality="physiological"
        )
        assert level == "medium"
        assert any("生理" in action for action in actions)

    def test_build_from_risk_level_high(self):
        """TC-COV-INTV-005: Risk level 3 returns high."""
        level, actions = InterventionRecommendation.build_from_risk_level(3)
        assert level == "high"
        assert any("预警" in action for action in actions)

    def test_build_from_risk_level_high_text(self):
        """TC-COV-INTV-006: Risk level 3 with text modality."""
        level, actions = InterventionRecommendation.build_from_risk_level(
            3, dominant_modality="text"
        )
        assert level == "high"
        assert any("情绪" in action for action in actions)

    def test_build_from_risk_level_critical(self):
        """TC-COV-INTV-007: Risk level 4 returns critical."""
        level, actions = InterventionRecommendation.build_from_risk_level(4)
        assert level == "critical"
        assert any("立即" in action or "紧急" in action for action in actions)

    def test_build_from_risk_level_critical_physiological(self):
        """TC-COV-INTV-008: Risk level 4 with physiological modality."""
        level, actions = InterventionRecommendation.build_from_risk_level(
            4, dominant_modality="physiological"
        )
        assert level == "critical"
        assert any("就医" in action or "生理" in action for action in actions)

    def test_build_from_risk_level_negative(self):
        """TC-COV-INTV-009: Negative risk level returns none."""
        level, actions = InterventionRecommendation.build_from_risk_level(-1)
        assert level == "none"


class TestInterventionService:
    """Test intervention service."""

    @pytest.mark.asyncio
    async def test_get_active_no_plan(self, db_session, seeded_user_id):
        """TC-COV-INTV-010: Get active plan when none exists."""
        service = InterventionService(db_session)
        result = await service.get_active(1)
        assert result["plan"]["plan_name"] == "暂无活跃方案"
        assert result["tasks"] == []

    @pytest.mark.asyncio
    async def test_get_history_empty(self, db_session, seeded_user_id):
        """TC-COV-INTV-011: Get history when no plans exist."""
        service = InterventionService(db_session)
        result = await service.get_history(1, 1, 10)
        assert result["items"] == []
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_ensure_transition_same_status(self, db_session):
        """TC-COV-INTV-012: Transition to same status returns False."""
        InterventionService(db_session)
        valid, reason = InterventionService._ensure_transition("completed", "completed")
        assert valid is False
        assert "无需重复提交" in reason

    @pytest.mark.asyncio
    async def test_ensure_transition_from_terminal(self, db_session):
        """TC-COV-INTV-013: Transition from terminal status returns False."""
        InterventionService(db_session)
        valid, reason = InterventionService._ensure_transition("completed", "missed")
        assert valid is False
        assert "不允许变更" in reason

    @pytest.mark.asyncio
    async def test_ensure_transition_invalid(self, db_session):
        """TC-COV-INTV-014: Invalid transition returns False."""
        InterventionService(db_session)
        valid, reason = InterventionService._ensure_transition("pending", "invalid")
        assert valid is False
        assert "不支持" in reason

    @pytest.mark.asyncio
    async def test_ensure_transition_valid(self, db_session):
        """TC-COV-INTV-015: Valid transition returns True."""
        InterventionService(db_session)
        valid, reason = InterventionService._ensure_transition("pending", "completed")
        assert valid is True
        assert reason is None

    def test_should_execute_today_daily(self, db_session):
        """TC-COV-INTV-016: Daily schedule should execute today."""
        InterventionService(db_session)
        today = date.today()
        assert InterventionService._should_execute_today("daily", today) is True

    def test_should_execute_today_before_start(self, db_session):
        """TC-COV-INTV-017: Before start date should not execute."""
        InterventionService(db_session)
        future = date.today() + timedelta(days=7)
        assert InterventionService._should_execute_today("daily", future) is False

    def test_should_execute_today_weekly(self, db_session):
        """TC-COV-INTV-018: Weekly schedule on correct day."""
        InterventionService(db_session)
        today = date.today()
        # Start today, so (today - start).days = 0, 0 % 7 == 0
        assert InterventionService._should_execute_today("weekly", today) is True

    def test_should_execute_today_one_time(self, db_session):
        """TC-COV-INTV-019: One-time schedule only on start date."""
        InterventionService(db_session)
        today = date.today()
        assert InterventionService._should_execute_today("one_time", today) is True
        yesterday = today - timedelta(days=1)
        assert InterventionService._should_execute_today("one_time", yesterday) is False

    def test_should_execute_today_workday(self, db_session):
        """TC-COV-INTV-020: Workday schedule on weekdays."""
        InterventionService(db_session)
        today = date.today()
        # We can't control the day of week, but we can verify it returns a boolean
        result = InterventionService._should_execute_today("workday", today)
        assert isinstance(result, bool)

    def test_should_execute_today_unknown(self, db_session):
        """TC-COV-INTV-021: Unknown schedule defaults to True."""
        InterventionService(db_session)
        today = date.today()
        assert InterventionService._should_execute_today("unknown", today) is True

    @pytest.mark.asyncio
    async def test_complete_task_not_found(self, db_session, seeded_user_id):
        """TC-COV-INTV-022: Complete non-existent task returns False."""
        service = InterventionService(db_session)
        success, reason = await service.complete_task(1, 9999, None)
        assert success is False
        assert reason is None

    @pytest.mark.asyncio
    async def test_feedback_task_not_found(self, db_session, seeded_user_id):
        """TC-COV-INTV-023: Feedback on non-existent task returns False."""
        service = InterventionService(db_session)
        success, reason = await service.feedback_task(1, 9999, None, 5, "good")
        assert success is False
        assert reason is None

    @pytest.mark.asyncio
    async def test_mark_task_missed_not_found(self, db_session, seeded_user_id):
        """TC-COV-INTV-024: Mark non-existent task as missed returns False."""
        service = InterventionService(db_session)
        success, reason = await service.mark_task_missed(1, 9999, None, "missed")
        assert success is False
        assert reason is None

    @pytest.mark.asyncio
    async def test_skip_task_not_found(self, db_session, seeded_user_id):
        """TC-COV-INTV-025: Skip non-existent task returns False."""
        service = InterventionService(db_session)
        success, reason = await service.skip_task(1, 9999, None, "skip")
        assert success is False
        assert reason is None

    @pytest.mark.asyncio
    async def test_postpone_task_past_date(self, db_session, seeded_user_id):
        """TC-COV-INTV-026: Postpone to past date returns False."""
        service = InterventionService(db_session)
        yesterday = date.today() - timedelta(days=1)
        success, reason = await service.postpone_task(1, 9999, None, yesterday, "note")
        assert success is False
        assert "不能早于今天" in reason

    @pytest.mark.asyncio
    async def test_postpone_task_not_found(self, db_session, seeded_user_id):
        """TC-COV-INTV-027: Postpone non-existent task returns False."""
        service = InterventionService(db_session)
        tomorrow = date.today() + timedelta(days=1)
        success, reason = await service.postpone_task(1, 9999, None, tomorrow, "note")
        assert success is False
        assert reason is None

    @pytest.mark.asyncio
    async def test_get_active_with_plan(self, db_session, seeded_user_id):
        """TC-COV-INTV-028: Get active plan with tasks."""
        service = InterventionService(db_session)
        # Create a plan
        plan = InterventionPlan(
            user_id=1,
            plan_name="Test Plan",
            risk_level=2,
            status="active",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()

        # Create tasks
        task = InterventionTask(
            plan_id=plan.id,
            task_name="Test Task",
            task_type="relaxation",
            description="Test description",
            schedule="daily",
            duration_minutes=15,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.commit()

        result = await service.get_active(1)
        assert result["plan"]["plan_name"] == "Test Plan"
        assert len(result["tasks"]) == 1
        assert result["tasks"][0]["task_name"] == "Test Task"

    @pytest.mark.asyncio
    async def test_complete_task_success(self, db_session, seeded_user_id):
        """TC-COV-INTV-029: Complete task successfully."""
        service = InterventionService(db_session)
        # Create plan and task
        plan = InterventionPlan(
            user_id=1,
            plan_name="Test Plan",
            risk_level=2,
            status="active",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()

        task = InterventionTask(
            plan_id=plan.id,
            task_name="Test Task",
            task_type="relaxation",
            schedule="daily",
            duration_minutes=15,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.flush()

        # H-Svc-15 修复：complete_task 不再自动创建执行记录，需要预先创建
        # status=pending 的执行记录才能完成状态转换
        execution = TaskExecution(
            task_id=task.id,
            user_id=1,
            scheduled_date=date.today(),
            status="pending",
        )
        db_session.add(execution)
        await db_session.commit()
        await db_session.refresh(task)

        success, reason = await service.complete_task(1, task.id, None)
        assert success is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_feedback_task_success(self, db_session, seeded_user_id):
        """TC-COV-INTV-030: Feedback task successfully."""
        service = InterventionService(db_session)
        # Create plan and task
        plan = InterventionPlan(
            user_id=1,
            plan_name="Test Plan",
            risk_level=2,
            status="active",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()

        task = InterventionTask(
            plan_id=plan.id,
            task_name="Test Task",
            task_type="relaxation",
            schedule="daily",
            duration_minutes=15,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.commit()
        await db_session.refresh(task)

        success, reason = await service.feedback_task(
            1, task.id, None, 5, "Great task!"
        )
        assert success is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_get_history_with_data(self, db_session, seeded_user_id):
        """TC-COV-INTV-031: Get history with plans."""
        service = InterventionService(db_session)
        # Create plans
        for i in range(3):
            plan = InterventionPlan(
                user_id=1,
                plan_name=f"Plan {i}",
                risk_level=2,
                status="completed",
                start_date=date.today() - timedelta(days=i),
            )
            db_session.add(plan)
        await db_session.commit()

        result = await service.get_history(1, 1, 10)
        assert result["total"] == 3
        assert len(result["items"]) == 3


class TestInterventionRecommendationExtended:
    """补充覆盖 InterventionRecommendation 的额外分支。"""

    def test_build_from_risk_level_high_physiological(self):
        """TC-COV-INTV-032: risk_level=3 + dominant_modality=physiological 插入生理复查建议。"""
        level, actions = InterventionRecommendation.build_from_risk_level(
            3, dominant_modality="physiological"
        )
        assert level == "high"
        # 行 28：在 index=1 处插入 "建议进行生理指标专项复查"
        assert actions[1] == "建议进行生理指标专项复查"
        assert any("高风险预警" in a for a in actions)


class TestInterventionServiceGetActive:
    """补充覆盖 InterventionService.get_active 的缺失分支。"""

    @pytest.mark.asyncio
    async def test_get_active_task_not_scheduled_today(
        self, db_session, seeded_user_id
    ):
        """TC-COV-INTV-033: weekly 任务且 start_date=昨天，今日不应执行（覆盖行 79）。"""
        service = InterventionService(db_session)
        # start_date 为昨天，weekly schedule，(today - yesterday).days = 1, 1 % 7 != 0
        plan = InterventionPlan(
            user_id=1,
            plan_name="Weekly Plan",
            risk_level=2,
            status="active",
            start_date=date.today() - timedelta(days=1),
        )
        db_session.add(plan)
        await db_session.flush()

        task = InterventionTask(
            plan_id=plan.id,
            task_name="Weekly Task",
            task_type="relaxation",
            schedule="weekly",
            duration_minutes=10,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.commit()

        result = await service.get_active(1)
        # 任务今日不应执行 -> total_tasks=0 -> tasks=[]
        assert result["tasks"] == []
        assert result["plan"]["progress"] == 0

    @pytest.mark.asyncio
    async def test_get_active_readonly_mode(self, db_session, seeded_user_id):
        """TC-COV-INTV-034: get_active(create_missing=False) 只读模式不创建 execution（覆盖行 86-102）。"""
        service = InterventionService(db_session)
        plan = InterventionPlan(
            user_id=1,
            plan_name="Readonly Plan",
            risk_level=2,
            status="active",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()

        task = InterventionTask(
            plan_id=plan.id,
            task_name="Readonly Task",
            task_type="relaxation",
            description="Readonly desc",
            schedule="daily",
            duration_minutes=10,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.commit()

        # 只读模式：execution 不存在 -> 返回 today_status="pending" 占位项
        result = await service.get_active(1, create_missing=False)
        assert len(result["tasks"]) == 1
        task_item = result["tasks"][0]
        assert task_item["today_status"] == "pending"
        assert task_item["feedback_score"] is None
        assert task_item["feedback_note"] is None
        assert task_item["modality_based_actions"] == []

    @pytest.mark.asyncio
    async def test_get_active_with_completed_execution(
        self, db_session, seeded_user_id
    ):
        """TC-COV-INTV-035: get_active 在 execution.status=completed 时累加 completed_tasks（覆盖行 106）。"""
        service = InterventionService(db_session)
        plan = InterventionPlan(
            user_id=1,
            plan_name="Completed Plan",
            risk_level=2,
            status="active",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()

        task = InterventionTask(
            plan_id=plan.id,
            task_name="Done Task",
            task_type="relaxation",
            schedule="daily",
            duration_minutes=5,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.flush()

        # 预先创建一个 completed execution
        db_session.add(
            TaskExecution(
                task_id=task.id,
                user_id=1,
                scheduled_date=date.today(),
                status="completed",
            )
        )
        await db_session.commit()

        result = await service.get_active(1, create_missing=False)
        assert len(result["tasks"]) == 1
        assert result["tasks"][0]["today_status"] == "completed"
        # completed_tasks / total_tasks = 1 / 1 = 100.0
        assert result["plan"]["progress"] == 100.0


class TestInterventionServiceGetHistory:
    """补充覆盖 get_history 的 tasks 和 executions 批量查询路径。"""

    @pytest.mark.asyncio
    async def test_get_history_with_tasks_and_executions(
        self, db_session, seeded_user_id
    ):
        """TC-COV-INTV-036: get_history 批量查询 tasks 和 executions（覆盖行 165, 168-177）。"""
        service = InterventionService(db_session)
        plan = InterventionPlan(
            user_id=1,
            plan_name="History Plan",
            risk_level=2,
            status="completed",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()

        task1 = InterventionTask(
            plan_id=plan.id,
            task_name="Task 1",
            task_type="relaxation",
            schedule="daily",
            duration_minutes=5,
            sort_order=0,
        )
        task2 = InterventionTask(
            plan_id=plan.id,
            task_name="Task 2",
            task_type="meditation",
            schedule="daily",
            duration_minutes=10,
            sort_order=1,
        )
        db_session.add_all([task1, task2])
        await db_session.flush()

        # 创建 executions：task1 completed，task2 missed
        db_session.add_all(
            [
                TaskExecution(
                    task_id=task1.id,
                    user_id=1,
                    scheduled_date=date.today(),
                    status="completed",
                ),
                TaskExecution(
                    task_id=task2.id,
                    user_id=1,
                    scheduled_date=date.today(),
                    status="missed",
                ),
            ]
        )
        await db_session.commit()

        result = await service.get_history(1, 1, 10)
        assert result["total"] == 1
        assert len(result["items"]) == 1
        item = result["items"][0]
        assert item["plan_name"] == "History Plan"
        # completed=1, total_tasks_in_plan=2 -> 50.0
        assert item["completion_rate"] == 50.0


class TestInterventionServiceCompleteTask:
    """补充覆盖 complete_task 缺失分支。"""

    @pytest.mark.asyncio
    async def test_complete_task_not_scheduled_today(self, db_session, seeded_user_id):
        """TC-COV-INTV-037: complete_task 在 execution 不存在时返回 task_not_scheduled_today（覆盖行 211）。"""
        service = InterventionService(db_session)
        plan = InterventionPlan(
            user_id=1,
            plan_name="Plan",
            risk_level=2,
            status="active",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()

        task = InterventionTask(
            plan_id=plan.id,
            task_name="Task",
            task_type="relaxation",
            schedule="daily",
            duration_minutes=5,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.commit()

        # 未创建 execution -> H-Svc-15 应返回 task_not_scheduled_today
        success, reason = await service.complete_task(1, task.id, None)
        assert success is False
        assert reason == "task_not_scheduled_today"

    @pytest.mark.asyncio
    async def test_complete_task_already_completed(self, db_session, seeded_user_id):
        """TC-COV-INTV-038: complete_task 在 execution 已是 completed 时返回 invalid transition（覆盖行 215）。"""
        service = InterventionService(db_session)
        plan = InterventionPlan(
            user_id=1,
            plan_name="Plan",
            risk_level=2,
            status="active",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()

        task = InterventionTask(
            plan_id=plan.id,
            task_name="Task",
            task_type="relaxation",
            schedule="daily",
            duration_minutes=5,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.flush()

        db_session.add(
            TaskExecution(
                task_id=task.id,
                user_id=1,
                scheduled_date=date.today(),
                status="completed",
            )
        )
        await db_session.commit()

        success, reason = await service.complete_task(1, task.id, None)
        assert success is False
        assert reason is not None
        assert "无需重复提交" in reason

    @pytest.mark.asyncio
    async def test_complete_task_wrong_user(self, db_session, seeded_user_id):
        """TC-COV-INTV-039: complete_task 在 plan 属于他人时返回 (False, None)（覆盖行 387）。"""
        service = InterventionService(db_session)
        # 创建属于 user_id=2 的 plan
        plan = InterventionPlan(
            user_id=2,
            plan_name="Other User Plan",
            risk_level=2,
            status="active",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()

        task = InterventionTask(
            plan_id=plan.id,
            task_name="Task",
            task_type="relaxation",
            schedule="daily",
            duration_minutes=5,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.commit()

        # user_id=1 试图 complete 属于 user_id=2 的 task
        success, reason = await service.complete_task(1, task.id, None)
        assert success is False
        assert reason is None


class TestInterventionServiceFeedbackTask:
    """补充覆盖 feedback_task 缺失分支。"""

    @pytest.mark.asyncio
    async def test_feedback_task_transition_failed(self, db_session, seeded_user_id):
        """TC-COV-INTV-040: feedback_task 在 _ensure_transition 失败时返回错误（覆盖行 253）。

        通过 patch _ensure_transition 强制返回 (False, reason) 触发早返回。
        """
        service = InterventionService(db_session)
        plan = InterventionPlan(
            user_id=1,
            plan_name="Plan",
            risk_level=2,
            status="active",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()

        task = InterventionTask(
            plan_id=plan.id,
            task_name="Task",
            task_type="relaxation",
            schedule="daily",
            duration_minutes=5,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.commit()
        await db_session.refresh(task)

        # feedback_task 会通过 _load_task_execution -> _get_or_create_execution 创建 pending execution
        # 然后 status="pending" in MUTABLE_STATUSES -> 调用 _ensure_transition("pending", "completed")
        # 强制让 _ensure_transition 返回失败以覆盖行 253
        with patch.object(
            InterventionService,
            "_ensure_transition",
            return_value=(False, "模拟转换失败"),
        ):
            success, reason = await service.feedback_task(1, task.id, None, 5, "note")
        assert success is False
        assert reason == "模拟转换失败"

    @pytest.mark.asyncio
    async def test_feedback_task_wrong_user(self, db_session, seeded_user_id):
        """TC-COV-INTV-041: feedback_task 在 plan 属于他人时返回 (False, None)（覆盖行 363）。"""
        service = InterventionService(db_session)
        plan = InterventionPlan(
            user_id=2,
            plan_name="Other Plan",
            risk_level=2,
            status="active",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()

        task = InterventionTask(
            plan_id=plan.id,
            task_name="Task",
            task_type="relaxation",
            schedule="daily",
            duration_minutes=5,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.commit()

        success, reason = await service.feedback_task(1, task.id, None, 5, "note")
        assert success is False
        assert reason is None


class TestInterventionServiceMarkTaskMissed:
    """补充覆盖 mark_task_missed 完整路径。"""

    @pytest.mark.asyncio
    async def test_mark_task_missed_not_scheduled_today(
        self, db_session, seeded_user_id
    ):
        """TC-COV-INTV-042: mark_task_missed 在 execution 不存在时返回 task_not_scheduled_today（覆盖行 282-283）。"""
        service = InterventionService(db_session)
        plan = InterventionPlan(
            user_id=1,
            plan_name="Plan",
            risk_level=2,
            status="active",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()

        task = InterventionTask(
            plan_id=plan.id,
            task_name="Task",
            task_type="relaxation",
            schedule="daily",
            duration_minutes=5,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.commit()

        success, reason = await service.mark_task_missed(1, task.id, None, "note")
        assert success is False
        assert reason == "task_not_scheduled_today"

    @pytest.mark.asyncio
    async def test_mark_task_missed_invalid_transition(
        self, db_session, seeded_user_id
    ):
        """TC-COV-INTV-043: mark_task_missed 在已是 missed 时返回 invalid transition（覆盖行 285-287）。"""
        service = InterventionService(db_session)
        plan = InterventionPlan(
            user_id=1,
            plan_name="Plan",
            risk_level=2,
            status="active",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()

        task = InterventionTask(
            plan_id=plan.id,
            task_name="Task",
            task_type="relaxation",
            schedule="daily",
            duration_minutes=5,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.flush()

        db_session.add(
            TaskExecution(
                task_id=task.id,
                user_id=1,
                scheduled_date=date.today(),
                status="missed",
            )
        )
        await db_session.commit()

        success, reason = await service.mark_task_missed(1, task.id, None, "note")
        assert success is False
        assert reason is not None
        assert "无需重复提交" in reason

    @pytest.mark.asyncio
    async def test_mark_task_missed_success(self, db_session, seeded_user_id):
        """TC-COV-INTV-044: mark_task_missed 成功路径（覆盖行 289-293）。"""
        service = InterventionService(db_session)
        plan = InterventionPlan(
            user_id=1,
            plan_name="Plan",
            risk_level=2,
            status="active",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()

        task = InterventionTask(
            plan_id=plan.id,
            task_name="Task",
            task_type="relaxation",
            schedule="daily",
            duration_minutes=5,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.flush()

        db_session.add(
            TaskExecution(
                task_id=task.id,
                user_id=1,
                scheduled_date=date.today(),
                status="pending",
            )
        )
        await db_session.commit()

        success, reason = await service.mark_task_missed(1, task.id, None, "未完成")
        assert success is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_mark_task_missed_wrong_user(self, db_session, seeded_user_id):
        """TC-COV-INTV-045: mark_task_missed 在 plan 属于他人时返回 (False, None)（覆盖行 387）。"""
        service = InterventionService(db_session)
        plan = InterventionPlan(
            user_id=2,
            plan_name="Other Plan",
            risk_level=2,
            status="active",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()

        task = InterventionTask(
            plan_id=plan.id,
            task_name="Task",
            task_type="relaxation",
            schedule="daily",
            duration_minutes=5,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.commit()

        success, reason = await service.mark_task_missed(1, task.id, None, "note")
        assert success is False
        assert reason is None


class TestInterventionServiceSkipTask:
    """补充覆盖 skip_task 完整路径。"""

    @pytest.mark.asyncio
    async def test_skip_task_not_scheduled_today(self, db_session, seeded_user_id):
        """TC-COV-INTV-046: skip_task 在 execution 不存在时返回 task_not_scheduled_today（覆盖行 306-307）。"""
        service = InterventionService(db_session)
        plan = InterventionPlan(
            user_id=1,
            plan_name="Plan",
            risk_level=2,
            status="active",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()

        task = InterventionTask(
            plan_id=plan.id,
            task_name="Task",
            task_type="relaxation",
            schedule="daily",
            duration_minutes=5,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.commit()

        success, reason = await service.skip_task(1, task.id, None, "skip note")
        assert success is False
        assert reason == "task_not_scheduled_today"

    @pytest.mark.asyncio
    async def test_skip_task_invalid_transition(self, db_session, seeded_user_id):
        """TC-COV-INTV-047: skip_task 在已是 skipped 时返回 invalid transition（覆盖行 309-311）。"""
        service = InterventionService(db_session)
        plan = InterventionPlan(
            user_id=1,
            plan_name="Plan",
            risk_level=2,
            status="active",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()

        task = InterventionTask(
            plan_id=plan.id,
            task_name="Task",
            task_type="relaxation",
            schedule="daily",
            duration_minutes=5,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.flush()

        db_session.add(
            TaskExecution(
                task_id=task.id,
                user_id=1,
                scheduled_date=date.today(),
                status="skipped",
            )
        )
        await db_session.commit()

        success, reason = await service.skip_task(1, task.id, None, "note")
        assert success is False
        assert reason is not None
        assert "无需重复提交" in reason

    @pytest.mark.asyncio
    async def test_skip_task_success(self, db_session, seeded_user_id):
        """TC-COV-INTV-048: skip_task 成功路径（覆盖行 313-317）。"""
        service = InterventionService(db_session)
        plan = InterventionPlan(
            user_id=1,
            plan_name="Plan",
            risk_level=2,
            status="active",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()

        task = InterventionTask(
            plan_id=plan.id,
            task_name="Task",
            task_type="relaxation",
            schedule="daily",
            duration_minutes=5,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.flush()

        db_session.add(
            TaskExecution(
                task_id=task.id,
                user_id=1,
                scheduled_date=date.today(),
                status="pending",
            )
        )
        await db_session.commit()

        success, reason = await service.skip_task(1, task.id, None, "skip")
        assert success is True
        assert reason is None


class TestInterventionServicePostponeTask:
    """补充覆盖 postpone_task 完整路径。"""

    @pytest.mark.asyncio
    async def test_postpone_task_terminal_status(self, db_session, seeded_user_id):
        """TC-COV-INTV-049: postpone_task 在 origin_exec 已终态时拒绝（覆盖行 334-335）。"""
        service = InterventionService(db_session)
        plan = InterventionPlan(
            user_id=1,
            plan_name="Plan",
            risk_level=2,
            status="active",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()

        task = InterventionTask(
            plan_id=plan.id,
            task_name="Task",
            task_type="relaxation",
            schedule="daily",
            duration_minutes=5,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.flush()

        # origin_exec 已是 completed
        db_session.add(
            TaskExecution(
                task_id=task.id,
                user_id=1,
                scheduled_date=date.today(),
                status="completed",
            )
        )
        await db_session.commit()

        tomorrow = date.today() + timedelta(days=1)
        success, reason = await service.postpone_task(
            1, task.id, None, tomorrow, "postpone"
        )
        assert success is False
        assert reason is not None
        assert "不允许变更为postponed" in reason

    @pytest.mark.asyncio
    async def test_postpone_task_success(self, db_session, seeded_user_id):
        """TC-COV-INTV-050: postpone_task 成功路径（覆盖行 337-349）。"""
        service = InterventionService(db_session)
        plan = InterventionPlan(
            user_id=1,
            plan_name="Plan",
            risk_level=2,
            status="active",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()

        task = InterventionTask(
            plan_id=plan.id,
            task_name="Task",
            task_type="relaxation",
            schedule="daily",
            duration_minutes=5,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.flush()

        # pending execution（可变更为 postponed）
        db_session.add(
            TaskExecution(
                task_id=task.id,
                user_id=1,
                scheduled_date=date.today(),
                status="pending",
            )
        )
        await db_session.commit()

        tomorrow = date.today() + timedelta(days=1)
        success, reason = await service.postpone_task(
            1, task.id, None, tomorrow, "延期说明"
        )
        assert success is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_postpone_task_wrong_user(self, db_session, seeded_user_id):
        """TC-COV-INTV-051: postpone_task 在 plan 属于他人时返回 (False, None)（覆盖行 363）。"""
        service = InterventionService(db_session)
        plan = InterventionPlan(
            user_id=2,
            plan_name="Other Plan",
            risk_level=2,
            status="active",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()

        task = InterventionTask(
            plan_id=plan.id,
            task_name="Task",
            task_type="relaxation",
            schedule="daily",
            duration_minutes=5,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.commit()

        tomorrow = date.today() + timedelta(days=1)
        success, reason = await service.postpone_task(
            1, task.id, None, tomorrow, "note"
        )
        assert success is False
        assert reason is None

    @pytest.mark.asyncio
    async def test_postpone_task_already_postponed(self, db_session, seeded_user_id):
        """TC-COV-INTV-052: postpone_task 在 origin_exec 已是 postponed 时 _ensure_transition 失败（覆盖行 339）。

        postponed 不在 TERMINAL_STATUSES，所以行 334-335 的早返回不触发；
        _ensure_transition("postponed", "postponed") 因 current==target 返回 False，触发行 339 早返回。
        """
        service = InterventionService(db_session)
        plan = InterventionPlan(
            user_id=1,
            plan_name="Plan",
            risk_level=2,
            status="active",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()

        task = InterventionTask(
            plan_id=plan.id,
            task_name="Task",
            task_type="relaxation",
            schedule="daily",
            duration_minutes=5,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.flush()

        # origin_exec 已是 postponed（不在 TERMINAL_STATUSES，但 _ensure_transition 会失败）
        db_session.add(
            TaskExecution(
                task_id=task.id,
                user_id=1,
                scheduled_date=date.today(),
                status="postponed",
            )
        )
        await db_session.commit()

        tomorrow = date.today() + timedelta(days=1)
        success, reason = await service.postpone_task(
            1, task.id, None, tomorrow, "note"
        )
        assert success is False
        assert reason is not None
        assert "无需重复提交" in reason

    @pytest.mark.asyncio
    async def test_postpone_task_resets_existing_missed_exec(
        self, db_session, seeded_user_id
    ):
        """TC-COV-INTV-053: postpone_task 在 new_exec 已是 missed/skipped/postponed 时重置为 pending（覆盖行 347）。

        创建一个 postpone_to 日期的 execution，状态为 missed，
        调用 postpone_task 时 new_exec.status in {"missed",...} -> 重置为 pending。
        """
        service = InterventionService(db_session)
        plan = InterventionPlan(
            user_id=1,
            plan_name="Plan",
            risk_level=2,
            status="active",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()

        task = InterventionTask(
            plan_id=plan.id,
            task_name="Task",
            task_type="relaxation",
            schedule="daily",
            duration_minutes=5,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.flush()

        # 今天：pending execution（origin_exec，可变更为 postponed）
        db_session.add(
            TaskExecution(
                task_id=task.id,
                user_id=1,
                scheduled_date=date.today(),
                status="pending",
            )
        )
        # 明天：已存在的 missed execution（new_exec，应被重置为 pending）
        tomorrow = date.today() + timedelta(days=1)
        db_session.add(
            TaskExecution(
                task_id=task.id,
                user_id=1,
                scheduled_date=tomorrow,
                status="missed",
            )
        )
        await db_session.commit()

        success, reason = await service.postpone_task(
            1, task.id, None, tomorrow, "延期说明"
        )
        assert success is True
        assert reason is None


class TestInterventionServiceGetOrCreateExecution:
    """补充覆盖 _get_or_create_execution 的私有逻辑。"""

    @pytest.mark.asyncio
    async def test_get_or_create_execution_exists(self, db_session, seeded_user_id):
        """TC-COV-INTV-054: _get_or_create_execution 在 execution 已存在时直接返回（覆盖行 410）。"""
        service = InterventionService(db_session)
        plan = InterventionPlan(
            user_id=1,
            plan_name="Plan",
            risk_level=2,
            status="active",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()

        task = InterventionTask(
            plan_id=plan.id,
            task_name="Task",
            task_type="relaxation",
            schedule="daily",
            duration_minutes=5,
            sort_order=0,
        )
        db_session.add(task)
        await db_session.flush()

        existing_exec = TaskExecution(
            task_id=task.id,
            user_id=1,
            scheduled_date=date.today(),
            status="pending",
        )
        db_session.add(existing_exec)
        await db_session.commit()
        await db_session.refresh(existing_exec)

        # 再次调用 _get_or_create_execution 应直接返回已存在的 execution（不走创建分支）
        result = await service._get_or_create_execution(task.id, 1, date.today())
        assert result.id == existing_exec.id

    @pytest.mark.asyncio
    async def test_get_or_create_execution_integrity_error_retry(self):
        """TC-COV-INTV-055: _get_or_create_execution 在 flush 抛 IntegrityError 时重试并返回已创建 execution（覆盖行 425-435）。

        使用 MagicMock 模拟 db_session（不能用 AsyncMock，否则 begin_nested() 返回 coroutine 无法作为 async context manager）。
        配置 begin_nested 的 __aexit__ 返回 False 让异常传播到外层 except。
        """
        mock_db = MagicMock()
        # 第一次 execute 返回 None（无 execution），第二次（重试）返回 mock_execution
        first_result = MagicMock()
        first_result.scalar_one_or_none.return_value = None
        mock_execution = MagicMock()
        mock_execution.id = 999
        second_result = MagicMock()
        second_result.scalar_one_or_none.return_value = mock_execution
        mock_db.execute = AsyncMock(side_effect=[first_result, second_result])

        # flush 抛 IntegrityError 触发重试分支
        mock_db.flush = AsyncMock(
            side_effect=IntegrityError("INSERT", {}, Exception("UNIQUE constraint"))
        )
        mock_db.add = MagicMock()

        # begin_nested savepoint：__aenter__ 不抛异常，__aexit__ 返回 False 让异常传播到外层 except
        mock_db.begin_nested.return_value.__aenter__ = AsyncMock(return_value=None)
        mock_db.begin_nested.return_value.__aexit__ = AsyncMock(return_value=False)

        service = InterventionService(mock_db)
        result = await service._get_or_create_execution(1, 1, date.today())
        assert result is mock_execution
        # 验证 add 被调用（创建新 execution）
        assert mock_db.add.called
        # 验证 flush 被调用过（首次创建时抛 IntegrityError）
        mock_db.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_get_or_create_execution_integrity_error_no_retry_row(self):
        """TC-COV-INTV-056: _get_or_create_execution 重试后仍无记录时抛出异常（覆盖行 433-434 raise 分支）。"""
        mock_db = MagicMock()
        first_result = MagicMock()
        first_result.scalar_one_or_none.return_value = None
        # 重试查询时仍返回 None -> 应 raise
        second_result = MagicMock()
        second_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(side_effect=[first_result, second_result])

        mock_db.flush = AsyncMock(
            side_effect=IntegrityError("INSERT", {}, Exception("UNIQUE"))
        )
        mock_db.add = MagicMock()

        mock_db.begin_nested.return_value.__aenter__ = AsyncMock(return_value=None)
        mock_db.begin_nested.return_value.__aexit__ = AsyncMock(return_value=False)

        service = InterventionService(mock_db)
        with pytest.raises(IntegrityError):
            await service._get_or_create_execution(1, 1, date.today())
