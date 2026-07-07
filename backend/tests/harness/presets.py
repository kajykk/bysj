from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import EducationContent
from app.models.intervention import InterventionPlan, InterventionTask, TaskExecution
from app.models.risk import RiskAssessment
from app.models.user import User
from tests.harness.core import HarnessScenario, HarnessSuite


@dataclass(slots=True)
class BackendHarnessContext:
    client: TestClient
    session: AsyncSession
    user_id: int
    auth_headers: dict[str, str]


class BackendHarnessFactory:
    def __init__(self, context: BackendHarnessContext) -> None:
        self.context = context

    def build(self) -> HarnessSuite:
        return HarnessSuite(
            scenarios=[
                HarnessScenario(
                    name="user-risk-report",
                    kind="integration",
                    setup=self._seed_risk_context,
                    execute=self._call_risk_report,
                ),
                HarnessScenario(
                    name="recommendation-explain",
                    kind="system",
                    setup=self._seed_recommendation_context,
                    execute=self._call_recommendations,
                ),
            ]
        )

    def _base_context(self) -> dict[str, Any]:
        return {
            "client": self.context.client,
            "session": self.context.session,
            "user_id": self.context.user_id,
            "auth_headers": self.context.auth_headers,
        }

    def _seed_risk_context(self, context: dict[str, Any]) -> dict[str, Any]:
        session: AsyncSession = context["session"]
        user_id = context["user_id"]
        user = User(
            id=user_id,
            username="harness_user",
            email="harness@test.com",
            password_hash="x",
            role="user",
            status="active",
        )
        session.add(user)
        session.add(
            RiskAssessment(
                user_id=user_id,
                risk_score=78,
                risk_level=3,
                structured_score=78,
                models_used=["harness"],
                risk_factors=[{"feature": "stress_level", "importance": 0.8}],
                assessment_type="structured",
            )
        )
        return {"expected_pass": True}

    def _seed_recommendation_context(self, context: dict[str, Any]) -> dict[str, Any]:
        session: AsyncSession = context["session"]
        session.add(
            EducationContent(
                title="联调-情绪舒缓练习",
                content_type="article",
                category="emotion",
                content="demo",
                summary="demo",
                status="active",
            )
        )
        return {"expected_pass": True}

    def _seed_intervention_context(self, context: dict[str, Any]) -> dict[str, Any]:
        session: AsyncSession = context["session"]
        user_id = context["user_id"]
        plan = InterventionPlan(
            user_id=user_id,
            plan_name="联调计划",
            risk_level=3,
            status="active",
            start_date=date.today(),
            end_date=date.today(),
        )
        session.add(plan)
        session.flush()
        task = InterventionTask(
            plan_id=plan.id,
            task_name="呼吸训练",
            task_type="meditation",
            description="demo",
            schedule="daily",
            duration_minutes=10,
            sort_order=0,
        )
        session.add(task)
        session.flush()
        session.add(
            TaskExecution(
                task_id=task.id,
                user_id=user_id,
                scheduled_date=date.today(),
                status="pending",
            )
        )
        context["task_id"] = task.id
        return {"expected_pass": True, "task_id": task.id}

    def _call_risk_report(self, context: dict[str, Any]) -> dict[str, Any]:
        client: TestClient = context["client"]
        response = client.get(
            "/api/v1/user/risk/report", headers=context["auth_headers"]
        )
        return {
            "passed": response.status_code == 200,
            "status_code": response.status_code,
            "response": response.json(),
        }

    def _call_recommendations(self, context: dict[str, Any]) -> dict[str, Any]:
        client: TestClient = context["client"]
        response = client.get(
            "/api/v1/user/content/recommendations", headers=context["auth_headers"]
        )
        payload = response.json()
        return {
            "passed": response.status_code == 200,
            "status_code": response.status_code,
            "response": payload,
        }

    def _call_task_flow(self, context: dict[str, Any]) -> dict[str, Any]:
        client: TestClient = context["client"]
        task_id = context["task_id"]
        complete = client.put(
            f"/api/v1/user/intervention/tasks/{task_id}/complete",
            headers=context["auth_headers"],
            json={"scheduled_date": date.today().isoformat()},
        )
        skip = client.put(
            f"/api/v1/user/intervention/tasks/{task_id}/skip",
            headers=context["auth_headers"],
            json={"scheduled_date": date.today().isoformat(), "note": "harness"},
        )
        return {
            "complete_status": complete.status_code,
            "skip_status": skip.status_code,
        }
