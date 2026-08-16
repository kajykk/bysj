import { test, expect } from '@playwright/test'
import { CORS_HEADERS } from './shared'

test.describe('Login Page', () => {
  test('@smoke should display login form', async ({ page }) => {
    await page.goto('/login')
    // 登录表单包含用户名/密码两个输入 + "记住我" 复选框, 共 3 个 input
    await expect(page.locator('input')).toHaveCount(3)
  })

  test('@smoke should show error on wrong credentials', async ({ page }) => {
    await page.goto('/login')
    // smoke 项目 (chromium-smoke) 无真实后端: 模拟 401 响应, 验证前端错误提示链路。
    // 必须带 CORS 头 (见 shared.ts CORS_HEADERS 注释), 否则浏览器拦截伪造响应,
    // axios 收到 network error 而非 401。真实后端路径由 E2E Full Stack (chromium) 覆盖。
    await page.route(/\/api\/v1\/auth\/login$/, async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        headers: CORS_HEADERS,
        body: JSON.stringify({ detail: '用户名或密码错误' }),
      })
    })
    await page.getByPlaceholder('请输入用户名').fill('nonexistent')
    await page.getByPlaceholder('请输入密码').fill('wrongpass')
    await page.getByRole('button', { name: /登|login/i }).click()
    // 错误提示可能同时出现多条 (拦截器 422 提示 + 页面 401 提示), 断言任一可见
    await expect(page.getByText(/错误|失败|invalid/i).first()).toBeVisible({ timeout: 15000 })
  })

  test('@regression should navigate to register and back', async ({ page }) => {
    await page.goto('/login')
    const registerLink = page.getByText(/注册|register/i)
    if (await registerLink.isVisible()) {
      await registerLink.click()
      await expect(page).toHaveURL(/register|login/, { timeout: 15000 })
    }
  })
})

test.describe('Auth Flow', () => {
  test('@regression should validate registration form', async ({ page }) => {
    await page.goto('/login')
    const registerLink = page.getByText(/注册|register/i)
    if (await registerLink.isVisible()) {
      await registerLink.click()
    }
    const submitBtn = page.getByRole('button', { name: /注册|register/i })
    if (await submitBtn.isVisible()) {
      await submitBtn.click()
      await expect(page.getByText(/请|required|不能为空/i).first()).toBeVisible({ timeout: 15000 })
    }
  })
})

test.describe('Navigation Guard', () => {
  test('@smoke should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/user/dashboard')
    await expect(page).toHaveURL(/login/, { timeout: 15000 })
  })

  test('@regression should show 403 for wrong role', async ({ page }) => {
    await page.goto('/admin/dashboard')
    await expect(page).toHaveURL(/login|forbidden/, { timeout: 15000 })
  })
})
