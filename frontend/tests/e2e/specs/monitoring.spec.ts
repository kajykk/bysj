import { test, expect } from '@playwright/test'
import { LoginPage } from '../pages/LoginPage'
import { MonitoringDashboardPage } from '../pages/MonitoringDashboardPage'

/**
 * 监控面板流程 E2E 测试
 * T-E2E-007 ~ T-E2E-009
 */

test.describe('监控面板流程', () => {
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page)
    await loginPage.goto()
    await loginPage.login('admin', 'admin123')
  })

  test('管理员访问监控面板 @critical', async ({ page }) => {
    const monitoringPage = new MonitoringDashboardPage(page)

    await monitoringPage.goto()

    // 验证面板加载
    await expect(monitoringPage.getDashboardTitle()).toBeVisible()
    await expect(monitoringPage.getMetricsPanel()).toBeVisible()
  })

  test('查看模型成功率和漂移告警 @critical', async ({ page }) => {
    const monitoringPage = new MonitoringDashboardPage(page)

    await monitoringPage.goto()

    // 验证模型成功率
    await expect(monitoringPage.getModelSuccessRate()).toBeVisible()

    // 验证漂移告警列表
    await expect(monitoringPage.getDriftAlertList()).toBeVisible()
  })

  test('标记告警为已解决 @critical', async ({ page }) => {
    const monitoringPage = new MonitoringDashboardPage(page)

    await monitoringPage.goto()

    // 标记第一个告警为已解决
    await monitoringPage.resolveFirstAlert()

    // 验证告警状态更新
    await expect(monitoringPage.getFirstAlertStatus()).toContainText('已解决')
  })
})
