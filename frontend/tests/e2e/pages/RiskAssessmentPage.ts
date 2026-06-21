import type { Page, Locator } from '@playwright/test'
import { BasePage } from './BasePage'

/**
 * Risk Assessment Page Object
 */
export class RiskAssessmentPage extends BasePage {
  constructor(page: Page) {
    super(page, '/risk-assessment')
  }

  /**
   * Fill structured data form
   */
  async fillStructuredData(data: {
    sleepHours: number
    exerciseMinutes: number
    stressLevel: number
  }): Promise<void> {
    await this.fillByTestId('sleep-hours-input', String(data.sleepHours))
    await this.fillByTestId('exercise-minutes-input', String(data.exerciseMinutes))
    await this.fillByTestId('stress-level-input', String(data.stressLevel))
  }

  /**
   * Fill text data
   */
  async fillTextData(text: string): Promise<void> {
    await this.fillByTestId('text-analysis-input', text)
  }

  /**
   * Fill physiological data
   */
  async fillPhysiologicalData(data: {
    heartRate: number
    bloodPressure: string
    temperature: number
  }): Promise<void> {
    await this.fillByTestId('heart-rate-input', String(data.heartRate))
    await this.fillByTestId('blood-pressure-input', data.bloodPressure)
    await this.fillByTestId('temperature-input', String(data.temperature))
  }

  /**
   * Submit assessment
   */
  async submit(): Promise<void> {
    await this.clickByTestId('submit-assessment-btn')
    await this.waitForLoad()
  }

  /**
   * Get result panel
   */
  getResultPanel(): Locator {
    return this.getByTestId('assessment-result-panel')
  }

  /**
   * Get risk score element
   */
  getRiskScore(): Locator {
    return this.getByTestId('risk-score-display')
  }

  /**
   * Get trend chart
   */
  getTrendChart(): Locator {
    return this.getByTestId('trend-chart')
  }
}
