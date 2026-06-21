import type { Page, Locator } from '@playwright/test'
import { BasePage } from './BasePage'

/**
 * Home Page Object
 */
export class HomePage extends BasePage {
  constructor(page: Page) {
    super(page, '/home')
  }

  /**
   * Get welcome message element
   */
  getWelcomeMessage(): Locator {
    return this.getByTestId('home-welcome-message')
  }

  /**
   * Get user info element
   */
  getUserInfo(): Locator {
    return this.getByTestId('home-user-info')
  }

  /**
   * Navigate to risk assessment
   */
  async navigateToRiskAssessment(): Promise<void> {
    await this.clickByTestId('nav-risk-assessment')
  }

  /**
   * Navigate to monitoring
   */
  async navigateToMonitoring(): Promise<void> {
    await this.clickByTestId('nav-monitoring')
  }

  /**
   * Navigate to reports
   */
  async navigateToReports(): Promise<void> {
    await this.clickByTestId('nav-reports')
  }

  /**
   * Navigate to settings
   */
  async navigateToSettings(): Promise<void> {
    await this.clickByTestId('nav-settings')
  }

  /**
   * Click logout button
   */
  async clickLogout(): Promise<void> {
    await this.clickByTestId('header-logout-btn')
  }
}
