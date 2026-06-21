import type { Page, Locator } from '@playwright/test'
import { BasePage } from './BasePage'

/**
 * Report Center Page Object
 */
export class ReportCenterPage extends BasePage {
  constructor(page: Page) {
    super(page, '/reports')
  }

  /**
   * Select report type
   */
  async selectReportType(type: string): Promise<void> {
    await this.clickByTestId(`report-type-${type}`)
  }

  /**
   * Generate PDF report
   */
  async generatePDF(): Promise<void> {
    await this.clickByTestId('generate-pdf-btn')
    await this.waitForLoad()
  }

  /**
   * Generate Excel report
   */
  async generateExcel(): Promise<void> {
    await this.clickByTestId('generate-excel-btn')
    await this.waitForLoad()
  }

  /**
   * Get download success message
   */
  getDownloadSuccessMessage(): Locator {
    return this.getByTestId('download-success-message')
  }

  /**
   * Get export history list
   */
  getExportHistoryList(): Locator {
    return this.getByTestId('export-history-list')
  }

  /**
   * Select date range
   */
  async selectDateRange(startDate: string, endDate: string): Promise<void> {
    await this.fillByTestId('date-range-start', startDate)
    await this.fillByTestId('date-range-end', endDate)
  }
}
