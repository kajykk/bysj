from __future__ import annotations

import json
from pathlib import Path

from .core import HarnessRun


class HarnessReporter:
    def __init__(self, output_dir: str | Path = "backend/test-artifacts") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _safe_value(self, value, seen: set[int] | None = None):
        if seen is None:
            seen = set()
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, dict):
            return {
                str(k): self._safe_value(v, seen)
                for k, v in value.items()
                if k != "client" and k != "session"
            }
        if isinstance(value, (list, tuple)):
            return [self._safe_value(item, seen) for item in value]
        if hasattr(value, "model_dump"):
            try:
                data = value.model_dump()
            except Exception:
                data = None
            if isinstance(data, dict):
                return {k: self._safe_value(v, seen) for k, v in data.items()}
        if hasattr(value, "__class__"):
            class_name = value.__class__.__name__
            module_name = value.__class__.__module__
            if module_name.startswith(("sqlalchemy", "torch", "tensorflow", "keras")):
                return f"<{module_name}.{class_name}>"
        return str(value)

    def write_json(self, run: HarnessRun, name: str = "harness-report.json") -> Path:
        path = self.output_dir / name
        payload = {
            "summary": {
                "passed": run.passed,
                "duration_ms": run.duration_ms,
                "result_count": len(run.results),
            },
            "results": [
                {
                    "name": result.name,
                    "kind": result.kind,
                    "passed": result.passed,
                    "duration_ms": result.duration_ms,
                    "error": result.error,
                    "details": self._safe_value(result.details),
                }
                for result in run.results
            ],
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return path

    def write_markdown(self, run: HarnessRun, name: str = "harness-report.md") -> Path:
        path = self.output_dir / name
        lines = [
            "# Harness Report",
            "",
            f"- Passed: {'yes' if run.passed else 'no'}",
            f"- Duration: {run.duration_ms:.2f} ms",
            f"- Scenarios: {len(run.results)}",
            "",
            "| Scenario | Kind | Passed | Duration (ms) | Request IDs |",
            "| --- | --- | --- | ---: | --- |",
        ]
        for result in run.results:
            steps = (
                result.details.get("steps", [])
                if isinstance(result.details, dict)
                else []
            )
            request_ids = (
                ", ".join(
                    sorted(
                        {
                            step.get("request_id")
                            for step in steps
                            if isinstance(step, dict) and step.get("request_id")
                        }
                    )
                )
                or "-"
            )
            lines.append(
                f"| {result.name} | {result.kind} | {'yes' if result.passed else 'no'} | {result.duration_ms:.2f} | {request_ids} |"
            )
            if steps:
                lines.append("")
                lines.append(f"### {result.name} steps")
                lines.append("")
                lines.append("| Step | Status | Request ID | Message |")
                lines.append("| --- | --- | --- | --- |")
                for step in steps:
                    lines.append(
                        f"| {step.get('name', '-') } | {step.get('status', '-') } | {step.get('request_id', '-') or '-'} | {step.get('message', '-') or '-'} |"
                    )
        path.write_text("\n".join(lines), encoding="utf-8")
        return path
