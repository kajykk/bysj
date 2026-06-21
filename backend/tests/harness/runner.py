from __future__ import annotations

from pathlib import Path

from .core import HarnessRun, HarnessSuite
from .reporting import HarnessReporter


def execute_harness(suite: HarnessSuite, base_context: dict | None = None, output_dir: str | Path = "backend/test-artifacts") -> HarnessRun:
    run = suite.run(base_context)
    reporter = HarnessReporter(output_dir=output_dir)
    reporter.write_json(run)
    reporter.write_markdown(run)
    return run
