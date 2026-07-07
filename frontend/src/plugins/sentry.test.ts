import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { type App } from 'vue'

/**
 * Sentry 插件单元测试
 * T-COV-SEN-FE-001: 前端 Sentry 集成
 *
 * 覆盖目标：initSentry、captureException、captureMessage 全部导出函数
 * 覆盖 initSentry 的 DSN 未配置早返回、生产/开发环境采样率差异、release 可选配置等分支
 */

// Mock @sentry/vue：拦截所有 Sentry API 调用，提供可观测的 spy
vi.mock('@sentry/vue', () => ({
  init: vi.fn(),
  captureException: vi.fn(),
  captureMessage: vi.fn(),
  browserTracingIntegration: vi.fn(),
  replayIntegration: vi.fn(),
}))

import * as Sentry from '@sentry/vue'
import { initSentry, captureException, captureMessage } from './sentry'

/** 构造最小可用的 app 对象，Sentry.init 被 mock 后不会实际使用 */
function createMockApp(): App {
  return { config: { globalProperties: {} } } as unknown as App
}

/** 构造最小 router 对象，仅传给 browserTracingIntegration */
function createMockRouter(): unknown {
  return { _isMockRouter: true }
}

describe('Sentry Plugin - T-COV-SEN-FE-001', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.unstubAllEnvs()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  describe('initSentry', () => {
    it('DSN 未配置（空字符串）时应早返回并输出 console.warn', () => {
      vi.stubEnv('VITE_SENTRY_DSN', '')
      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

      initSentry(createMockApp(), createMockRouter())

      expect(Sentry.init).not.toHaveBeenCalled()
      expect(warnSpy).toHaveBeenCalledWith('Sentry DSN not configured')
      warnSpy.mockRestore()
    })

    it('DSN 为 undefined 时也应早返回并输出 console.warn', () => {
      // 不 stub VITE_SENTRY_DSN，默认 undefined
      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

      initSentry(createMockApp(), createMockRouter())

      expect(Sentry.init).not.toHaveBeenCalled()
      expect(warnSpy).toHaveBeenCalledWith('Sentry DSN not configured')
      warnSpy.mockRestore()
    })

    it('配置 DSN 后应调用 Sentry.init 并传入 dsn 与 environment', () => {
      vi.stubEnv('VITE_SENTRY_DSN', 'https://test@sentry.io/1')
      vi.stubEnv('MODE', 'development')

      initSentry(createMockApp(), createMockRouter())

      expect(Sentry.init).toHaveBeenCalledTimes(1)
      const initArgs = vi.mocked(Sentry.init).mock.calls[0][0] as any
      expect(initArgs.dsn).toBe('https://test@sentry.io/1')
      expect(initArgs.environment).toBe('development')
    })

    it('开发环境（PROD=false）默认 tracesSampleRate 应为 1.0', () => {
      vi.stubEnv('VITE_SENTRY_DSN', 'https://test@sentry.io/1')
      // 默认 PROD=false（vitest test 模式）
      // 不设置 VITE_SENTRY_TRACES_SAMPLE_RATE

      initSentry(createMockApp(), createMockRouter())

      const initArgs = vi.mocked(Sentry.init).mock.calls[0][0] as any
      expect(initArgs.tracesSampleRate).toBe(1.0)
    })

    it('生产环境（PROD=true）默认 tracesSampleRate 应为 0.01', () => {
      vi.stubEnv('VITE_SENTRY_DSN', 'https://test@sentry.io/1')
      vi.stubEnv('PROD', true as any)
      // 不设置 VITE_SENTRY_TRACES_SAMPLE_RATE，使用 PROD 三元运算

      initSentry(createMockApp(), createMockRouter())

      const initArgs = vi.mocked(Sentry.init).mock.calls[0][0] as any
      expect(initArgs.tracesSampleRate).toBe(0.01)
    })

    it('自定义 VITE_SENTRY_TRACES_SAMPLE_RATE 应覆盖默认值', () => {
      vi.stubEnv('VITE_SENTRY_DSN', 'https://test@sentry.io/1')
      vi.stubEnv('VITE_SENTRY_TRACES_SAMPLE_RATE', '0.5')

      initSentry(createMockApp(), createMockRouter())

      const initArgs = vi.mocked(Sentry.init).mock.calls[0][0] as any
      expect(initArgs.tracesSampleRate).toBe(0.5)
    })

    it('默认 replaysSessionSampleRate 应为 0.01，replaysOnErrorSampleRate 应为 1.0', () => {
      vi.stubEnv('VITE_SENTRY_DSN', 'https://test@sentry.io/1')

      initSentry(createMockApp(), createMockRouter())

      const initArgs = vi.mocked(Sentry.init).mock.calls[0][0] as any
      expect(initArgs.replaysSessionSampleRate).toBe(0.01)
      expect(initArgs.replaysOnErrorSampleRate).toBe(1.0)
    })

    it('自定义 VITE_SENTRY_REPLAYS_SAMPLE_RATE 应覆盖默认值', () => {
      vi.stubEnv('VITE_SENTRY_DSN', 'https://test@sentry.io/1')
      vi.stubEnv('VITE_SENTRY_REPLAYS_SAMPLE_RATE', '0.1')

      initSentry(createMockApp(), createMockRouter())

      const initArgs = vi.mocked(Sentry.init).mock.calls[0][0] as any
      expect(initArgs.replaysSessionSampleRate).toBe(0.1)
    })

    it('应正确配置 browserTracingIntegration 和 replayIntegration', () => {
      vi.stubEnv('VITE_SENTRY_DSN', 'https://test@sentry.io/1')
      const mockRouter = createMockRouter()

      initSentry(createMockApp(), mockRouter)

      expect(Sentry.browserTracingIntegration).toHaveBeenCalledTimes(1)
      expect(Sentry.browserTracingIntegration).toHaveBeenCalledWith({ router: mockRouter })
      expect(Sentry.replayIntegration).toHaveBeenCalledTimes(1)
      expect(Sentry.replayIntegration).toHaveBeenCalledWith({
        maskAllText: true,
        blockAllMedia: true,
        maskAllInputs: true,
      })
      const initArgs = vi.mocked(Sentry.init).mock.calls[0][0] as any
      expect(initArgs.integrations).toHaveLength(2)
    })

    it('应配置 ignoreErrors 过滤常见噪声错误', () => {
      vi.stubEnv('VITE_SENTRY_DSN', 'https://test@sentry.io/1')

      initSentry(createMockApp(), createMockRouter())

      const initArgs = vi.mocked(Sentry.init).mock.calls[0][0] as any
      expect(initArgs.ignoreErrors).toEqual(
        expect.arrayContaining([
          'ResizeObserver loop limit exceeded',
          'ResizeObserver loop completed with undelivered notifications',
          'Network Error',
          'Navigation cancelled',
          'Request aborted',
          'timeout of 0ms exceeded',
        ])
      )
    })

    it('应配置 denyUrls 过滤浏览器扩展 URL（4 个正则）', () => {
      vi.stubEnv('VITE_SENTRY_DSN', 'https://test@sentry.io/1')

      initSentry(createMockApp(), createMockRouter())

      const initArgs = vi.mocked(Sentry.init).mock.calls[0][0] as any
      expect(initArgs.denyUrls).toHaveLength(4)
      expect(initArgs.denyUrls[0]).toBeInstanceOf(RegExp)
    })

    it('VITE_APP_VERSION 配置时应传入 release', () => {
      vi.stubEnv('VITE_SENTRY_DSN', 'https://test@sentry.io/1')
      vi.stubEnv('VITE_APP_VERSION', '1.2.3')

      initSentry(createMockApp(), createMockRouter())

      const initArgs = vi.mocked(Sentry.init).mock.calls[0][0] as any
      expect(initArgs.release).toBe('1.2.3')
    })

    it('VITE_APP_VERSION 未配置时不应传入 release', () => {
      vi.stubEnv('VITE_SENTRY_DSN', 'https://test@sentry.io/1')
      // 不设置 VITE_APP_VERSION

      initSentry(createMockApp(), createMockRouter())

      const initArgs = vi.mocked(Sentry.init).mock.calls[0][0] as any
      expect(initArgs.release).toBeUndefined()
    })

    it('environment 应取自 import.meta.env.MODE', () => {
      vi.stubEnv('VITE_SENTRY_DSN', 'https://test@sentry.io/1')
      vi.stubEnv('MODE', 'staging')

      initSentry(createMockApp(), createMockRouter())

      const initArgs = vi.mocked(Sentry.init).mock.calls[0][0] as any
      expect(initArgs.environment).toBe('staging')
    })
  })

  describe('captureException', () => {
    it('应调用 Sentry.captureException 并附加 extra 上下文', () => {
      const error = new Error('test error')
      const context = { userId: 123, action: 'test' }

      captureException(error, context)

      expect(Sentry.captureException).toHaveBeenCalledTimes(1)
      expect(Sentry.captureException).toHaveBeenCalledWith(error, { extra: context })
    })

    it('不传 context 时 extra 应为 undefined', () => {
      const error = new Error('no context')

      captureException(error)

      expect(Sentry.captureException).toHaveBeenCalledWith(error, { extra: undefined })
    })
  })

  describe('captureMessage', () => {
    it('应调用 Sentry.captureMessage，默认 level 为 info', () => {
      captureMessage('test message')

      expect(Sentry.captureMessage).toHaveBeenCalledTimes(1)
      expect(Sentry.captureMessage).toHaveBeenCalledWith('test message', 'info')
    })

    it('应支持自定义 level=warning', () => {
      captureMessage('warning message', 'warning')

      expect(Sentry.captureMessage).toHaveBeenCalledWith('warning message', 'warning')
    })

    it('应支持自定义 level=error', () => {
      captureMessage('error message', 'error')

      expect(Sentry.captureMessage).toHaveBeenCalledWith('error message', 'error')
    })
  })
})
