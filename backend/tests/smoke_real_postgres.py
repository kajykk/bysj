from __future__ import annotations

import asyncio
import os
import time
from datetime import date

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:12345678@localhost:5432/depression_system")

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.core.database import AsyncSessionLocal
from app.models import EducationContent, InterventionPlan, InterventionTask, RiskAssessment, TaskExecution, User

import pytest

pytestmark = [pytest.mark.requires_external, pytest.mark.integration]


async def prepare_user_data(username: str) -> tuple[int, int]:
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.username == username))).scalar_one()

        # risk data for report/recommendation
        db.add(
            RiskAssessment(
                user_id=user.id,
                risk_score=66,
                risk_level=3,
                structured_score=66,
                models_used=["smoke"],
                risk_factors=[{"feature": "stress_level", "importance": 0.7}],
