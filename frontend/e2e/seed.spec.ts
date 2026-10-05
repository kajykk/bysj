import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

import { test, expect } from '@playwright/test'

test.describe.configure({ mode: 'serial' })

const baseURL = 'http://127.0.0.1:8000/api/v1'

// ISSUE-004 修复：从环境变量读取种子密码，与后端 .env 配置保持一致
// AUDIT-2026-10-01：移除 `|| '***REMOVED***'` 这类回落默认值——把已知口令写进源码，
// 等于让「仓库不预置明文口令」这句话不成立。缺失时直接失败，并说明怎么补。
function requireEnv(name: string): string {
  const value = process.env[name]
  if (!value) {
    throw new Error(
      `缺少环境变量 ${name}：E2E 种子口令不再提供默认值。` +
        '请在本机 .env（或 CI 环境）注入后再运行 E2E。',
    )
  }
  return value
}

/** 惰性解析口令的 getter —— 模块加载时不求值，仅在实际读取时求值。 */
function lazyPassword(envName: string): () => string {
  let cached: string | undefined
  return () => (cached ??= requireEnv(envName))
}

// SEC-FIX-2026-10-05（改为惰性求值）:
//   原实现在下面的数组字面量里直接调用 requireEnv(...)，属于**模块顶层求值**。
//   而 Playwright 会先加载全部 spec 文件再按 project 的 grep 过滤 —— 于是
//   即使 pr-quality-gates.yml 的 e2e-smoke project 只跑 `@smoke`
//   （纯 mock API、不起真实后端、也不该有种子口令），这个文件在**收集阶段**
//   就抛 `缺少环境变量 E2E_ADMIN_PASSWORD`，最终报 `No tests found`：
//   一个与被测代码完全无关的门禁失败。
//
//   改为惰性后：口令在 `test()` 真正执行、读取 accounts 时才求值。
//   本 spec 需要真实后端（打 127.0.0.1:8000），因此真正跑到它时缺口令仍会抛错 ——
//   安全加固与「明确失败」的行为都没被削弱，只是不再污染无关 project 的收集阶段。
const accounts = [
  { username: 'admin', password: lazyPassword('E2E_ADMIN_PASSWORD') },
  { username: 'dr_wang', password: lazyPassword('E2E_COUNSELOR_PASSWORD') },
  // user_none 是种子数据中的无风险用户 (seed.py 中定义)
  { username: 'user_none', password: lazyPassword('E2E_USER_PASSWORD') },
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
    // SEC-FIX-2026-10-05: password 现为惰性 getter，必须在此显式求值为字符串，
    // 否则 JSON.stringify 会把函数丢掉，请求体里将没有 password 字段。
    const credentials = { username: account.username, password: account.password() }
    const res = await request.post(`${baseURL}/auth/login`, { data: credentials })
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
