declare module 'web-vitals' {
  export type MetricRating = 'good' | 'needs-improvement' | 'poor'

  export interface Metric {
    name: 'CLS' | 'FCP' | 'FID' | 'INP' | 'LCP' | 'TTFB'
    value: number
    rating: MetricRating
    delta: number
    id: string
    entries: PerformanceEntry[]
  }

  export type ReportCallback = (metric: Metric) => void

  export function getCLS(onReport: ReportCallback, opts?: { reportAllChanges?: boolean }): void
  export function getFID(onReport: ReportCallback, opts?: { reportAllChanges?: boolean }): void
  export function getFCP(onReport: ReportCallback, opts?: { reportAllChanges?: boolean }): void
  export function getLCP(onReport: ReportCallback, opts?: { reportAllChanges?: boolean }): void
  export function getTTFB(onReport: ReportCallback, opts?: { reportAllChanges?: boolean }): void
  export function getINP(onReport: ReportCallback, opts?: { reportAllChanges?: boolean }): void
}
