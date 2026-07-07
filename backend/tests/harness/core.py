from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Protocol


@dataclass(slots=True)
class HarnessAssertion:
    name: str
    passed: bool
    message: str = ""


@dataclass(slots=True)
class HarnessStep:
    name: str
    status: str
    message: str = ""
    request_id: str | None = None
    snapshot: dict[str, Any] = field(default_factory=dict)


class ScenarioCallable(Protocol):
    def __call__(self, context: dict[str, Any]) -> dict[str, Any] | None: ...


@dataclass(slots=True)
class HarnessResult:
    name: str
    kind: str
    passed: bool
    duration_ms: float
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass(slots=True)
class HarnessRun:
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    results: list[HarnessResult] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        if self.finished_at is None:
            return 0.0
        return (self.finished_at - self.started_at).total_seconds() * 1000

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)


@dataclass(slots=True)
class HarnessScenario:
    name: str
    kind: str
    setup: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None
    execute: ScenarioCallable | None = None
    teardown: Callable[[dict[str, Any]], None] | None = None

    def run(self, context: dict[str, Any]) -> HarnessResult:
        start = datetime.now(timezone.utc)
        try:
            if self.setup is not None:
                setup_result = self.setup(context)
                if setup_result:
                    context.update(setup_result)
            output = self.execute(context) if self.execute is not None else None
            if output:
                context.update(output)
            assertions = (
                output.get("assertions", []) if isinstance(output, dict) else []
            )
            steps = output.get("steps", []) if isinstance(output, dict) else []
            passed = (
                all(assertion.passed for assertion in assertions)
                if assertions
                else bool(
                    output.get("passed", context.get("expected_pass", True))
                    if isinstance(output, dict)
                    else context.get("expected_pass", True)
                )
            )
            if assertions and not passed:
                passed = all(
                    getattr(assertion, "passed", False) for assertion in assertions
                )
            details = {
                "output": output or {},
                "context": {k: v for k, v in context.items() if k != "client"},
                "assertions": [
                    {
                        "name": assertion.name,
                        "passed": assertion.passed,
                        "message": assertion.message,
                    }
                    for assertion in assertions
                ],
                "steps": [
                    {
                        "name": step.name,
                        "status": step.status,
                        "message": step.message,
                        "request_id": step.request_id,
                        "snapshot": step.snapshot,
                    }
                    for step in steps
                ],
            }
            return HarnessResult(
                name=self.name,
                kind=self.kind,
                passed=passed,
                duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
                details=details,
            )
        except Exception as exc:  # pragma: no cover - harness capture path
            return HarnessResult(
                name=self.name,
                kind=self.kind,
                passed=False,
                duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
                error=str(exc),
                details={
                    "context": {k: v for k, v in context.items() if k != "client"}
                },
            )
        finally:
            if self.teardown is not None:
                self.teardown(context)


@dataclass(slots=True)
class HarnessSuite:
    scenarios: list[HarnessScenario]

    def run(self, base_context: dict[str, Any] | None = None) -> HarnessRun:
        context = dict(base_context or {})
        run = HarnessRun()
        for scenario in self.scenarios:
            run.results.append(scenario.run(context.copy()))
        run.finished_at = datetime.now(timezone.utc)
        return run
