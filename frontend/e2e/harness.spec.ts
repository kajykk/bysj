import { fileURLToPath } from 'node:url'

import { test, expect } from '@playwright/test'

import { createHarnessReport, normalizeHarnessResult, writeHarnessReport } from '@/harness/report'

const reportPath = fileURLToPath(new URL('../playwright-report/harness-report.playwright.json', import.meta.url))
const backendReportHref = '../backend/test-artifacts/harness-report.md'

const routes = [
  {
    method: 'GET' as const,
    url: /\/api\/v1\/user\/risk\/report$/,
    body: { data: { risk_level: 3, risk_score: 78 } },
  },
  {
    method: 'GET' as const,
    url: /\/api\/v1\/user\/content\/recommendations$/,
    body: { data: { explain: { strategy: 'sleep hygiene' } } },
  },
]

const results: Array<ReturnType<typeof normalizeHarnessResult>> = []

test.beforeEach(async ({ page }) => {
  for (const route of routes) {
    await page.route(route.url, async (routeHandler) => {
      await routeHandler.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(route.body),
      })
    })
  }
})

test.afterAll(() => {
  const report = createHarnessReport({
    source: 'playwright',
    passed: results.every((result) => result.status === 'passed'),
    scenarioCount: results.length,
    results,
    meta: {
      runner: 'playwright',
      framework: 'playwright',
      version: '1.0',
    },
  })
  writeHarnessReport(reportPath, report)
})

test('user dashboard shell renders with mocked API data', async ({ page }) => {
  const startedAt = performance.now()
  await page.goto('/user/dashboard')
  await expect(page.locator('body')).toBeVisible()
  results.push(
    normalizeHarnessResult({
      name: 'user dashboard shell renders with mocked API data',
      kind: 'system',
      status: 'passed',
      durationMs: performance.now() - startedAt,
      details: { route: '/user/dashboard', backendReportHref },
    }),
  )
})

test('risk page shell renders with mocked API data', async ({ page }) => {
  const startedAt = performance.now()
  await page.goto('/user/risk')
  await expect(page.locator('body')).toBeVisible()
  results.push(
    normalizeHarnessResult({
      name: 'risk page shell renders with mocked API data',
      kind: 'system',
      status: 'passed',
      durationMs: performance.now() - startedAt,
      details: { route: '/user/risk', backendReportHref },
    }),
  )
})
