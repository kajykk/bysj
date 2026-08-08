/**
 * 空白区域优化 - 跨浏览器兼容性验证脚本
 * 用法: node scripts/blank-audit-crossbrowser.mjs
 * 前置: 5173 = 优化后 dev server（VITE_BACKEND_PROXY_TARGET=http://localhost:8001）
 * 引擎: firefox / webkit / msedge(Chromium) 三引擎同页对比
 */
import { firefox, webkit, chromium } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const OUT = path.resolve('blank-audit-shots', 'crossbrowser')
const BASE = 'http://127.0.0.1:5173'

const VIEWPORTS = {
  desktop: { width: 1440, height: 900 },
  tablet: { width: 900, height: 1200 },
  mobile: { width: 390, height: 844 },
}

const CREDENTIALS = {
  admin: { username: 'admin', password: 'E2E@Admin123' },
  counselor: { username: 'dr_wang', password: 'E2E@Counselor123' },
  user: { username: 'user_moderate', password: 'E2E@User123' },
}

// [role, path, viewport]
const TARGETS = [
  [null, '/login', 'tablet'],
  ['user', '/user/dashboard', 'desktop'],
  ['user', '/user/settings', 'desktop'],
  ['user', '/user/settings', 'tablet'],
  ['user', '/user/risk', 'mobile'],
  ['counselor', '/counselor/dashboard', 'desktop'],
  ['admin', '/admin/dashboard', 'desktop'],
]

const slug = (p) => p.replace(/^\//, '').replace(/\//g, '-') || 'home'

const ENGINES = [
  ['firefox', firefox],
  ['webkit', webkit],
  ['msedge', chromium],
]

async function doLogin(page, role) {
  const cred = CREDENTIALS[role]
  await page.evaluate(() => window.sessionStorage.clear()).catch(() => {})
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => {})
  await page.getByPlaceholder('请输入用户名').fill(cred.username)
  await page.getByPlaceholder('请输入密码').fill(cred.password)
  await page.getByRole('button', { name: /登录|登 录/ }).click()
  await page.waitForURL(`**/${role}/**`, { timeout: 30000 }).catch(() => {})
  await page
    .waitForFunction(() => !!window.sessionStorage.getItem('token'), null, { timeout: 20000 })
    .catch(() => {})
  await page.waitForTimeout(600)
}

async function dismissTour(page) {
  // 关闭新手引导浮层，避免遮挡布局核查
  await page
    .locator('.el-tour__close-btn, .el-tour__close, button[aria-label="close"]')
    .first()
    .click({ timeout: 3000 })
    .catch(() => {})
}

for (const [engineName, engine] of ENGINES) {
  const launchOpts = engineName === 'msedge' ? { channel: 'msedge' } : {}
  const browser = await engine.launch({ ...launchOpts, args: ['--no-sandbox'] })
  const context = await browser.newContext({ viewport: VIEWPORTS.desktop })
  const page = await context.newPage()
  page.setDefaultTimeout(30000)
  let currentRole = null

  for (const [role, route, vp] of TARGETS) {
    if (role && role !== currentRole) {
      await doLogin(page, role)
      currentRole = role
    }
    await page.setViewportSize(VIEWPORTS[vp])
    try {
      await page.goto(`${BASE}${route}`, { waitUntil: 'networkidle', timeout: 30000 })
    } catch {
      await page.goto(`${BASE}${route}`, { waitUntil: 'load', timeout: 30000 }).catch(() => {})
    }
    if (role && page.url().includes('/login')) {
      await doLogin(page, role)
      await page.goto(`${BASE}${route}`, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {})
    }
    await page.waitForTimeout(1200)
    await dismissTour(page)
    await page.waitForTimeout(400)
    const file = path.join(OUT, `${engineName}-${vp}-${slug(route)}.png`)
    fs.mkdirSync(OUT, { recursive: true })
    await page.screenshot({ path: file, fullPage: true })
    console.log(`[ok] ${engineName} ${vp} ${route}`)
  }
  await context.close()
  await browser.close()
}
console.log(`\nDONE -> ${OUT}`)
