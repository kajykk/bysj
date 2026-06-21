import asyncio
import os
from datetime import date
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:12345678@localhost:5432/depression_system")

from app.main import app  # noqa: E402
from app.models.admin import EducationContent  # noqa: E402
from app.models.intervention import InterventionPlan, InterventionTask, TaskExecution  # noqa: E402
from app.models.risk import RiskAssessment  # noqa: E402
from app.models.user import User  # noqa: E402


async def prepare_user_data(user_id: int) -> int:
    engine = create_async_engine(os.environ["DATABASE_URL"], future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_maker() as db:
        risk = RiskAssessment(
            user_id=user_id,
            risk_score=72,
            risk_level=3,
            structured_score=72,
            models_used=["manual"],
            risk_factors=[{"feature": "stress_level", "importance": 0.7}],
            assessment_type="structured",
        )
        db.add(risk)

        content = EducationContent(
            title="情绪稳定练习",
            content_type="article",
            category="emotion",
            content="content",
            summary="summary",
            status="active",
        )
        db.add(content)

        plan = InterventionPlan(
            user_id=user_id,
            plan_name="自动冒烟计划",
            risk_level=3,
            status="active",
            start_date=date.today(),
            end_date=date.today(),
        )
        db.add(plan)
        await db.flush()

        task = InterventionTask(
            plan_id=plan.id,
            task_name="呼吸训练",
            task_type="meditation",
            description="desc",
            schedule="daily",
            duration_minutes=10,
            sort_order=0,
        )
        db.add(task)
        await db.flush()

        db.add(
            TaskExecution(
                task_id=task.id,
                user_id=user_id,
                scheduled_date=date.today(),
                status="pending",
            )
        )

        await db.commit()
        task_id = task.id

    await engine.dispose()
    return task_id


def run() -> None:
    client = TestClient(app)

    username = f"smoke_{uuid4().hex[:8]}"
    password = "Smoke@12345"
    email = f"{username}@test.com"

    reg = client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": email, "password": password, "role": "user"},
    )
    assert reg.status_code == 200, reg.text

    login = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200, login.text
    token = login.json()["data"]["access_token"]
    user_id = login.json()["data"]["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    task_id = asyncio.run(prepare_user_data(user_id))

    report = client.get("/api/v1/user/risk/report", headers=headers)
    trend = client.get("/api/v1/user/risk/trend?days=30", headers=headers)
    export_csv = client.get("/api/v1/user/risk/export?format=csv&days=30", headers=headers)

    complete = client.put(
        f"/api/v1/user/intervention/tasks/{task_id}/complete",
        json={"scheduled_date": date.today().isoformat()},
        headers=headers,
    )
    conflict = client.put(
        f"/api/v1/user/intervention/tasks/{task_id}/skip",
        json={"scheduled_date": date.today().isoformat(), "note": "after complete"},
        headers=headers,
    )

    rec = client.get("/api/v1/user/content/recommendations?page=1&page_size=10", headers=headers)

    assert report.status_code == 200, report.text
    assert trend.status_code == 200, trend.text
    assert export_csv.status_code == 200, export_csv.text
    assert "text/csv" in export_csv.headers.get("content-type", "")
    assert complete.status_code == 200, complete.text
    assert conflict.status_code == 409, conflict.text
    assert rec.status_code == 200, rec.text
    assert "explain" in rec.json()["data"], rec.text

    print(
        {
            "register": reg.status_code,
            "login": login.status_code,
            "risk_report": report.status_code,
            "risk_trend": trend.status_code,
            "risk_export_csv": export_csv.status_code,
            "task_complete": complete.status_code,
            "task_conflict": conflict.status_code,
            "recommendation": rec.status_code,
            "recommendation_has_explain": "explain" in rec.json()["data"],
            "csv_content_type": export_csv.headers.get("content-type"),
        }
    )


if __name__ == "__main__":
    run()
