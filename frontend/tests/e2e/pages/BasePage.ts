import type { Page, Locator } from '@playwright/test'

/**
 * Base Page Object for E2E tests.
 * Provides common navigation, interaction, and assertion capabilities.
 */
export abstract class BasePage {
  protected page: Page
  protected baseUrl: string

  constructor(page: Page, baseUrl: string = '/') {
    this.page = page
    this.baseUrl = baseUrl
  }

  /**
   * Navigate to the page URL
   */
  async goto(): Promise<void> {
    await this.page.goto(this.baseUrl)
  }

  /**
   * Wait for page to be fully loaded
   */
  async waitForLoad(): Promise<void> {
    await this.page.waitForLoadState('networkidle')
  }

  /**
   * Get element by data-testid
   */
  getByTestId(testId: string): Locator {
    return this.page.locator(`[data-testid="${testId}"]`)
  }

  /**
   * Click element by data-testid
   */
  async clickByTestId(testId: string): Promise<void> {
    await this.getByTestId(testId).click()
  }

  /**
   * Fill input by data-testid
   */
  async fillByTestId(testId: string, value: string): Promise<void> {
    await this.getByTestId(testId).fill(value)
  }

  /**
   * Get text content by data-testid
   */
  async getTextByTestId(testId: string): Promise<string | null> {
    return this.getByTestId(testId).textContent()
  }

  /**
   * Check if element is visible
   */
  async isVisible(testId: string): Promise<boolean> {
    return this.getByTestId(testId).isVisible()
  }

  /**
   * Wait for element to be visible
   */
  async waitForVisible(testId: string, timeout: number = 5000): Promise<void> {
    await this.getByTestId(testId).waitFor({ state: 'visible', timeout })
  }

  /**
   * Wait for element to be hidden
   */
  async waitForHidden(testId: string, timeout: number = 5000): Promise<void> {
    await this.getByTestId(testId).waitFor({ state: 'hidden', timeout })
  }

  /**
   * Assert element contains text
   */
  async assertContainsText(testId: string, expectedText: string): Promise<void> {
    await this.getByTestId(testId).waitFor({ state: 'visible' })
    const text = await this.getTextByTestId(testId)
    if (!text?.includes(expectedText)) {
      throw new Error(`Expected element [data-testid="${testId}"] to contain "${expectedText}", but got "${text}"`)
    }
  }

  /**
   * Take screenshot
   */
  async screenshot(name: string): Promise<void> {
    await this.page.screenshot({ path: `tests/e2e/screenshots/${name}.png` })
  }

  /**
   * Get current URL
   */
  getUrl(): string {
    return this.page.url()
  }

  /**
   * Wait for URL to contain path
   */
  async waitForUrl(path: string, timeout: number = 5000): Promise<void> {
    await this.page.waitForURL(`**${path}`, { timeout })
  }
}
