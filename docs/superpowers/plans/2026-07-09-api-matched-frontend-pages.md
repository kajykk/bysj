# API-Matched Frontend Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers- (recommended) or superpowers- to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build frontend pages for user, counselor, and admin flows that match the backend OpenAPI contract for all required interactions, data displays, and submissions.

**Architecture:** Keep the existing Vue 3 + Element Plus app structure, but make each role page a thin composition layer over the shared API adapters. Pages should own only UI state, validation, and orchestration; API modules should own request shapes and response typing; i18n should own all visible copy. Where the current page already exists, replace placeholder or partial behavior with contract-aligned data loading and mutation flows rather than adding parallel implementations.

**Tech Stack:** Vue 3, TypeScript, Vue Router, Pinia, Element Plus, vue-i18n, existing `frontend/src/api/*` adapters, ECharts where already used.

## Global Constraints

- Match backend OpenAPI request parameters and response shapes exactly for all implemented actions.
- Use the existing `frontend/src/api/*` request wrapper and typed adapter pattern.
- Preserve the current role-based routing and navigation structure.
- Show explicit loading, empty, success, and error states for all network-backed UI.
- Keep changes focused to the relevant page, API adapter, and locale files for each flow.
- Do not introduce mock-only behavior in the final implementation.

---

### Task 1: Align and complete the user dashboard data flow

**Files:**
- Modify: `frontend/src/views/user/UserDashboard.vue`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/en-US.ts`

**Interfaces:**
- Consumes: `userApi.getRiskReport()`, `userApi.getRiskTrend(days)`, `userApi.getActiveIntervention()`, `userApi.getUserWarnings({ page, page_size, is_read })`, `userApi.getDataHistory({ page, page_size })`
- Produces: dashboard sections for risk overview, latest assessment, intervention, trend, and unread warnings with matching loading/error states

- [ ] **Step 1: Verify the dashboard loads all five backend-backed sections from the existing adapters**

- [ ] **Step 2: Fix any duplicate or inconsistent dashboard orchestration so each request is owned by one loader and partial failures are surfaced once**

- [ ] **Step 3: Expand locale strings so the dashboard copy covers all loading, empty, and CTA states in both languages**

- [ ] **Step 4: Run the relevant frontend tests or lint target for the dashboard page and confirm it renders without diagnostics**

### Task 2: Make the user risk page submit and display contract-aligned assessment results

**Files:**
- Modify: `frontend/src/views/user/UserRiskPage.vue`
- Modify: `frontend/src/api/userRiskApi.ts`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/en-US.ts`

**Interfaces:**
- Consumes: `userApi.collectStructuredData(payload)`, `userApi.analyzeText(payload)`, `userApi.recordPhysiological(payload)`, `userApi.getRiskReport()`, `userApi.getRiskTrend(days)`, `userApi.getAssessmentDetail(id)`
- Produces: assessment forms, submission results, risk summary cards, and record detail panels that mirror backend fields

- [ ] **Step 1: Map each assessment entry form to the exact request payload required by the matching OpenAPI endpoint**

- [ ] **Step 2: Render backend response fields such as `risk_score`, `risk_level`, `severity`, `warning_generated`, and `warning_id` directly in the result view**

- [ ] **Step 3: Add or adjust any API adapter helper needed to normalize optional fields without changing the backend contract**

- [ ] **Step 4: Validate the page with lint/tests and confirm form submission, result rendering, and error handling work end-to-end**

### Task 3: Complete the user warnings and warning settings pages

