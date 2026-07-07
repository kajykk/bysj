import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

import { test, expect } from '@playwright/test'

test.describe.configure({ mode: 'serial' })

const baseURL = 'http://127.0.0.1:8000/api/v1'

// ISSUE-004 修复：从环境变量读取种子密码，与后端 .env 配置保持一致
// 优先使用 E2E_*_PASSWORD 环境变量；若未设置则使用默认值（与 .env.example 对齐）
const accounts = [
  { username: 'admin', password: process.env.E2E_ADMIN_PASSWORD || 'E2E@Admin123' },
  { username: 'dr_wang', password: process.env.E2E_COUNSELOR_PASSWORD || 'E2E@Counselor123' },
  // user_none 是种子数据中的无风险用户 (seed.py 中定义)
  { username: 'user_none', password: process.env.E2E_USER_PASSWORD || 'E2E@User123' },
]

const seedReportPath = fileURLToPath(new URL('../playwright-report/seed-report.json', import.meta.url))

// eslint-disable-next-line no-empty-pattern
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
