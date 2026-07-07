from __future__ import annotations

import asyncio
from datetime import date
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import EducationContent
from app.models.intervention import InterventionPlan, InterventionTask, TaskExecution
from app.models.risk import RiskAssessment
from tests.harness.core import (
    HarnessAssertion,
    HarnessScenario,
    HarnessStep,
    HarnessSuite,
)


def build_suite(_: dict[str, Any]) -> HarnessSuite:
    return HarnessSuite(
        scenarios=[
            HarnessScenario(
                name="risk-report",
                kind="integration",
                setup=_seed_risk,
                execute=_call_risk_report,
            ),
            HarnessScenario(
                name="recommendations",
                kind="system",
                setup=_seed_recommendations,
                execute=_call_recommendations,
            ),
            HarnessScenario(
                name="task-flow",
                kind="system",
                setup=_seed_task_flow,
                execute=_call_task_flow,
            ),
        ]
    )


def _seed_risk(context: dict[str, Any]) -> dict[str, Any]:
    session: AsyncSession = context["session"]
    user_id = context["user_id"]
    request_id = f"req-{uuid4().hex[:12]}"
    session.add(
        RiskAssessment(
            user_id=user_id,
            risk_score=78,
            risk_level=3,
            structured_score=78,
            models_used=["harness"],
            risk_factors=[],
            assessment_type="structured",
        )
    )
    asyncio.run(session.flush())
    return {
        "expected_pass": True,
        "request_id": request_id,
        "snapshots": {"seed": {"user_id": user_id, "risk_level": 3}},
    }


def _seed_recommendations(context: dict[str, Any]) -> dict[str, Any]:
    session: AsyncSession = context["session"]
    session.add(
        EducationContent(
            title="harness",
            content_type="article",
            category="emotion",
            content="demo",
            summary="demo",
            status="active",
        )
    )
    asyncio.run(session.flush())
    return {
        "expected_pass": True,
        "snapshots": {"seed": {"content_type": "article", "category": "emotion"}},
    }


def _seed_task_flow(context: dict[str, Any]) -> dict[str, Any]:
    session: AsyncSession = context["session"]
    user_id = context["user_id"]
    request_id = f"req-{uuid4().hex[:12]}"

    async def _seed() -> dict[str, Any]:
        plan = InterventionPlan(
            user_id=user_id,
            plan_name="harness",
            risk_level=3,
            status="active",
            start_date=date.today(),
            end_date=date.today(),
        )
        session.add(plan)
        await session.flush()
        task = InterventionTask(
            plan_id=plan.id,
            task_name="breathing",
            task_type="meditation",
            description="demo",
            schedule="daily",
            duration_minutes=10,
            sort_order=0,
        )
        session.add(task)
        await session.flush()
        task_execution = TaskExecution(
            task_id=task.id,
            user_id=user_id,
            scheduled_date=date.today(),
            status="pending",
        )
        session.add(task_execution)
        await session.flush()
        return {
            "task_id": task.id,
            "request_id": request_id,
            "snapshots": {
                "task": {
                    "plan_id": plan.id,
                    "task_id": task.id,
                    "status": task_execution.status,
                }
            },
        }

    return asyncio.run(_seed())


def _call_risk_report(context: dict[str, Any]) -> dict[str, Any]:
    client: TestClient = context["client"]
    response = client.get(
        "/api/v1/user/risk/report",
        headers={
            **context["auth_headers"],
            "X-Request-Id": context.get("request_id", ""),
        },
    )
    assertions = [
        HarnessAssertion(name="risk-report-status", passed=response.status_code == 200)
    ]
    steps = [
        HarnessStep(
            name="request",
            status="passed",
            request_id=context.get("request_id"),
            snapshot={
                "path": "/api/v1/user/risk/report",
                "status_code": response.status_code,
            },
        )
    ]
    return {
        "assertions": assertions,
        "steps": steps,
        "status_code": response.status_code,
        "response": response.json(),
    }


def _call_recommendations(context: dict[str, Any]) -> dict[str, Any]:
    client: TestClient = context["client"]
    response = client.get(
        "/api/v1/user/content/recommendations",
        headers={
            **context["auth_headers"],
            "X-Request-Id": context.get("request_id", ""),
        },
    )
    assertions = [
        HarnessAssertion(
            name="recommendations-status", passed=response.status_code == 200
        )
    ]
    steps = [
        HarnessStep(
            name="request",
            status="passed",
            request_id=context.get("request_id"),
            snapshot={
                "path": "/api/v1/user/content/recommendations",
                "status_code": response.status_code,
            },
        )
    ]
    return {
        "assertions": assertions,
        "steps": steps,
        "status_code": response.status_code,
        "response": response.json(),
    }


def _call_task_flow(context: dict[str, Any]) -> dict[str, Any]:
    client: TestClient = context["client"]
    task_id = context["task_id"]
    request_id = context.get("request_id", f"req-{uuid4().hex[:12]}")
    complete = client.put(
        f"/api/v1/user/intervention/tasks/{task_id}/complete",
        headers={**context["auth_headers"], "X-Request-Id": request_id},
        json={"scheduled_date": date.today().isoformat()},
    )
    skip = client.put(
        f"/api/v1/user/intervention/tasks/{task_id}/skip",
        headers={**context["auth_headers"], "X-Request-Id": request_id},
        json={"scheduled_date": date.today().isoformat(), "note": "harness"},
    )
    assertions = [
        HarnessAssertion(name="complete-status", passed=complete.status_code == 200),
        HarnessAssertion(name="skip-conflict", passed=skip.status_code == 409),
    ]
    steps = [
        HarnessStep(
            name="complete",
            status="passed" if complete.status_code == 200 else "failed",
            request_id=request_id,
            snapshot={"task_id": task_id, "status_code": complete.status_code},
        ),
        HarnessStep(
            name="skip",
            status="passed" if skip.status_code == 409 else "failed",
            request_id=request_id,
            snapshot={"task_id": task_id, "status_code": skip.status_code},
        ),
    ]
    return {
        "assertions": assertions,
        "steps": steps,
        "complete_status": complete.status_code,
        "skip_status": skip.status_code,
        "request_id": request_id,
    }
