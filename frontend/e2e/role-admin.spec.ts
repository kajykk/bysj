import { fileURLToPath } from 'node:url'

import { test, expect } from '@playwright/test'

test.describe.configure({ mode: 'serial' })

import { attachReportLinks, createHarnessReport, normalizeHarnessResult, writeHarnessReport } from '@/harness/report'
import { expectTableVisible, loginAsRole, ROLE_FLOW_CONFIG } from './shared'

const reportPath = fileURLToPath(new URL('../playwright-report/role-admin-report.json', import.meta.url))
const backendReportHref = '../backend/test-artifacts/harness-report.md'
const results: Array<ReturnType<typeof normalizeHarnessResult>> = []
const flow = ROLE_FLOW_CONFIG.admin

test.beforeEach(async () => undefined)

test.afterAll(() => {
  writeHarnessReport(reportPath, createHarnessReport({ source: 'playwright', passed: results.every((r) => r.status === 'passed'), scenarioCount: results.length, results, meta: { runner: 'playwright', framework: 'playwright', version: '1.0' } }))
})

test('admin flow closes login -> dashboard -> templates -> logs loop', async ({ page }) => {
  const startedAt = performance.now()
  await loginAsRole(page, 'admin')
  await expect(page.getByRole('heading', { name: flow.dashboardHeading })).toBeVisible()
  for (const highlight of flow.dashboardHighlights) {
    await expect(page.getByText(highlight, { exact: true })).toBeVisible()
  }

  for (const [index, route] of flow.secondaryRoutes.entries()) {
    await page.goto(route)
    await expect(page).toHaveURL(new RegExp(route.replaceAll('/', '\\/')))
    await expect(page.getByText(flow.secondaryHeadings[index], { exact: true }).first()).toBeVisible()
  }

  results.push(normalizeHarnessResult(attachReportLinks({ name: 'admin flow closes login -> dashboard -> templates -> logs loop', kind: 'system', status: 'passed', durationMs: performance.now() - startedAt, details: { role: 'admin', backendReportHref }, error: null }, { backend: backendReportHref })))
})
