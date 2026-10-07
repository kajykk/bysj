/**
 * CSP 取证探针：判断生产产物是否真的依赖 'unsafe-eval'。
 *
 * 用法：
 *   npm run build          # 先构建（探针读的是 dist，不是源码）
 *   node scripts/csp-probe.mjs
 *
 * 做法：真实 Chromium + 真实产物，遍历登录后路由，对两档 CSP 做逐路由 A/B：
 *   A = script-src 'self'              （去掉 unsafe-eval，待验证的目标档）
 *   B = script-src 'self' 'unsafe-eval'（基线档）
 * 采集：securitypolicyviolation 事件（含 sourceFile/lineNumber）、console error、
 *       pageerror、渲染指标（body 文本长度 / canvas 数量）。
 * 判定只看 A-B 差值：两边同时崩 = 与 CSP 无关；只有 A 崩 = 确实存在 eval 依赖。
 *
 * 三个必须保留的防假绿设计（都踩过坑）：
 *   1. 静态服务器必须做 SPA 回退 —— 否则所有前端路由 404，"零违规"是假绿。
 *   2. 每条路由用独立 browser context —— 同页连续导航会状态污染，后续路由渲染退化。
 *   3. API 要按端点返回真实形状 —— 形状不对时图表走"加载失败"分支，canvas 恒为 0，
 *      ECharts 代码根本没执行，等于没覆盖。
 * 另：本脚本的捕获器须先用正向对照证明有效（外部脚本内主动 eval，应抓到
 *     blockedURI=eval）；否则"0 条"可能只是检测器失灵。
 */
import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const DIST = path.join(__dirname, '..', 'dist')

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.tt': 'font/ttf',
  '.ttf': 'font/ttf',
  '.webmanifest': 'application/manifest+json',
  '.txt': 'text/plain; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
}

const BASE_CSP =
  "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'; " +
  "img-src 'self' data: blob:; font-src 'self' data:; style-src 'self' 'unsafe-inline'; " +
  "connect-src 'self' https://sentry.io https://*.sentry.io"

const VARIANTS = [
  { key: 'A', name: "A: script-src 'self'（无 unsafe-eval）", csp: `${BASE_CSP}; script-src 'self'` },
  { key: 'B', name: "B: script-src 'self' 'unsafe-eval'（基线）", csp: `${BASE_CSP}; script-src 'self' 'unsafe-eval'` },
]

const PROFILES = [
  {
    role: 'user',
    routes: [
      '/user/dashboard',
      '/user/risk',
      '/user/assessments',
      '/user/reports',
      '/user/warnings',
      '/user/content',
      '/user/intervention',
      '/user/settings',
      '/user/model-training',
    ],
  },
  {
    role: 'super_admin',
    routes: [
      '/admin/dashboard',
      '/admin/templates',
      '/admin/audit-logs',
      '/admin/crisis-events',
      '/admin/alerts',
      '/admin/reports',
      '/admin/observability',
      '/admin/monitoring',
      '/admin/canary',
      '/admin/settings',
    ],
  },
]

/**
 * 按端点分派的真实形状桩数据。
 * 目的：让图表/列表真正渲染，从而把 ECharts 等运行时代码也纳入 CSP 覆盖。
 * 没有这一步，图表组件因数据形状不对而走"加载失败"分支，canvas 恒为 0 —— 覆盖缺口。
 */
