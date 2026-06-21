import { test, expect } from '@playwright/test'
import { LoginPage } from '../pages/LoginPage'

/**
 * 灰度发布流程 E2E 测试
 * T-E2E-010 ~ T-E2E-012
 */

test.describe('灰度发布流程', () => {
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page)
    await loginPage.goto()
    await loginPage.login('admin', 'admin123')
  })

  test('创建灰度 @critical', async ({ page }) => {
    // 访问灰度管理页面
    await page.goto('/canary')

    // 点击创建灰度按钮
    await page.click('[data-testid="create-canary-btn"]')

    // 填写灰度信息
    await page.fill('[data-testid="canary-name-input"]', 'v1.6.0-test')
    await page.fill('[data-testid="canary-version-input"]', '1.6.0')

    // 提交
    await page.click('[data-testid="submit-canary-btn"]')

    // 验证创建成功
    await expect(page.locator('[data-testid="canary-success-message"]')).toBeVisible()
  })

  test('调整流量 @critical', async ({ page }) => {
    // 访问灰度管理页面
    await page.goto('/canary')

    // 找到第一个灰度并调整流量
    await page.click('[data-testid="adjust-traffic-btn"]')
    await page.fill('[data-testid="traffic-percentage-input"]', '50')
    await page.click('[data-testid="save-traffic-btn"]')

    // 验证更新成功
    await expect(page.locator('[data-testid="traffic-updated-message"]')).toBeVisible()
  })

  test('触发回滚 @critical', async ({ page }) => {
    // 访问灰度管理页面
    await page.goto('/canary')

    // 找到第一个灰度并回滚
    await page.click('[data-testid="rollback-btn"]')

    // 确认回滚
    await page.click('[data-testid="confirm-rollback-btn"]')

    // 验证回滚成功
    await expect(page.locator('[data-testid="rollback-success-message"]')).toBeVisible()
  })
})
