import { test, expect } from '@playwright/test'
import { LoginPage } from '../pages/LoginPage'
import { HomePage } from '../pages/HomePage'
// import { RiskAssessmentPage } from '../pages/RiskAssessmentPage'
// import { MonitoringDashboardPage } from '../pages/MonitoringDashboardPage'
// import { ReportCenterPage } from '../pages/ReportCenterPage'
import { TEST_USERS } from '../fixtures/test-data'

test.describe('Navigation Flow', () => {
  test('TC-E2E-HP-016: Unauthenticated user is redirected to login', async ({ page }) => {
    // Try to access protected page without login
    await page.goto('/risk-assessment')
    await page.waitForLoadState('networkidle')

    // Should redirect to login
    await expect(page).toHaveURL(/.*login.*/)
  })

  test('TC-E2E-HP-017: Authenticated user can access all pages', async ({ page }) => {
    // Login first
    const loginPage = new LoginPage(page)
    await loginPage.goto()
    await loginPage.login(TEST_USERS.valid.email, TEST_USERS.valid.password)

    // Navigate to different pages
    const homePage = new HomePage(page)

    await homePage.navigateToRiskAssessment()
    await expect(page).toHaveURL('/risk-assessment')

    await homePage.navigateToMonitoring()
    await expect(page).toHaveURL('/monitoring')

    await homePage.navigateToReportCenter()
    await expect(page).toHaveURL('/reports')
  })

  test('TC-E2E-HP-018: User can navigate back to home from any page', async ({ page }) => {
    // Login first
    const loginPage = new LoginPage(page)
    await loginPage.goto()
    await loginPage.login(TEST_USERS.valid.email, TEST_USERS.valid.password)

    // Go to risk assessment
    const homePage = new HomePage(page)
    await homePage.navigateToRiskAssessment()
    await expect(page).toHaveURL('/risk-assessment')

    // Navigate back to home
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page).toHaveURL('/')
  })
})
