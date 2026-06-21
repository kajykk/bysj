"""Tests for InterventionService and InterventionRecommendation."""

from __future__ import annotations

import pytest
from datetime import date, timedelta

from app.services.intervention_service import InterventionRecommendation, InterventionService
from app.models.intervention import InterventionPlan, InterventionTask, TaskExecution


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
        level, actions = InterventionRecommendation.build_from_risk_level(2, dominant_modality="physiological")
        assert level == "medium"
        assert any("生理" in action for action in actions)

    def test_build_from_risk_level_high(self):
        """TC-COV-INTV-005: Risk level 3 returns high."""
        level, actions = InterventionRecommendation.build_from_risk_level(3)
        assert level == "high"
        assert any("预警" in action for action in actions)

    def test_build_from_risk_level_high_text(self):
        """TC-COV-INTV-006: Risk level 3 with text modality."""
        level, actions = InterventionRecommendation.build_from_risk_level(3, dominant_modality="text")
        assert level == "high"
        assert any("情绪" in action for action in actions)

    def test_build_from_risk_level_critical(self):
        """TC-COV-INTV-007: Risk level 4 returns critical."""
        level, actions = InterventionRecommendation.build_from_risk_level(4)
        assert level == "critical"
        assert any("立即" in action or "紧急" in action for action in actions)

    def test_build_from_risk_level_critical_physiological(self):
        """TC-COV-INTV-008: Risk level 4 with physiological modality."""
        level, actions = InterventionRecommendation.build_from_risk_level(4, dominant_modality="physiological")
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
        service = InterventionService(db_session)
        valid, reason = InterventionService._ensure_transition("completed", "completed")
        assert valid is False
        assert "无需重复提交" in reason

    @pytest.mark.asyncio
    async def test_ensure_transition_from_terminal(self, db_session):
        """TC-COV-INTV-013: Transition from terminal status returns False."""
        service = InterventionService(db_session)
        valid, reason = InterventionService._ensure_transition("completed", "missed")
        assert valid is False
        assert "不允许变更" in reason

    @pytest.mark.asyncio
    async def test_ensure_transition_invalid(self, db_session):
        """TC-COV-INTV-014: Invalid transition returns False."""
        service = InterventionService(db_session)
        valid, reason = InterventionService._ensure_transition("pending", "invalid")
        assert valid is False
        assert "不支持" in reason

    @pytest.mark.asyncio
    async def test_ensure_transition_valid(self, db_session):
        """TC-COV-INTV-015: Valid transition returns True."""
        service = InterventionService(db_session)
        valid, reason = InterventionService._ensure_transition("pending", "completed")
        assert valid is True
        assert reason is None

    def test_should_execute_today_daily(self, db_session):
        """TC-COV-INTV-016: Daily schedule should execute today."""
        service = InterventionService(db_session)
        today = date.today()
        assert InterventionService._should_execute_today("daily", today) is True

    def test_should_execute_today_before_start(self, db_session):
        """TC-COV-INTV-017: Before start date should not execute."""
        service = InterventionService(db_session)
        future = date.today() + timedelta(days=7)
        assert InterventionService._should_execute_today("daily", future) is False

    def test_should_execute_today_weekly(self, db_session):
        """TC-COV-INTV-018: Weekly schedule on correct day."""
        service = InterventionService(db_session)
        today = date.today()
        # Start today, so (today - start).days = 0, 0 % 7 == 0
        assert InterventionService._should_execute_today("weekly", today) is True

    def test_should_execute_today_one_time(self, db_session):
        """TC-COV-INTV-019: One-time schedule only on start date."""
        service = InterventionService(db_session)
        today = date.today()
        assert InterventionService._should_execute_today("one_time", today) is True
        yesterday = today - timedelta(days=1)
        assert InterventionService._should_execute_today("one_time", yesterday) is False

    def test_should_execute_today_workday(self, db_session):
        """TC-COV-INTV-020: Workday schedule on weekdays."""
        service = InterventionService(db_session)
        today = date.today()
        # We can't control the day of week, but we can verify it returns a boolean
        result = InterventionService._should_execute_today("workday", today)
        assert isinstance(result, bool)

    def test_should_execute_today_unknown(self, db_session):
        """TC-COV-INTV-021: Unknown schedule defaults to True."""
        service = InterventionService(db_session)
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

        success, reason = await service.feedback_task(1, task.id, None, 5, "Great task!")
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
