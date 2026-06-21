import { test, expect } from '@playwright/test'
import { LoginPage } from '../pages/LoginPage'
import { RiskAssessmentPage } from '../pages/RiskAssessmentPage'

/**
 * 风险评估流程 E2E 测试
 * T-E2E-004 ~ T-E2E-006
 */

test.describe('风险评估流程', () => {
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page)
    await loginPage.goto()
    await loginPage.login('testuser', 'password123')
  })

  test('结构化数据提交到结果展示 @critical', async ({ page }) => {
    const riskPage = new RiskAssessmentPage(page)

    await riskPage.goto()
    await riskPage.fillStructuredData({
      sleepHours: 7,
      exerciseMinutes: 30,
      stressLevel: 3,
    })
    await riskPage.submit()

    // 验证结果展示
    await expect(riskPage.getResultPanel()).toBeVisible()
    await expect(riskPage.getRiskScore()).toBeVisible()
  })

  test('文本上传分析到报告查看 @critical', async ({ page }) => {
    const riskPage = new RiskAssessmentPage(page)

    await riskPage.goto()
    await riskPage.fillTextData('最近工作压力很大，睡眠质量不好')
    await riskPage.submit()

    // 验证结果展示
    await expect(riskPage.getResultPanel()).toBeVisible()
  })

  test('生理数据录入到趋势查看 @critical', async ({ page }) => {
    const riskPage = new RiskAssessmentPage(page)

    await riskPage.goto()
    await riskPage.fillPhysiologicalData({
      heartRate: 72,
      bloodPressure: '120/80',
      temperature: 36.5,
    })
    await riskPage.submit()

    // 验证结果展示
    await expect(riskPage.getResultPanel()).toBeVisible()
    await expect(riskPage.getTrendChart()).toBeVisible()
  })
})
