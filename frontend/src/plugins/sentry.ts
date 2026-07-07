import * as Sentry from '@sentry/vue'
import { type App } from 'vue'
import { type Router } from 'vue-router'

export function initSentry(app: App, router: Router) {
  const dsn = import.meta.env.VITE_SENTRY_DSN
  if (!dsn) {
    console.warn('Sentry DSN not configured')
    return
  }

  Sentry.init({
    app,
    dsn,
    integrations: [
      Sentry.browserTracingIntegration({ router }),
      Sentry.replayIntegration({
        maskAllText: true,
        blockAllMedia: true,
        maskAllInputs: true,
      }),
    ],
    // L-FE-7 修复：生产环境默认采样率从 0.1 降为 0.01 减少配额消耗，开发环境保持 1.0 便于排查
    tracesSampleRate: parseFloat(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE || (import.meta.env.PROD ? '0.01' : '1.0')),
    // M-36 修复：降低常规会话录制率，减少带宽和存储消耗
    // 默认从 0.1 (10%) 降低到 0.01 (1%)，错误会话保持 100% 录制
    replaysSessionSampleRate: parseFloat(import.meta.env.VITE_SENTRY_REPLAYS_SAMPLE_RATE || '0.01'),
    replaysOnErrorSampleRate: 1.0,
    environment: import.meta.env.MODE,
    // M-FE-16 修复：过滤常见噪声错误，避免 Sentry 配额浪费
    ignoreErrors: [
      'ResizeObserver loop limit exceeded',
      'ResizeObserver loop completed with undelivered notifications',
      'Network Error',
      'Navigation cancelled',
      'Request aborted',
      'timeout of 0ms exceeded',
    ],
    // M-FE-16 修复：过滤来自浏览器扩展和本地预览的 URL
    denyUrls: [
      /chrome-extension:\/\//,
      /moz-extension:\/\//,
      /safari-extension:\/\//,
      /extensions\//,
    ],
    // L-04 修复：release 可能为 undefined（VITE_APP_VERSION 未配置时），传 undefined 会导致 Sentry 警告
    // 仅在 release 有值时传入
    ...(import.meta.env.VITE_APP_VERSION ? { release: import.meta.env.VITE_APP_VERSION } : {}),
  })
}

export function captureException(error: Error, context?: Record<string, unknown>) {
  Sentry.captureException(error, {
    extra: context,
  })
}

export function captureMessage(message: string, level: Sentry.SeverityLevel = 'info') {
  Sentry.captureMessage(message, level)
}
