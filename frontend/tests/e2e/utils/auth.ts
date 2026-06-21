import type { Page } from '@playwright/test'
import { LoginPage } from '../pages/LoginPage'

/**
 * Authentication utilities for E2E tests
 */

/**
 * Login with valid credentials
 */
export async function login(page: Page, email: string, password: string): Promise<void> {
  const loginPage = new LoginPage(page)
  await loginPage.goto()
  await loginPage.login(email, password)
}

/**
 * Logout current user
 */
export async function logout(page: Page): Promise<void> {
  await page.goto('/')
  await page.waitForLoadState('networkidle')

  const userMenu = page.locator('[data-testid="user-menu"]')
  if (await userMenu.isVisible().catch(() => false)) {
    await userMenu.click()
    await page.locator('[data-testid="logout-button"]').click()
    await page.waitForURL('**/login')
  }
}

/**
 * Check if user is authenticated
 */
export async function isAuthenticated(page: Page): Promise<boolean> {
  await page.goto('/')
  await page.waitForLoadState('networkidle')
  const userMenu = page.locator('[data-testid="user-menu"]')
  return userMenu.isVisible().catch(() => false)
}

/**
 * Setup authenticated state
 */
export async function setupAuth(page: Page): Promise<void> {
  // Check if already authenticated
  if (await isAuthenticated(page)) {
    return
  }

  // Login with test credentials
  await login(page, 'test@example.com', 'TestPassword123')
}
