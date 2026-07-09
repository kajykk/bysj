# Product Improvement Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-subagent-driven-development or superpowers-executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Based on the product evaluation, deliver a prioritized, testable improvement plan for the depression warning system that strengthens product positioning, closes the core user journey, improves UX consistency, and adds measurable business and operational feedback loops.

**Architecture:** The work is organized into five streams that can be executed in sequence or in parallel where dependencies allow: product strategy, core workflow redesign, UX consistency and accessibility, analytics and metrics, and performance/reliability hardening. Each task names the concrete files to inspect or change, the expected outcome, and the verification method so implementation can proceed with minimal context.

**Tech Stack:** Vue 3, TypeScript, Vite, Pinia, Vue Router, Element Plus, ECharts, Playwright, Vitest, existing project docs and planning artifacts.

## Global Constraints

- Keep the current role model intact unless a task explicitly changes route access or navigation.
- Preserve existing backend contracts unless the plan explicitly introduces a UI-only adaptation.
- Maintain the existing bilingual/i18n structure for any new user-facing copy.
- Do not remove existing audit/security/stability protections while improving UX.
- Every user-visible change must have at least one regression check: unit, component, E2E, or manual verification.
- P0 improvements must be completed before any P1 polish work in the same execution batch.
- Any new metric must be tied to a file, route, or event that already exists or is introduced in the same task.
- Avoid introducing new dependencies unless the current codebase cannot support the requirement.

---

## Scope Summary

### Key findings from the evaluation

- Product positioning is directionally clear, but the value proposition is not yet expressed as a concise, differentiated narrative.
- The core task chain exists across routes, but it is fragmented across pages and does not feel like one guided workflow.
- UX is functional and fairly mature, but visual language, mobile behavior, and action feedback are inconsistent.
- The product serves a B2B / institutional workflow, yet the commercial model, packaging, and adoption path are not visible in the product.
- The codebase already contains quality scaffolding (tests, monitoring, route guards, WebSocket handling), which can be leveraged to improve the product without large architectural risk.

### Recommended priority order

1. P0 — unify the core workflow and rescue path
2. P1 — improve task efficiency, clarity, and trust
3. P1 — standardize UX patterns and accessibility
4. P2 — add data instrumentation and business visibility
5. P2 — harden performance and mobile edge cases

---

## Task 1: Clarify product positioning and landing narrative

**Files:**
- Modify: `frontend/src/views/login/LoginPage.vue`
- Modify: `frontend/src/views/user/UserDashboard.vue`
- Modify: `frontend/src/views/admin/AdminDashboard.vue`
- Modify: `frontend/src/views/counselor/CounselorDashboard.vue`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/en-US.ts`
- Test: `frontend/src/views/login/LoginPage.vue` or related component test file if copy is rendered in a testable component

**Interfaces:**
- Consumes: current auth/role flow, existing dashboard shells, existing i18n keys.
- Produces: a clearer product narrative, role-specific value statements, and concise CTA copy that can be reused across dashboards and login.

- [ ] **Step 1: Identify the first-screen copy gaps**

Review the login page and the top section of each role dashboard. Record the current headline, subheadline, and CTA text that a first-time user sees. Confirm which copy is generic and which copy already communicates the value proposition.

- [ ] **Step 2: Draft the revised positioning copy**

Create a new copy set that communicates the product in one sentence, such as: “面向机构的心理风险识别、预警与干预协同平台。” Keep the tone professional, calm, and operational rather than promotional.

Suggested copy structure:

```text
Headline: 让风险评估、预警干预、复评闭环在一个平台中完成
Subheadline: 面向用户、咨询师与管理员的机构级心理健康管理工作台
Primary CTA: 立即进入工作台
Secondary CTA: 查看核心流程
```

- [ ] **Step 3: Wire the copy into i18n keys**

Add role-aware keys in `frontend/src/i18n/locales/zh-CN.ts` and `frontend/src/i18n/locales/en-US.ts` so the dashboards can reference the same positioning language without hard-coded strings.

- [ ] **Step 4: Keep route-level behavior unchanged**

Do not alter routing or auth guards in this task. Only update the messages and visible copy.

- [ ] **Step 5: Verify the updated narrative on login and dashboards**

Run the app locally and inspect the login page plus the first fold of the three dashboards to confirm the value proposition is immediately visible.

Expected outcome: first-time users can tell what the product does, for whom, and why it is different without reading a full page of features.

---

## Task 2: Turn the core workflow into one guided journey

**Files:**
- Modify: `frontend/src/layouts/MainLayout.vue`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/views/user/UserDashboard.vue`
- Modify: `frontend/src/views/user/UserRiskPage.vue`
- Modify: `frontend/src/views/user/UserInterventionPage.vue`
- Modify: `frontend/src/views/user/UserReportsPage.vue`
- Modify: `frontend/src/views/user/UserWarningsPage.vue`
- Modify: `frontend/src/views/user/components/RiskReportTab.vue`
- Modify: `frontend/src/views/user/components/StructuredAssessTab.vue`
- Modify: `frontend/src/views/user/components/TextAssessTab.vue`
- Modify: `frontend/src/views/user/components/PhysioTab.vue`
- Test: `frontend/e2e/core-flows.spec.ts`
- Test: `frontend/tests/e2e/specs/risk-assessment.spec.ts`
- Test: `frontend/tests/e2e/specs/reports.spec.ts`

