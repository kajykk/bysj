# Test Overview

_Last generated: 2026-04-16 21:47:34Z_

## Summary

| Area | Status | Report | Notes |
| --- | --- | --- | --- |
| Backend pytest/harness | Passed | [backend harness markdown](../backend/test-artifacts/harness-report.md) / [backend harness json](../backend/test-artifacts/harness-report.json) | Backend harness integration summary from pytest. |
| Playwright E2E | Configured | [playwright report](../frontend/playwright-report) | Playwright HTML report and per-role JSON artifacts are available. |

## Coverage Snapshot

| Scenario | Coverage | Key files | Gap | Reports |
| --- | --- | --- | --- | --- |
| S1 Auth & login | Covered | `backend/tests/api/test_auth_flow.py`, `frontend/e2e/role-user.spec.ts` | Need token refresh/expiry full UI | `backend/test-artifacts/harness-report.md`, `frontend/playwright-report` |
| S2 Route guard & permissions | Covered | `backend/tests/api/test_routing_and_security_p0p1.py`, `frontend/e2e/role-counselor.spec.ts` | Need button-level permission checks | `backend/test-artifacts/harness-report.md`, `frontend/playwright-report` |
| S3 Risk report | Covered | `backend/tests/api/test_risk_export.py`, `backend/tests/harness/scenarios/scenario_backend_smoke.py` | Need richer failure snapshots | `backend/test-artifacts/harness-report.md`, `frontend/playwright-report` |
| S4 Input & recommendation chain | Covered | `backend/tests/api/test_content_recommendation.py`, `frontend/e2e/role-user.spec.ts` | Need UI validation for malformed input | `backend/test-artifacts/harness-report.md`, `frontend/playwright-report` |
| S5 Intervention task flow | Covered | `backend/tests/api/test_intervention_state_machine.py`, `backend/tests/test_harness_integration.py` | Need more conflict paths in E2E | `backend/test-artifacts/harness-report.md`, `frontend/playwright-report` |
| S6 Counselor workspace | Covered | `backend/tests/api/test_counselor_admin.py`, `frontend/e2e/role-counselor.spec.ts` | Need real consultation forms | `backend/test-artifacts/harness-report.md`, `frontend/playwright-report` |
| S7 Admin console | Covered | `backend/tests/api/test_health_and_admin_logs.py`, `frontend/e2e/role-admin.spec.ts` | Need settings/template edit flows | `backend/test-artifacts/harness-report.md`, `frontend/playwright-report` |
| S8 Observability/audit | Covered | `backend/tests/api/test_request_id_audit.py`, `backend/tests/harness/reporting.py` | Need unified cross-link index | `backend/test-artifacts/harness-report.md`, `frontend/playwright-report` |

## Failure Summary

- No backend harness failures recorded in the latest report.

## Report Links

- Backend markdown report: [harness-report.md](../backend/test-artifacts/harness-report.md)
- Backend JSON report: [harness-report.json](../backend/test-artifacts/harness-report.json)
- Playwright report folder: [playwright-report](../frontend/playwright-report)
- Playwright user report JSON: [role-user-report.json](../frontend/playwright-report/role-user-report.json)
- Playwright counselor report JSON: [role-counselor-report.json](../frontend/playwright-report/role-counselor-report.json)
- Playwright admin report JSON: [role-admin-report.json](../frontend/playwright-report/role-admin-report.json)

## Notes

- User / counselor / admin Playwright flows should prefer real UI routes, form fields, and button-driven transitions.
- The backend harness report intentionally keeps only lightweight context and step snapshots for easier triage.
- This file is a template. Regenerate it after test runs to refresh coverage, links, and failure summaries.
