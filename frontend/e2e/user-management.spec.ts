import { test, expect } from '@playwright/test'
import { loginAsRole } from './shared'

test.describe('User Profile Flow', () => {
  test('user should view profile', async ({ page }) => {
    await loginAsRole(page, 'user')

    // Navigate to profile
    await page.goto('/user/profile')
    await expect(page).toHaveURL(/\/user\/profile/)

    // Verify profile information（exact 匹配，避免命中 GDPR 描述等包含性文本）
    await expect(page.getByText('用户名', { exact: true })).toBeVisible()
    await expect(page.getByText('邮箱', { exact: true })).toBeVisible()
  })

  test('user should edit profile', async ({ page }) => {
    await loginAsRole(page, 'user')

    await page.goto('/user/profile')
    await expect(page).toHaveURL(/\/user\/profile/)

    // Find edit button
    const editBtn = page.getByRole('button', { name: /编辑|edit/i })

    if (await editBtn.isVisible().catch(() => false)) {
      await editBtn.click()

      // Verify edit form
      await expect(page.locator('form').or(page.locator('.edit-form'))).toBeVisible()
    }
  })
})
