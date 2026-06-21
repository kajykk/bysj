import { test, expect } from '@playwright/test'
import { LoginPage } from '../pages/LoginPage'
import { RiskAssessmentPage } from '../pages/RiskAssessmentPage'
import { setupAuth } from '../utils/auth'

test.describe('Error Handling Flow', () => {
  test('TC-E2E-HP-019: Invalid login shows error message', async ({ page }) => {
    const loginPage = new LoginPage(page)
    await loginPage.goto()

    await loginPage.login('wrong@email.com', 'wrongpassword')

    const errorMessage = await loginPage.getErrorMessage()
    expect(errorMessage).toBeTruthy()
    expect(errorMessage?.toLowerCase()).toContain('error')
  })

  test('TC-E2E-HP-020: Empty form submission shows validation', async ({ page }) => {
    const loginPage = new LoginPage(page)
    await loginPage.goto()

    await loginPage.clickLogin()

    // Should still be on login page with some indication of error
    await expect(page).toHaveURL('/login')
  })

  test('TC-E2E-HP-021: Invalid prediction data handled gracefully', async ({ page }) => {
    await setupAuth(page)

    const riskPage = new RiskAssessmentPage(page)
    await riskPage.goto()

    // Submit with invalid data
    await riskPage.fillStructuredData({
      sleepHours: -5,
      exerciseMinutes: -10,
    })
    await riskPage.submitPrediction()

    // Should not crash, might show error or fallback
    const currentUrl = page.url()
    expect(currentUrl).toContain('risk-assessment')
  })

  test('TC-E2E-HP-022: 404 page handled gracefully', async ({ page }) => {
    await page.goto('/non-existent-page')
    await page.waitForLoadState('networkidle')

    // Should show 404 or redirect
    const currentUrl = page.url()
    expect(currentUrl).not.toContain('non-existent-page')
  })
})
