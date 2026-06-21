from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.models.intervention import InterventionPlan, InterventionTask, TaskExecution
from app.models.risk import RiskAssessment, WarningNotification, WarningSetting
from app.models.user import User, UserCounselorBinding

logger = logging.getLogger(__name__)

_event_loop: asyncio.AbstractEventLoop | None = None


def _get_loop() -> asyncio.AbstractEventLoop:
    global _event_loop
    if _event_loop is None or _event_loop.is_closed():
        _event_loop = asyncio.new_event_loop()
    return _event_loop


def _run_async(coro):
    loop = _get_loop()
    return loop.run_until_complete(coro)


async def _notify_warning(user_id: int, warning_id: int, risk_level: int, trigger_reason: str, counselor_id: int | None) -> None:
    try:
        from app.core.contracts import normalize_risk_level
        from app.core.ws import notify_warning, notify_counselor

        level_str = normalize_risk_level(risk_level)
        await notify_warning(user_id, warning_id, level_str, trigger_reason)
        if counselor_id:
            await notify_counselor(counselor_id, user_id, warning_id, level_str)
    except Exception:
        logger.warning("Failed to send WebSocket notification for warning %d", warning_id, exc_info=True)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=60, time_limit=300, soft_time_limit=270)
def daily_risk_scan(self):
    logger.info("Starting daily risk scan")
    _run_async(_daily_risk_scan_impl())
    logger.info("Daily risk scan completed")


async def _daily_risk_scan_impl():
    async with AsyncSessionLocal() as db:
        active_users_stmt = select(User).where(User.role == "user", User.status == "active")
        users = (await db.execute(active_users_stmt)).scalars().all()

        # P1-E 修复：日志添加业务上下文（用户数、告警数）
        scanned_count = 0
        warning_count = 0

        for user in users:
            scanned_count += 1
            latest_risk_stmt = (
                select(RiskAssessment)
                .where(RiskAssessment.user_id == user.id)
                .order_by(RiskAssessment.created_at.desc())
                .limit(1)
            )
            latest_risk = (await db.execute(latest_risk_stmt)).scalar_one_or_none()

            if latest_risk is None:
                continue

            days_since = (datetime.now(UTC) - latest_risk.created_at).days
            if days_since > 7 and latest_risk.risk_level >= 2:
                setting_stmt = select(WarningSetting).where(WarningSetting.user_id == user.id)
                setting = (await db.execute(setting_stmt)).scalar_one_or_none()
                threshold = setting.threshold_level if setting else 2

                if latest_risk.risk_level >= threshold:
                    existing_stmt = select(WarningNotification).where(
                        WarningNotification.user_id == user.id,
                        WarningNotification.trigger_reason.like("%超过7天未评估%"),
                        WarningNotification.created_at >= datetime.now(UTC) - timedelta(days=1),
                    )
                    existing = (await db.execute(existing_stmt)).scalar_one_or_none()
                    if existing is None:
                        warning = WarningNotification(
                            user_id=user.id,
                            risk_assessment_id=latest_risk.id,
                            previous_level=latest_risk.risk_level,
                            current_level=latest_risk.risk_level,
                            trigger_reason=f"用户风险等级{latest_risk.risk_level}级且超过{days_since}天未评估，建议关注",
                        )
                        bind_stmt = select(UserCounselorBinding).where(
                            UserCounselorBinding.user_id == user.id,
                            UserCounselorBinding.status == "active",
                        )
                        binding = (await db.execute(bind_stmt)).scalar_one_or_none()
                        if binding:
                            warning.counselor_id = binding.counselor_id
                        db.add(warning)
                        await db.flush()
                        warning_count += 1
                        await _notify_warning(user.id, warning.id, latest_risk.risk_level, warning.trigger_reason, warning.counselor_id)

        await db.commit()
        logger.info(
            "Daily risk scan summary: scanned=%d users, generated=%d warnings",
            scanned_count, warning_count,
        )


@celery_app.task(bind=True, max_retries=1, time_limit=120, soft_time_limit=100)
def stale_warning_reminder(self):
    logger.info("Starting stale warning reminder")
    _run_async(_stale_warning_reminder_impl())
    logger.info("Stale warning reminder completed")


