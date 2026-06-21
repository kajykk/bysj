import { test, expect } from '@playwright/test'
import { loginAsRole } from './shared'

test.describe('Assessment Flow', () => {
  test('should complete PHQ-9 assessment', async ({ page }) => {
    await loginAsRole(page, 'user')
    
    // Navigate to assessment page
    await page.goto('/user/assessment')
    await expect(page).toHaveURL(/\/user\/assessment/)
    
    // Fill PHQ-9 questionnaire
    const questions = page.locator('.phq9-question')
    const count = await questions.count()
    
    for (let i = 0; i < count; i++) {
      await questions.nth(i).locator('input[type="radio"]').first().check()
    }
    
    // Submit assessment
    await page.getByRole('button', { name: /提交|submit/i }).click()
    
    // Verify result page
    await expect(page.getByText(/评估结果|assessment result/i)).toBeVisible({ timeout: 15000 })
    await expect(page.getByText(/分数|score/i)).toBeVisible()
  })

  test('should show validation for incomplete assessment', async ({ page }) => {
    await loginAsRole(page, 'user')
    
    await page.goto('/user/assessment')
    await expect(page).toHaveURL(/\/user\/assessment/)
    
    // Try to submit without answering
    await page.getByRole('button', { name: /提交|submit/i }).click()
    
    // Verify validation message
    await expect(page.getByText(/请回答|required|请完成/i).first()).toBeVisible({ timeout: 10000 })
  })

  test('should view assessment history', async ({ page }) => {
    await loginAsRole(page, 'user')
    
    await page.goto('/user/assessment/history')
    await expect(page).toHaveURL(/\/user\/assessment\/history/)
    
    // Verify history table or list
    await expect(page.getByRole('table').or(page.locator('.assessment-list'))).toBeVisible()
  })
})
