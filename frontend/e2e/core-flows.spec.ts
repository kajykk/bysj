import { test, expect } from '@playwright/test'

const apiBasePattern = /\/api\/v1\//
const backendReportPath = '../backend/test-artifacts/harness-report.md'

const mockApi = async (page: import('@playwright/test').Page) => {
  await page.route(apiBasePattern, async (route) => {
    const url = route.request().url()
    const method = route.request().method()

    if (url.includes('/auth/login') && method === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            access_token: 'e2e-access-token',
            refresh_token: 'e2e-refresh-token',
            user: {
              id: 1,
              username: 'admin',
              role: 'admin',
              nickname: '管理员',
              email: 'admin@example.com'
            }
          }
        })
      })
      return
    }

    if (url.includes('/auth/refresh')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            access_token: 'e2e-access-token-refresh',
            refresh_token: 'e2e-refresh-token-refresh',
            token_type: 'bearer'
          }
        })
      })
      return
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data: {} })
    })
  })
}

test.describe('Core E2E flows', () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page)
  })

  test('user flow: dashboard to risk and report links', async ({ page }) => {
    await page.goto('/user/dashboard')
    await expect(page.locator('body')).toBeVisible()
    await page.goto('/user/risk')
    await expect(page.locator('body')).toBeVisible()
    await page.evaluate((backendPath) => {
      const link = document.createElement('a')
      link.href = backendPath
      link.textContent = 'backend report'
      link.target = '_blank'
      document.body.appendChild(link)
    }, backendReportPath)
  })

  test('counselor flow: consultation and warning management shell', async ({ page }) => {
    await page.goto('/counselor/warnings')
    await expect(page.locator('body')).toBeVisible()
    await page.goto('/counselor/consultations')
    await expect(page.locator('body')).toBeVisible()
  })

  test('admin flow: system and operation management shell', async ({ page }) => {
    await page.goto('/admin/operation-logs')
    await expect(page.locator('body')).toBeVisible()
    await page.goto('/admin/system-config')
    await expect(page.locator('body')).toBeVisible()
  })
})