**Interfaces:**
- Consumes: current user routes, dashboard shortcuts, risk assessment flow, intervention flow, reports flow.
- Produces: a guided “assess → understand → intervene → review” journey with clearer transitions and next-action prompts.

- [ ] **Step 1: Map the current user journey**

Trace the main user journey from dashboard to risk page, intervention page, warning list, and report center. List every point where the user must decide what to do next without guidance.

- [ ] **Step 2: Add next-step guidance cards**

On `UserDashboard.vue`, show a single prioritized next action based on current state:
- no assessment yet → start assessment
- assessment exists but risk is high → view explanation and intervention
- intervention active → continue tasks
- unread warnings exist → review warnings

Use a compact card with one primary action and one secondary link.

- [ ] **Step 3: Add workflow breadcrumbs or step markers**

In `MainLayout.vue` or the relevant user pages, surface a simple workflow indicator so users know where they are in the journey. Keep it lightweight and avoid creating a second navigation system.

- [ ] **Step 4: Strengthen the risk page progression**

In `UserRiskPage.vue` and the assessment components, ensure that after an assessment is submitted the user sees:
- the result summary
- the explanation for the score or severity
- the next recommended action

If the result is high risk, the UI must not leave the user on a generic success message alone.

- [ ] **Step 5: Improve post-warning actions**

In `UserWarningsPage.vue`, make each warning row lead to a next best action, such as viewing the full report or entering the intervention flow.

- [ ] **Step 6: Expand regression coverage for the journey**

Extend `frontend/e2e/core-flows.spec.ts` to verify the full journey from login to assessment to intervention to report review. Add at least one assertion for each transition so the workflow cannot regress silently.

Expected outcome: the main product story becomes a connected journey instead of a collection of pages.

---

## Task 3: Improve information architecture and command clarity

**Files:**
- Modify: `frontend/src/layouts/MainLayout.vue`
- Modify: `frontend/src/config/permissions.ts`
- Modify: `frontend/src/config/routeAccess.ts`
- Modify: `frontend/src/config/feature.ts`
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/router/guard.ts`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/en-US.ts`
- Test: `frontend/src/router/index.test.ts`
- Test: `frontend/src/router/guard.test.ts`
- Test: `frontend/src/config/routeAccess.test.ts`

**Interfaces:**
- Consumes: existing roles, permissions, route guards, and menu structure.
- Produces: a cleaner navigation model, stronger role separation, and a more discoverable command structure.

- [ ] **Step 1: Reclassify menu items by user intent**

Review the current menu items and group them into three buckets for each role:
- daily work
- review and history
- system/settings

Only keep the most important first-level entries visible by default.

- [ ] **Step 2: Reduce top-level navigation noise**

