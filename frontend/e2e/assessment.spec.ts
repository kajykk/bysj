import { test, expect } from '@playwright/test'
import { loginAsRole } from './shared'

test.describe('Assessment Flow', () => {
  test('should render structured assessment form', async ({ page }) => {
    await loginAsRole(page, 'user')

    await page.goto('/user/risk')
    await expect(page).toHaveURL(/\/user\/risk/)

    const structuredTab = page.getByRole('tab', { name: /结构化评估|structured/i })
    if (!(await structuredTab.isVisible().catch(() => false))) {
      test.skip(true, '当前用户无结构化评估权限，跳过')
      return
    }
    await structuredTab.click()

    // 单页模式表单应包含提交按钮
    await expect(page.getByRole('button', { name: /提交|submit/i })).toBeVisible({ timeout: 10000 })
  })

  test('should show validation for incomplete assessment', async ({ page }) => {
    await loginAsRole(page, 'user')

    await page.goto('/user/risk')
    await expect(page).toHaveURL(/\/user\/risk/)

    const structuredTab = page.getByRole('tab', { name: /结构化评估|structured/i })
    if (!(await structuredTab.isVisible().catch(() => false))) {
      test.skip(true, '当前用户无结构化评估权限，跳过')
      return
    }
    await structuredTab.click()

    // 表单字段自带默认值，直接提交会通过校验；先清空必填的年龄字段再提交
    const ageInput = page.locator('.el-input-number').first().locator('input')
    await ageInput.click()
    await ageInput.press('Control+A')
    await ageInput.press('Backspace')

    // 提交后应触发必填校验错误
    await page.getByRole('button', { name: /提交|submit/i }).click()
    await expect(page.locator('.el-form-item__error').first()).toBeVisible({ timeout: 10000 })
  })

  test('should view assessment history', async ({ page }) => {
    await loginAsRole(page, 'user')

    await page.goto('/user/assessments')
    await expect(page).toHaveURL(/\/user\/assessments/)

    // el-table 渲染表头/表体两个 table，取第一个
    await expect(page.getByRole('table').first()).toBeVisible()
  })
})
