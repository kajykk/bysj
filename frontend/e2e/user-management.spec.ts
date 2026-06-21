import { test, expect } from '@playwright/test'
import { loginAsRole } from './shared'

test.describe('User Management Flow', () => {
  test('admin should view user list', async ({ page }) => {
    await loginAsRole(page, 'admin')
    
    // Navigate to user management
    await page.goto('/admin/users')
    await expect(page).toHaveURL(/\/admin\/users/)
    
    // Verify user table
    await expect(page.getByRole('table')).toBeVisible()
    
    // Verify page heading
    await expect(page.getByRole('heading', { name: /用户|user/i })).toBeVisible()
  })

  test('admin should search users', async ({ page }) => {
    await loginAsRole(page, 'admin')
    
    await page.goto('/admin/users')
    await expect(page).toHaveURL(/\/admin\/users/)
    
    // Find search input
    const searchInput = page.getByPlaceholder(/搜索|search/i).or(page.locator('input[type="search"]')).first()
    
    if (await searchInput.isVisible().catch(() => false)) {
      await searchInput.fill('test')
      await searchInput.press('Enter')
      
      // Verify search results
      await expect(page.getByRole('table')).toBeVisible()
    }
  })

  test('user should view profile', async ({ page }) => {
    await loginAsRole(page, 'user')
    
    // Navigate to profile
    await page.goto('/user/profile')
    await expect(page).toHaveURL(/\/user\/profile/)
    
    // Verify profile information
    await expect(page.getByText(/用户名|username/i)).toBeVisible()
    await expect(page.getByText(/邮箱|email/i)).toBeVisible()
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
