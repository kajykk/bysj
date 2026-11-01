import { test } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { loginAsRole } from './shared'

/**
 * UI 视觉改造的基线截图采集器。
 *
 * 默认跳过，只在显式设置 UI_BASELINE=1 时运行：
 *   UI_BASELINE=1 UI_BASELINE_OUT=B0-baseline npx playwright test e2e/ui-baseline.spec.ts
 *
 * 产物落在仓库根 outputs/ui-refresh/<UI_BASELINE_OUT>/（outputs/ 已被 gitignore），
 * 供 docs/UI_BEAUTIFY_PLAN.md 的每批对照使用。
 */

const outputDir = path.resolve(
  fileURLToPath(new URL('.', import.meta.url)),
  '../../outputs/ui-refresh',
  process.env.UI_BASELINE_OUT || 'B0-baseline',
)

const ADMIN_PAGES: Array<[name: string, route: string]> = [
  ['dashboard', '/admin/dashboard'],
  ['operation-logs', '/admin/operation-logs'],
  ['alerts', '/admin/alerts'],
  ['crisis-events', '/admin/crisis-events'],
  ['observability', '/admin/observability'],
  ['settings', '/admin/settings'],
]

const THEMES = ['light', 'dark'] as const

test.describe('UI baseline capture', () => {
  test.skip(!process.env.UI_BASELINE, '仅 UI_BASELINE=1 时采集基线截图')
  test.use({ viewport: { width: 1440, height: 900 } })

  test('capture admin pages in light and dark', async ({ page }) => {
    test.setTimeout(180_000)
    fs.mkdirSync(outputDir, { recursive: true })

    await loginAsRole(page, 'admin')

    const manifest: Array<Record<string, string>> = []

    for (const theme of THEMES) {
      await page.evaluate((value) => localStorage.setItem('theme', value), theme)

      for (const [name, route] of ADMIN_PAGES) {
        await page.goto(route)
        await page.waitForLoadState('domcontentloaded')
        // 等图表/异步卡片稳定；不使用 networkidle —— WebSocket 长连接会让它永不触发
        await page.waitForTimeout(2500)

        const appliedTheme = await page.evaluate(() =>
          document.documentElement.classList.contains('dark') ? 'dark' : 'light',
        )
        if (appliedTheme !== theme) {
          throw new Error(`主题未生效: 期望 ${theme}, 实际 ${appliedTheme} (${route})`)
        }

        const file = `${name}-${theme}.png`
        await page.screenshot({ path: path.join(outputDir, file), fullPage: true })
        manifest.push({ file, route, theme, themeApplied: appliedTheme })
      }
    }

    fs.writeFileSync(
      path.join(outputDir, 'manifest.json'),
      JSON.stringify(
        {
          capturedAt: new Date().toISOString(),
          viewport: '1440x900',
          pages: ADMIN_PAGES.map(([name, route]) => ({ name, route })),
          themes: THEMES,
          shots: manifest,
        },
        null,
        2,
      ),
      'utf8',
    )
  })
})
