from __future__ import annotations

from tests.harness.core import HarnessAssertion, HarnessScenario, HarnessSuite
from tests.harness.reporting import HarnessReporter


def test_harness_suite_collects_results() -> None:
    suite = HarnessSuite(
        scenarios=[
            HarnessScenario(
                name="pass",
                kind="unit",
                execute=lambda _: {"assertions": [HarnessAssertion(name="truthy", passed=True)]},
            ),
            HarnessScenario(
                name="fail",
                kind="integration",
                execute=lambda _: {"assertions": [HarnessAssertion(name="falsey", passed=False)]},
            ),
        ]
    )

    run = suite.run({"expected_pass": True})

    assert len(run.results) == 2
    assert run.results[0].passed is True
    assert run.results[1].passed is False
    assert run.passed is False


def test_harness_reporter_writes_outputs(tmp_path) -> None:
    suite = HarnessSuite([HarnessScenario(name="pass", kind="unit", execute=lambda _: None)])
    run = suite.run({"expected_pass": True})
    reporter = HarnessReporter(output_dir=tmp_path)

    json_path = reporter.write_json(run)
    md_path = reporter.write_markdown(run)

    assert json_path.exists()
    assert md_path.exists()
