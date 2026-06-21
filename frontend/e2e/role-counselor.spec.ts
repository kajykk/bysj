import { fileURLToPath } from 'node:url'

import { test, expect } from '@playwright/test'

test.describe.configure({ mode: 'serial' })

import { attachReportLinks, createHarnessReport, normalizeHarnessResult, writeHarnessReport } from '@/harness/report'
import { expectTableVisible, loginAsRole, ROLE_FLOW_CONFIG } from './shared'

const reportPath = fileURLToPath(new URL('../playwright-report/role-counselor-report.json', import.meta.url))
const backendReportHref = '../backend/test-artifacts/harness-report.md'
const results: Array<ReturnType<typeof normalizeHarnessResult>> = []
const flow = ROLE_FLOW_CONFIG.counselor

test.beforeEach(async () => undefined)

test.afterAll(() => {
  writeHarnessReport(reportPath, createHarnessReport({ source: 'playwright', passed: results.every((r) => r.status === 'passed'), scenarioCount: results.length, results, meta: { runner: 'playwright', framework: 'playwright', version: '1.0' } }))
})

test('counselor flow closes login -> warnings -> users -> detail loop', async ({ page }) => {
  const startedAt = performance.now()
  await loginAsRole(page, 'counselor')
  await expect(page.getByRole('heading', { name: flow.dashboardHeading })).toBeVisible()
  for (const highlight of flow.dashboardHighlights) {
    await expect(page.getByText(highlight, { exact: true })).toBeVisible()
  }

  await page.goto(flow.secondaryRoutes[0])
  await expect(page).toHaveURL(/\/counselor\/warnings/)
  await expect(page.getByText(flow.secondaryHeadings[0], { exact: true }).first()).toBeVisible()

  await page.goto(flow.secondaryRoutes[1])
  await expect(page).toHaveURL(/\/counselor\/users/)
  await expect(page.getByText(flow.secondaryHeadings[1], { exact: true }).first()).toBeVisible()

  await page.goto(flow.detailRoute ?? '/counselor/users/1')
  await expect(page).toHaveURL(/\/counselor\/users\/1/)
  await expect(page.getByText('用户详情', { exact: false }).first()).toBeVisible()

  results.push(normalizeHarnessResult(attachReportLinks({ name: 'counselor flow closes login -> warnings -> users -> detail loop', kind: 'system', status: 'passed', durationMs: performance.now() - startedAt, details: { role: 'counselor', backendReportHref }, error: null }, { backend: backendReportHref })))
})