function stubFor(url) {
  const u = url.split('?')[0]
  const mk = (data) => ({ code: 0, message: 'ok', data })
  if (u.includes('/user/risk/trend'))
    return mk({
      days: 30,
      direction: 'up',
      points: [
        { date: '2026-10-01', risk_score: 42, risk_level: 2 },
        { date: '2026-10-03', risk_score: 48, risk_level: 2 },
        { date: '2026-10-05', risk_score: 55, risk_level: 3 },
        { date: '2026-10-07', risk_score: 61, risk_level: 3 },
      ],
    })
  if (u.includes('/user/risk/report'))
    return mk({
      risk_score: 61.2,
      risk_level: 3,
      trend: 'up',
      severity: 'high',
      main_factors: ['睡眠质量下降', '社交活动减少'],
      recommendations: ['保持规律作息', '预约咨询师访谈'],
      generated_at: '2026-10-08T00:00:00',
    })
  if (u.includes('/user/data/history'))
    return mk({
      items: [
        {
          id: 11,
          type: 'structured',
          created_at: '2026-10-01T08:30:00',
          data: { scale: 'PHQ-9', severity: 'high', risk_score: 72.5 },
        },
      ],
      total: 1,
      page: 1,
      page_size: 10,
    })
  if (u.includes('/admin/stats'))
    return mk({
      users: { total: 10, today: 1, delta: 0.1 },
      counselors: 2,
      warnings: { today: 1, unhandled: 1 },
      assessments: { total: 5, high_risk: 1 },
      templates: { active: 3, total: 5 },
      services: [{ name: 'api', status: 'ok' }],
    })
  if (u.includes('/user/warnings') || u.includes('/reports/pdf/jobs') || u.includes('logs'))
    return mk({ items: [], total: 0 })
  return mk({ items: [], total: 0 })
}

function startServer(csp) {
  const server = http.createServer((req, res) => {
    const headers = { 'Content-Security-Policy': csp }
    if (req.url.startsWith('/api/')) {
      res.writeHead(200, { ...headers, 'Content-Type': 'application/json; charset=utf-8' })
      res.end(JSON.stringify(stubFor(req.url)))
      return
    }
    let urlPath = decodeURIComponent(req.url.split('?')[0])
    if (urlPath === '/' || urlPath.endsWith('/')) urlPath = '/index.html'
    let filePath = path.join(DIST, urlPath)
    // SPA 回退：无扩展名的未知路径一律返回 index.html（对齐 nginx try_files）
    // 注意：没有这一步，所有前端路由都会 404，"零违规" 就是假绿
    if (!fs.existsSync(filePath) && !path.extname(urlPath)) {
      filePath = path.join(DIST, 'index.html')
    }
    if (!filePath.startsWith(DIST) || !fs.existsSync(filePath)) {
      res.writeHead(404, headers)
      res.end('not found')
      return
    }
    res.writeHead(200, {
      ...headers,
      'Content-Type': MIME[path.extname(filePath).toLowerCase()] || 'application/octet-stream',
    })
    fs.createReadStream(filePath).pipe(res)
  })
  return new Promise((resolve) => server.listen(0, () => resolve(server)))
}

async function runVariant(variant) {
  const server = await startServer(variant.csp)
  const port = server.address().port
  const browser = await chromium.launch()
  const out = []

  for (const profile of PROFILES) {
   for (const route of profile.routes) {
    // 每条路由独立上下文：同页连续导航会残留状态（实测后续路由渲染退化到 53 字符）
    const context = await browser.newContext()
    // 登录态 + CSP 违规捕获器，均在任何页面脚本之前注入
    await context.addInitScript(
      ({ role }) => {
        try {
          const user = {
            id: 1,
            username: 'probe',
            role,
            tenant_id: 1,
            permissions: [],
          }
          localStorage.setItem('user', JSON.stringify(user))
          sessionStorage.setItem('token', 'probe-token')
          sessionStorage.setItem('token_expiry', String(Date.now() + 3600_000))
        } catch {}
        window.__cspViolations = []
        document.addEventListener(
          'securitypolicyviolation',
          (e) => {
            window.__cspViolations.push({
              directive: e.violatedDirective,
              blockedURI: e.blockedURI,
              sourceFile: e.sourceFile,
              lineNumber: e.lineNumber,
              columnNumber: e.columnNumber,
              sample: e.sample,
            })
          },
          true
        )
      },
      { role: profile.role }
    )

    const page = await context.newPage()
    const consoleErrs = []
    const pageErrs = []
    page.on('console', (m) => {
      if (m.type() === 'error') consoleErrs.push(m.text().slice(0, 160))
    })
    page.on('pageerror', (e) => pageErrs.push(String(e).slice(0, 160)))

    await page.goto(`http://127.0.0.1:${port}${route}`, { waitUntil: 'load' })
    await page.waitForTimeout(2500)
    const v = await page.evaluate(() => window.__cspViolations || [])
    const dom = await page.evaluate(() => ({
      bodyLen: (document.body.innerText || '').trim().length,
      canvases: document.querySelectorAll('canvas').length,
      appLen: document.getElementById('app')?.innerHTML.length ?? -1,
    }))
    out.push({
      route,
      role: profile.role,
      finalUrl: new URL(page.url()).pathname,
      violations: v.length,
      firstViolation: v[0] || null,
      evalViolations: v.filter((x) => x.blockedURI === 'eval').length,
      bodyLen: dom.bodyLen,
      canvases: dom.canvases,
      appLen: dom.appLen,
      consoleErrs,
      pageErrs,
    })
    await context.close()
   }
  }

  await browser.close()
  server.close()
  return { variant, rows: out }
}

