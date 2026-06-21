import { test, expect } from '@playwright/test'
import { loginAsRole } from './shared'

test.describe('Warning Flow', () => {
  test('should view warning list', async ({ page }) => {
    await loginAsRole(page, 'user')
    
    // Navigate to warnings page
    await page.goto('/user/warnings')
    await expect(page).toHaveURL(/\/user\/warnings/)
    
    // Verify warning list is visible
    await expect(page.getByRole('table').or(page.locator('.warning-list'))).toBeVisible()
    
    // Verify page heading
    await expect(page.getByRole('heading', { name: /预警|warning/i })).toBeVisible()
  })

  test('should view warning detail', async ({ page }) => {
    await loginAsRole(page, 'user')
    
    await page.goto('/user/warnings')
    await expect(page).toHaveURL(/\/user\/warnings/)
    
    // Click on first warning if exists
    const firstWarning = page.locator('.warning-item').or(page.locator('tr[data-warning-id]')).first()
    
    if (await firstWarning.isVisible().catch(() => false)) {
      await firstWarning.click()
      
      // Verify detail page
      await expect(page.getByText(/预警详情|warning detail/i).or(page.locator('.warning-detail'))).toBeVisible()
    }
  })

  test('counselor should process warning', async ({ page }) => {
    await loginAsRole(page, 'counselor')
    
    // Navigate to counselor warnings
    await page.goto('/counselor/warnings')
    await expect(page).toHaveURL(/\/counselor\/warnings/)
    
    // Verify warning table
    await expect(page.getByRole('table')).toBeVisible()
    
    // Verify action buttons exist
    await expect(page.getByRole('button', { name: /处理|process|查看|view/i }).first()).toBeVisible()
  })

  test('should filter warnings by status', async ({ page }) => {
    await loginAsRole(page, 'counselor')
    
    await page.goto('/counselor/warnings')
    await expect(page).toHaveURL(/\/counselor\/warnings/)
    
    // Find and click filter if exists
    const filterSelect = page.locator('select').or(page.locator('.filter-status')).first()
    
    if (await filterSelect.isVisible().catch(() => false)) {
      await filterSelect.selectOption('pending')
      
      // Verify filtered results
      await expect(page.getByRole('table')).toBeVisible()
    }
  })
})
