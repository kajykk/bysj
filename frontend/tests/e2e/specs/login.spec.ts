import { test, expect } from '@playwright/test'
import { LoginPage } from '../pages/LoginPage'
import { HomePage } from '../pages/HomePage'

/**
 * 用户登录流程 E2E 测试
 * T-E2E-001 ~ T-E2E-003
 */

test.describe('用户登录流程', () => {
  test('正常登录跳转首页 @critical', async ({ page }) => {
    const loginPage = new LoginPage(page)
    const homePage = new HomePage(page)

    await loginPage.goto()
    await loginPage.login('testuser', 'password123')

    // 验证跳转到首页
    await expect(page).toHaveURL(/.*home/)
    await expect(homePage.getWelcomeMessage()).toBeVisible()
  })

  test('错误密码提示错误 @critical', async ({ page }) => {
    const loginPage = new LoginPage(page)

    await loginPage.goto()
    await loginPage.login('testuser', 'wrongpassword')

    // 验证错误提示
    await expect(loginPage.getErrorMessage()).toBeVisible()
    await expect(loginPage.getErrorMessage()).toContainText('用户名或密码错误')
  })

  test('未认证访问跳转登录页 @critical', async ({ page }) => {
    // 直接访问需要认证的页面
    await page.goto('/dashboard')

    // 验证重定向到登录页
    await expect(page).toHaveURL(/.*login/)
  })
})