**Files:**
- Modify: `frontend/src/views/user/UserWarningsPage.vue`
- Modify: `frontend/src/views/user/UserSettingsPage.vue`
- Modify: `frontend/src/api/userWarningsApi.ts`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/en-US.ts`

**Interfaces:**
- Consumes: `userApi.getUserWarnings()`, `userApi.markUserWarningRead(warningId)`, `userApi.markAllWarningsRead()`, `userApi.getWarningSettings()`, `userApi.updateWarningSettings(payload)`
- Produces: warning list actions, unread/read state changes, and editable notification preference forms

- [ ] **Step 1: Ensure warning list actions call the read and read-all endpoints with the correct IDs and refresh behavior**

- [ ] **Step 2: Make the warning settings form submit the exact backend payload shape, including quiet hours and notification channels**

- [ ] **Step 3: Add localized feedback strings for save, success, empty, and error states**

- [ ] **Step 4: Run targeted checks for the warnings flow and verify API mutations update the UI correctly**

### Task 4: Complete the user intervention pages and task mutation flows

**Files:**
- Modify: `frontend/src/views/user/UserInterventionPage.vue`
- Modify: `frontend/src/api/userInterventionApi.ts`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/en-US.ts`

**Interfaces:**
- Consumes: `userApi.getActiveIntervention()`, `userApi.getInterventionHistory()`, `userApi.completeInterventionTask(taskId, scheduledDate)`, `userApi.feedbackInterventionTask(taskId, payload)`, `userApi.skipInterventionTask(taskId, payload)`, `userApi.markInterventionTaskMissed(taskId, payload)`, `userApi.postponeInterventionTask(taskId, payload)`
- Produces: active plan cards, task list actions, feedback dialogs, and history tables

- [ ] **Step 1: Wire the task action buttons and dialogs to the exact backend mutation signatures**

- [ ] **Step 2: Show updated task status, feedback, and progress after each mutation succeeds**

- [ ] **Step 3: Add history pagination and empty/error states aligned to the API response shape**

- [ ] **Step 4: Run checks for the intervention flow and confirm mutation-driven refreshes behave correctly**

### Task 5: Complete reports pages for the user role and align shared report entry points

**Files:**
- Modify: `frontend/src/views/user/UserReportsPage.vue`
- Modify: `frontend/src/layouts/MainLayout.vue`
- Modify: `frontend/src/router/index.ts` only if a route label or alias needs correction
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/en-US.ts`

**Interfaces:**
- Consumes: existing report-related API adapters already exported through `userApi`
- Produces: report listing / download entry points with correct navigation and user-facing status feedback

- [ ] **Step 1: Verify the report page uses the correct API adapters and response fields for listing and download actions**

- [ ] **Step 2: Align navigation labels, route titles, and page copy with the actual available user report flow**

- [ ] **Step 3: Confirm the report page handles empty states, async job states, and failure states cleanly**

- [ ] **Step 4: Run a final smoke test across the user role pages and confirm no regressions in navigation**

### Task 6: Fill out counselor and admin dashboards with contract-backed summary data

**Files:**
- Modify: `frontend/src/views/counselor/CounselorDashboard.vue`
- Modify: `frontend/src/views/admin/AdminDashboard.vue`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/en-US.ts`

**Interfaces:**
- Consumes: role-appropriate API modules already present in `frontend/src/api/*` and exported through the role pages
- Produces: role dashboards with meaningful summary cards, shortcuts, and data tables that match the currently exposed backend capabilities

- [ ] **Step 1: Inspect the existing counselor and admin pages and replace placeholders with actual API-backed panels**

- [ ] **Step 2: Keep each dashboard focused on the data that the corresponding role can actually act on**

- [ ] **Step 3: Add localized empty, loading, and action copy for both dashboards**

- [ ] **Step 4: Run lint/tests for both dashboards and confirm their routes render successfully**

### Task 7: Final verification and cleanup

**Files:**
- Modify: any files touched above if diagnostics require fixes

**Interfaces:**
- Consumes: all updated pages and API adapters
- Produces: a verified frontend that passes lint/tests and is ready for manual QA

- [ ] **Step 1: Run the project’s frontend lint and targeted tests for the modified pages**

- [ ] **Step 2: Fix any diagnostics introduced by the implementation**

- [ ] **Step 3: Re-run the same checks and ensure they pass cleanly**

- [ ] **Step 4: Update the task list to reflect completed work**
