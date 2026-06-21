import type { Page } from '@playwright/test'
import { BasePage } from './BasePage'

/**
 * Login Page Object
 */
export class LoginPage extends BasePage {
  constructor(page: Page) {
    super(page, '/login')
  }

  /**
   * Navigate to login page
   */
  async goto(): Promise<void> {
    await this.page.goto('/login')
    await this.waitForLoad()
  }

  /**
   * Fill email input
   */
  async fillEmail(email: string): Promise<void> {
    await this.fillByTestId('login-email', email)
  }

  /**
   * Fill password input
   */
  async fillPassword(password: string): Promise<void> {
    await this.fillByTestId('login-password', password)
  }

  /**
   * Click login button
   */
  async clickLogin(): Promise<void> {
    await this.clickByTestId('login-submit')
  }

  /**
   * Perform full login
   */
  async login(email: string, password: string): Promise<void> {
    await this.fillEmail(email)
    await this.fillPassword(password)
    await this.clickLogin()
    await this.waitForLoad()
  }

  /**
   * Get error message
   */
  async getErrorMessage(): Promise<string | null> {
    return this.getTextByTestId('login-error')
  }

  /**
   * Check if login form is visible
   */
  async isLoginFormVisible(): Promise<boolean> {
    return this.isVisible('login-form')
  }

  /**
   * Click register link
   */
  async clickRegister(): Promise<void> {
    await this.clickByTestId('login-register-link')
  }

  /**
   * Click forgot password link
   */
  async clickForgotPassword(): Promise<void> {
    await this.clickByTestId('login-forgot-password')
  }
}
