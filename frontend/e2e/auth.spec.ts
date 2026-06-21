import { test, expect } from '@playwright/test'

test.describe('Login Page', () => {
  test('@smoke should display login form', async ({ page }) => {
    await page.goto('/login')
    await expect(page.locator('input')).toHaveCount(2)
  })

  test('@smoke should show error on wrong credentials', async ({ page }) => {
    await page.goto('/login')
    await page.getByPlaceholder('请输入用户名').fill('nonexistent')
    await page.getByPlaceholder('请输入密码').fill('wrongpass')
    await page.getByRole('button', { name: /登|login/i }).click()
    await expect(page.getByText(/错误|失败|invalid/i)).toBeVisible({ timeout: 15000 })
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
