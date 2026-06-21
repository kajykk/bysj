from __future__ import annotations

import pytest

from tests.harness.registry import HarnessRegistry
from tests.harness.runner import execute_harness


@pytest.mark.integration
def test_backend_harness_suite_runs(client, db_session, seeded_user_id) -> None:
    context = {
        "client": client,
        "session": db_session,
        "user_id": seeded_user_id,
        "auth_headers": {"Authorization": "Bearer test-token"},
    }
    suite = HarnessRegistry().build(context)

    run = execute_harness(suite, context, output_dir="backend/test-artifacts")

    assert run.results
    assert run.passed is True
