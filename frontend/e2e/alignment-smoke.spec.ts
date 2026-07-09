// frontend/e2e/alignment-smoke.spec.ts
import { test, expect } from '@playwright/test'
import { loginAsRole } from './shared'

test.describe('前后端对齐 smoke', () => {
  test('admin 可见 4 新菜单 + crisis-events + 进入页面', async ({ page }) => {
    await loginAsRole(page, 'admin')
    const navTexts = ['报告中心', '可观测性', '系统监控', '金丝雀管理', '危机事件']
    for (const text of navTexts) {
      await expect(page.getByRole('menuitem', { name: text }).or(page.getByText(text, { exact: true })).first()).toBeVisible()
    }
    const routes = ['/admin/reports', '/admin/observability', '/admin/monitoring', '/admin/canary', '/admin/crisis-events']
    for (const route of routes) {
      await page.goto(route)
      await expect(page).toHaveURL(new RegExp(route.replaceAll('/', '\\/')))
    }
  })

  test('user 可见报告中心入口 + 访问 admin 页面被拒绝', async ({ page }) => {
    await loginAsRole(page, 'user')
    await expect(page.getByText('报告中心', { exact: true }).first()).toBeVisible()
    await page.goto('/admin/canary')
    await expect(page).not.toHaveURL(/\/admin\/canary$/)
  })
})
