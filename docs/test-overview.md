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

## 本地测试环境（Windows）

### Windows libmagic

`tests/api` 中与上传相关的用例（`test_upload_security.py`、`test_user_upload.py`、
`test_uploads_auth.py`）依赖 `python-magic` 做 MIME 探测。Windows 上它需要
`site-packages/magic/libmagic/` 下的 `libmagic.dll` 与 `magic.mgc` 两个文件，
宿主 PATH 里没有这个目录时 `import magic` 会失败、上传接口会 fail-closed 返回 503。

1. 安装（开发依赖，不要写进 `requirements.txt`）：

   ```powershell
   backend\.venv\Scripts\python -m pip install "python-magic==0.4.27" "python-magic-bin==0.4.14"
   ```

2. 确认文件存在：

   ```powershell
   Get-ChildItem backend\.venv\Lib\site-packages\magic\libmagic
   # 期望看到 libmagic.dll / magic.mgc
   ```

3. 无需手工配置：`backend/tests/conftest.py` 会在导入 `app` 之前自动探测上述目录，
   并注入 `PATH` 与 `MAGIC`。若需要手工排查，可等价设置：

   ```powershell
   $env:PATH  = "E:\code\bysj\backend\.venv\Lib\site-packages\magic\libmagic;" + $env:PATH
   $env:MAGIC = "E:\code\bysj\backend\.venv\Lib\site-packages\magic\libmagic\magic.mgc"
   ```

4. 找不到 libmagic 时，上传类用例会在 collection 阶段被 **SKIP** 并打印原因
   （`libmagic 不可用（未找到 magic/libmagic/magic.mgc）…`），不会以 503 误判为业务失败。
   Linux/CI 上改用系统包（Debian/Ubuntu: `apt-get install libmagic1`）。

### 测试超时熔断

`pytest.ini` 配置了 `timeout = 120` / `timeout_method = thread`，依赖
`requirements-dev.txt` 中的 `pytest-timeout`。若未安装该插件，pytest 只会告警
`Unknown config option: timeout` 并静默忽略超时配置，整套测试可能在慢网络/外部
依赖处挂起。装完可用 `python -m pytest --version` 或启动日志确认插件已加载。

## Notes

- User / counselor / admin Playwright flows should prefer real UI routes, form fields, and button-driven transitions.
- The backend harness report intentionally keeps only lightweight context and step snapshots for easier triage.
- This file is a template. Regenerate it after test runs to refresh coverage, links, and failure summaries.
