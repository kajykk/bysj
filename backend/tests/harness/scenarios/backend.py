from __future__ import annotations

from tests.harness.core import HarnessSuite
from tests.harness.presets import BackendHarnessFactory


def build_suite(context) -> HarnessSuite:
    return BackendHarnessFactory(context).build()
