import { getCLS, getFID, getFCP, getLCP, getTTFB, type Metric } from 'web-vitals'

import { captureMessage } from '@/plugins/sentry'

export interface WebVitalsReport {
  name: string
  value: number
  rating: 'good' | 'needs-improvement' | 'poor'
  delta?: number
  entries?: PerformanceEntry[]
}

function sendToAnalytics(metric: Metric) {
  const report: WebVitalsReport = {
    name: metric.name,
    value: metric.value,
    rating: metric.rating,
    delta: metric.delta,
    entries: metric.entries,
  }

  // Send to Sentry as breadcrumb
  captureMessage(`Web Vital: ${metric.name}`, 'info')

  // Send to backend analytics endpoint
  if (import.meta.env.PROD) {
    fetch('/api/analytics/web-vitals', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(report),
      keepalive: true,
    }).catch(() => {
      // Silently fail to not impact performance
    })
  }

  // Log to console in development
  if (import.meta.env.DEV) {
    console.log(`[Web Vitals] ${metric.name}:`, report)
  }
}

export function initWebVitals() {
  getCLS(sendToAnalytics)
  getFID(sendToAnalytics)
  getFCP(sendToAnalytics)
  getLCP(sendToAnalytics)
  getTTFB(sendToAnalytics)
}

export function getWebVitalsSummary(): Promise<Record<string, number>> {
  return new Promise((resolve) => {
    const metrics: Record<string, number> = {}
    let count = 0
    const expected = 5

    const collector = (metric: Metric) => {
      metrics[metric.name] = metric.value
      count++
      if (count >= expected) {
        resolve(metrics)
      }
    }

    getCLS(collector)
    getFID(collector)
    getFCP(collector)
    getLCP(collector)
    getTTFB(collector)

    // Timeout after 10 seconds
    setTimeout(() => resolve(metrics), 10000)
  })
}
