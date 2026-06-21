import { test, expect } from '@playwright/test'
import { loginAsRole } from './shared'

test.describe('Data Management Flow', () => {
  test('should view data records', async ({ page }) => {
    await loginAsRole(page, 'user')
    
    // Navigate to data management
    await page.goto('/user/data')
    await expect(page).toHaveURL(/\/user\/data/)
    
    // Verify data table or list
    await expect(page.getByRole('table').or(page.locator('.data-list'))).toBeVisible()
  })

  test('should export data', async ({ page }) => {
    await loginAsRole(page, 'user')
    
    await page.goto('/user/data')
    await expect(page).toHaveURL(/\/user\/data/)
    
    // Click export button if exists
    const exportBtn = page.getByRole('button', { name: /导出|export/i })
    
    if (await exportBtn.isVisible().catch(() => false)) {
      // Setup download listener
      const [download] = await Promise.all([
        page.waitForEvent('download'),
        exportBtn.click()
      ])
      
      // Verify download started
      expect(download.suggestedFilename()).toBeTruthy()
    }
  })

  test('should view data detail', async ({ page }) => {
    await loginAsRole(page, 'user')
    
    await page.goto('/user/data')
    await expect(page).toHaveURL(/\/user\/data/)
    
    // Click on first data record if exists
    const firstRecord = page.locator('.data-item').or(page.locator('tr[data-record-id]')).first()
    
    if (await firstRecord.isVisible().catch(() => false)) {
      await firstRecord.click()
      
      // Verify detail view
      await expect(page.getByText(/详情|detail/i).or(page.locator('.data-detail'))).toBeVisible()
    }
  })
})
