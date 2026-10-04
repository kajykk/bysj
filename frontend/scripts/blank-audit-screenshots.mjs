/**
 * 空白区域优化 - 优化前后多端截图对比脚本
 * 用法: node scripts/blank-audit-screenshots.mjs
 * 可选: SHOT_LABELS=after node scripts/blank-audit-screenshots.mjs （仅重拍指定组）
 * 前置: 5173 = 优化后 dev server, 5174 = 优化前(baseline worktree) dev server
 *       后端已播种 admin / dr_wang / user_moderate 账号
 */
import { chromium } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const OUT = path.resolve('blank-audit-shots')
const BASES = {
  before: 'http://127.0.0.1:5174',
  after: 'http://127.0.0.1:5173',
}

const VIEWPORTS = {
  desktop: { width: 1440, height: 900 },
  tablet: { width: 900, height: 1200 }, // 登录页断点错位的核心区间 769–960
  mobile: { width: 390, height: 844 },
}

// AUDIT-2026-10-01 (P1-31): 不再硬编码 E2E 口令；从环境变量读取，缺失即失败。
const CREDENTIALS = {
  admin: { username: 'admin', password: process.env.E2E_ADMIN_PASSWORD },
  counselor: { username: 'dr_wang', password: process.env.E2E_COUNSELOR_PASSWORD },
  user: { username: 'user_moderate', password: process.env.E2E_USER_PASSWORD },
}

const MISSING = Object.entries(CREDENTIALS)
  .filter(([, c]) => !c.password)
  .map(([role]) => role)
if (MISSING.length) {
  console.error(
    `缺少环境变量口令: ${MISSING.join(', ')} —— 需注入 E2E_ADMIN_PASSWORD / E2E_COUNSELOR_PASSWORD / E2E_USER_PASSWORD`,
  )
  process.exit(1)
}

// [role, path, 视口集合]
const TARGETS = [
  [null, '/login', ['desktop', 'tablet', 'mobile']],
  [null, '/reset-password', ['tablet']],
  ['user', '/user/dashboard', ['desktop', 'tablet', 'mobile']],
  ['user', '/user/risk', ['desktop', 'tablet', 'mobile']],
  ['user', '/user/settings', ['desktop', 'tablet']],
  ['user', '/user/assessments', ['desktop', 'mobile']],
  ['user', '/user/warnings', ['desktop']],
  ['counselor', '/counselor/dashboard', ['desktop', 'tablet', 'mobile']],
  ['counselor', '/counselor/settings', ['desktop', 'tablet']],
  ['counselor', '/counselor/warnings', ['desktop']],
  ['admin', '/admin/dashboard', ['desktop', 'tablet']],
  ['admin', '/admin/alerts', ['desktop']],
  ['admin', '/admin/operation-logs', ['desktop']],
]

const slug = (p) => p.replace(/^\//, '').replace(/\//g, '-') || 'home'

const LABELS = (process.env.SHOT_LABELS || 'before,after').split(',')

async function doLogin(page, base, role) {
  const cred = CREDENTIALS[role]
  // 切换角色前先清掉旧会话，避免已登录态访问 /login 被守卫重定向
  await page.evaluate(() => window.sessionStorage.clear()).catch(() => {})
  await page.goto(`${base}/login`, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => {})
  await page.getByPlaceholder('请输入用户名').fill(cred.username)
  await page.getByPlaceholder('请输入密码').fill(cred.password)
  await page.getByRole('button', { name: /登录|登 录/ }).click()
  await page.waitForURL(`**/${role}/**`, { timeout: 30000 }).catch(() => {})
  // 等待令牌真正落盘（sessionStorage），避免整页跳转先于令牌写入被守卫打回登录页
  await page
    .waitForFunction(() => !!window.sessionStorage.getItem('token'), null, { timeout: 20000 })
    .catch(() => {})
  await page.waitForTimeout(600)
}

async function shoot(browser, base, label) {
  const context = await browser.newContext({ viewport: VIEWPORTS.desktop })
  const page = await context.newPage()
  page.setDefaultTimeout(30000)
  let currentRole = null

  for (const [role, route, vps] of TARGETS) {
    // 每个目标拍摄前确保会话有效且角色匹配：角色不同或无令牌则（重新）登录
    if (role) {
      const hasToken = await page.evaluate(() => !!window.sessionStorage.getItem('token')).catch(() => false)
      if (role !== currentRole || !hasToken) {
        await doLogin(page, base, role)
        currentRole = role
      }
    }

    for (const vp of vps) {
      await page.setViewportSize(VIEWPORTS[vp])
      try {
        await page.goto(`${base}${route}`, { waitUntil: 'networkidle', timeout: 30000 })
      } catch {
        await page.goto(`${base}${route}`, { waitUntil: 'load', timeout: 30000 }).catch(() => {})
      }
      if (role && page.url().includes('/login')) {
        await doLogin(page, base, role)
        currentRole = role
        await page.goto(`${base}${route}`, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {})
      }
      await page.waitForTimeout(1200)
      const file = path.join(OUT, `${label}`, `${vp}-${slug(route)}.png`)
      fs.mkdirSync(path.dirname(file), { recursive: true })
      await page.screenshot({ path: file, fullPage: true })
      console.log(`[ok] ${label} ${vp} ${route} -> ${page.url().replace(base, '')}`)
    }
  }
  await context.close()
}

const browser = await chromium.launch({ channel: 'msedge', args: ['--no-sandbox'] })
try {
  for (const label of LABELS) {
    await shoot(browser, BASES[label], label)
  }
  console.log(`\nDONE -> ${OUT}`)
} finally {
  await browser.close()
}
