"""Cleanup legacy rows before applying stricter schema/model constraints.

This script is intentionally conservative and idempotent:
- trims overlong string fields
- clamps numeric fields into allowed ranges
- normalizes a few enum-like values
- fixes inverted min/max score pairs

Run it before Alembic migrations that add new CHECK/length constraints.

Usage:
  python backend/scripts/cleanup_constraints.py
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:12345678@localhost:5432/depression_system")

from app.core.config import settings  # noqa: E402


@dataclass(frozen=True)
class CleanupStep:
    name: str
    sql: str


STEPS: tuple[CleanupStep, ...] = (
    CleanupStep(
        "users.username_length",
        "UPDATE users SET username = LEFT(username, 50) WHERE LENGTH(username) > 50",
    ),
    CleanupStep(
        "users.email_length",
        "UPDATE users SET email = LEFT(email, 100) WHERE LENGTH(email) > 100",
    ),
    CleanupStep(
        "users.phone_length",
        "UPDATE users SET phone = LEFT(phone, 20) WHERE phone IS NOT NULL AND LENGTH(phone) > 20",
    ),
    CleanupStep(
        "users.password_hash_length",
        "UPDATE users SET password_hash = LEFT(password_hash, 255) WHERE LENGTH(password_hash) > 255",
    ),
    CleanupStep(
        "users.role_length",
        "UPDATE users SET role = LEFT(role, 20) WHERE LENGTH(role) > 20",
    ),
    CleanupStep(
        "users.status_length",
        "UPDATE users SET status = LEFT(status, 20) WHERE LENGTH(status) > 20",
    ),
    CleanupStep(
        "users.avatar_url_length",
        "UPDATE users SET avatar_url = LEFT(avatar_url, 500) WHERE avatar_url IS NOT NULL AND LENGTH(avatar_url) > 500",
    ),
    CleanupStep(
        "user_profiles.age_range",
        "UPDATE user_profiles SET age = CASE WHEN age < 0 THEN 0 WHEN age > 120 THEN 120 ELSE age END WHERE age IS NOT NULL AND (age < 0 OR age > 120)",
    ),
    CleanupStep(
        "user_counselor_bindings.bind_code_length",
        "UPDATE user_counselor_bindings SET bind_code = LEFT(bind_code, 10) WHERE LENGTH(bind_code) > 10",
    ),
    CleanupStep(
        "warning_notifications.level_range",
        "UPDATE warning_notifications SET current_level = LEAST(GREATEST(current_level, 0), 10), previous_level = CASE WHEN previous_level IS NULL THEN NULL ELSE LEAST(GREATEST(previous_level, 0), 10) END WHERE current_level < 0 OR current_level > 10 OR previous_level < 0 OR previous_level > 10",
    ),
    CleanupStep(
        "warning_thresholds.level_scores",
        "UPDATE warning_thresholds SET min_score = LEAST(GREATEST(min_score, 0), 100), max_score = LEAST(GREATEST(max_score, 0), 100)",
    ),
    CleanupStep(
        "warning_thresholds.score_order",
        "UPDATE warning_thresholds SET max_score = min_score WHERE max_score < min_score",
    ),
    CleanupStep(
        "model_registry.metrics",
        "UPDATE model_registry SET accuracy = CASE WHEN accuracy IS NULL THEN NULL ELSE LEAST(GREATEST(accuracy, 0), 1) END, f1_score = CASE WHEN f1_score IS NULL THEN NULL ELSE LEAST(GREATEST(f1_score, 0), 1) END, latency_ms = CASE WHEN latency_ms IS NULL THEN NULL ELSE GREATEST(latency_ms, 0) END WHERE accuracy IS NOT NULL OR f1_score IS NOT NULL OR latency_ms IS NOT NULL",
    ),
    CleanupStep(
        "education_contents.numeric_fields",
        "UPDATE education_contents SET duration_minutes = CASE WHEN duration_minutes IS NULL THEN NULL ELSE GREATEST(duration_minutes, 0) END, sort_order = GREATEST(sort_order, 0), view_count = GREATEST(view_count, 0) WHERE duration_minutes IS NOT NULL OR sort_order < 0 OR view_count < 0",
    ),
    CleanupStep(
        "intervention_plans.risk_progress",
        "UPDATE intervention_plans SET risk_level = LEAST(GREATEST(risk_level, 0), 10), progress = LEAST(GREATEST(progress, 0), 100) WHERE risk_level < 0 OR risk_level > 10 OR progress < 0 OR progress > 100",
    ),
    CleanupStep(
        "intervention_tasks.numeric_fields",
        "UPDATE intervention_tasks SET duration_minutes = CASE WHEN duration_minutes IS NULL THEN NULL ELSE GREATEST(duration_minutes, 1) END, sort_order = GREATEST(sort_order, 0) WHERE (duration_minutes IS NOT NULL AND duration_minutes < 1) OR sort_order < 0",
    ),
    CleanupStep(
        "task_executions.feedback_score",
        "UPDATE task_executions SET feedback_score = CASE WHEN feedback_score IS NULL THEN NULL ELSE LEAST(GREATEST(feedback_score, 1), 5) END WHERE feedback_score IS NOT NULL AND (feedback_score < 1 OR feedback_score > 5)",
    ),
    CleanupStep(
        "intervention_templates.estimated_weeks",
        "UPDATE intervention_templates SET estimated_weeks = CASE WHEN estimated_weeks IS NULL THEN NULL ELSE LEAST(GREATEST(estimated_weeks, 1), 52) END WHERE estimated_weeks IS NOT NULL AND (estimated_weeks < 1 OR estimated_weeks > 52)",
    ),
    CleanupStep(
        "operation_logs.operator_role_length",
        "UPDATE operation_logs SET operator_role = LEFT(operator_role, 20) WHERE operator_role IS NOT NULL AND LENGTH(operator_role) > 20",
    ),
    CleanupStep(
        "operation_logs.action_type_length",
        "UPDATE operation_logs SET action_type = LEFT(action_type, 50) WHERE LENGTH(action_type) > 50",
    ),
    CleanupStep(
        "operation_logs.target_type_length",
        "UPDATE operation_logs SET target_type = LEFT(target_type, 50) WHERE target_type IS NOT NULL AND LENGTH(target_type) > 50",
    ),
    CleanupStep(
        "operation_logs.ip_address_length",
        "UPDATE operation_logs SET ip_address = LEFT(ip_address, 50) WHERE ip_address IS NOT NULL AND LENGTH(ip_address) > 50",
    ),
    CleanupStep(
        "data_drafts.draft_type_length",
        "UPDATE data_drafts SET draft_type = LEFT(draft_type, 50) WHERE LENGTH(draft_type) > 50",
    ),
    CleanupStep(
        "structured_assessments.assessment_type_length",
        "UPDATE structured_assessments SET assessment_type = LEFT(assessment_type, 50) WHERE LENGTH(assessment_type) > 50",
    ),
    CleanupStep(
        "physiological_records.source_length",
        "UPDATE physiological_records SET source = LEFT(source, 50) WHERE LENGTH(source) > 50",
    ),
)


async def _exec_step(session: AsyncSession, step: CleanupStep) -> int:
    result = await session.execute(text(step.sql))
    return int(getattr(result, "rowcount", 0) or 0)


async def cleanup(steps: Iterable[CleanupStep] = STEPS) -> None:
    engine = create_async_engine(settings.database_url, future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_maker() as session:
        for step in steps:
            count = await _exec_step(session, step)
            await session.commit()
            print(f"[cleanup] {step.name}: {count} row(s) updated")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(cleanup())
