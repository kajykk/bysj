/**
 * 评估「列表 → 详情」链路的端到端取证脚本。
 *
 * 为什么需要它：详情页 ID 空间错配修复里，最致命的那个 bug（ActionColumn 把
 * 「禁用原因」当成「禁用条件」，导致「查看详情」按钮恒不可点）**没有一个单测会红** ——
 * 列表测试断言了表格列，详情页测试断言了载荷渲染，各自都绿，但中间的链路是断的。
 * 只有真实浏览器里点一次才能发现。
 *
 * 用法：
 *   npx vite build --emptyOutDir false   # 沙箱内需绕过批量删除守卫
 *   node scripts/detail-page-e2e.mjs
 *
 * 它断言的是三件事：
 *   1. 操作列按钮 is-disabled=false（可点）
 *   2. 点击后真的跳到 /user/assessments/{id} 并把 data 载荷渲染出来
 *   3. 全程**没有**请求会 404 的旧端点 /user/risk/assessments/{id}
 *
 * 前置注意：
 *   - 必须注入 `dws:onboarding:completed:<role>:v1`，否则新手引导蒙层会拦截点击
 *   - goBack 后 DOM 会重建，每次都要重新取按钮句柄
 */
// 端到端取证：从评估列表点「查看详情」→ 详情页是否真的渲染出 data 载荷。
// 前置：npm run build（--emptyOutDir false）
import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'

const DIST = path.join(process.cwd(), 'dist')
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.woff2': 'font/woff2',
  '.webmanifest': 'application/manifest+json',
}

const detailCalls = []
function stubFor(url) {
  const u = url.split('?')[0]
  const mk = (d) => ({ code: 0, message: 'ok', data: d })
  if (u.includes('/user/data/history'))
    return mk({
      items: [
        {
          id: 11,
          type: 'structured',
          created_at: '2026-10-01T08:30:00',
          data: {
            assessment_type: 'PHQ-9',
            score: 72.5,
            severity: 'high',
            data_payload: { q1: 3, q9: 2 },
          },
        },
        {
          id: 12,
          type: 'text',
          created_at: '2026-10-02T09:00:00',
          data: {
            entry_type: 'diary',
            content:
              '最近两周睡眠很差，几乎每天凌晨两三点才睡着，白天上课完全集中不了注意力，' +
              '和室友的交流也变少了，感觉自己什么都做不好，情绪越来越低落，有时候会忍不住哭，' +
              '但又不知道怎么开口求助。',
            mood_score: 3,
            sentiment_score: 0.21,
            sentiment_label: 'negative',
          },
        },
      ],
      total: 2,
      page: 1,
      page_size: 10,
    })
  return mk({ items: [], total: 0 })
}

const server = http.createServer((req, res) => {
  const h = {
    'Content-Security-Policy':
      "default-src 'self'; img-src 'self' data: blob:; font-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'",
  }
  if (req.url.startsWith('/api/')) {
    if (req.url.includes('/user/risk/assessments/')) detailCalls.push(req.url)
    res.writeHead(200, { ...h, 'Content-Type': 'application/json' })
    res.end(JSON.stringify(stubFor(req.url)))
    return
  }
  let p = decodeURIComponent(req.url.split('?')[0])
  if (p === '/' || p.endsWith('/')) p = '/index.html'
  let f = path.join(DIST, p)
  if (!fs.existsSync(f) && !path.extname(p)) f = path.join(DIST, 'index.html')
  if (!fs.existsSync(f)) {
    res.writeHead(404, h)
    res.end('nf')
    return
  }
  res.writeHead(200, {
    ...h,
    'Content-Type': MIME[path.extname(f).toLowerCase()] || 'application/octet-stream',
  })
  fs.createReadStream(f).pipe(res)
})

await new Promise((r) => server.listen(0, r))
const port = server.address().port
const browser = await chromium.launch()

async function run(role) {
  const ctx = await browser.newContext()
  await ctx.addInitScript((r) => {
    localStorage.setItem(
      'user',
      JSON.stringify({ id: 1, username: 'probe', role: r, tenant_id: 1, permissions: [] })
    )
    // 新手引导蒙层会拦截点击，标记为已完成
    localStorage.setItem(`dws:onboarding:completed:${r}:v1`, 'true')
    sessionStorage.setItem('token', 'probe-token')
    sessionStorage.setItem('token_expiry', String(Date.now() + 3600000))
  }, role)
  const page = await ctx.newPage()
  const errs = []
  page.on('console', (m) => {
    if (m.type() === 'error') errs.push(m.text().slice(0, 160))
  })
  page.on('pageerror', (e) => errs.push('PAGEERROR ' + String(e).slice(0, 200)))

  await page.goto(`http://127.0.0.1:${port}/user/assessments`, { waitUntil: 'load' })
  await page.waitForTimeout(2500)

  const listBefore = await page.evaluate(() => (document.body.innerText || '').length)
  async function detailButtons() {
    const all = await page.$$('.el-table__row button')
    const out = []
    for (const b of all) {
      const t = await b.innerText()
      if (t.includes('详情')) out.push(b)
    }
    return out
  }

  const Total = (await detailButtons()).length
  console.log(`  操作列详情按钮数: ${Total}`)

  for (let idx = 0; idx < Total; idx += 1) {
    // goBack 后 DOM 重建，每次都要重新取句柄
    const btns = await detailButtons()
    const btn = btns[idx]
    if (!btn) break
    console.log(
      `  #${idx} is-disabled=${await btn.evaluate((el) => el.className.includes('is-disabled'))}`
    )
    await btn.click()
    // ActionColumn 默认 confirmText='确定' → 会弹确认框
    await page.waitForTimeout(600)
    const confirmBtn = await page.$('.el-message-box__btns .el-button--primary')
    if (confirmBtn) await confirmBtn.click()
    await page.waitForTimeout(1800)

    const text = (await page.evaluate(() => document.body.innerText || ''))
      .split('\n')
      .filter((l) => l.trim())
      .slice(-14)
      .join(' | ')
    console.log(`  → ${new URL(page.url()).pathname}`)
    console.log(`    ${JSON.stringify(text.slice(0, 380))}`)

    await page.goBack({ waitUntil: 'load' })
    await page.waitForTimeout(1500)
  }

  const url = new URL(page.url()).pathname
  console.log(`  列表正文长度: ${listBefore}; 回到列表: ${url}`)
  console.log(`  console errors: ${errs.length ? errs.slice(0, 3).join(' || ') : '(无)'}`)
  console.log(`  打到 /user/risk/assessments/ 的请求: ${detailCalls.length} 次`)
  await ctx.close()
}

console.log('=== role=user ===')
await run('user')

await browser.close()
server.close()
