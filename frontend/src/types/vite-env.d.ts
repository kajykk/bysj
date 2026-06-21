interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_BACKEND_PROXY_TARGET?: string
  readonly VITE_CSP_NONCE?: string
  readonly VITE_ENABLE_MOCK_FALLBACK?: string
  readonly VITE_SENTRY_DSN?: string
  readonly VITE_SENTRY_ENVIRONMENT?: string
  readonly VITE_SENTRY_TRACES_SAMPLE_RATE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare interface LayoutShift extends PerformanceEntry {
  value: number
  hadRecentInput: boolean
}
