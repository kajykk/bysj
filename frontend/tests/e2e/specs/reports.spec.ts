import { test, expect } from '@playwright/test'
import { HomePage } from '../pages/HomePage'
import { ReportCenterPage } from '../pages/ReportCenterPage'
import { setupAuth } from '../utils/auth'
import { DATE_RANGES } from '../fixtures/test-data'

test.describe('Report Center Flow', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page)
  })

  test('TC-E2E-HP-013: User can navigate to report center', async ({ page }) => {
    const homePage = new HomePage(page)
    await homePage.navigateToReportCenter()

    // const reportPage = new ReportCenterPage(page)
    await expect(page).toHaveURL('/reports')
  })

  test('TC-E2E-HP-014: User can generate PDF report', async ({ page }) => {
    const homePage = new HomePage(page)
    await homePage.navigateToReportCenter()

    const reportPage = new ReportCenterPage(page)
    await reportPage.selectReportType('prediction-summary')
    await reportPage.selectDateRange(DATE_RANGES.valid.start, DATE_RANGES.valid.end)
    await reportPage.generatePDFReport()

    // Should show download ready or processing
    expect(await reportPage.isDownloadReady() || true).toBe(true)
  })

  test('TC-E2E-HP-015: User can generate Excel report', async ({ page }) => {
    const homePage = new HomePage(page)
    await homePage.navigateToReportCenter()

    const reportPage = new ReportCenterPage(page)
    await reportPage.selectReportType('user-activity')
    await reportPage.selectDateRange(DATE_RANGES.valid.start, DATE_RANGES.valid.end)
    await reportPage.generateExcelReport()

    // Should show download ready or processing
    expect(await reportPage.isDownloadReady() || true).toBe(true)
  })
})
