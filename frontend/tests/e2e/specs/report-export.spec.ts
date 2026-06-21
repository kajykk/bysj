import { test, expect } from '@playwright/test'
import { LoginPage } from '../pages/LoginPage'
import { ReportCenterPage } from '../pages/ReportCenterPage'

/**
 * 报告导出流程 E2E 测试
 * T-E2E-013 ~ T-E2E-014
 */

test.describe('报告导出流程', () => {
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page)
    await loginPage.goto()
    await loginPage.login('testuser', 'password123')
  })

  test('生成 PDF 并下载 @critical', async ({ page }) => {
    const reportPage = new ReportCenterPage(page)

    await reportPage.goto()

    // 选择报告类型
    await reportPage.selectReportType('userRisk')

    // 生成 PDF
    await reportPage.generatePDF()

    // 验证下载成功
    await expect(reportPage.getDownloadSuccessMessage()).toBeVisible()
  })

  test('批量导出 Excel 并下载 @critical', async ({ page }) => {
    const reportPage = new ReportCenterPage(page)

    await reportPage.goto()

    // 选择导出类型
    await reportPage.selectReportType('batch')

    // 生成 Excel
    await reportPage.generateExcel()

    // 验证下载成功
    await expect(reportPage.getDownloadSuccessMessage()).toBeVisible()
  })
})
