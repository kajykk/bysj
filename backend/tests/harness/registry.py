from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any, Callable

from tests.harness.core import HarnessSuite

ScenarioFactory = Callable[[dict[str, Any]], HarnessSuite]


@dataclass(slots=True)
class HarnessRegistry:
    root_package: str = "tests.harness.scenarios"
    name_pattern: str = "scenario_*.py"
    factories: dict[str, ScenarioFactory] = field(default_factory=dict)

    def discover(self) -> dict[str, ScenarioFactory]:
        discovered: dict[str, ScenarioFactory] = dict(self.factories)
        try:
            package = import_module(self.root_package)
        except ModuleNotFoundError:
            return discovered

        package_path = Path(package.__file__).resolve().parent
        for file in sorted(package_path.glob(self.name_pattern)):
            if file.stem.startswith("_"):
                continue
            module = import_module(f"{self.root_package}.{file.stem}")
            factory = getattr(module, "build_suite", None)
            if callable(factory):
                scenario_name = file.stem.removeprefix("scenario_")
                discovered[scenario_name] = factory
        self.factories.update(discovered)
        return discovered

    def build(self, context: dict[str, Any]) -> HarnessSuite:
        suites = [factory(context) for factory in self.discover().values()]
        scenarios = [scenario for suite in suites for scenario in suite.scenarios]
        return HarnessSuite(scenarios=scenarios)