const results = []
for (const v of VARIANTS) results.push(await runVariant(v))

const [A, B] = results
console.log('\n逐路由 A/B 对比  (A=无 unsafe-eval, B=基线)')
console.log('-'.repeat(96))
console.log(
  'route'.padEnd(26),
  'A违规'.padEnd(7),
  'B违规'.padEnd(7),
  'A.eval'.padEnd(8),
  'B.eval'.padEnd(8),
  'A.bodyLen'.padEnd(10),
  'B.bodyLen'.padEnd(10),
  'A.canvas',
  'B.canvas'
)
for (let i = 0; i < A.rows.length; i++) {
  const a = A.rows[i]
  const b = B.rows[i]
  console.log(
    a.route.padEnd(26),
    String(a.violations).padEnd(7),
    String(b.violations).padEnd(7),
    String(a.evalViolations).padEnd(8),
    String(b.evalViolations).padEnd(8),
    String(a.bodyLen).padEnd(10),
    String(b.bodyLen).padEnd(10),
    String(a.canvases).padEnd(8),
    String(b.canvases)
  )
}

const allV = [...A.rows.flatMap((r) => (r.firstViolation ? [r] : []))]
console.log('\nA 档（无 unsafe-eval）全部违规明细：')
if (!allV.length) console.log('  (无)')
allV.forEach((r) => {
  const v = r.firstViolation
  console.log(`  ${r.route}`)
  console.log(`      directive=${v.directive} blocked=${v.blockedURI}`)
  console.log(`      at=${v.sourceFile}:${v.lineNumber}:${v.columnNumber}`)
  if (v.sample) console.log(`      sample=${JSON.stringify(v.sample.slice(0, 140))}`)
})

// 自检：确认每条路由真的渲染了（否则"零违规"是 404 造成的假绿）
const notRendered = A.rows.filter((r) => r.bodyLen < 30 || r.finalUrl !== r.route)
console.log('\n路由渲染自检（A 档）：')
if (!notRendered.length) console.log('  全部 19 条路由均已渲染且 URL 未跳转')
notRendered.forEach((r) =>
  console.log(`  !! ${r.route} 未渲染: finalUrl=${r.finalUrl} bodyLen=${r.bodyLen}`)
)

const totalA = A.rows.reduce((s, r) => s + r.violations, 0)
const totalB = B.rows.reduce((s, r) => s + r.violations, 0)
const lenDiff = A.rows.filter((r, i) => Math.abs(r.bodyLen - B.rows[i].bodyLen) > 0).length
console.log('\n' + '='.repeat(96))
console.log(`A 档违规总数=${totalA}   B 档违规总数=${totalB}`)
console.log(`渲染文本长度 A/B 不一致的路由数=${lenDiff} / ${A.rows.length}`)
console.log(
  totalA > totalB
    ? '裁定：去掉 unsafe-eval 产生新增违规 → 存在 eval 依赖，需按首个违规点治理'
    : '裁定：两档违规数一致（均为 0 或同量）且渲染无差异 → 产物不依赖 eval，unsafe-eval 可移除'
)