In `MainLayout.vue`, reorder or de-emphasize low-frequency items so the main working path stays visible. For example, move low-frequency admin maintenance pages behind a “更多” grouping if the current page density is too high.

- [ ] **Step 3: Align route titles and breadcrumbs with user language**

Ensure route titles, breadcrumb labels, and menu labels share the same wording. Avoid using different names for the same concept across pages.

- [ ] **Step 4: Validate role boundaries**

Check that users only see the routes and navigation items appropriate to their role. If a route is visible but not actionable, either hide it or add an explicit explanation of why it is unavailable.

- [ ] **Step 5: Verify the IA with tests**

Update router and route-access tests to verify the revised menu/guard behavior, including at least one unauthorized access case and one role-specific visible menu case.

Expected outcome: the UI feels easier to scan, the role model feels intentional, and users can predict where commands live.

---

## Task 4: Standardize UX patterns and accessibility

**Files:**
- Modify: `frontend/src/layouts/MainLayout.vue`
- Modify: `frontend/src/views/user/UserDashboard.vue`
- Modify: `frontend/src/views/user/UserRiskPage.vue`
- Modify: `frontend/src/views/user/UserInterventionPage.vue`
- Modify: `frontend/src/views/user/UserReportsPage.vue`
- Modify: `frontend/src/views/admin/AdminDashboard.vue`
- Modify: `frontend/src/views/counselor/CounselorDashboard.vue`
- Modify: `frontend/src/styles/theme.scss`
- Modify: `frontend/src/styles/variables.scss`
- Modify: `frontend/src/styles/utilities.scss`
- Modify: `frontend/src/styles/mixins.scss`
- Test: `frontend/src/styles/styles.test.ts`
- Test: `frontend/src/views/user/UserDashboard.loading.test.ts`

**Interfaces:**
- Consumes: the current shared design tokens and page shells.
- Produces: a more consistent visual system, improved keyboard and mobile accessibility, and uniform feedback behavior.

- [ ] **Step 1: Audit the most repeated UI patterns**

Identify repeated patterns such as:
- dashboard card shells
- page headers
- action bars
- loading/error/empty states
- badge/tag semantics
- mobile collapse behavior

- [ ] **Step 2: Normalize header and card styles**

Consolidate repeated header spacing, typography, and action alignment rules into shared style tokens or utilities. Avoid changing every page independently if one shared component or mixin can cover the pattern.

- [ ] **Step 3: Tighten loading and empty-state feedback**

Standardize the way loading skeletons, reload actions, and empty states appear so the user sees the same interaction logic on every page.

- [ ] **Step 4: Improve keyboard and screen-reader support**

Make sure all interactive icons, collapse controls, and warning entry points have accessible labels, focus states, and keyboard activation paths.

- [ ] **Step 5: Refine mobile layout behavior**

Review the current mobile breakpoints and ensure the main action remains visible without overlapping sidebar, header, or action buttons. If needed, simplify the header action cluster on small screens.

- [ ] **Step 6: Regression-test the shared styles**

Update style or component tests that cover loading, layout shell, and responsive states. Confirm the main dashboard and layout still render correctly after token changes.

Expected outcome: the product feels like one system instead of several inconsistent screens.

---

## Task 5: Make the business model visible in the product

