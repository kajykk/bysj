import type { Page, Locator } from '@playwright/test'
import { BasePage } from './BasePage'

/**
 * Monitoring Dashboard Page Object
 */
export class MonitoringDashboardPage extends BasePage {
  constructor(page: Page) {
    super(page, '/monitoring')
  }

  /**
   * Get dashboard title
   */
  getDashboardTitle(): Locator {
    return this.getByTestId('monitoring-dashboard-title')
  }

  /**
   * Get metrics panel
   */
  getMetricsPanel(): Locator {
    return this.getByTestId('metrics-panel')
  }

  /**
   * Get model success rate element
   */
  getModelSuccessRate(): Locator {
    return this.getByTestId('model-success-rate')
  }

  /**
   * Get drift alert list
   */
  getDriftAlertList(): Locator {
    return this.getByTestId('drift-alert-list')
  }

  /**
   * Resolve first alert
   */
  async resolveFirstAlert(): Promise<void> {
    await this.clickByTestId('resolve-alert-btn-0')
    await this.waitForLoad()
  }

  /**
   * Get first alert status
   */
  getFirstAlertStatus(): Locator {
    return this.getByTestId('alert-status-0')
  }

  /**
   * Switch time granularity
   */
  async switchTimeGranularity(granularity: '1h' | '6h' | '24h' | '7d'): Promise<void> {
    await this.clickByTestId(`time-granularity-${granularity}`)
    await this.waitForLoad()
  }
}
