import { fileURLToPath } from 'node:url'

import { test, expect } from '@playwright/test'

test.describe.configure({ mode: 'serial' })

import { attachReportLinks, createHarnessReport, normalizeHarnessResult, writeHarnessReport } from '@/harness/report'
import { expectTableVisible, loginAsRole, ROLE_FLOW_CONFIG } from './shared'

const reportPath = fileURLToPath(new URL('../playwright-report/role-user-report.json', import.meta.url))
const backendReportHref = '../backend/test-artifacts/harness-report.md'
const results: Array<ReturnType<typeof normalizeHarnessResult>> = []
const flow = ROLE_FLOW_CONFIG.user

test.beforeEach(async () => undefined)

test.afterAll(() => {
  writeHarnessReport(reportPath, createHarnessReport({ source: 'playwright', passed: results.every((r) => r.status === 'passed'), scenarioCount: results.length, results, meta: { runner: 'playwright', framework: 'playwright', version: '1.0' } }))
})

test('user flow closes login -> dashboard -> risk -> intervention loop', async ({ page }) => {
  const startedAt = performance.now()
  await loginAsRole(page, 'user')
  await expect(page.getByRole('heading', { name: flow.dashboardHeading })).toBeVisible()
  await expect(page.getByRole('main').getByText('干预计划', { exact: true }).first()).toBeVisible()
  for (const highlight of flow.dashboardHighlights) {
    await expect(page.getByRole('main').getByText(highlight, { exact: true }).first()).toBeVisible()
  }

  await page.goto(flow.secondaryRoutes[0])
  await expect(page).toHaveURL(/\/user\/risk/)
  await expect(page.getByText(flow.secondaryHeadings[0], { exact: true }).first()).toBeVisible()

  await page.goto(flow.secondaryRoutes[1])
  await expect(page).toHaveURL(/\/user\/intervention/)
  await expect(page.getByText(flow.secondaryHeadings[1], { exact: true }).first()).toBeVisible()

  await page.goto(flow.secondaryRoutes[2])
  await expect(page).toHaveURL(/\/user\/warnings/)
  await expect(page.getByText(flow.secondaryHeadings[2], { exact: true }).first()).toBeVisible()

  results.push(normalizeHarnessResult(attachReportLinks({ name: 'user flow closes login -> dashboard -> risk -> intervention loop', kind: 'system', status: 'passed', durationMs: performance.now() - startedAt, details: { role: 'user', backendReportHref }, error: null }, { backend: backendReportHref })))
})
