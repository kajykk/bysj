// P1-1 性能优化：Sentry SDK 改为动态导入，避免未配置 DSN 时加载 50-100KB 无用代码。
// initSentry 保持同步签名（main.ts 不需改动），内部 fire-and-forget 异步加载。
// captureException/captureMessage 在 Sentry 加载完成前为 no-op，加载后正常上报。
import { type App } from 'vue'
import { type Router } from 'vue-router'
import type { SeverityLevel } from '@sentry/vue'

type SentryModule = typeof import('@sentry/vue')

let sentryModule: SentryModule | null = null

export function initSentry(app: App, router: Router) {
  const dsn = import.meta.env.VITE_SENTRY_DSN
  if (!dsn) {
    console.warn('Sentry DSN not configured')
    return
  }

  // 异步加载 Sentry SDK，不阻塞首屏渲染
  import('@sentry/vue')
    .then((Sentry) => {
      sentryModule = Sentry
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
    })
    .catch((err) => {
      console.warn('Failed to load Sentry:', err)
    })
}

export function captureException(error: Error, context?: Record<string, unknown>) {
  if (!sentryModule) return
  sentryModule.captureException(error, {
    extra: context,
  })
}

export function captureMessage(message: string, level: SeverityLevel = 'info') {
  if (!sentryModule) return
  sentryModule.captureMessage(message, level)
}