async def _stale_warning_reminder_impl():
    async with AsyncSessionLocal() as db:
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        unhandled_stmt = select(WarningNotification).where(
            WarningNotification.is_handled == False,
            WarningNotification.created_at < cutoff,
            WarningNotification.current_level >= 3,
        )
        stale_warnings = (await db.execute(unhandled_stmt)).scalars().all()

        for warning in stale_warnings:
            if warning.counselor_id:
                logger.info(
                    "Reminder: Warning %d for user %d is unhandled for >24h (counselor: %d)",
                    warning.id,
                    warning.user_id,
                    warning.counselor_id,
                )


@celery_app.task(bind=True, max_retries=1, time_limit=180, soft_time_limit=160)
def daily_intervention_check(self):
    logger.info("Starting daily intervention check")
    _run_async(_daily_intervention_check_impl())
    logger.info("Daily intervention check completed")


async def _daily_intervention_check_impl():
    async with AsyncSessionLocal() as db:
        active_plans_stmt = select(InterventionPlan).where(InterventionPlan.status == "active")
        plans = (await db.execute(active_plans_stmt)).scalars().all()

        # P1-E 修复：日志添加业务上下文（计划数、完成任务数）
        plan_count = len(plans)
        completed_plan_count = 0
        execution_created_count = 0

        today = date.today()

        for plan in plans:
            if plan.end_date and plan.end_date < today:
                plan.status = "completed"
                completed_plan_count += 1
                continue

            tasks_stmt = select(InterventionTask).where(InterventionTask.plan_id == plan.id)
            tasks = (await db.execute(tasks_stmt)).scalars().all()

            for task in tasks:
                if (task.schedule or "daily").strip().lower() == "daily":
                    existing_stmt = select(TaskExecution).where(
                        TaskExecution.task_id == task.id,
                        TaskExecution.user_id == plan.user_id,
                        TaskExecution.scheduled_date == today,
                    )
                    existing = (await db.execute(existing_stmt)).scalar_one_or_none()
                    if existing is None:
                        execution = TaskExecution(
                            task_id=task.id,
                            user_id=plan.user_id,
                            scheduled_date=today,
                            status="pending",
                        )
                        db.add(execution)
                        execution_created_count += 1

            total_tasks_stmt = select(func.count()).select_from(TaskExecution).where(
                TaskExecution.user_id == plan.user_id,
                TaskExecution.task_id.in_([t.id for t in tasks]),
            )
            completed_tasks_stmt = select(func.count()).select_from(TaskExecution).where(
                TaskExecution.user_id == plan.user_id,
                TaskExecution.status == "completed",
                TaskExecution.task_id.in_([t.id for t in tasks]),
            )
            total = (await db.execute(total_tasks_stmt)).scalar_one()
            completed = (await db.execute(completed_tasks_stmt)).scalar_one()
            if total > 0:
                plan.progress = int(completed / total * 100)

        await db.commit()
        logger.info(
            "Daily intervention check summary: plans=%d, completed_plans=%d, executions_created=%d",
            plan_count, completed_plan_count, execution_created_count,
        )


@celery_app.task(bind=True, max_retries=1, time_limit=120, soft_time_limit=100)
def weekly_log_archive(self):
    logger.info("Starting weekly log archive")
    _run_async(_weekly_log_archive_impl())
    logger.info("Weekly log archive completed")


async def _weekly_log_archive_impl():
    async with AsyncSessionLocal() as db:
        from app.services.admin_service import AdminService

        service = AdminService(db)
        count = await service.archive_old_logs(days=90)
        logger.info("Archived %d old operation logs", count)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30, time_limit=60, soft_time_limit=50)
def canary_auto_rollback_check(self):
    logger.info("Starting canary auto-rollback check")
    _run_async(_canary_auto_rollback_check_impl())
    logger.info("Canary auto-rollback check completed")


async def _canary_auto_rollback_check_impl():
    async with AsyncSessionLocal() as db:
        from app.services.auto_rollback_service import auto_rollback_service

        results = await auto_rollback_service.check_all_canaries(db)
        for result in results:
            if result.should_rollback:
                logger.warning(
                    "Auto-rollback triggered for canary %d: %s",
                    result.canary_id,
                    result.reason,
                )
            else:
                logger.debug(
                    "Canary %d health check: %s (metrics: %s)",
                    result.canary_id,
                    result.reason,
                    result.metrics,
                )
