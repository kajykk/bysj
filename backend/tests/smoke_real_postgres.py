"""Smoke test against a real PostgreSQL instance.

This test requires an external PostgreSQL database and is skipped by default.
Set DATABASE_URL env var to point to a real PostgreSQL instance to run.
"""

from __future__ import annotations

import asyncio
import os
from datetime import date

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:12345678@localhost:5432/depression_system",
)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.main import app
from app.models import (
    InterventionPlan,
    InterventionTask,
    RiskAssessment,
    TaskExecution,
    User,
)

pytestmark = [pytest.mark.requires_external, pytest.mark.integration]


async def prepare_user_data(username: str) -> tuple[int, int]:
    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.username == username))
        ).scalar_one()

        # risk data for report/recommendation
        db.add(
            RiskAssessment(
                user_id=user.id,
                risk_score=66,
                risk_level=3,
                structured_score=66,
                models_used=["smoke"],
                risk_factors=[{"feature": "stress_level", "importance": 0.7}],
                created_at=date(2024, 1, 1),
            )
        )
        await db.flush()

        # intervention plan + task
        plan = InterventionPlan(
            user_id=user.id,
            title="Smoke test plan",
            description="plan from smoke test",
            status="active",
        )
        db.add(plan)
        await db.flush()

        task = InterventionTask(
            plan_id=plan.id,
            title="Smoke test task",
            description="task from smoke test",
            status="pending",
        )
        db.add(task)
        await db.flush()

        execution = TaskExecution(
            task_id=task.id,
            user_id=user.id,
            status="completed",
        )
        db.add(execution)
        await db.commit()
        return user.id, plan.id


@pytest.mark.skip(
    reason="Requires external PostgreSQL; run manually with DATABASE_URL set"
)
def test_smoke_real_postgres():
    """Smoke test: verify app boots and basic CRUD works against real PostgreSQL."""
    client = TestClient(app)
    resp = client.get("/api/v1/version")
    assert resp.status_code == 200

    asyncio.run(prepare_user_data("testuser_smoke"))
