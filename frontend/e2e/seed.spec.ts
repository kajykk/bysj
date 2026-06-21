import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

import { test, expect } from '@playwright/test'

test.describe.configure({ mode: 'serial' })

const baseURL = 'http://127.0.0.1:8000/api/v1'
const accounts = [
  { username: 'admin', password: 'E2E@Admin123' },
  { username: 'dr_wang', password: 'E2E@Counselor123' },
  { username: 'user_normal', password: 'E2E@User123' },
]

const seedReportPath = fileURLToPath(new URL('../playwright-report/seed-report.json', import.meta.url))

test.afterEach(async ({}, testInfo) => {
  const entries = testInfo.errors.map((error) => ({ message: error.message, stack: error.stack ?? null }))
  mkdirSync(dirname(seedReportPath), { recursive: true })
  const payload = {
    name: testInfo.title,
    status: testInfo.status,
    expectedStatus: testInfo.expectedStatus,
    startedAt: new Date().toISOString(),
    errors: entries,
  }
  writeFileSync(seedReportPath, JSON.stringify(payload, null, 2), 'utf-8')
})

test('seed accounts are available', async ({ request }) => {
  const checks: Array<{ username: string; passed: boolean; status: number; detail: string }> = []

  for (const account of accounts) {
    const res = await request.post(`${baseURL}/auth/login`, { data: account })
    const passed = res.ok()
    let detail = 'ok'
    if (!passed) {
      try {
        const body = await res.json()
        detail = body?.detail || body?.message || `HTTP ${res.status()}`
      } catch {
        detail = `HTTP ${res.status()}`
      }
    }
    checks.push({ username: account.username, passed, status: res.status(), detail })
  }

  mkdirSync(dirname(seedReportPath), { recursive: true })
  writeFileSync(seedReportPath, JSON.stringify({ checks }, null, 2), 'utf-8')

  for (const check of checks) {
    expect(check.passed, `${check.username} login failed: ${check.detail}`).toBeTruthy()
  }
})
