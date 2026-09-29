from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / 'docs' / 'test-overview.md'
BACKEND_MD = ROOT / 'backend' / 'test-artifacts' / 'harness-report.md'
BACKEND_JSON = ROOT / 'backend' / 'test-artifacts' / 'harness-report.json'
PLAYWRIGHT_DIR = ROOT / 'frontend' / 'playwright-report'
SEED_REPORT_JSON = PLAYWRIGHT_DIR / 'seed-report.json'


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def backend_status() -> tuple[str, str, str]:
    if BACKEND_MD.exists() and BACKEND_JSON.exists():
        data = read_json(BACKEND_JSON)
        passed = data.get('summary', {}).get('passed')
        return ('Passed' if passed else 'Failed', '../backend/test-artifacts/harness-report.md', 'Backend harness integration summary from pytest.')
    return ('Unknown', '../backend/test-artifacts/harness-report.md', 'Backend harness reports not found yet.')


def playwright_status() -> tuple[str, str, str]:
    if PLAYWRIGHT_DIR.exists():
        return ('Configured', '../frontend/playwright-report', 'Playwright HTML report and per-role JSON artifacts are available.')
    return ('Missing', '../frontend/playwright-report', 'Playwright report folder is missing.')


def seed_status() -> tuple[str, str, str]:
    if not SEED_REPORT_JSON.exists():
        return ('Unknown', '../frontend/playwright-report/seed-report.json', 'Seed report has not been generated yet.')
    data = read_json(SEED_REPORT_JSON)
    checks = data.get('checks', [])
    if not checks:
        return ('Unknown', '../frontend/playwright-report/seed-report.json', 'Seed report is empty.')
    passed = all(check.get('passed') for check in checks)
    failing = [check for check in checks if not check.get('passed')]
    if passed:
        return ('Passed', '../frontend/playwright-report/seed-report.json', 'All seed login checks passed.')
    detail = '; '.join(f"{item.get('username')}: {item.get('detail') or 'login failed'}" for item in failing)
    return ('Failed', '../frontend/playwright-report/seed-report.json', f'Seed login failures: {detail}')


def failure_summary() -> str:
    backend = read_json(BACKEND_JSON)
    results = backend.get('results', [])
    failing = [r for r in results if not r.get('passed')]
    if not failing:
        return '- No backend harness failures recorded in the latest report.'
    lines = []
    for item in failing[:10]:
        lines.append(f"- {item.get('name', 'unknown')}: {item.get('error') or 'assertion failed'}")
    return '\n'.join(lines)


def scenario_rows() -> str:
    rows = [
        ('S1 Auth & login', 'Covered', ['backend/tests/api/test_auth_flow.py', 'frontend/e2e/role-user.spec.ts'], 'Need token refresh/expiry full UI'),
        ('S2 Route guard & permissions', 'Covered', ['backend/tests/api/test_routing_and_security_p0p1.py', 'frontend/e2e/role-counselor.spec.ts'], 'Need button-level permission checks'),
        ('S3 Risk report', 'Covered', ['backend/tests/api/test_risk_export.py', 'backend/tests/harness/scenarios/scenario_backend_smoke.py'], 'Need richer failure snapshots'),
        ('S4 Input & recommendation chain', 'Covered', ['backend/tests/api/test_content_recommendation.py', 'frontend/e2e/role-user.spec.ts'], 'Need UI validation for malformed input'),
        ('S5 Intervention task flow', 'Covered', ['backend/tests/api/test_intervention_state_machine.py', 'backend/tests/test_harness_integration.py'], 'Need more conflict paths in E2E'),
        ('S6 Counselor workspace', 'Covered', ['backend/tests/api/test_counselor_admin.py', 'frontend/e2e/role-counselor.spec.ts'], 'Need real consultation forms'),
        ('S7 Admin console', 'Covered', ['backend/tests/api/test_health_and_admin_logs.py', 'frontend/e2e/role-admin.spec.ts'], 'Need settings/template edit flows'),
        ('S8 Observability/audit', 'Covered', ['backend/tests/api/test_request_id_audit.py', 'backend/tests/harness/reporting.py'], 'Need unified cross-link index'),
    ]
    rendered = []
    for scenario, coverage, files, gap in rows:
        rendered.append(
            f"| {scenario} | {coverage} | {', '.join(f'`{f}`' for f in files)} | {gap} | `backend/test-artifacts/harness-report.md`, `frontend/playwright-report` |"
        )
    return '\n'.join(rendered)


def render() -> str:
    template = DOC.read_text(encoding='utf-8')
    backend_state, backend_link, backend_note = backend_status()
    playwright_state, playwright_link, playwright_note = playwright_status()
    template = template.replace('{{generated_at}}', datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ'))
    template = template.replace('{{backend_status}}', backend_state)
    template = template.replace('{{backend_report_md}}', backend_link)
    template = template.replace('{{backend_report_json}}', '../backend/test-artifacts/harness-report.json')
    template = template.replace('{{backend_note}}', backend_note)
    seed_state, seed_link, seed_note = seed_status()
    template = template.replace('{{playwright_status}}', playwright_state)
    template = template.replace('{{playwright_report_dir}}', playwright_link)
    template = template.replace('{{playwright_note}}', playwright_note)
    template = template.replace('{{seed_status}}', seed_state)
    template = template.replace('{{seed_report_json}}', seed_link)
    template = template.replace('{{seed_note}}', seed_note)
    template = template.replace('{{coverage_rows}}', scenario_rows())
    template = template.replace('{{failure_summary}}', failure_summary())
    template = template.replace('{{backend_report_md_name}}', 'harness-report.md')
    template = template.replace('{{backend_report_json_name}}', 'harness-report.json')
    template = template.replace('{{playwright_report_dir_name}}', 'playwright-report')
    template = template.replace('{{playwright_result_links}}', '- Playwright user report JSON: [role-user-report.json](../frontend/playwright-report/role-user-report.json)\n- Playwright counselor report JSON: [role-counselor-report.json](../frontend/playwright-report/role-counselor-report.json)\n- Playwright admin report JSON: [role-admin-report.json](../frontend/playwright-report/role-admin-report.json)')
    return template


def main() -> None:
    DOC.write_text(render(), encoding='utf-8')


if __name__ == '__main__':
    main()
