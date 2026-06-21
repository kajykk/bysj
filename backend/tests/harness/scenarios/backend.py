from __future__ import annotations

from tests.harness.presets import BackendHarnessFactory
from tests.harness.core import HarnessSuite


def build_suite(context) -> HarnessSuite:
    return BackendHarnessFactory(context).build()