**Files:**
- Modify: `frontend/src/views/admin/AdminSettingsPage.vue`
- Modify: `frontend/src/views/admin/AdminDashboard.vue`
- Modify: `frontend/src/views/admin/AdminReportsPage.vue`
- Modify: `frontend/src/views/admin/AdminTemplatesPage.vue`
- Modify: `frontend/src/views/admin/AdminMonitoringPage.vue`
- Modify: `frontend/src/views/counselor/CounselorSettingsPage.vue`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/en-US.ts`
- Test: `frontend/src/views/admin/AdminDashboard.test.ts`
- Test: `frontend/src/views/admin/AdminReportsPage.test.ts`

**Interfaces:**
- Consumes: existing admin settings, monitoring, templates, and reports pages.
- Produces: a clearer institutional packaging narrative and operational visibility that supports a B2B sales conversation.

- [ ] **Step 1: Define what “business model visibility” means in-product**

Make the commercial story visible without adding a sales website. The product should communicate:
- what modules exist
- which role uses each module
- what adoption/usage signals matter
- what operational outcomes the institution gets

- [ ] **Step 2: Add module / license / usage context to admin surfaces**

On the admin side, expose contextual information such as:
- enabled modules
- license or deployment status
- recent usage or adoption indicators
- operational health and usage warnings

- [ ] **Step 3: Add an institution-facing summary in reports**

Create a concise summary block that can be shown in reports or admin dashboards to explain product value in business terms rather than technical terms.

- [ ] **Step 4: Keep the implementation product-facing, not marketing-only**

Avoid building a separate marketing page. The information should help administrators and decision-makers understand adoption, value, and health inside the system they already use.

- [ ] **Step 5: Verify the updated admin narratives**

Update dashboard/report tests to ensure the new summary or context block renders and does not break role-specific pages.

Expected outcome: the product becomes easier to explain, sell, and manage in an institutional setting.

---

## Task 6: Add measurable analytics and evaluation hooks

**Files:**
- Modify: `frontend/src/api/observabilityApi.ts`
- Modify: `frontend/src/api/monitoringApi.ts`
- Modify: `frontend/src/api/reportsApi.ts`
- Modify: `frontend/src/composables/usePerformanceMonitor.ts`
- Modify: `frontend/src/utils/httpFeedback.ts`
- Modify: `frontend/src/views/user/UserDashboard.vue`
- Modify: `frontend/src/views/user/UserRiskPage.vue`
- Modify: `frontend/src/views/counselor/CounselorDashboard.vue`
- Modify: `frontend/src/views/admin/AdminObservabilityPage.vue`
- Modify: `frontend/src/views/admin/AdminMonitoringPage.vue`
- Modify: `frontend/src/views/admin/AdminReportsPage.vue`
- Test: `frontend/src/api/observabilityApi.test.ts`
- Test: `frontend/src/composables/usePerformanceMonitor.test.ts`
- Test: `frontend/tests/e2e/specs/monitoring.spec.ts`

**Interfaces:**
- Consumes: existing observability and monitoring infrastructure.
- Produces: product metrics that can support the evaluation criteria and future business decisions.

- [ ] **Step 1: Define the top metrics the product must show**

Track at minimum:
- assessment completion rate
- average completion time
- warning response time
- intervention follow-through rate
- page load P95 for key flows
- API error rate for critical endpoints

- [ ] **Step 2: Map metrics to existing pages or events**

Reuse the current observability and monitoring surfaces where possible. If a metric cannot be shown yet, define the event or data source needed and keep the gap explicit.

- [ ] **Step 3: Add a visible “product health” or “flow health” section**

Surface a concise summary that shows whether the product is helping users complete their task chain successfully.

- [ ] **Step 4: Make error and latency states actionable**

If a metric degrades, the UI should point to the next troubleshooting action rather than just showing a red indicator.

- [ ] **Step 5: Update observability tests**

Ensure the new metrics view and data mappings are covered by tests and are not dependent on accidental API shapes.

Expected outcome: the team can measure whether the product is improving the actual user journey, not just shipping screens.

---

## Task 7: Harden performance, reliability, and mobile edge cases

**Files:**
- Modify: `frontend/src/layouts/MainLayout.vue`
- Modify: `frontend/src/views/user/UserDashboard.vue`
- Modify: `frontend/src/views/user/UserRiskPage.vue`
- Modify: `frontend/src/views/user/UserInterventionPage.vue`
- Modify: `frontend/src/utils/sharedResize.ts`
- Modify: `frontend/src/utils/useBreakpoint.ts`
- Modify: `frontend/src/composables/usePerformanceMonitor.ts`
- Modify: `frontend/src/utils/errorPolicy.ts`
- Modify: `frontend/src/utils/httpError.ts`
- Modify: `frontend/src/utils/httpFeedback.ts`
- Test: `frontend/src/composables/useBreakpoint.test.ts`
- Test: `frontend/src/composables/usePerformanceMonitor.test.ts`
- Test: `frontend/src/utils/errorPolicy.test.ts`
- Test: `frontend/tests/e2e/specs/error-handling.spec.ts`

**Interfaces:**
- Consumes: current responsive behavior, error handling, and monitoring utilities.
- Produces: a more robust experience on smaller screens and under slow or failing network conditions.

- [ ] **Step 1: Review the main reliability risks**

Check the areas most likely to hurt user trust:
- sidebar and header overlap on mobile
- stale data after reconnects or route changes
- slow chart or dashboard renders
- repeated resize listeners
- unhandled request errors

- [ ] **Step 2: Make retry / fallback behavior more explicit**

Ensure users can recover from failures in a predictable way. Error states should tell the user what failed and what to do next.

- [ ] **Step 3: Reduce duplicate listeners and wasted renders**

Where possible, share debounce/resize handling and avoid repeated initialization on every route transition.

- [ ] **Step 4: Validate mobile interactions on narrow widths**

Confirm that the main task flow remains usable on mobile widths and that the header/sidebar do not obscure primary actions.

- [ ] **Step 5: Add regression coverage for failure states**

Extend error-handling and breakpoint tests so the new fallback behavior does not regress.

Expected outcome: the product remains usable and understandable when the environment is imperfect.

---

## Task 8: Define the rollout, review, and success metrics

**Files:**
- Create or modify: `docs/superpowers/plans/2026-07-09-product-improvement-plan.md` if updated during execution
- Create: `docs/superpowers/plans/2026-07-09-product-improvement-execution-notes.md` if implementation proceeds
- Modify: `frontend/docs/regression-checklist.md`
- Modify: `frontend/docs/api-field-mapping.md`
- Modify: `frontend/tests/e2e/specs/navigation.spec.ts`
- Modify: `frontend/tests/e2e/specs/report-export.spec.ts`

**Interfaces:**
- Consumes: outputs from Tasks 1-7.
- Produces: a rollout order, acceptance criteria, and a measurable definition of success.

- [ ] **Step 1: Turn the plan into an implementation order**

Sequence the work as:
1. positioning copy
2. workflow guidance
3. IA cleanup
4. UX consistency
5. business visibility
6. analytics hooks
7. performance/mobile hardening

- [ ] **Step 2: Define acceptance criteria for each priority level**

Write explicit criteria such as:
- user can identify the product purpose within 10 seconds
- user can reach the next recommended action from the dashboard in one click
- counsel/admin pages show relevant contextual summaries
- key journey pages remain green in regression checks

- [ ] **Step 3: Define final success metrics**

Add a simple success scorecard that includes both product and technical metrics, for example:
- task completion rate
- warning response time
- assessment completion time
- page load P95
- error rate
- user-reported clarity score

- [ ] **Step 4: Establish review checkpoints**

Plan one checkpoint after the P0/P1 work and one checkpoint after the analytics/performance work so the product direction can be corrected early if needed.

- [ ] **Step 5: Run the final verification pass**

Confirm every changed screen has at least one corresponding test or manual verification note and every new product metric has a source.

Expected outcome: the implementation can proceed in a controlled order with clear pass/fail criteria.

---

## Suggested execution phases

### Phase A — Foundation / P0
- Task 1
- Task 2

### Phase B — IA and consistency / P1
- Task 3
- Task 4

### Phase C — Commercial and measurable product / P2
- Task 5
- Task 6

### Phase D — Reliability hardening / P2
- Task 7

### Phase E — Rollout governance
- Task 8

---

## Self-review checklist

- [ ] Every evaluation gap from the report is mapped to at least one task.
- [ ] Each task has exact file paths.
- [ ] Each task has a clear output and a verification step.
- [ ] The plan separates product, UX, business, analytics, and technical hardening work.
- [ ] No task depends on undefined files or missing types.
- [ ] The plan can be executed incrementally, with useful results after each task.

## Recommended next action

Start with **Task 1** and **Task 2** together if the goal is to make the product feel coherent quickly. If the team prefers safer sequencing, complete Task 1 first, then ship Task 2 as the core workflow milestone.
